import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean,
    Enum, Text, Float, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database import Base


class PlatformEnum(str, enum.Enum):
    """Supported network device platforms."""
    IOS = "ios"
    NXOS = "nxos"
    EOS = "eos"
    DELLOS10 = "dellos10"
    PANOS = "panos"
    FORTIOS = "fortios"


class BackupJobStatus(str, enum.Enum):
    """Backup job status."""
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class BackupResultStatus(str, enum.Enum):
    """Individual device backup result status."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class Site(Base):
    """Network site/location."""
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("code", name="uq_site_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    gitea_repo_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = relationship("Device", back_populates="site", cascade="all, delete-orphan")


class CredentialSet(Base):
    """Stored credentials for device access."""
    __tablename__ = "credential_sets"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(255), nullable=False)
    encrypted_password = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = relationship("Device", back_populates="credential_set")


class Device(Base):
    """Network device inventory entry."""
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("hostname", "site_id", name="uq_device_hostname_site"),
        Index("idx_device_platform", "platform"),
        Index("idx_device_site", "site_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String(255), nullable=False)
    ip = Column(String(45), nullable=False)
    platform = Column(Enum(PlatformEnum), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False, index=True)
    credential_id = Column(Integer, ForeignKey("credential_sets.id"), nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    site = relationship("Site", back_populates="devices")
    credential_set = relationship("CredentialSet", back_populates="devices")
    backup_results = relationship("BackupResult", back_populates="device", cascade="all, delete-orphan")


class BackupJob(Base):
    """Backup job tracking."""
    __tablename__ = "backup_jobs"
    __table_args__ = (Index("idx_backup_job_status", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    triggered_by = Column(String(255), nullable=False)
    status = Column(Enum(BackupJobStatus), default=BackupJobStatus.RUNNING, index=True)
    total_devices = Column(Integer, nullable=False)
    completed_devices = Column(Integer, default=0)
    failed_devices = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    results = relationship("BackupResult", back_populates="job", cascade="all, delete-orphan")


class BackupResult(Base):
    """Individual device backup result within a job."""
    __tablename__ = "backup_results"
    __table_args__ = (
        Index("idx_backup_result_job", "job_id"),
        Index("idx_backup_result_device", "device_id"),
        Index("idx_backup_result_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("backup_jobs.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    status = Column(Enum(BackupResultStatus), nullable=False)
    config_hash = Column(String(64), nullable=True)
    gitea_commit_sha = Column(String(40), nullable=True)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    backed_up_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("BackupJob", back_populates="results")
    device = relationship("Device", back_populates="backup_results")
