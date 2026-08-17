#!/bin/sh
# 数据库 + 上传目录每日备份
# 保留 7 天,7 天前的自动清理

set -e
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_BACKUP="$BACKUP_DIR/db_$TIMESTAMP.db"
UPLOADS_BACKUP="$BACKUP_DIR/uploads_$TIMESTAMP.tar.gz"

echo "[backup] start $TIMESTAMP"

# 1. 数据库(SQLite 备份用 .backup 命令保证一致性)
if [ -f /data/db/xiulijiu.db ]; then
    sqlite3 /data/db/xiulijiu.db ".backup '$DB_BACKUP'"
    echo "[backup] db -> $DB_BACKUP"
fi

# 2. 上传目录
if [ -d /data/uploads ] && [ "$(ls -A /data/uploads)" ]; then
    tar -czf "$UPLOADS_BACKUP" -C /data uploads
    echo "[backup] uploads -> $UPLOADS_BACKUP"
fi

# 3. 清理 7 天前的
find "$BACKUP_DIR" -type f -mtime +7 -name "*.db" -delete
find "$BACKUP_DIR" -type f -mtime +7 -name "*.tar.gz" -delete
echo "[backup] cleanup done"

# 4. 上传(可选 - 留给运维配置 S3/OSS 客户端)
# rclone copy "$DB_BACKUP" remote:xiulijiu-backup/db/ || true
