"""
Backup engine: orchestrates a BackupJob across CLI and API devices.

Architecture
────────────
• CLI devices (IOS/NX-OS/EOS/OS10): run via Nornir + ThreadedRunner (50 workers).
  A Nornir Processor bridges the thread pool back to the asyncio event loop so
  each device completion triggers an immediate DB update + WebSocket publish.

• API devices (PAN-OS, FortiOS): run concurrently via asyncio.gather with a
  configurable semaphore (default 30 concurrent).

• progress_queues: module-level dict keyed by job_id.  The WebSocket endpoint
  (dashboard.py) imports this dict directly — never rebind it.
"""
import asyncio
import dataclasses
import hashlib
import logging
import queue as sync_queue
from datetime import datetime, timezone
from typing import Dict, List, Optional

from nornir.core import Nornir
from nornir.core.configuration import Config
from nornir.core.inventory import Host
from nornir.core.task import AggregatedResult, MultiResult, Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.api_tasks import backup_fortinet, backup_palo_alto
from app.core.cli_tasks import backup_config_cli
from app.core.gitea_client import GiteaClient
from app.core.nornir_inventory import DeviceData, build_nornir_inventory, load_device_data
from app.core.scrubber import scrub_config
from app.models import BackupJob, BackupJobStatus, BackupResult, BackupResultStatus

logger = logging.getLogger(__name__)

# Shared progress queues: job_id → asyncio.Queue of progress dicts.
# The WebSocket router imports this dict reference — it must never be rebound.
progress_queues: Dict[int, asyncio.Queue] = {}


class _DeviceCompletionProcessor:
    """
    Nornir Processor that forwards per-host completion events from the
    Nornir thread pool back into the asyncio event loop via
    loop.call_soon_threadsafe.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self._loop = loop
        self._queue = queue

    # ── Processor protocol methods ─────────────────────────────────────────────

    def task_started(self, task: Task) -> None:
        pass

    def task_completed(self, task: Task, result: AggregatedResult) -> None:
        pass

    def task_instance_started(self, task: Task, host: Host) -> None:
        pass

    def task_instance_completed(self, task: Task, host: Host, result: MultiResult) -> None:
        self._loop.call_soon_threadsafe(
            self._queue.put_nowait,
            {"hostname": host.name, "multi_result": result},
        )

    def subtask_instance_started(self, task: Task, host: Host) -> None:
        pass

    def subtask_instance_completed(self, task: Task, host: Host, result: MultiResult) -> None:
        pass


class BackupEngine:
    """Orchestrates a BackupJob from job creation to final status update."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Optional[Settings] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.gitea = GiteaClient(
            self.settings.gitea_url,
            self.settings.gitea_token,
            self.settings.gitea_org,
        )

    # ── Public entry point ─────────────────────────────────────────────────────

    async def run_backup(self, job_id: int, device_ids: List[int]) -> None:
        """
        Run a full backup job.

        1. Load devices with eager-loaded relationships.
        2. Resolve credentials; immediately fail devices with no creds.
        3. Split into CLI vs. API groups.
        4. Run CLI group via Nornir (threaded) + streaming processor.
        5. Run API group via asyncio.gather + semaphore.
        6. Finalise job status.
        """
        job = await self._fetch_job(job_id)
        if job is None:
            logger.error("BackupJob %d not found — aborting", job_id)
            return

        job.started_at = datetime.now(timezone.utc)
        job.status = BackupJobStatus.RUNNING
        await self.session.commit()

        # Ensure a progress queue exists for WebSocket consumers.
        if job_id not in progress_queues:
            progress_queues[job_id] = asyncio.Queue()
        pq: asyncio.Queue = progress_queues[job_id]

        try:
            all_devices = await load_device_data(
                session=self.session,
                settings=self.settings,
                device_ids=device_ids,
            )

            cli_devices: List[DeviceData] = []
            api_devices: List[DeviceData] = []

            for dev in all_devices:
                if dev.username is None or dev.password is None:
                    # Tier-3 credential failure: record immediately, don't attempt connection.
                    await self._record_failure(
                        job=job,
                        device_id=dev.device_id,
                        error_message="No credentials available (device-level, global env vars both missing)",
                        pq=pq,
                    )
                elif dev.is_api_device:
                    api_devices.append(dev)
                else:
                    cli_devices.append(dev)

            if cli_devices:
                await self._run_cli_backups(job, cli_devices, pq)

            if api_devices:
                await self._run_api_backups(job, api_devices, pq)

            job.status = BackupJobStatus.COMPLETE

        except Exception as exc:
            logger.exception("BackupJob %d encountered a fatal error: %s", job_id, exc)
            job.status = BackupJobStatus.FAILED
        finally:
            job.completed_at = datetime.now(timezone.utc)
            await self.session.commit()
            await pq.put({
                "completed": job.completed_devices,
                "total": job.total_devices,
                "failed": job.failed_devices,
                "status": job.status.value,
                "job_id": job_id,
            })

    # ── CLI path (Nornir / Netmiko) ────────────────────────────────────────────

    async def _run_cli_backups(
        self,
        job: BackupJob,
        cli_devices: List[DeviceData],
        pq: asyncio.Queue,
    ) -> None:
        """Run CLI backups via Nornir ThreadedRunner with a per-device processor."""
        loop = asyncio.get_event_loop()
        completion_queue: asyncio.Queue = asyncio.Queue()
        processor = _DeviceCompletionProcessor(loop=loop, queue=completion_queue)

        inventory = build_nornir_inventory(cli_devices)
        config = Config(
            runner={
                "plugin": "threaded",
                "options": {"num_workers": self.settings.nornir_num_workers},
            }
        )
        nr = Nornir(inventory=inventory, config=config)
        nr = nr.with_processors([processor])

        expected = len(cli_devices)
        processed = 0

        async def _nornir_in_thread() -> None:
            try:
                await asyncio.to_thread(lambda: nr.run(task=backup_config_cli))
            finally:
                # Push sentinel so the drain loop exits even if count mismatches.
                completion_queue.put_nowait(None)

        async def _drain_completions() -> None:
            nonlocal processed
            while processed < expected:
                item = await completion_queue.get()
                if item is None:
                    break
                hostname: str = item["hostname"]
                multi_result: MultiResult = item["multi_result"]

                if multi_result.failed:
                    failed_results = [r for r in multi_result if r.failed]
                    exc = failed_results[0].exception if failed_results else None
                    error_msg = str(exc) if exc else "Unknown Nornir task failure"
                    dev_id = next(
                        (d.device_id for d in cli_devices if d.hostname == hostname), None
                    )
                    if dev_id is not None:
                        await self._record_failure(job, dev_id, error_msg, pq)
                else:
                    data: dict = multi_result[0].result
                    await self._commit_config(job=job, dev_data_map=cli_devices, data=data, pq=pq)

                processed += 1

        await asyncio.gather(_nornir_in_thread(), _drain_completions())

    # ── API path (PAN-OS / FortiOS) ────────────────────────────────────────────

    async def _run_api_backups(
        self,
        job: BackupJob,
        api_devices: List[DeviceData],
        pq: asyncio.Queue,
    ) -> None:
        """Run API-based backups concurrently with a semaphore."""
        sem = asyncio.Semaphore(self.settings.api_semaphore_limit)

        async def _backup_one(dev: DeviceData) -> None:
            async with sem:
                await self._backup_api_device(job, dev, pq)

        await asyncio.gather(*[_backup_one(d) for d in api_devices], return_exceptions=True)

    async def _backup_api_device(
        self, job: BackupJob, dev: DeviceData, pq: asyncio.Queue
    ) -> None:
        try:
            if dev.platform == "panos":
                result = await backup_palo_alto(
                    hostname=dev.hostname,
                    ip=dev.ip,
                    username=dev.username,
                    password=dev.password,
                    device_id=dev.device_id,
                )
            elif dev.platform == "fortios":
                result = await backup_fortinet(
                    hostname=dev.hostname,
                    ip=dev.ip,
                    username=dev.username,
                    password=dev.password,
                    device_id=dev.device_id,
                )
            else:
                raise ValueError(f"Unknown API platform: {dev.platform!r}")

            await self._commit_config(
                job=job,
                dev_data_map=[dev],
                data=result,
                pq=pq,
            )
        except Exception as exc:
            logger.error("API backup failed for %s: %s", dev.hostname, exc)
            await self._record_failure(job, dev.device_id, str(exc), pq)

    # ── Gitea commit ───────────────────────────────────────────────────────────

    async def _commit_config(
        self,
        job: BackupJob,
        dev_data_map: List[DeviceData],
        data: dict,
        pq: asyncio.Queue,
    ) -> None:
        """Scrub → hash → Gitea commit → record BackupResult → notify."""
        hostname: str = data.get("hostname", "unknown")
        device_id: int = data.get("device_id", 0)
        platform: str = data.get("platform", "")
        raw_config: str = data.get("config", "")

        # Look up site info from the pre-loaded device list.
        dev = next((d for d in dev_data_map if d.device_id == device_id), None)
        if dev is None:
            logger.error("Could not find DeviceData for device_id=%d hostname=%s", device_id, hostname)
            await self._record_failure(job, device_id, "Internal: DeviceData not found", pq)
            return

        try:
            scrubbed = scrub_config(raw_config, platform)
            config_hash = hashlib.sha256(scrubbed.encode()).hexdigest()

            repo_full = f"{self.settings.gitea_org}/{dev.gitea_repo_name}"
            await self.gitea.ensure_repo(site_code=dev.site_code, repo_name=dev.gitea_repo_name)
            commit_sha = await self.gitea.commit_config(
                repo=repo_full,
                device_hostname=hostname,
                config_text=scrubbed,
                commit_message=f"Automated backup: {hostname}",
            )

            br = BackupResult(
                job_id=job.id,
                device_id=device_id,
                status=BackupResultStatus.SUCCESS,
                config_hash=config_hash,
                gitea_commit_sha=commit_sha,
            )
            self.session.add(br)
            job.completed_devices += 1
            await self.session.commit()

            logger.info("Committed backup for %s  sha=%s…", hostname, (commit_sha or "")[:12])

        except Exception as exc:
            logger.error("Failed to commit config for %s: %s", hostname, exc)
            await self._record_failure(job, device_id, str(exc), pq)
            return

        await pq.put({
            "completed": job.completed_devices,
            "total": job.total_devices,
            "failed": job.failed_devices,
            "status": "running",
            "job_id": job.id,
        })

    # ── Failure recording ──────────────────────────────────────────────────────

    async def _record_failure(
        self,
        job: BackupJob,
        device_id: int,
        error_message: str,
        pq: asyncio.Queue,
    ) -> None:
        try:
            br = BackupResult(
                job_id=job.id,
                device_id=device_id,
                status=BackupResultStatus.FAILED,
                error_message=error_message,
            )
            self.session.add(br)
            job.completed_devices += 1
            job.failed_devices += 1
            await self.session.commit()
        except Exception as exc:
            logger.error("_record_failure DB error: %s", exc)

        await pq.put({
            "completed": job.completed_devices,
            "total": job.total_devices,
            "failed": job.failed_devices,
            "status": "running",
            "job_id": job.id,
        })

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _fetch_job(self, job_id: int) -> Optional[BackupJob]:
        result = await self.session.execute(
            select(BackupJob).where(BackupJob.id == job_id)
        )
        return result.scalars().first()
