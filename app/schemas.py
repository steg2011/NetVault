from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PlatformSchema(str, Enum):
    """Platform enum for schemas."""
    IOS = "ios"
    NXOS = "nxos"
    EOS = "eos"
    DELLOS10 = "dellos10"
    PANOS = "panos"
    FORTIOS = "fortios"


class SiteBase(BaseModel):
    """Base site schema."""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    gitea_repo_name: str = Field(..., min_length=1, max_length=255)


class SiteCreate(SiteBase):
    """Create site request."""
    pass


class SiteUpdate(BaseModel):
    """Update site request."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    gitea_repo_name: Optional[str] = Field(None, min_length=1, max_length=255)


class SiteResponse(SiteBase):
    """Site response."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CredentialSetBase(BaseModel):
    """Base credential set schema."""
    label: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)


class CredentialSetCreate(CredentialSetBase):
    """Create credential set request."""
    password: str = Field(..., min_length=1)


class CredentialSetUpdate(BaseModel):
    """Update credential set request."""
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1)


class CredentialSetResponse(CredentialSetBase):
    """Credential set response (no password returned)."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceBase(BaseModel):
    """Base device schema."""
    hostname: str = Field(..., min_length=1, max_length=255)
    ip: str = Field(..., min_length=7, max_length=45)
    platform: PlatformSchema
    site_id: int


class DeviceCreate(DeviceBase):
    """Create device request."""
    credential_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    """Update device request."""
    hostname: Optional[str] = Field(None, min_length=1, max_length=255)
    ip: Optional[str] = Field(None, min_length=7, max_length=45)
    platform: Optional[PlatformSchema] = None
    site_id: Optional[int] = None
    credential_id: Optional[int] = None
    enabled: Optional[bool] = None


class DeviceResponse(DeviceBase):
    """Device response."""
    id: int
    credential_id: Optional[int] = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BackupJobStatus(str, Enum):
    """Backup job status enum."""
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class BackupResultStatus(str, Enum):
    """Backup result status enum."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class BackupResultResponse(BaseModel):
    """Backup result response."""
    id: int
    job_id: int
    device_id: int
    status: BackupResultStatus
    config_hash: Optional[str] = None
    gitea_commit_sha: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    backed_up_at: datetime

    class Config:
        from_attributes = True


class BackupJobResponse(BaseModel):
    """Backup job response."""
    id: int
    triggered_at: datetime
    triggered_by: str
    status: BackupJobStatus
    total_devices: int
    completed_devices: int
    failed_devices: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: List[BackupResultResponse] = []

    class Config:
        from_attributes = True


class BackupJobCreate(BaseModel):
    """Create backup job request."""
    triggered_by: str = Field(..., min_length=1, max_length=255)
    site_id: Optional[int] = None


class BackupProgressMessage(BaseModel):
    """WebSocket progress message."""
    completed: int
    total: int
    failed: int
    status: str
    job_id: int


class DeviceHistoryResponse(BaseModel):
    """Device backup history response."""
    device_id: int
    hostname: str
    results: List[BackupResultResponse]


class DiffResponse(BaseModel):
    """Diff response."""
    device_id: int
    hostname: str
    unified_diff: str


# ── Schedules ─────────────────────────────────────────────────────────────────

class ScheduleFrequencySchema(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class BackupScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    frequency: ScheduleFrequencySchema
    hour: int = Field(2, ge=0, le=23)
    day_of_week: int = Field(0, ge=0, le=6)
    site_id: Optional[int] = None
    enabled: bool = True


class BackupScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    frequency: Optional[ScheduleFrequencySchema] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    site_id: Optional[int] = None
    enabled: Optional[bool] = None


class BackupScheduleResponse(BaseModel):
    id: int
    name: str
    frequency: ScheduleFrequencySchema
    hour: int
    day_of_week: int
    site_id: Optional[int] = None
    enabled: bool
    created_at: datetime
    last_run_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Device status ─────────────────────────────────────────────────────────────

class DeviceStatusItem(BaseModel):
    device_id: int
    hostname: str
    ip: str
    platform: str
    site_id: int
    site_name: str
    site_code: str
    enabled: bool
    last_backup_at: Optional[datetime] = None
    last_backup_status: Optional[str] = None
    last_backup_error: Optional[str] = None
    last_job_id: Optional[int] = None


class DeviceStatusPage(BaseModel):
    items: List[DeviceStatusItem]
    total: int
    page: int
    page_size: int
    pages: int
