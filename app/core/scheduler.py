"""
APScheduler integration for recurring backup schedules.

On startup, all enabled BackupSchedule rows are loaded and registered as
CronTrigger jobs.  CRUD operations on schedules keep the live scheduler
in sync via add_schedule_job / remove_schedule_job.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone="UTC")


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


# ── Trigger helpers ────────────────────────────────────────────────────────────

def _make_trigger(frequency: str, hour: int, day_of_week: int) -> CronTrigger:
    if frequency == "hourly":
        return CronTrigger(minute=0, timezone="UTC")
    if frequency == "daily":
        return CronTrigger(hour=hour, minute=0, timezone="UTC")
    if frequency == "weekly":
        return CronTrigger(day_of_week=day_of_week, hour=hour, minute=0, timezone="UTC")
    raise ValueError(f"Unknown frequency: {frequency}")


def _apscheduler_job_id(schedule_id: int) -> str:
    return f"backup_schedule_{schedule_id}"


# ── Scheduled job function ─────────────────────────────────────────────────────

async def _fire_scheduled_backup(schedule_id: int) -> None:
    """Create and run a BackupJob for the given schedule."""
    from datetime import datetime
    from sqlalchemy import select, update as sa_update
    from app.database import get_session_factory
    from app.models import BackupSchedule, BackupJob, Device

    factory = get_session_factory()

    async with factory() as session:
        sched_result = await session.execute(
            select(BackupSchedule).where(BackupSchedule.id == schedule_id)
        )
        schedule = sched_result.scalars().first()
        if not schedule or not schedule.enabled:
            logger.info("Schedule %d skipped (disabled or not found)", schedule_id)
            return

        query = select(Device).where(Device.enabled == True)
        if schedule.site_id:
            query = query.where(Device.site_id == schedule.site_id)

        devices = (await session.execute(query)).scalars().all()
        if not devices:
            logger.warning("Schedule %d: no enabled devices — skipping", schedule_id)
            return

        db_job = BackupJob(
            triggered_by=f"schedule:{schedule.name}",
            total_devices=len(devices),
        )
        session.add(db_job)
        await session.execute(
            sa_update(BackupSchedule)
            .where(BackupSchedule.id == schedule_id)
            .values(last_run_at=datetime.utcnow())
        )
        await session.commit()

        job_id = db_job.id
        device_ids = [d.id for d in devices]

    logger.info(
        "Schedule %d triggered backup job %d for %d device(s)",
        schedule_id, job_id, len(device_ids),
    )

    # Re-use the same background runner used by the API
    from app.routers.backups import _run_backup_engine
    await _run_backup_engine(job_id=job_id, device_ids=device_ids)


# ── Scheduler management ───────────────────────────────────────────────────────

def add_schedule_job(schedule) -> None:
    """Register (or replace) a schedule in the live APScheduler."""
    trigger = _make_trigger(
        schedule.frequency.value, schedule.hour, schedule.day_of_week
    )
    job_id = _apscheduler_job_id(schedule.id)
    _scheduler.add_job(
        _fire_scheduled_backup,
        trigger=trigger,
        id=job_id,
        args=[schedule.id],
        replace_existing=True,
    )
    logger.info("Registered APScheduler job %s (%s)", job_id, schedule.frequency.value)


def remove_schedule_job(schedule_id: int) -> None:
    """Remove a schedule from the live APScheduler (no-op if absent)."""
    job_id = _apscheduler_job_id(schedule_id)
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
        logger.info("Removed APScheduler job %s", job_id)


async def load_and_start() -> None:
    """Load enabled schedules from DB and start the scheduler. Call from lifespan."""
    from sqlalchemy import select
    from app.database import get_session_factory
    from app.models import BackupSchedule

    factory = get_session_factory()
    async with factory() as session:
        schedules = (
            await session.execute(
                select(BackupSchedule).where(BackupSchedule.enabled == True)
            )
        ).scalars().all()

    for schedule in schedules:
        add_schedule_job(schedule)

    _scheduler.start()
    logger.info("APScheduler started with %d active schedule(s)", len(schedules))


def stop() -> None:
    """Gracefully stop APScheduler. Call from lifespan shutdown."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
