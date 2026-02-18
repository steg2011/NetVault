import logging
from typing import Dict, Any, Optional
from nornir.core.inventory import Inventory, Host, Group, Groups, Hosts, HostOrGroup
from nornir.plugins.inventory.plugin import InventoryPlugin
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Device, Site, CredentialSet, PlatformEnum
from app.config import Settings

logger = logging.getLogger(__name__)


class PostgreSQLInventoryPlugin(InventoryPlugin):
    """Nornir inventory plugin backed by PostgreSQL."""

    def __init__(self, **kwargs):
        """Initialize the plugin."""
        super().__init__(**kwargs)
        self.session: Optional[AsyncSession] = None
        self.settings: Optional[Settings] = None
        self.netmiko_platform_map = {
            PlatformEnum.IOS.value: "cisco_ios",
            PlatformEnum.NXOS.value: "cisco_nxos",
            PlatformEnum.EOS.value: "arista_eos",
            PlatformEnum.DELLOS10.value: "dell_os10",
            PlatformEnum.PANOS.value: "paloaltonetworks_panos",
            PlatformEnum.FORTIOS.value: "fortinet_fortios",
        }

    async def load_async(
        self,
        session: AsyncSession,
        settings: Settings,
        devices: list = None
    ) -> Inventory:
        """
        Load inventory from PostgreSQL asynchronously.

        Args:
            session: SQLAlchemy async session
            settings: Application settings
            devices: Optional list of device IDs to load (load all if None)

        Returns:
            Nornir Inventory
        """
        self.session = session
        self.settings = settings

        # Query devices with joined relationships
        query = select(Device).join(Site).outerjoin(CredentialSet)

        if devices:
            query = query.where(Device.id.in_(devices))

        result = await session.execute(query)
        db_devices = result.unique().scalars().all()

        hosts = Hosts()
        groups = Groups()

        for device in db_devices:
            # Get credentials from device, then fallback to global env vars
            username = None
            password = None

            if device.credential_set:
                username = device.credential_set.username
                # Decrypt password
                from cryptography.fernet import Fernet
                cipher = Fernet(settings.fernet_key.encode())
                password = cipher.decrypt(device.credential_set.encrypted_password.encode()).decode()
            else:
                username = settings.net_user_global
                password = settings.net_pass_global

            # Map platform enum to Netmiko device type
            netmiko_platform = self.netmiko_platform_map.get(device.platform.value, device.platform.value)

            # Create Host object
            host = Host(
                name=device.hostname,
                hostname=device.ip,
                port=22,
                username=username,
                password=password,
                platform=netmiko_platform,
                data={
                    "site_code": device.site.code,
                    "device_id": device.id,
                    "platform": device.platform.value,
                    "site_name": device.site.name,
                    "gitea_repo_name": device.site.gitea_repo_name,
                }
            )

            hosts[device.hostname] = host

            logger.debug(f"Loaded host {device.hostname} ({netmiko_platform})")

        return Inventory(hosts=hosts, groups=groups)

    def load(self) -> Inventory:
        """
        Synchronous load method (required by InventoryPlugin interface).
        This is a placeholder; use load_async instead.
        """
        raise NotImplementedError(
            "Use load_async(session, settings, devices) instead"
        )
