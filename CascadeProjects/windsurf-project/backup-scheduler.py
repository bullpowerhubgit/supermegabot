#!/usr/bin/env python3
"""
SuperMegaBot Backup Scheduler
Automated backup scheduling with launchd integration
"""

import os
import sys
import json
import plistlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class BackupScheduler:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.backup_script = os.path.join(self.script_dir, 'cloud-backup.py')
        self.config_dir = os.path.expanduser('~/Library/LaunchAgents')
        self.plist_file = os.path.join(self.config_dir, 'com.supermegabot.backup.plist')
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        
    def create_launchd_plist(self, interval_hours: int = 24) -> dict:
        """Create launchd plist for scheduled backups"""
        script_path = os.path.abspath(self.backup_script)
        
        plist = {
            'Label': 'com.supermegabot.backup',
            'ProgramArguments': [
                '/usr/bin/python3',
                script_path,
                '--backup'
            ],
            'StartInterval': interval_hours * 3600,  # Convert hours to seconds
            'RunAtLoad': False,
            'StandardOutPath': os.path.expanduser('~/Library/Logs/SuperMegaBot-Backup.log'),
            'StandardErrorPath': os.path.expanduser('~/Library/Logs/SuperMegaBot-Backup-Error.log'),
            'WorkingDirectory': self.script_dir
        }
        
        return plist
    
    def install_scheduler(self, interval_hours: int = 24) -> bool:
        """Install launchd agent for scheduled backups"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            
            plist = self.create_launchd_plist(interval_hours)
            
            with open(self.plist_file, 'wb') as f:
                plistlib.dump(plist, f)
            
            print(f"✅ Launchd plist created: {self.plist_file}")
            
            # Load the agent
            result = subprocess.run(
                ['launchctl', 'load', self.plist_file],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                print(f"✅ Backup scheduler installed (interval: {interval_hours} hours)")
                return True
            else:
                print(f"❌ Failed to load launchd agent: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error installing scheduler: {e}")
            return False
    
    def uninstall_scheduler(self) -> bool:
        """Uninstall launchd agent"""
        try:
            if not os.path.exists(self.plist_file):
                print("⚠️  Scheduler not installed")
                return True
            
            # Unload the agent
            result = subprocess.run(
                ['launchctl', 'unload', self.plist_file],
                capture_output=True, text=True
            )
            
            # Remove plist file
            os.remove(self.plist_file)
            
            print("✅ Backup scheduler uninstalled")
            return True
            
        except Exception as e:
            print(f"❌ Error uninstalling scheduler: {e}")
            return False
    
    def check_scheduler_status(self) -> dict:
        """Check if scheduler is running"""
        try:
            result = subprocess.run(
                ['launchctl', 'list'],
                capture_output=True, text=True
            )
            
            is_running = 'com.supermegabot.backup' in result.stdout
            
            status = {
                'installed': os.path.exists(self.plist_file),
                'running': is_running,
                'plist_file': self.plist_file if os.path.exists(self.plist_file) else None
            }
            
            return status
            
        except Exception as e:
            print(f"❌ Error checking status: {e}")
            return {'installed': False, 'running': False, 'plist_file': None}
    
    def get_next_backup_time(self, interval_hours: int = 24) -> str:
        """Calculate next scheduled backup time"""
        now = datetime.now()
        next_backup = now + timedelta(hours=interval_hours)
        return next_backup.strftime('%Y-%m-%d %H:%M:%S')
    
    def view_logs(self) -> bool:
        """View backup logs"""
        log_file = os.path.expanduser('~/Library/Logs/SuperMegaBot-Backup.log')
        error_log = os.path.expanduser('~/Library/Logs/SuperMegaBot-Backup-Error.log')
        
        print("\n📋 Backup Logs:")
        print("=" * 60)
        
        if os.path.exists(log_file):
            print(f"\n📄 {log_file}:")
            with open(log_file, 'r') as f:
                print(f.read()[-2000:])  # Last 2000 characters
        else:
            print("No standard log file found")
        
        if os.path.exists(error_log):
            print(f"\n❌ {error_log}:")
            with open(error_log, 'r') as f:
                content = f.read()
                if content:
                    print(content[-2000:])
                else:
                    print("No errors logged")
        else:
            print("No error log file found")
        
        return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SuperMegaBot Backup Scheduler')
    parser.add_argument('--install', '-i', type=int, metavar='HOURS',
                       help='Install scheduler with interval in hours')
    parser.add_argument('--uninstall', '-u', action='store_true',
                       help='Uninstall scheduler')
    parser.add_argument('--status', '-s', action='store_true',
                       help='Check scheduler status')
    parser.add_argument('--logs', '-l', action='store_true',
                       help='View backup logs')
    
    args = parser.parse_args()
    
    scheduler = BackupScheduler()
    
    if args.install:
        scheduler.install_scheduler(args.install)
    elif args.uninstall:
        scheduler.uninstall_scheduler()
    elif args.status:
        status = scheduler.check_scheduler_status()
        print("\n📊 Scheduler Status:")
        print("=" * 60)
        print(f"Installed: {'✅ Yes' if status['installed'] else '❌ No'}")
        print(f"Running: {'✅ Yes' if status['running'] else '❌ No'}")
        if status['plist_file']:
            print(f"Plist: {status['plist_file']}")
        if status['running']:
            print(f"Next backup: {scheduler.get_next_backup_time()}")
    elif args.logs:
        scheduler.view_logs()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
