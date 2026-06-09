#!/bin/bash
set -e; echo "🗄️ RudiBot Backup $(date)"; BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"; mkdir -p "$BACKUP_DIR"; echo "📦 Backing up database..."; PGPASSWORD=$SUPABASE_DB_PASSWORD pg_dump -h $SUPABASE_HOST -U postgres -d postgres > "$BACKUP_DIR/db.sql"; echo "💾 Backing up config..."; cp .env "$BACKUP_DIR/" 2>/dev/null || true; echo "✅ Backup complete: $BACKUP_DIR"
