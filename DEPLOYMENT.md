# AGNCF Deployment Guide

Complete guide for deploying Air-Gapped Network Config Fortress to production.

## Pre-Deployment Checklist

- [ ] Debian 12 server (4GB RAM minimum, 10GB storage minimum)
- [ ] Docker & Docker Compose installed
- [ ] SSH access to server
- [ ] Air-gapped environment verified (no outbound internet)
- [ ] Network connectivity to all target network devices
- [ ] Backup of any existing configurations

## Step 1: Prepare the Server

### Install Docker & Docker Compose

```bash
# Update system packages
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
sudo apt-get install -y docker.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
docker compose version
```

### Create Application Directory

```bash
# Create application home
sudo mkdir -p /opt/agncf
sudo chown $USER:$USER /opt/agncf
cd /opt/agncf
```

## Step 2: Prepare Wheels for Offline Installation

On a machine with internet access:

```bash
# Clone the repository
git clone <repo> agncf
cd agncf

# Download all wheel dependencies
mkdir -p wheels
pip download -r requirements.txt -d wheels/

# Create tarball for transfer
tar -czf agncf-wheels.tar.gz wheels/

# Transfer to air-gapped server
scp agncf-wheels.tar.gz user@server:/opt/agncf/
```

On the air-gapped server:

```bash
cd /opt/agncf
tar -xzf agncf-wheels.tar.gz
```

## Step 3: Deploy Application

```bash
# Copy application code to /opt/agncf
# (Already done if using git clone)

# Initialize environment
python3 scripts/init_env.py

# Edit .env with your configuration
nano .env
```

### Critical .env Settings

```bash
# Database
DB_NAME=agncf
DB_USER=agncf_user
DB_PASSWORD=<generate_strong_password>

# Gitea
GITEA_URL=http://gitea:3000
GITEA_TOKEN=<generate_in_gitea_admin>
GITEA_ORG=agncf
GITEA_SECRET_KEY=<generate_strong_key>

# Encryption
FERNET_KEY=<output_from_init_env.py>

# Global credentials (optional fallback)
NET_USER_GLOBAL=<if_needed>
NET_PASS_GLOBAL=<if_needed>

# Application
LOG_LEVEL=INFO
```

### Generate Gitea Token

After starting services:

```bash
# Access Gitea UI
# http://<server>:3000/admin/applications

# Create new OAuth2 token:
# - Name: agncf
# - Scopes: repo, admin
# Copy token to .env as GITEA_TOKEN
```

## Step 4: Start Services

```bash
# Build images with offline wheels
docker compose build

# Start all services
docker compose up -d

# Verify services are running
docker compose ps

# Expected output:
# agncf-db     postgres:15-alpine      healthy
# agncf-gitea  gitea/gitea:latest      running
# agncf-app    agncf:latest            running
```

## Step 5: Verify Deployment

```bash
# Check application health
curl http://localhost:8000/health

# Access web UI
# Dashboard: http://<server>:8000/dashboard
# Inventory: http://<server>:8000/inventory
# API Docs: http://<server>:8000/api/docs
# Gitea: http://<server>:8000:3000

# Check logs
docker compose logs -f app
```

## Step 6: Initial Configuration

1. **Create a Site**
   - Navigate to Inventory page
   - Click "+ Add Site"
   - Enter code, name, and Gitea repository name

2. **Create Credential Set**
   - Click "+ Add Credential Set"
   - Enter label, username, password
   - Password is encrypted with Fernet key

3. **Add Devices**
   - Click "+ Add Device"
   - Enter hostname, IP, platform
   - Assign to site and credential set

4. **Test Backup**
   - Navigate to Dashboard
   - Click "Start Backup"
   - Monitor real-time progress via WebSocket

## Security Considerations

### Network Isolation
- Keep application on isolated network segment
- Restrict access to port 8000 (FastAPI)
- Use firewall rules to block unnecessary traffic

### Credentials Management
- Rotate passwords regularly
- Store Fernet key securely (not in Git)
- Never commit .env with real secrets
- Use Docker secrets for sensitive data in production

### Database Security
```bash
# Strong PostgreSQL password
openssl rand -base64 32

# Enable PostgreSQL SSL (optional)
# Update docker-compose.yml with POSTGRES_INITDB_ARGS
```

### Access Control
- Restrict SSH to authorized users
- Use key-based authentication
- Implement rate limiting (nginx reverse proxy)
- Monitor access logs

## Backup & Recovery

### Database Backup

```bash
# Scheduled backup (crontab)
0 2 * * * docker exec agncf-db pg_dump -U agncf_user agncf > /opt/agncf/backups/db_$(date +\%Y\%m\%d).sql

# Or use Makefile
make db-backup
```

### Gitea Repository Backup

```bash
# Backup Gitea data directory
sudo tar -czf /opt/agncf/backups/gitea_$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/agncf_gitea_data/_data/

# Recovery
sudo tar -xzf /opt/agncf/backups/gitea_*.tar.gz -C /
docker compose restart gitea
```

### Full System Recovery

```bash
# Stop services
docker compose down

# Restore PostgreSQL
docker compose up -d db
sleep 10
docker exec -i agncf-db psql -U agncf_user agncf < /opt/agncf/backups/db_*.sql

# Restore Gitea (if needed)
sudo tar -xzf /opt/agncf/backups/gitea_*.tar.gz -C /

# Start all services
docker compose up -d
```

## Monitoring

### Check Service Health

```bash
# All containers
docker compose ps

# Specific service logs
docker compose logs app
docker compose logs db
docker compose logs gitea

# Real-time monitoring
docker stats

# Disk usage
df -h /opt/agncf
du -sh /opt/agncf/*
```

### Common Issues

**Database connection timeout**
```bash
docker compose logs db
docker compose restart db
```

**Gitea API errors**
```bash
# Verify token
curl -H "Authorization: token <TOKEN>" http://localhost:3000/api/v1/user

# Check Gitea logs
docker compose logs gitea
```

**High memory usage**
```bash
# Check current workers setting
grep NORNIR_NUM_WORKERS .env

# Reduce workers if memory constrained
NORNIR_NUM_WORKERS=25
API_SEMAPHORE_LIMIT=15
```

## Scaling Considerations

### For Large Device Inventories (2000+)

1. **Increase database pool**
   ```
   pool_size=50
   max_overflow=20
   ```

2. **Optimize Nornir workers**
   ```
   NORNIR_NUM_WORKERS=100  (with 8GB+ RAM)
   ```

3. **Add database indices**
   ```sql
   CREATE INDEX idx_backup_results_device_date
   ON backup_results(device_id, backed_up_at);
   ```

4. **Archive old backups**
   ```python
   # Implement retention policy
   # Keep last 100 backups per device
   # Archive others to cold storage
   ```

## Maintenance

### Regular Tasks

**Weekly**
- [ ] Check disk usage
- [ ] Review error logs
- [ ] Verify backup completion

**Monthly**
- [ ] Database maintenance (VACUUM, ANALYZE)
- [ ] Review backup retention
- [ ] Test recovery procedures
- [ ] Update device inventory

**Quarterly**
- [ ] Full system backup
- [ ] Security audit
- [ ] Performance analysis
- [ ] Test failover

### Database Maintenance

```bash
# Connect to database
docker exec -it agncf-db psql -U agncf_user -d agncf

# Maintenance commands
VACUUM ANALYZE;
REINDEX DATABASE agncf;
```

## Troubleshooting

### Application won't start
```bash
# Check logs
docker compose logs app

# Verify configuration
cat .env

# Restart from scratch
docker compose down -v
docker compose up
```

### Backup job hangs
```bash
# Check device connectivity
ping <device_ip>

# Verify credentials
# Check SSH/API access to device

# Monitor real-time
docker compose logs -f app | grep <device_hostname>
```

### Database bloat
```bash
# Check database size
docker exec agncf-db du -sh /var/lib/postgresql/data

# Clean up old backups
DELETE FROM backup_results WHERE backed_up_at < NOW() - INTERVAL '90 days';
```

## Upgrade Procedure

```bash
# Stop services
docker compose down

# Pull latest code
git pull origin main

# Review changes
git log --oneline -5

# Rebuild images
docker compose build

# Run migrations if needed
docker compose run --rm app alembic upgrade head

# Start services
docker compose up -d

# Verify
docker compose ps
curl http://localhost:8000/health
```

## Support & Documentation

- API Documentation: http://<server>:8000/api/docs
- README: /opt/agncf/README.md
- Logs: docker compose logs
- Configuration: /opt/agncf/.env

## Emergency Contact

For critical issues:
1. Check logs: `docker compose logs`
2. Verify connectivity: `ping <device>`
3. Test Gitea API: `curl http://gitea:3000/api/v1/repos`
4. Database connectivity: `docker exec agncf-db psql`
