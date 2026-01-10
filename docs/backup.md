# Backup and Restore Strategy

## Overview

SQLite database and Redis data are the critical stateful components.

## Backup Scripts

### SQLite Backup

```bash
#!/bin/bash
# backup_db.sh - Run daily via cron

BACKUP_DIR="/backups"
DB_PATH="/data/search.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup with SQLite online backup API
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/search_$TIMESTAMP.db'"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "search_*.db" -mtime +7 -delete

echo "Backup completed: search_$TIMESTAMP.db"
```

### Redis Backup

```bash
#!/bin/bash
# backup_redis.sh

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Trigger Redis background save
redis-cli BGSAVE

# Wait for save to complete
while [ $(redis-cli LASTSAVE) == $(redis-cli LASTSAVE) ]; do
    sleep 1
done

# Copy RDB file
cp /data/dump.rdb "$BACKUP_DIR/redis_$TIMESTAMP.rdb"

echo "Redis backup completed: redis_$TIMESTAMP.rdb"
```

## Restore Procedures

### SQLite Restore

```bash
# Stop the web service
docker compose stop web crawler

# Restore from backup
cp /backups/search_YYYYMMDD_HHMMSS.db /data/search.db

# Restart services
docker compose up -d web crawler
```

### Redis Restore

```bash
# Stop Redis
docker compose stop redis

# Replace RDB file
cp /backups/redis_YYYYMMDD_HHMMSS.rdb /path/to/redis/data/dump.rdb

# Start Redis
docker compose up -d redis
```

## Cron Schedule (Example)

```cron
# /etc/cron.d/web-search-backup

# Daily SQLite backup at 3 AM
0 3 * * * root /scripts/backup_db.sh >> /var/log/backup.log 2>&1

# Redis backup every 6 hours
0 */6 * * * root /scripts/backup_redis.sh >> /var/log/backup.log 2>&1
```

## Cloud Storage (Optional)

For off-site backups, sync to S3 or similar:

```bash
# After local backup
aws s3 sync /backups s3://your-bucket/web-search-backups/ --delete
```
