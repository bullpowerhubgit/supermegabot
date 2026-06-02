import asyncio
import sys
sys.path.append('modules')

async def create_manual_backup():
    print('📦 Erstelle manuelles Cloud Backup...')
    
    try:
        from cloud_backup_manager import CloudBackupManager
        
        manager = CloudBackupManager()
        
        # Backup erstellen mit Timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'final_backup_{timestamp}'
        result = await manager.create_backup(backup_name)
        
        if result.get('success'):
            print(f'✅ Backup erfolgreich erstellt!')
            print(f'📁 Backup Name: {result["backup_name"]}')
            print(f'📊 Größe: {result["metadata"]["total_size"] / (1024*1024):.1f}MB')
            print(f'🌐 Cloud-Ergebnisse: {list(result["cloud_results"].keys())}')
            
            # Backups auflisten
            print('\n📋 Aktuelle Backups:')
            backups = await manager.list_backups()
            print(f'   Total: {backups.get("total_backups", 0)}')
            print(f'   Local: {len(backups.get("local_backups", []))}')
            print(f'   Cloud: {len(backups.get("cloud_backups", []))}')
            
            return True
        else:
            print(f'❌ Backup fehlgeschlagen: {result.get("error")}')
            return False
            
    except Exception as e:
        print(f'💥 Backup Fehler: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(create_manual_backup())
    print(f'\n🏁 Backup Ergebnis: {"Erfolg" if success else "Fehlgeschlagen"}')
