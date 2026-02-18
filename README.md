# Air-Gapped Network Config Fortress (AGNCF)

A production-ready Python application for backing up, versioning, and monitoring configurations from 2,000+ multi-vendor network devices in strictly air-gapped environments.

## Architecture

- **Backend**: FastAPI + Uvicorn
- **Database**: PostgreSQL 15
- **Inventory**: Nornir 3.x with PostgreSQL plugin
- **CLI Devices**: Netmiko + nornir-netmiko (Cisco IOS/NX-OS, Arista EOS, Dell OS10)
- **API Devices**: httpx (Palo Alto XML API, Fortinet REST API)
- **Version Control**: Gitea (self-hosted, API-driven)
- **Frontend**: Jinja2 templates + vanilla JS (no external CDN)
- **Deployment**: Docker Compose on Debian 12

## Features

- **Multi-vendor Support**
  - Cisco IOS/NX-OS
  - Arista EOS
  - Dell OS10
  - Palo Alto Networks
  - Fortinet FortiOS

- **Credential Management**
  - Fernet encryption at rest
  - Tiered resolution (device-specific → global env → failure handling)
  - Secure storage in PostgreSQL

- **Configuration Scrubbing**
  - Platform-aware regex patterns
  - Removes dynamic fields (uptime, timestamps, serial numbers)
  - Supports all 6 platforms

- **Gitea Integration**
  - Idempotent repository creation
  - Automatic file commits with unified diffs
  - Version history per device

- **Real-time Progress**
  - WebSocket-based job progress streaming
  - Live device backup status
  - Async batch processing (50 CLI workers, 30 API concurrent)

- **Web UI**
  - Dashboard with job tracking
  - Inventory management (sites, devices, credentials)
  - Configuration diff viewer with syntax highlighting
  - Air-gapped (no CDN, all assets bundled)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- 4GB+ RAM, 10GB+ storage
- No internet access required after initial build

### Setup

1. **Clone and configure**:
   ```bash
   git clone <repo>
   cd agncf
   cp .env.example .env
   # Edit .env with your values
   ```

2. **Generate cryptographic keys** (if not present):
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Paste the key into `.env` as `FERNET_KEY`

3. **Build and start**:
   ```bash
   docker compose up -d
   ```

4. **Access**:
   - Dashboard: http://localhost:8000/dashboard
   - Inventory: http://localhost:8000/inventory
   - API Docs: http://localhost:8000/api/docs
   - Gitea: http://localhost:3000

### Initialize Data

1. Create a Site in the Inventory UI
2. Create Credential Sets for device authentication
3. Add Devices (assign to sites, link credentials)
4. Start backup jobs from Dashboard

## API Endpoints

### Inventory

- `POST /api/sites` - Create site
- `GET /api/sites` - List sites
- `PUT /api/sites/{id}` - Update site
- `DELETE /api/sites/{id}` - Delete site

- `POST /api/devices` - Create device
- `GET /api/devices` - List devices
- `PUT /api/devices/{id}` - Update device
- `DELETE /api/devices/{id}` - Delete device

- `POST /api/credentials` - Create credential set
- `GET /api/credentials` - List credentials
- `PUT /api/credentials/{id}` - Update credentials
- `DELETE /api/credentials/{id}` - Delete credentials

### Backups

- `POST /api/backups/jobs` - Trigger backup job
- `GET /api/backups/jobs` - List backup jobs
- `GET /api/backups/jobs/{id}` - Get job details
- `GET /api/backups/device/{id}/history` - Device backup history
- `GET /api/backups/diff/{id}` - Get configuration diff

### WebSocket

- `WS /ws/job/{job_id}` - Stream backup progress

## Database Schema

### Sites
- `id`, `code` (unique), `name`, `gitea_repo_name`

### Devices
- `id`, `hostname`, `ip`, `platform` (enum), `site_id` (FK), `credential_id` (FK)

### CredentialSets
- `id`, `label`, `username`, `encrypted_password` (Fernet)

### BackupJobs
- `id`, `triggered_at`, `triggered_by`, `status`, `total_devices`, `completed_devices`, `failed_devices`

### BackupResults
- `id`, `job_id` (FK), `device_id` (FK), `status`, `config_hash` (SHA-256), `gitea_commit_sha`, `error_message`, `duration_seconds`

## Configuration Scrubbing

Platform-specific regex patterns remove:

**Cisco IOS/NX-OS/EOS/Dell OS10**:
- Uptime values
- Configuration change timestamps
- NTP clock periods
- Crypto PKI certificates

**Palo Alto**:
- Serial numbers
- Uptime
- App/threat/antivirus/Wildfire versions

**Fortinet**:
- UUID values
- Timestamps
- Build numbers

**All Platforms**:
- IPv4 addresses (masked to `<ip-address>`)
- ISO timestamps (masked to `<timestamp>`)

## Credential Resolution (Priority Order)

1. Device-specific credential set (device.credential_id → CredentialSet)
2. Global environment variables (NET_USER_GLOBAL / NET_PASS_GLOBAL)
3. Failure → mark device as failed, continue job

## Testing

```bash
# Run scrubber tests
pytest tests/test_scrubber.py -v

# Run all tests
pytest -v

# With coverage
pytest --cov=app tests/
```

## Production Deployment

1. **Pre-build wheels** (for offline installation):
   ```bash
   pip download -r requirements.txt -d wheels/
   docker build -t agncf:prod .
   ```

2. **Use environment-based configuration**:
   - All secrets via `.env` or Docker secrets
   - No hardcoded credentials

3. **Monitor logs**:
   ```bash
   docker logs -f agncf-app
   ```

4. **Backup database**:
   ```bash
   docker exec agncf-db pg_dump -U agncf_user agncf > backup.sql
   ```

## Troubleshooting

### Backup jobs failing for specific devices
- Check logs: `docker logs agncf-app`
- Verify credentials in UI
- Test connectivity to device

### Gitea integration issues
- Ensure Gitea token is valid: `/api/v1/user` endpoint
- Check network connectivity between app and gitea services
- Verify org exists in Gitea

### Database connection errors
- Verify postgres service is healthy: `docker ps`
- Check DATABASE_URL in .env
- Review db logs: `docker logs agncf-db`

## Architecture Decisions

**Async/Await**: All DB operations use asyncpg + SQLAlchemy async for true parallelism

**Nornir + CLI**: 50 concurrent workers for CLI devices (netmiko SSH connections are IO-bound)

**API Semaphore**: 30 concurrent limit for Palo Alto/Fortinet (prevents API rate limiting)

**Gitea API**: Contents API for commits ensures transactional consistency

**Fernet Encryption**: Symmetric encryption suitable for secrets at rest in PostgreSQL

**No CDN**: All frontend assets bundled inline in templates for air-gapped operation

## Contributing

1. Follow PEP 8
2. Add tests for new features
3. Ensure all scrubber tests pass
4. Document new endpoints

## License

Internal Use Only

## Support

For issues, check logs and verify:
1. All services running (`docker ps`)
2. Database connectivity
3. Gitea accessibility
4. Network connectivity to devices
