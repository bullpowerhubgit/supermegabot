import asyncio
import sys
sys.path.append('modules')

async def test_backup_restore():
    print('🔄 Teste Cloud Backup Restore...')
    
    try:
        from cloud_backup_manager import CloudBackupManager
        
        manager = CloudBackupManager()
        
        # Backups auflisten
        print('📋 Verfügbare Backups:')
        backups = await manager.list_backups()
        
        if backups.get('total_backups', 0) == 0:
            print('❌ Keine Backups verfügbar')
            return False
        
        # Neuestes Backup finden
        local_backups = backups.get('local_backups', [])
        if not local_backups:
            print('❌ Keine lokalen Backups verfügbar')
            return False
        
        latest_backup = local_backups[0]
        print(f'📁 Neuestes Backup: {latest_backup.get("name")}')
        print(f'📊 Größe: {latest_backup.get("size", 0) / (1024*1024):.1f}MB')
        print(f'📅 Erstellt: {latest_backup.get("created")}')
        
        # Restore testen
        print('\n🔄 Starte Restore...')
        # Remove .zip extension for restore function
        backup_name = latest_backup.get('name').replace('.zip', '')
        restore_result = await manager.restore_backup(backup_name)
        
        if restore_result.get('success'):
            print(f'✅ Restore erfolgreich!')
            print(f'📁 Wiederhergestellt: {restore_result.get("files_restored", 0)} Dateien')
            print(f'📊 Größe: {restore_result.get("total_size", 0) / (1024*1024):.1f}MB')
            return True
        else:
            print(f'❌ Restore fehlgeschlagen: {restore_result.get("error")}')
            return False
            
    except Exception as e:
        print(f'💥 Restore Fehler: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_backup_restore())
    print(f'\n🏁 Restore Ergebnis: {"Erfolg" if success else "Fehlgeschlagen"}')
