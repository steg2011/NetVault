import logging
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db_session
from app.models import BackupSchedule, Site
from app.schemas import BackupScheduleCreate, BackupScheduleUpdate, BackupScheduleResponse
from app.core.scheduler import add_schedule_job, remove_schedule_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("", response_model=List[BackupScheduleResponse])
async def list_schedules(session: AsyncSession = Depends(get_db_session)):
    """Return all backup schedules."""
    result = await session.execute(select(BackupSchedule).order_by(BackupSchedule.id))
    return result.scalars().all()


@router.post("", response_model=BackupScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(data: BackupScheduleCreate, session: AsyncSession = Depends(get_db_session)):
    """Create a new recurring backup schedule."""
    if data.site_id:
        site = (await session.execute(select(Site).where(Site.id == data.site_id))).scalars().first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

    schedule = BackupSchedule(**data.model_dump())
    session.add(schedule)
    await session.commit()
    await session.refresh(schedule)

    if schedule.enabled:
        add_schedule_job(schedule)

    logger.info("Created schedule %d (%s, %s)", schedule.id, schedule.name, schedule.frequency)
    return schedule


@router.put("/{schedule_id}", response_model=BackupScheduleResponse)
async def update_schedule(
    schedule_id: int,
    data: BackupScheduleUpdate,
    session: AsyncSession = Depends(get_db_session),
):
    """Update an existing schedule."""
    result = await session.execute(select(BackupSchedule).where(BackupSchedule.id == schedule_id))
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if data.site_id is not None:
        site = (await session.execute(select(Site).where(Site.id == data.site_id))).scalars().first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(schedule, key, value)

    await session.commit()
    await session.refresh(schedule)

    # Re-register with updated trigger
    remove_schedule_job(schedule_id)
    if schedule.enabled:
        add_schedule_job(schedule)

    return schedule


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: int, session: AsyncSession = Depends(get_db_session)):
    """Delete a schedule."""
    result = await session.execute(select(BackupSchedule).where(BackupSchedule.id == schedule_id))
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    remove_schedule_job(schedule_id)
    await session.delete(schedule)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{schedule_id}/toggle", response_model=BackupScheduleResponse)
async def toggle_schedule(schedule_id: int, session: AsyncSession = Depends(get_db_session)):
    """Enable or disable a schedule."""
    result = await session.execute(select(BackupSchedule).where(BackupSchedule.id == schedule_id))
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = not schedule.enabled
    await session.commit()
    await session.refresh(schedule)

    if schedule.enabled:
        add_schedule_job(schedule)
    else:
        remove_schedule_job(schedule_id)

    return schedule
