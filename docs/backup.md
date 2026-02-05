# Backup and Restore Strategy

## Overview
Production uses PostgreSQL (via Docker Compose). Local development may use SQLite when `DATABASE_URL` is unset. Redis is optional and not required for the crawler queue.

## PostgreSQL Backup (Docker)
Create a dump from the running container:

```bash
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker exec -t web-search-postgres pg_dump -U websearch websearch \
  > "$BACKUP_DIR/websearch_$TIMESTAMP.sql"
```

## PostgreSQL Restore (Docker)
Restore a dump into the container:

```bash
cat /backups/websearch_YYYYMMDD_HHMMSS.sql | \
  docker exec -i web-search-postgres psql -U websearch websearch
```

## SQLite Backup (Local Dev)
If you are running in SQLite mode:

```bash
BACKUP_DIR="/backups"
DB_PATH="/data/search.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/search_$TIMESTAMP.db'"
```

## Cron Schedule (Example)
```cron
# Daily PostgreSQL dump at 3 AM
0 3 * * * root /scripts/backup_pg.sh >> /var/log/backup.log 2>&1
```
