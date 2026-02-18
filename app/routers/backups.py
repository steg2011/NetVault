import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from app.database import get_db_session
from app.models import BackupJob, BackupResult, Device
from app.schemas import BackupJobCreate, BackupJobResponse, BackupResultResponse, DeviceHistoryResponse, DiffResponse
from app.core.backup_engine import BackupEngine
from app.core.gitea_client import GiteaClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.post("/jobs", response_model=BackupJobResponse, status_code=status.HTTP_201_CREATED)
async def create_backup_job(
    job_create: BackupJobCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session)
):
    """Trigger a new backup job."""
    from app.config import get_settings

    settings = get_settings()

    query = select(Device).where(Device.enabled == True)
    if job_create.site_id:
        query = query.where(Device.site_id == job_create.site_id)

    result = await session.execute(query)
    devices = result.scalars().all()

    if not devices:
        raise HTTPException(status_code=400, detail="No devices to backup")

    db_job = BackupJob(
        triggered_by=job_create.triggered_by,
        total_devices=len(devices)
    )
    session.add(db_job)
    await session.commit()
    await session.refresh(db_job)

    logger.info(f"Created backup job {db_job.id} for {len(devices)} devices")

    background_tasks.add_task(
        run_backup_engine,
        job_id=db_job.id,
        device_ids=[d.id for d in devices]
    )

    return db_job


async def run_backup_engine(job_id: int, device_ids: List[int]):
    """Run the backup engine in the background."""
    from app.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        engine = BackupEngine(session=session)
        await engine.run_backup(job_id=job_id, device_ids=device_ids)


@router.get("/jobs", response_model=List[BackupJobResponse])
async def list_backup_jobs(session: AsyncSession = Depends(get_db_session)):
    """List all backup jobs."""
    result = await session.execute(
        select(BackupJob).order_by(desc(BackupJob.triggered_at)).limit(100)
    )
    jobs = result.scalars().all()
    return jobs


@router.get("/jobs/{job_id}", response_model=BackupJobResponse)
async def get_backup_job(job_id: int, session: AsyncSession = Depends(get_db_session)):
    """Get a specific backup job."""
    result = await session.execute(select(BackupJob).where(BackupJob.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Backup job not found")
    return job


@router.get("/device/{device_id}/history", response_model=DeviceHistoryResponse)
async def get_device_backup_history(device_id: int, session: AsyncSession = Depends(get_db_session)):
    """Get backup history for a device (last 5 results)."""
    device_result = await session.execute(select(Device).where(Device.id == device_id))
    device = device_result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    results_query = await session.execute(
        select(BackupResult).where(BackupResult.device_id == device_id)
        .order_by(desc(BackupResult.backed_up_at))
        .limit(5)
    )
    results = results_query.scalars().all()

    return DeviceHistoryResponse(
        device_id=device.id,
        hostname=device.hostname,
        results=results
    )


@router.get("/diff/{device_id}", response_model=DiffResponse)
async def get_device_diff(device_id: int, session: AsyncSession = Depends(get_db_session)):
    """Get unified diff for latest backup of a device."""
    device_result = await session.execute(select(Device).where(Device.id == device_id))
    device = device_result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    site_result = await session.execute(select(Device.site).where(Device.id == device_id))

    from app.config import get_settings
    settings = get_settings()
    gitea = GiteaClient(settings.gitea_url, settings.gitea_token)

    try:
        unified_diff = await gitea.get_diff(
            repo=device.site.gitea_repo_name,
            device_hostname=device.hostname
        )
    except Exception as e:
        logger.error(f"Failed to get diff for device {device.hostname}: {str(e)}")
        unified_diff = f"Error retrieving diff: {str(e)}"

    return DiffResponse(
        device_id=device.id,
        hostname=device.hostname,
        unified_diff=unified_diff
    )
