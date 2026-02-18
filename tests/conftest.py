import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database import Base
from app.models import Site, Device, CredentialSet, BackupJob, BackupResult
from app.config import Settings


@pytest.fixture
async def test_db_session():
    """Create test database session."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        gitea_url="http://localhost:3000",
        gitea_token="test-token",
        gitea_org="test-org",
        fernet_key="testFERNETkeyBase64EncodedStringHere1234567890",
        net_user_global="testuser",
        net_pass_global="testpass",
        nornir_num_workers=10,
        api_semaphore_limit=5,
        log_level="INFO",
        debug=False
    )


@pytest.fixture
async def sample_site(test_db_session):
    """Create a sample site."""
    site = Site(
        code="SITE001",
        name="Test Site 1",
        gitea_repo_name="test-site-1"
    )
    test_db_session.add(site)
    await test_db_session.commit()
    await test_db_session.refresh(site)
    return site


@pytest.fixture
async def sample_credential_set(test_db_session):
    """Create a sample credential set."""
    from cryptography.fernet import Fernet

    fernet_key = Fernet.generate_key()
    cipher = Fernet(fernet_key)
    encrypted_password = cipher.encrypt(b"testpass123").decode()

    cred = CredentialSet(
        label="test-creds",
        username="testuser",
        encrypted_password=encrypted_password
    )
    test_db_session.add(cred)
    await test_db_session.commit()
    await test_db_session.refresh(cred)
    return cred


@pytest.fixture
async def sample_device(test_db_session, sample_site, sample_credential_set):
    """Create a sample device."""
    from app.models import PlatformEnum

    device = Device(
        hostname="test-router-1",
        ip="192.168.1.1",
        platform=PlatformEnum.IOS,
        site_id=sample_site.id,
        credential_id=sample_credential_set.id,
        enabled=True
    )
    test_db_session.add(device)
    await test_db_session.commit()
    await test_db_session.refresh(device)
    return device


@pytest.fixture
async def sample_backup_job(test_db_session):
    """Create a sample backup job."""
    from app.models import BackupJobStatus

    job = BackupJob(
        triggered_by="test-user",
        total_devices=1,
        status=BackupJobStatus.RUNNING
    )
    test_db_session.add(job)
    await test_db_session.commit()
    await test_db_session.refresh(job)
    return job


def pytest_collection_modifyitems(config, items):
    """Add asyncio marker to all async tests."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
