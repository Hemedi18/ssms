# Production Deployment & Operations Guide

This guide describes how to deploy the **SIM SMS Gateway** backend using Docker Compose, configure PostgreSQL, terminate HTTPS with automated TLS certificates, and manage automated database backups.

---

## 1. Architecture Overview

```
                      ┌─────────────────────────────────────────┐
                      │              Docker Host                │
                      │                                         │
Internet / Clients ───┼─► [ Caddy / Nginx Reverse Proxy (TLS) ] │
                      │                    │                    │
                      │                    ▼                    │
                      │       [ FastAPI Backend (:8000) ]       │
                      │         │                  │            │
                      │         ▼                  ▼            │
                      │   [ PostgreSQL ]     [ Webhook Worker ] │
                      └─────────────────────────────────────────┘
```

---

## 2. Docker Compose Deployment

The repository includes a production-ready `docker-compose.yml`.

### Step 1: Clone Repository & Create `.env`
```bash
git clone https://github.com/your-org/sim-sms-gateway.git
cd sim-sms-gateway

# Copy example environment
cp backend/.env.example .env
```

### Step 2: Configure Environment Variables
Edit `.env` with strong production secrets:
```ini
ENVIRONMENT=production
SECRET_KEY=change-me-to-a-64-character-random-hex-string
DEBUG=false
ALLOWED_HOSTS=["sms.yourdomain.com"]

# Database Configuration (PostgreSQL)
DATABASE_URL=postgresql://gateway_user:StrongPassword123@db:5432/gateway_db

# Rate Limiting & Safety
DEFAULT_RATE_LIMIT=120
ALLOWLIST_DESTINATIONS=[]
DEVICE_OFFLINE_THRESHOLD_SECONDS=90
```

### Step 3: Launch Containers
```bash
docker compose up -d --build
```
This launches:
1. `db`: PostgreSQL 16 Alpine container with a persistent volume `postgres_data`.
2. `api`: FastAPI REST API container running Uvicorn with auto-migrations.
3. `worker`: Background asynchronous worker processing webhook deliveries and lease timeouts.

### Step 4: Run Initial Migrations & Provision Admin Key
```bash
# Verify database schema is up to date
docker compose exec api alembic upgrade head

# Create initial Production API Key
docker compose exec api python -m app.cli create-api-key --name "ProductionRoot"
```

---

## 3. HTTPS Reverse Proxy Configuration

Never expose raw HTTP to the public internet. Use Caddy or Nginx to handle TLS termination.

### Option A: Caddy (Recommended - Automatic Let's Encrypt TLS)
Create `/etc/caddy/Caddyfile`:
```caddy
sms.yourdomain.com {
    reverse_proxy localhost:8000 {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
    }

    # Strict Security Headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
}
```
Reload Caddy:
```bash
sudo systemctl reload caddy
```

---

## 4. Database Backup & Disaster Recovery

### Automated Daily Backup Script
Save as `/usr/local/bin/backup-gateway-db.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/sms_gateway"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/gateway_db_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# Dump PostgreSQL database compressed
docker compose exec -T db pg_dump -U gateway_user gateway_db | gzip > "$BACKUP_FILE"

# Rotate backups (keep last 14 days)
find "$BACKUP_DIR" -type f -name "gateway_db_*.sql.gz" -mtime +14 -delete

echo "Backup completed successfully: $BACKUP_FILE"
```
Make executable and schedule in cron:
```bash
chmod +x /usr/local/bin/backup-gateway-db.sh
# Run every day at 03:00 UTC
(crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/bin/backup-gateway-db.sh") | crontab -
```

### Database Restoration Procedure
```bash
# 1. Decompress and restore database dump
gunzip < /var/backups/sms_gateway/gateway_db_20261024_030000.sql.gz | docker compose exec -T db psql -U gateway_user -d gateway_db

# 2. Restart API to refresh connections
docker compose restart api worker
```
