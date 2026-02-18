"""
Custom Nornir inventory builder backed by PostgreSQL.

Because Nornir uses a thread pool (not asyncio), we cannot make async DB
calls from inside a Nornir task.  The solution: load all device data
asynchronously *before* creating the Nornir object, convert each row to a
plain Python dataclass (no SQLAlchemy ORM references), then build the
Nornir Inventory from those plain objects in sync code.
"""
import dataclasses
import logging
from typing import Dict, List, Optional

from cryptography.fernet import Fernet
from nornir.core.inventory import Defaults, Groups, Host, Hosts, Inventory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models import Device, PlatformEnum

logger = logging.getLogger(__name__)

# Mapping from our platform enum → Netmiko device_type string
PLATFORM_TO_NETMIKO: Dict[str, str] = {
    PlatformEnum.IOS.value: "cisco_ios",
    PlatformEnum.NXOS.value: "cisco_nxos",
    PlatformEnum.EOS.value: "arista_eos",
    PlatformEnum.DELLOS10.value: "dell_os10",
    PlatformEnum.PANOS.value: "paloaltonetworks_panos",
    PlatformEnum.FORTIOS.value: "fortinet_fortios",
}

# Platforms handled via REST/XML API (not CLI/Netmiko)
API_PLATFORMS = {PlatformEnum.PANOS.value, PlatformEnum.FORTIOS.value}


@dataclasses.dataclass
class DeviceData:
    """Plain-Python snapshot of a Device row — safe to pass to threads."""

    device_id: int
    hostname: str
    ip: str
    platform: str          # enum value, e.g. "ios"
    netmiko_platform: str  # Netmiko device_type, e.g. "cisco_ios"
    username: Optional[str]
    password: Optional[str]
    port: int
    site_code: str
    gitea_repo_name: str
    is_api_device: bool


async def load_device_data(
    session: AsyncSession,
    settings: Settings,
    device_ids: Optional[List[int]] = None,
) -> List[DeviceData]:
    """
    Asynchronously load devices (with site + credentials eagerly loaded),
    decrypt passwords, and return a list of plain DeviceData instances.

    Credential resolution order:
      1. Device-level CredentialSet (decrypted with Fernet)
      2. Global NET_USER_GLOBAL / NET_PASS_GLOBAL env vars
      3. None (caller must handle the missing-credential case)
    """
    query = (
        select(Device)
        .options(selectinload(Device.site), selectinload(Device.credential_set))
        .where(Device.enabled == True)
    )
    if device_ids:
        query = query.where(Device.id.in_(device_ids))

    result = await session.execute(query)
    rows = result.unique().scalars().all()

    cipher = Fernet(settings.fernet_key.encode())
    devices: List[DeviceData] = []

    for row in rows:
        username: Optional[str] = None
        password: Optional[str] = None

        if row.credential_set:
            username = row.credential_set.username
            password = cipher.decrypt(
                row.credential_set.encrypted_password.encode()
            ).decode()
        elif settings.net_user_global and settings.net_pass_global:
            username = settings.net_user_global
            password = settings.net_pass_global
        # else: both remain None → caller marks device as failed

        platform_val = row.platform.value
        netmiko_platform = PLATFORM_TO_NETMIKO.get(platform_val, platform_val)

        devices.append(
            DeviceData(
                device_id=row.id,
                hostname=row.hostname,
                ip=row.ip,
                platform=platform_val,
                netmiko_platform=netmiko_platform,
                username=username,
                password=password,
                port=22,
                site_code=row.site.code,
                gitea_repo_name=row.site.gitea_repo_name,
                is_api_device=platform_val in API_PLATFORMS,
            )
        )

    return devices


def build_nornir_inventory(devices: List[DeviceData]) -> Inventory:
    """
    Build a Nornir Inventory from pre-loaded DeviceData objects.

    Only CLI-capable devices (not panos/fortios) should be passed here.
    """
    hosts = Hosts()

    for dev in devices:
        hosts[dev.hostname] = Host(
            name=dev.hostname,
            hostname=dev.ip,
            port=dev.port,
            username=dev.username,
            password=dev.password,
            platform=dev.netmiko_platform,
            data={
                "device_id": dev.device_id,
                "platform": dev.platform,
                "site_code": dev.site_code,
                "gitea_repo_name": dev.gitea_repo_name,
            },
        )
        logger.debug("Added host %s (%s) to Nornir inventory", dev.hostname, dev.netmiko_platform)

    return Inventory(hosts=hosts, groups=Groups(), defaults=Defaults())
