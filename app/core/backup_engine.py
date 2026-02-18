import logging
import asyncio
import hashlib
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from nornir import InitNornir
from nornir.core.exceptions import NornirExecutionError

from app.models import Device, BackupJob, BackupResult, BackupResultStatus, BackupJobStatus, CredentialSet
from app.config import Settings, get_settings
from app.core.nornir_inventory import PostgreSQLInventoryPlugin
from app.core.scrubber import scrub_config
from app.core.gitea_client import GiteaClient
from app.core.cli_tasks import backup_config_cli
from app.core.api_tasks import backup_palo_alto, backup_fortinet

logger = logging.getLogger(__name__)

# Global progress queues for WebSocket updates
progress_queues: Dict[int, asyncio.Queue] = {}


async def get_progress_queue(job_id: int) -> asyncio.Queue:
    """Get or create progress queue for a job."""
    if job_id not in progress_queues:
        progress_queues[job_id] = asyncio.Queue()
    return progress_queues[job_id]


class BackupEngine:
    """Orchestrates backup jobs across multiple devices."""

    def __init__(self, session: AsyncSession, settings: Optional[Settings] = None):
        self.session = session
        self.settings = settings or get_settings()
        self.gitea = GiteaClient(
            self.settings.gitea_url,
            self.settings.gitea_token,
            self.settings.gitea_org
        )

    async def run_backup(self, job_id: int, device_ids: List[int]) -> None:
        """
        Run backup for specified devices.

        Args:
            job_id: Backup job ID
            device_ids: List of device IDs to backup
        """
        job_result = await self.session.execute(select(BackupJob).where(BackupJob.id == job_id))
        job = job_result.scalars().first()
        if not job:
            logger.error(f"Backup job {job_id} not found")
            return

        job.started_at = datetime.utcnow()
        job.status = BackupJobStatus.RUNNING
        await self.session.commit()

        queue = await get_progress_queue(job_id)

        try:
            # Separate CLI and API devices
            cli_devices = []
            api_devices = []

            for device_id in device_ids:
                device_result = await self.session.execute(
                    select(Device).where(Device.id == device_id)
                )
                device = device_result.scalars().first()

                if not device:
                    logger.warning(f"Device {device_id} not found")
                    continue

                if device.platform.value in ["panos", "fortios"]:
                    api_devices.append(device)
                else:
                    cli_devices.append(device)

            # Run CLI backups via Nornir
            if cli_devices:
                await self._run_cli_backups(job, cli_devices, queue)

            # Run API backups
            if api_devices:
                await self._run_api_backups(job, api_devices, queue)

            # Update job status
            job.status = BackupJobStatus.COMPLETE
            job.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Backup job {job_id} failed: {str(e)}")
            job.status = BackupJobStatus.FAILED
            job.completed_at = datetime.utcnow()

        finally:
            await self.session.commit()
            await queue.put({
                "completed": job.completed_devices,
                "total": job.total_devices,
                "failed": job.failed_devices,
                "status": job.status.value,
                "job_id": job_id
            })

    async def _run_cli_backups(self, job: BackupJob, devices: List[Device], queue: asyncio.Queue) -> None:
        """Run backups for CLI-based devices using Nornir."""
        try:
            inventory_plugin = PostgreSQLInventoryPlugin()
            inventory = await inventory_plugin.load_async(
                session=self.session,
                settings=self.settings,
                devices=[d.id for d in devices]
            )

            nr = InitNornir(inventory=inventory)

            # Run backup task with specified number of workers
            results = nr.run(
                task=backup_config_cli,
                num_workers=self.settings.nornir_num_workers
            )

            # Process results
            for hostname, device_result in results.items():
                device_id = None
                config_text = None
                error = None

                for task_name, task_result in device_result.items():
                    if task_result.failed:
                        error = task_result.result.get("error", "Unknown error")
                        device_id = task_result.result.get("device_id")
                    else:
                        config_text = task_result.result.get("config")
                        config_hash = task_result.result.get("hash")
                        device_id = task_result.result.get("device_id")
                        platform = task_result.result.get("platform")

                        if config_text and device_id:
                            await self._commit_config(
                                job=job,
                                device_id=device_id,
                                hostname=hostname,
                                config_text=config_text,
                                platform=platform,
                                queue=queue
                            )

                if error and device_id:
                    await self._record_failure(
                        job=job,
                        device_id=device_id,
                        error_message=error,
                        queue=queue
                    )

        except NornirExecutionError as e:
            logger.error(f"Nornir execution error: {str(e)}")
            for device in devices:
                await self._record_failure(
                    job=job,
                    device_id=device.id,
                    error_message=f"Nornir execution error: {str(e)}",
                    queue=queue
                )
        except Exception as e:
            logger.error(f"CLI backup error: {str(e)}")
            for device in devices:
                await self._record_failure(
                    job=job,
                    device_id=device.id,
                    error_message=str(e),
                    queue=queue
                )

    async def _run_api_backups(self, job: BackupJob, devices: List[Device], queue: asyncio.Queue) -> None:
        """Run backups for API-based devices with semaphore limiting."""
        semaphore = asyncio.Semaphore(self.settings.api_semaphore_limit)

        async def backup_with_semaphore(device: Device):
            async with semaphore:
                return await self._backup_api_device(device, job, queue)

        tasks = [backup_with_semaphore(device) for device in devices]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _backup_api_device(self, device: Device, job: BackupJob, queue: asyncio.Queue) -> None:
        """Backup a single API-based device."""
        try:
            # Resolve credentials
            username, password = await self._resolve_credentials(device)

            if not username or not password:
                await self._record_failure(
                    job=job,
                    device_id=device.id,
                    error_message="No credentials available",
                    queue=queue
                )
                return

            # Execute platform-specific backup
            if device.platform.value == "panos":
                result = await backup_palo_alto(
                    hostname=device.hostname,
                    ip=device.ip,
                    username=username,
                    password=password,
                    device_id=device.id
                )
            elif device.platform.value == "fortios":
                result = await backup_fortinet(
                    hostname=device.hostname,
                    ip=device.ip,
                    username=username,
                    password=password,
                    device_id=device.id
                )
            else:
                await self._record_failure(
                    job=job,
                    device_id=device.id,
                    error_message=f"Unsupported API platform: {device.platform.value}",
                    queue=queue
                )
                return

            config_text = result["config"]
            platform = result["platform"]

            await self._commit_config(
                job=job,
                device_id=device.id,
                hostname=device.hostname,
                config_text=config_text,
                platform=platform,
                queue=queue
            )

        except Exception as e:
            logger.error(f"API backup failed for {device.hostname}: {str(e)}")
            await self._record_failure(
                job=job,
                device_id=device.id,
                error_message=str(e),
                queue=queue
            )

    async def _resolve_credentials(self, device: Device) -> tuple[str, str]:
        """
        Resolve credentials for a device with priority fallback.

        Returns:
            (username, password) tuple
        """
        # Priority 1: Device credential set
        if device.credential_id:
            cred_result = await self.session.execute(
                select(CredentialSet).where(CredentialSet.id == device.credential_id)
            )
            cred_set = cred_result.scalars().first()

            if cred_set:
                from cryptography.fernet import Fernet
                cipher = Fernet(self.settings.fernet_key.encode())
                password = cipher.decrypt(cred_set.encrypted_password.encode()).decode()
                return cred_set.username, password

        # Priority 2: Global environment variables
        if self.settings.net_user_global and self.settings.net_pass_global:
            return self.settings.net_user_global, self.settings.net_pass_global

        # Priority 3: Fail with no credentials
        return None, None

    async def _commit_config(
        self,
        job: BackupJob,
        device_id: int,
        hostname: str,
        config_text: str,
        platform: str,
        queue: asyncio.Queue
    ) -> None:
        """Commit configuration to Gitea and record success."""
        try:
            # Scrub configuration
            scrubbed_config = scrub_config(config_text, platform)
            config_hash = hashlib.sha256(scrubbed_config.encode()).hexdigest()

            # Get device and site
            device_result = await self.session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = device_result.scalars().first()

            if not device:
                logger.error(f"Device {device_id} not found for commit")
                return

            # Ensure Gitea repo
            repo = await self.gitea.ensure_repo(
                site_code=device.site.code,
                repo_name=device.site.gitea_repo_name
            )

            # Commit to Gitea
            commit_sha = await self.gitea.commit_config(
                repo=repo,
                device_hostname=hostname,
                config_text=scrubbed_config,
                commit_message=f"Automated backup: {hostname}"
            )

            # Record success
            backup_result = BackupResult(
                job_id=job.id,
                device_id=device_id,
                status=BackupResultStatus.SUCCESS,
                config_hash=config_hash,
                gitea_commit_sha=commit_sha,
                duration_seconds=None
            )

            self.session.add(backup_result)
            job.completed_devices += 1
            await self.session.commit()

            logger.info(f"Completed backup for {hostname}")

            # Notify progress
            await queue.put({
                "completed": job.completed_devices,
                "total": job.total_devices,
                "failed": job.failed_devices,
                "status": "running",
                "job_id": job.id
            })

        except Exception as e:
            logger.error(f"Failed to commit config for {hostname}: {str(e)}")
            await self._record_failure(job, device_id, str(e), queue)

    async def _record_failure(
        self,
        job: BackupJob,
        device_id: int,
        error_message: str,
        queue: asyncio.Queue
    ) -> None:
        """Record a backup failure."""
        try:
            backup_result = BackupResult(
                job_id=job.id,
                device_id=device_id,
                status=BackupResultStatus.FAILED,
                error_message=error_message
            )

            self.session.add(backup_result)
            job.completed_devices += 1
            job.failed_devices += 1
            await self.session.commit()

            await queue.put({
                "completed": job.completed_devices,
                "total": job.total_devices,
                "failed": job.failed_devices,
                "status": "running",
                "job_id": job.id
            })

        except Exception as e:
            logger.error(f"Failed to record backup failure: {str(e)}")
