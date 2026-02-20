import asyncio
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import Base
from app.models import BackupJob, BackupJobStatus, CredentialSet, Device, PlatformEnum, Site


# ── Test database ──────────────────────────────────────────────────────────────

@pytest.fixture
async def test_db_session():
    """In-memory SQLite async session for tests (no PostgreSQL required)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ── Settings fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def test_settings():
    """Return a Settings instance with a valid Fernet key and test values."""
    fernet_key = Fernet.generate_key().decode()
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        gitea_url="http://localhost:3000",
        gitea_token="test-token",
        gitea_org="test-org",
        fernet_key=fernet_key,
        net_user_global="testuser",
        net_pass_global="testpass",
        nornir_num_workers=2,
        api_semaphore_limit=2,
        log_level="WARNING",
        debug=False,
    )


# ── ORM fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
async def sample_site(test_db_session):
    site = Site(code="SITE001", name="Test Site 1", gitea_repo_name="test-site-1")
    test_db_session.add(site)
    await test_db_session.commit()
    await test_db_session.refresh(site)
    return site


@pytest.fixture
async def sample_credential_set(test_db_session, test_settings):
    cipher = Fernet(test_settings.fernet_key.encode())
    encrypted_password = cipher.encrypt(b"testpass123").decode()
    cred = CredentialSet(
        label="test-creds",
        username="testuser",
        encrypted_password=encrypted_password,
    )
    test_db_session.add(cred)
    await test_db_session.commit()
    await test_db_session.refresh(cred)
    return cred


@pytest.fixture
async def sample_device(test_db_session, sample_site, sample_credential_set):
    device = Device(
        hostname="test-router-1",
        ip="192.168.1.1",
        platform=PlatformEnum.IOS,
        site_id=sample_site.id,
        credential_id=sample_credential_set.id,
        enabled=True,
    )
    test_db_session.add(device)
    await test_db_session.commit()
    await test_db_session.refresh(device)
    return device


@pytest.fixture
async def sample_backup_job(test_db_session):
    job = BackupJob(
        triggered_by="test-user",
        total_devices=1,
        status=BackupJobStatus.RUNNING,
    )
    test_db_session.add(job)
    await test_db_session.commit()
    await test_db_session.refresh(job)
    return job


# ── Multi-platform device fixtures ─────────────────────────────────────────

@pytest.fixture
async def cli_devices(test_db_session, sample_site, sample_credential_set):
    """Create sample CLI devices for all supported platforms."""
    platforms = [
        ("cisco_ios", "router-ios-1", "192.168.1.1", PlatformEnum.IOS),
        ("cisco_nxos", "router-nxos-1", "192.168.1.2", PlatformEnum.NXOS),
        ("arista_eos", "switch-eos-1", "192.168.1.3", PlatformEnum.EOS),
        ("dell_os10", "switch-os10-1", "192.168.1.4", PlatformEnum.OS10),
    ]
    devices = []
    for _, hostname, ip, platform_enum in platforms:
        device = Device(
            hostname=hostname,
            ip=ip,
            platform=platform_enum,
            site_id=sample_site.id,
            credential_id=sample_credential_set.id,
            enabled=True,
        )
        test_db_session.add(device)
        devices.append(device)

    await test_db_session.commit()
    for device in devices:
        await test_db_session.refresh(device)
    return devices


@pytest.fixture
async def api_devices(test_db_session, sample_site, sample_credential_set):
    """Create sample API devices for all supported platforms."""
    platforms = [
        ("fw-palo-1", "10.4.1.1", PlatformEnum.PANOS),
        ("fw-fortinet-1", "10.5.1.1", PlatformEnum.FORTIOS),
    ]
    devices = []
    for hostname, ip, platform_enum in platforms:
        device = Device(
            hostname=hostname,
            ip=ip,
            platform=platform_enum,
            site_id=sample_site.id,
            credential_id=sample_credential_set.id,
            enabled=True,
        )
        test_db_session.add(device)
        devices.append(device)

    await test_db_session.commit()
    for device in devices:
        await test_db_session.refresh(device)
    return devices


@pytest.fixture
async def all_devices(cli_devices, api_devices):
    """Combine CLI and API devices into one list."""
    return cli_devices + api_devices


# ── Asyncio marker helper ──────────────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
