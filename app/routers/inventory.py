import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List

from app.database import get_db_session
from app.models import Site, Device, CredentialSet
from app.schemas import (
    SiteCreate, SiteUpdate, SiteResponse,
    DeviceCreate, DeviceUpdate, DeviceResponse,
    CredentialSetCreate, CredentialSetUpdate, CredentialSetResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["inventory"])


# ==================== SITES ====================

@router.post("/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(site: SiteCreate, session: AsyncSession = Depends(get_db_session)):
    """Create a new site."""
    existing = await session.execute(select(Site).where(Site.code == site.code))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Site with this code already exists")

    db_site = Site(**site.model_dump())
    session.add(db_site)
    await session.commit()
    await session.refresh(db_site)
    logger.info(f"Created site: {db_site.code}")
    return db_site


@router.get("/sites", response_model=List[SiteResponse])
async def list_sites(session: AsyncSession = Depends(get_db_session)):
    """List all sites."""
    result = await session.execute(select(Site).order_by(Site.code))
    return result.scalars().all()


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(site_id: int, session: AsyncSession = Depends(get_db_session)):
    """Get a specific site."""
    result = await session.execute(select(Site).where(Site.id == site_id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.put("/sites/{site_id}", response_model=SiteResponse)
async def update_site(site_id: int, site_update: SiteUpdate, session: AsyncSession = Depends(get_db_session)):
    """Update a site."""
    result = await session.execute(select(Site).where(Site.id == site_id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data = site_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(site, key, value)

    await session.commit()
    await session.refresh(site)
    logger.info(f"Updated site: {site.code}")
    return site


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(site_id: int, session: AsyncSession = Depends(get_db_session)):
    """Delete a site."""
    result = await session.execute(select(Site).where(Site.id == site_id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await session.delete(site)
    await session.commit()
    logger.info(f"Deleted site: {site.code}")


# ==================== CREDENTIAL SETS ====================

@router.post("/credentials", response_model=CredentialSetResponse, status_code=status.HTTP_201_CREATED)
async def create_credential_set(cred: CredentialSetCreate, session: AsyncSession = Depends(get_db_session)):
    """Create a new credential set."""
    from cryptography.fernet import Fernet
    from app.config import get_settings

    settings = get_settings()
    cipher = Fernet(settings.fernet_key.encode())
    encrypted_pwd = cipher.encrypt(cred.password.encode()).decode()

    existing = await session.execute(select(CredentialSet).where(CredentialSet.label == cred.label))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Credential set with this label already exists")

    db_cred = CredentialSet(
        label=cred.label,
        username=cred.username,
        encrypted_password=encrypted_pwd
    )
    session.add(db_cred)
    await session.commit()
    await session.refresh(db_cred)
    logger.info(f"Created credential set: {db_cred.label}")
    return db_cred


@router.get("/credentials", response_model=List[CredentialSetResponse])
async def list_credentials(session: AsyncSession = Depends(get_db_session)):
    """List all credential sets."""
    result = await session.execute(select(CredentialSet).order_by(CredentialSet.label))
    return result.scalars().all()


@router.get("/credentials/{cred_id}", response_model=CredentialSetResponse)
async def get_credential_set(cred_id: int, session: AsyncSession = Depends(get_db_session)):
    """Get a specific credential set."""
    result = await session.execute(select(CredentialSet).where(CredentialSet.id == cred_id))
    cred = result.scalars().first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential set not found")
    return cred


@router.put("/credentials/{cred_id}", response_model=CredentialSetResponse)
async def update_credential_set(
    cred_id: int,
    cred_update: CredentialSetUpdate,
    session: AsyncSession = Depends(get_db_session)
):
    """Update a credential set."""
    from cryptography.fernet import Fernet
    from app.config import get_settings

    result = await session.execute(select(CredentialSet).where(CredentialSet.id == cred_id))
    cred = result.scalars().first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential set not found")

    if cred_update.username:
        cred.username = cred_update.username

    if cred_update.password:
        settings = get_settings()
        cipher = Fernet(settings.fernet_key.encode())
        encrypted_pwd = cipher.encrypt(cred_update.password.encode()).decode()
        cred.encrypted_password = encrypted_pwd

    await session.commit()
    await session.refresh(cred)
    logger.info(f"Updated credential set: {cred.label}")
    return cred


@router.delete("/credentials/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential_set(cred_id: int, session: AsyncSession = Depends(get_db_session)):
    """Delete a credential set."""
    result = await session.execute(select(CredentialSet).where(CredentialSet.id == cred_id))
    cred = result.scalars().first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential set not found")

    await session.delete(cred)
    await session.commit()
    logger.info(f"Deleted credential set: {cred.label}")


# ==================== DEVICES ====================

@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(device: DeviceCreate, session: AsyncSession = Depends(get_db_session)):
    """Create a new device."""
    site_result = await session.execute(select(Site).where(Site.id == device.site_id))
    if not site_result.scalars().first():
        raise HTTPException(status_code=404, detail="Site not found")

    if device.credential_id:
        cred_result = await session.execute(select(CredentialSet).where(CredentialSet.id == device.credential_id))
        if not cred_result.scalars().first():
            raise HTTPException(status_code=404, detail="Credential set not found")

    existing = await session.execute(
        select(Device).where(
            and_(Device.hostname == device.hostname, Device.site_id == device.site_id)
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Device with this hostname already exists in this site")

    db_device = Device(**device.model_dump())
    session.add(db_device)
    await session.commit()
    await session.refresh(db_device)
    logger.info(f"Created device: {db_device.hostname}")
    return db_device


@router.get("/devices", response_model=List[DeviceResponse])
async def list_devices(site_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    """List all devices, optionally filtered by site."""
    query = select(Device)
    if site_id:
        query = query.where(Device.site_id == site_id)
    result = await session.execute(query.order_by(Device.hostname))
    return result.scalars().all()


@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, session: AsyncSession = Depends(get_db_session)):
    """Get a specific device."""
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.put("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(device_id: int, device_update: DeviceUpdate, session: AsyncSession = Depends(get_db_session)):
    """Update a device."""
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if device_update.site_id:
        site_result = await session.execute(select(Site).where(Site.id == device_update.site_id))
        if not site_result.scalars().first():
            raise HTTPException(status_code=404, detail="Site not found")

    if device_update.credential_id:
        cred_result = await session.execute(select(CredentialSet).where(CredentialSet.id == device_update.credential_id))
        if not cred_result.scalars().first():
            raise HTTPException(status_code=404, detail="Credential set not found")

    update_data = device_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(device, key, value)

    await session.commit()
    await session.refresh(device)
    logger.info(f"Updated device: {device.hostname}")
    return device


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, session: AsyncSession = Depends(get_db_session)):
    """Delete a device."""
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await session.delete(device)
    await session.commit()
    logger.info(f"Deleted device: {device.hostname}")
