# AGNCF Architecture Documentation

Complete technical architecture overview of the Air-Gapped Network Config Fortress.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Air-Gapped Environment                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              FastAPI Application (Uvicorn)              │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Web UI Layer (Jinja2 Templates + Vanilla JS)       │ │  │
│  │  │ • Dashboard (real-time progress via WebSocket)    │ │  │
│  │  │ • Inventory Management (Sites/Devices/Creds)      │ │  │
│  │  │ • Diff Viewer (with syntax highlighting)          │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                          │                               │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ REST API Layer (FastAPI Routers)                  │ │  │
│  │  │ • /api/sites, /api/devices, /api/credentials     │ │  │
│  │  │ • /api/backups/jobs, /api/backups/diffs          │ │  │
│  │  │ • WS /ws/job/{job_id} (WebSocket progress)       │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                          │                               │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Business Logic Layer                               │ │  │
│  │  │ ┌──────────────────────────────────────────────┐  │ │  │
│  │  │ │ BackupEngine (Orchestrator)                 │  │ │  │
│  │  │ │ • Manages backup job execution              │  │ │  │
│  │  │ │ • Coordinates CLI & API device backups      │  │ │  │
│  │  │ │ • Publishes progress events to WebSocket    │  │ │  │
│  │  │ └──────────────────────────────────────────────┘  │ │  │
│  │  │                                                    │ │  │
│  │  │ ┌──────────────────┬──────────────────────────┐   │ │  │
│  │  │ │ CLI Path         │ API Path                │   │ │  │
│  │  │ │ ┌──────────────┐ │ ┌────────────────────┐ │   │ │  │
│  │  │ │ │   Nornir     │ │ │  asyncio.gather()  │ │   │ │  │
│  │  │ │ │  + Netmiko   │ │ │  + Semaphore(30)   │ │   │ │  │
│  │  │ │ │ 50 workers   │ │ │ Palo Alto + Fortinet│   │ │  │
│  │  │ │ │              │ │ │                    │ │   │ │  │
│  │  │ │ │ • cisco_ios  │ │ │ • backup_paloalto()│   │ │  │
│  │  │ │ │ • cisco_nxos │ │ │ • backup_fortinet()│   │ │  │
│  │  │ │ │ • arista_eos │ │ │                    │ │   │ │  │
│  │  │ │ │ • dell_os10  │ │ │                    │ │   │ │  │
│  │  │ │ └──────────────┘ │ └────────────────────┘ │   │ │  │
│  │  │ └──────────────────┴──────────────────────────┘   │ │  │
│  │  │                      │                            │ │  │
│  │  │ ┌────────────────────┴────────────────────────┐   │ │  │
│  │  │ │  ConfigScrubber (Platform-aware)           │   │ │  │
│  │  │ │  • Removes dynamic fields (uptime, stamps) │   │ │  │
│  │  │ │  • Supports 6 platforms + common patterns  │   │ │  │
│  │  │ │  • Output: SHA-256 hash for comparison     │   │ │  │
│  │  │ └────────────────────┬────────────────────────┘   │ │  │
│  │  │                      │                            │ │  │
│  │  │ ┌────────────────────┴────────────────────────┐   │ │  │
│  │  │ │  GiteaClient (API Integration)             │   │ │  │
│  │  │ │  • ensure_repo() - idempotent repo create │   │ │  │
│  │  │ │  • commit_config() - atomic commits        │   │ │  │
│  │  │ │  • get_diff() - unified diffs from API    │   │ │  │
│  │  │ └────────────────────┬────────────────────────┘   │ │  │
│  │  │                      ▼                            │ │  │
│  │  │               Gitea API v1                       │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                      │                                  │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Data Access Layer (SQLAlchemy Async + asyncpg)    │ │  │
│  │  │ • ORM Models (Site, Device, BackupJob, etc.)      │ │  │
│  │  │ • Relationships enforced at DB level              │ │  │
│  │  │ • Connection pooling: 20 size + 10 overflow       │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          │                                      │
├──────────────────────────┼──────────────────────────────────────┤
│                          │                                       │
│  ┌──────────────────────────────────────┐                      │
│  │ PostgreSQL 15 (Database)             │                      │
│  │ • sites, devices, credential_sets    │                      │
│  │ • backup_jobs, backup_results        │                      │
│  │ • Foreign keys + indices              │                      │
│  │ • Fernet-encrypted passwords          │                      │
│  └──────────────────────────────────────┘                      │
│                          │                                       │
│  ┌──────────────────────────────────────┐                      │
│  │ Gitea (Version Control)              │                      │
│  │ • Organization: agncf                │                      │
│  │ • Repository per Site                │                      │
│  │ • Files: {hostname}.txt               │                      │
│  │ • Commit history for diffs           │                      │
│  └──────────────────────────────────────┘                      │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│                    Network Boundary                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│                   NETWORK DEVICES (2000+)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │   IOS    │ │  NX-OS   │ │   EOS    │ │ OS10     │           │
│  │ (SSH)    │ │ (SSH)    │ │ (SSH)    │ │ (SSH)    │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                   │
│  ┌──────────┐ ┌──────────┐                                       │
│  │ Palo Alto│ │ Fortinet │                                       │
│  │ (XML API)│ │ (REST)   │                                       │
│  └──────────┘ └──────────┘                                       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. Application Layer (app/main.py)

**Responsibility**: FastAPI application setup, routing, lifecycle management

**Key Features**:
- Async context manager for startup/shutdown
- Database initialization on startup
- Route registration
- Static HTML pages with bundled CSS/JS

**Lifespan Flow**:
1. Startup: Initialize DB, setup logging
2. Serve requests
3. Shutdown: Close DB connections

### 2. Web UI Layer (app/templates/)

**Responsibility**: User-facing interfaces (no external CDN)

**Pages**:
- `base.html`: Shared layout, styles, structure
- `inventory.html`: CRUD for sites/devices/credentials
- `dashboard.html`: Job listing, backup trigger, auto-refresh
- `diff_view.html`: Unified diff rendering with syntax highlighting

**Features**:
- Responsive design (mobile-friendly)
- Form validation
- Modal dialogs
- Real-time updates via fetch/WebSocket
- No external dependencies

### 3. REST API Layer (app/routers/)

**Responsibility**: HTTP endpoint implementation

**routers/inventory.py**:
```
POST   /api/sites              - Create site
GET    /api/sites              - List sites
GET    /api/sites/{id}         - Get site
PUT    /api/sites/{id}         - Update site
DELETE /api/sites/{id}         - Delete site

POST   /api/devices            - Create device
GET    /api/devices            - List devices (with ?site_id filter)
GET    /api/devices/{id}       - Get device
PUT    /api/devices/{id}       - Update device
DELETE /api/devices/{id}       - Delete device

POST   /api/credentials        - Create credential set
GET    /api/credentials        - List credential sets
GET    /api/credentials/{id}   - Get credential
PUT    /api/credentials/{id}   - Update credential
DELETE /api/credentials/{id}   - Delete credential
```

**routers/backups.py**:
```
POST   /api/backups/jobs                  - Trigger backup
GET    /api/backups/jobs                  - List jobs
GET    /api/backups/jobs/{id}             - Get job details
GET    /api/backups/device/{id}/history   - Device backup history (last 5)
GET    /api/backups/diff/{id}             - Get latest diff
```

**routers/dashboard.py**:
```
GET    /dashboard              - Render dashboard page
WS     /ws/job/{job_id}        - WebSocket progress stream
```

### 4. Business Logic Layer

#### BackupEngine (app/core/backup_engine.py)

**Responsibility**: Orchestrate backup jobs across all devices

**Key Methods**:
- `run_backup(job_id, device_ids)`: Main job coordinator
- `_run_cli_backups()`: Nornir-based backup for SSH devices
- `_run_api_backups()`: Async gather with semaphore for API devices
- `_backup_api_device()`: Single API device backup
- `_resolve_credentials()`: Tiered credential lookup
- `_commit_config()`: Scrub and commit to Gitea
- `_record_failure()`: Track failed backups

**Execution Flow**:
```
run_backup(job_id, device_ids)
├── Load devices from DB
├── Separate into CLI vs API
├── _run_cli_backups()
│   ├── Load Nornir inventory from PostgreSQL
│   ├── Execute with 50 workers (netmiko)
│   ├── Process results
│   └── _commit_config() or _record_failure()
├── _run_api_backups()
│   ├── For each device:
│   │   ├── _backup_api_device()
│   │   ├── Resolve credentials
│   │   ├── Execute platform-specific backup
│   │   └── _commit_config() or _record_failure()
│   └── (limited to 30 concurrent via asyncio.Semaphore)
└── Update job status to COMPLETE/FAILED
```

**Progress Tracking**:
- Each backup publishes to asyncio.Queue (keyed by job_id)
- Messages contain: `{completed, total, failed, status, job_id}`
- WebSocket consumers receive real-time updates

#### CLI Task Executor (app/core/cli_tasks.py)

**Responsibility**: Netmiko-based config retrieval

**Device Support**:
- Cisco IOS: `show running-config`
- Cisco NX-OS: `show running-config`
- Arista EOS: `show running-config`
- Dell OS10: `show running-config`

**Nornir Integration**:
- Task name: `backup_config_cli`
- Runs via nornir-netmiko plugin
- 50 concurrent workers
- Returns: config text + SHA-256 hash

#### API Task Executor (app/core/api_tasks.py)

**Responsibility**: API-based config retrieval for non-SSH devices

**Palo Alto Backup Flow**:
1. GET `/api/?type=keygen` → Retrieve API key
2. Parse XML response for session token
3. GET `/api/?type=export&category=configuration` → Config export

**Fortinet Backup Flow**:
1. POST `/api/v2/auth/login` → Authenticate (get Bearer token)
2. GET `/api/v2/monitor/system/config/backup` → Config export

**Error Handling**:
- Network timeouts → Fail device, continue job
- Auth failures → Log, fail device, continue
- Invalid config → Hash mismatch, still commit (for manual review)

#### Configuration Scrubber (app/core/scrubber.py)

**Responsibility**: Remove dynamic fields before committing

**Platform-Specific Patterns**:

| Platform | Patterns Removed |
|----------|------------------|
| IOS | Uptime, config change time, NTP clock period, crypto certs |
| NX-OS | System uptime, config change time, serial/module numbers |
| EOS | System uptime, config change time, hostname, mgmt hostname |
| OS10 | Date/time, uptime, config change time |
| Palo Alto | Serial, uptime, app/threat/AV/Wildfire versions |
| Fortinet | UUID, timestamp, lastupdate, build number |
| All | IPv4 addresses, ISO timestamps |

**Output**:
- Scrubbed config text
- SHA-256 hash (for change detection)
- Suitable for long-term version control

#### Gitea Client (app/core/gitea_client.py)

**Responsibility**: Version control integration via Gitea API

**Methods**:
- `ensure_repo(site_code, repo_name)`: Idempotent repo creation
  - Check if repo exists
  - Create org if needed
  - Create repo with auto_init

- `commit_config(repo, device_hostname, config_text, commit_message)`:
  - Base64 encode content
  - Check if file exists (get SHA)
  - PUT to contents API
  - Return commit SHA

- `get_diff(repo, device_hostname)`: Retrieve unified diff
  - Get commits for file (last 2)
  - Use compare endpoint
  - Return patch text

**Error Handling**:
- Timeouts → Raise exception → Record failure
- Rate limiting → Retry with backoff (not implemented, add if needed)
- Missing repo → Auto-create on first commit attempt

#### Nornir Inventory Plugin (app/core/nornir_inventory.py)

**Responsibility**: Dynamic inventory from PostgreSQL

**Implementation**:
- Custom InventoryPlugin subclass
- Async load_async() method
- Queries: Device + Site + CredentialSet (joined)
- Maps platform enums to Netmiko device types
- Decrypts passwords using Fernet

**Device Type Mapping**:
```python
{
    "ios": "cisco_ios",
    "nxos": "cisco_nxos",
    "eos": "arista_eos",
    "dellos10": "dell_os10",
    "panos": "paloaltonetworks_panos",
    "fortios": "fortinet_fortios",
}
```

**Host Data**:
```python
{
    "site_code": Site.code,
    "device_id": Device.id,
    "platform": Device.platform,
    "site_name": Site.name,
    "gitea_repo_name": Site.gitea_repo_name,
}
```

### 5. Data Access Layer (app/database.py)

**Responsibility**: SQLAlchemy async engine & session management

**Engine Configuration**:
- Driver: asyncpg (PostgreSQL async driver)
- Pool size: 20
- Max overflow: 10
- Pre-ping: True (verify connections alive)
- Echo: Controlled by DEBUG setting

**Session Factory**:
- async_sessionmaker for dependency injection
- Automatic session cleanup
- FastAPI dependency: `get_db_session()`

### 6. Data Models (app/models.py)

**Schema Overview**:

```sql
sites (
  id INT PRIMARY KEY,
  code VARCHAR UNIQUE NOT NULL,
  name VARCHAR NOT NULL,
  gitea_repo_name VARCHAR NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)

credential_sets (
  id INT PRIMARY KEY,
  label VARCHAR UNIQUE NOT NULL,
  username VARCHAR NOT NULL,
  encrypted_password TEXT NOT NULL (Fernet),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)

devices (
  id INT PRIMARY KEY,
  hostname VARCHAR NOT NULL,
  ip VARCHAR NOT NULL,
  platform ENUM (ios, nxos, eos, dellos10, panos, fortios),
  site_id INT NOT NULL -> sites(id),
  credential_id INT NULLABLE -> credential_sets(id),
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (hostname, site_id),
  INDEX (platform, site_id)
)

backup_jobs (
  id INT PRIMARY KEY,
  triggered_at TIMESTAMP DEFAULT NOW(),
  triggered_by VARCHAR NOT NULL,
  status ENUM (running, complete, failed),
  total_devices INT NOT NULL,
  completed_devices INT DEFAULT 0,
  failed_devices INT DEFAULT 0,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  INDEX (status)
)

backup_results (
  id INT PRIMARY KEY,
  job_id INT NOT NULL -> backup_jobs(id),
  device_id INT NOT NULL -> devices(id),
  status ENUM (success, failed, skipped),
  config_hash VARCHAR(64) NOT NULL (SHA-256),
  gitea_commit_sha VARCHAR(40),
  error_message TEXT,
  duration_seconds FLOAT,
  backed_up_at TIMESTAMP DEFAULT NOW(),
  INDEX (job_id, device_id, status)
)
```

**Relationships**:
- Site → Devices (1:many, cascade delete)
- Site → BackupJobs (implicit via Devices)
- CredentialSet → Devices (1:many)
- Device → BackupResults (1:many, cascade delete)
- BackupJob → BackupResults (1:many, cascade delete)

### 7. Configuration Management (app/config.py)

**Responsibility**: Settings loading from environment variables

**Settings Class** (Pydantic):
- Reads `.env` via pydantic-settings
- All secrets loaded from env
- Validates required fields
- Provides defaults where sensible

**Key Settings**:
- `database_url`: PostgreSQL connection string
- `gitea_url`, `gitea_token`: API access
- `fernet_key`: Encryption key (base64)
- `net_user_global`, `net_pass_global`: Fallback credentials
- `nornir_num_workers`: CLI concurrency (default 50)
- `api_semaphore_limit`: API concurrency (default 30)
- `log_level`: Logging verbosity

## Concurrency Model

### CLI Devices (Netmiko + Nornir)

**Model**: Thread-pool based (50 workers)

```
Device 1 ─┐
Device 2 ─┼─ Nornir Task Group ─ 50 Concurrent SSH Connections ─ Show Config
Device 3 ─┤
...       │
Device 50 ┴─ (Queued, waiting for available worker)
```

**Why 50?**:
- SSH connections are IO-bound
- Each connection holds a file descriptor
- 50 is reasonable for most systems without ulimit adjustment
- Configurable via `NORNIR_NUM_WORKERS`

### API Devices (asyncio + Semaphore)

**Model**: Async coroutines with concurrency limiting

```
Device 1 ──────┐
Device 2 ──────┼─ asyncio.gather() ─ Semaphore(30) ─ 30 Concurrent HTTP Requests
Device 3 ──────┤
...            │
Device 30 ─────┴─ (Queued)
```

**Why 30?**:
- HTTP requests are async (true concurrency)
- Prevents API rate limiting
- Avoids overwhelming target firewalls
- Configurable via `API_SEMAPHORE_LIMIT`

### WebSocket Progress Broadcasting

**Model**: asyncio.Queue per job

```
BackupEngine.run_backup()
├── Publishes progress_queue[job_id].put(message) after each device
│   (non-blocking, fire-and-forget)
└── Continues processing next device

WebSocket endpoint
├── Awaits progress_queue[job_id].get()
├── Sends JSON to client
└── Repeat
```

## Credential Resolution Strategy

**Priority Order**:

1. **Device Credential Set** (device.credential_id)
   - Fetch CredentialSet by ID
   - Decrypt password using Fernet
   - Use for this device only

2. **Global Environment Variables**
   - `NET_USER_GLOBAL` + `NET_PASS_GLOBAL`
   - Used for all devices without explicit credentials
   - Typically for homogeneous environments

3. **Failure**
   - No credentials available
   - Record BackupResult with FAILED status
   - Continue job (don't abort entire backup)

**Implementation** (backup_engine.py):
```python
async def _resolve_credentials(device):
    # Priority 1
    if device.credential_id:
        cred_set = get from DB
        return decrypt(cred_set.encrypted_password)

    # Priority 2
    if SETTINGS.net_user_global and SETTINGS.net_pass_global:
        return SETTINGS.net_user_global, SETTINGS.net_pass_global

    # Priority 3
    return None, None  # Caller will fail device, continue job
```

## Error Handling Strategy

**Goal**: Never abort entire backup due to single device failure

**Scenarios**:

| Scenario | Handling |
|----------|----------|
| Device unreachable | SSH/API timeout → catch exception → record FAILED |
| Auth failure | Netmiko exception → catch → record FAILED |
| No credentials | None returned → record FAILED |
| Config retrieval error | Exception during show/export → record FAILED |
| Scrubbing error | Regex error (rare) → log, use unscrubbed config, continue |
| Gitea commit failure | Network error → record FAILED, continue (can retry) |
| Progress publish | Queue full (shouldn't happen) → log, ignore |

**Result**: Partial success on per-device basis

```
Job: 100 devices
├── 85 successful commits
├── 10 authentication failures (recorded)
├── 3 unreachable (timeouts)
├── 2 config retrieval errors

Final Status: COMPLETE (not FAILED)
Failed count: 15
```

## Deployment Architecture

### Docker Compose Services

```yaml
agncf-db:      postgres:15-alpine        # Database
agncf-gitea:   gitea/gitea:latest        # Version control
agncf-app:     agncf:latest              # FastAPI application
```

### Network Topology

```
Docker Network: agncf_net (bridge)
├── app container (port 8000)
├── db container (port 5432, internal only)
└── gitea container (port 3000, internal only)

External Access:
├── HTTP: localhost:8000 → Uvicorn (FastAPI)
└── Gitea UI: localhost:3000 → Gitea HTTP
```

### Storage

```
Docker Volumes:
├── db_data      (PostgreSQL data)
├── gitea_data   (Gitea repositories & config)
└── backups/     (Local backup directory, bind mount)
```

## Performance Characteristics

### Throughput

**CLI Devices**:
- ~2-5 seconds per device (SSH overhead + show running-config)
- 50 workers → ~10-25 devices/minute
- 2000 devices → 80-200 minutes (1.3-3.3 hours)

**API Devices**:
- ~1-2 seconds per device (faster than SSH)
- 30 concurrent → ~15-30 devices/minute
- 1000 devices → 33-67 minutes (0.5-1 hour)

**Combined**:
- 1500 CLI + 500 API → ~2.5-4 hours total

### Database

**Query Performance**:
- Device list: ~0.5ms (indexed by site, platform)
- Credential lookup: ~0.1ms (indexed by id)
- Backup history: ~1ms (indexed by device_id, date)

**Storage**:
- Per device per backup: ~50KB config + DB record
- 2000 devices × 100 backups = 10GB configs
- PostgreSQL size: ~100MB (with indices)

### Memory

**Application Memory**:
- Base FastAPI/Nornir: ~200MB
- Per concurrent device: ~5-10MB
- Max (100 concurrent): ~1GB
- Recommended: 2-4GB

**Database Memory**:
- PostgreSQL shared_buffers: ~256MB (default)
- Gitea: ~300MB
- Total: ~800MB
- Recommended: 2GB

## Security Considerations

### Authentication & Authorization

**Current**: None (internal network assumption)

**For External Access**, add:
- API key validation
- JWT tokens
- Role-based access control (RBAC)
- Audit logging

### Encryption

**At Rest**:
- Database passwords: Fernet symmetric encryption
- Database itself: PostgreSQL native encryption (optional)
- SSH private keys: N/A (not stored)

**In Transit**:
- HTTPS: Recommended (add reverse proxy)
- SSH: Netmiko handles
- Gitea API: HTTP (internal only)

**Secrets Management**:
- All secrets from environment variables
- Fernet key in `.env` (not in Git)
- Database password in `.env` (not in Git)
- Gitea token in `.env` (not in Git)

### Access Control

**Network Level**:
- No internet access (air-gapped)
- SSH to devices (credentials encrypted)
- Gitea internal (Docker network only)

**Database Level**:
- PostgreSQL user: agncf_user (limited grants)
- Network: Only Docker network access

## Extensibility Points

### Adding New Platform Support

1. **Update models.py**:
   ```python
   class PlatformEnum(str, enum.Enum):
       NEW_PLATFORM = "new_platform"
   ```

2. **Add netmiko device type** (if CLI):
   ```python
   # nornir_inventory.py
   netmiko_platform_map["new_platform"] = "vendor_new_platform"
   ```
   OR **Create API task** (if API-based):
   ```python
   # api_tasks.py
   async def backup_new_platform(...):
       # Implementation
   ```

3. **Update backup_engine.py**:
   ```python
   elif device.platform.value == "new_platform":
       result = await backup_new_platform(...)
   ```

4. **Add scrubber patterns** (app/core/scrubber.py):
   ```python
   "new_platform": [
       (r"pattern_to_remove", "replacement"),
   ]
   ```

### Adding Custom Backup Processing

```python
# In backup_engine._commit_config():
# Add post-processing hook
processed_config = custom_processor.process(scrubbed_config)
```

### Adding Backup Retention Policies

```python
# Archive or delete old backups
DELETE FROM backup_results
WHERE backed_up_at < NOW() - INTERVAL '90 days'
AND status = 'success'
AND job_id NOT IN (latest 10 per device);
```

---

## References

- **Nornir**: https://nornir.readthedocs.io/
- **Netmiko**: https://pynet.twb-tech.com/netmiko.html
- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Gitea API**: https://docs.gitea.io/en-us/api-docs/
- **Fernet Encryption**: https://cryptography.io/en/latest/fernet/
