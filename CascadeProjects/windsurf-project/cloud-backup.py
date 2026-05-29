#!/usr/bin/env python3
"""
SuperMegaBot Cloud Backup
Professional cloud backup solution with multiple provider support
"""

import os
import sys
import json
import shutil
import hashlib
import datetime
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading
import time

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class CloudBackup:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__),
            'cloud-backup-config.json'
        )
        self.config = self.load_config()
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        self.backup_stats = {
            'total_files': 0,
            'total_size': 0,
            'backed_up': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None
        }

    def load_config(self) -> Dict:
        """Load backup configuration from file"""
        default_config = {
            'backup_paths': [
                os.path.expanduser('~/Documents'),
                os.path.expanduser('~/Desktop'),
                os.path.expanduser('~/Pictures'),
                os.path.expanduser('~/Downloads')
            ],
            'exclude_patterns': [
                '*.tmp',
                '*.cache',
                '.DS_Store',
                'node_modules',
                '.git',
                '__pycache__',
                '*.pyc'
            ],
            'providers': {
                'local': {
                    'enabled': True,
                    'backup_dir': os.path.expanduser('~/SuperMegaBot-Backups')
                },
                'dropbox': {
                    'enabled': False,
                    'path': os.path.expanduser('~/Dropbox/SuperMegaBot-Backups')
                },
                'google_drive': {
                    'enabled': False,
                    'path': os.path.expanduser('~/Google Drive/SuperMegaBot-Backups')
                },
                'icloud': {
                    'enabled': False,
                    'path': os.path.expanduser('~/Library/Mobile Documents/com~apple~CloudDocs/SuperMegaBot-Backups')
                },
                'aws_s3': {
                    'enabled': False,
                    'bucket': '',
                    'region': 'us-east-1',
                    'access_key': '',
                    'secret_key': ''
                }
            },
            'compression': {
                'enabled': True,
                'format': 'zip'
            },
            'encryption': {
                'enabled': False,
                'password': ''
            },
            'scheduling': {
                'enabled': False,
                'interval_hours': 24
            }
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except Exception as e:
                print(f"Warning: Could not load config, using defaults: {e}")

        return default_config

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"Error saving config: {e}")

    def should_exclude(self, file_path: str) -> bool:
        """Check if file should be excluded based on patterns"""
        for pattern in self.config['exclude_patterns']:
            if pattern in file_path:
                return True
        return False

    def get_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return ""

    def get_backup_size(self, path: str) -> int:
        """Calculate total size of directory/file"""
        total_size = 0
        if os.path.isfile(path):
            return os.path.getsize(path)
        
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if not self.should_exclude(file_path):
                    try:
                        total_size += os.path.getsize(file_path)
                    except Exception:
                        pass
        return total_size

    def format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def backup_to_local(self, backup_name: str) -> bool:
        """Backup to local directory"""
        local_config = self.config['providers']['local']
        if not local_config['enabled']:
            return False

        backup_dir = local_config['backup_dir']
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"{backup_name}_{timestamp}")
        
        print(f"\n📦 Local Backup: {backup_path}")
        
        success = True
        for source_path in self.config['backup_paths']:
            if os.path.exists(source_path):
                dest_path = os.path.join(backup_path, os.path.basename(source_path))
                try:
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, dest_path, 
                                      ignore=shutil.ignore_patterns(
                                          *self.config['exclude_patterns']
                                      ))
                    else:
                        shutil.copy2(source_path, dest_path)
                    
                    size = self.get_backup_size(source_path)
                    print(f"  ✅ {os.path.basename(source_path)}: {self.format_size(size)}")
                    self.backup_stats['backed_up'] += 1
                except Exception as e:
                    print(f"  ❌ {os.path.basename(source_path)}: {e}")
                    self.backup_stats['failed'] += 1
                    success = False
        
        return success

    def backup_to_dropbox(self, backup_name: str) -> bool:
        """Backup to Dropbox folder"""
        dropbox_config = self.config['providers']['dropbox']
        if not dropbox_config['enabled']:
            return False

        backup_dir = dropbox_config['path']
        if not os.path.exists(backup_dir):
            print(f"⚠️  Dropbox path not found: {backup_dir}")
            return False

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"{backup_name}_{timestamp}")
        
        print(f"\n☁️  Dropbox Backup: {backup_path}")
        
        success = True
        for source_path in self.config['backup_paths']:
            if os.path.exists(source_path):
                dest_path = os.path.join(backup_path, os.path.basename(source_path))
                try:
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, dest_path,
                                      ignore=shutil.ignore_patterns(
                                          *self.config['exclude_patterns']
                                      ))
                    else:
                        shutil.copy2(source_path, dest_path)
                    
                    size = self.get_backup_size(source_path)
                    print(f"  ✅ {os.path.basename(source_path)}: {self.format_size(size)}")
                    self.backup_stats['backed_up'] += 1
                except Exception as e:
                    print(f"  ❌ {os.path.basename(source_path)}: {e}")
                    self.backup_stats['failed'] += 1
                    success = False
        
        return success

    def backup_to_google_drive(self, backup_name: str) -> bool:
        """Backup to Google Drive folder"""
        gdrive_config = self.config['providers']['google_drive']
        if not gdrive_config['enabled']:
            return False

        backup_dir = gdrive_config['path']
        if not os.path.exists(backup_dir):
            print(f"⚠️  Google Drive path not found: {backup_dir}")
            return False

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"{backup_name}_{timestamp}")
        
        print(f"\n🔵 Google Drive Backup: {backup_path}")
        
        success = True
        for source_path in self.config['backup_paths']:
            if os.path.exists(source_path):
                dest_path = os.path.join(backup_path, os.path.basename(source_path))
                try:
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, dest_path,
                                      ignore=shutil.ignore_patterns(
                                          *self.config['exclude_patterns']
                                      ))
                    else:
                        shutil.copy2(source_path, dest_path)
                    
                    size = self.get_backup_size(source_path)
                    print(f"  ✅ {os.path.basename(source_path)}: {self.format_size(size)}")
                    self.backup_stats['backed_up'] += 1
                except Exception as e:
                    print(f"  ❌ {os.path.basename(source_path)}: {e}")
                    self.backup_stats['failed'] += 1
                    success = False
        
        return success

    def backup_to_icloud(self, backup_name: str) -> bool:
        """Backup to iCloud Drive"""
        icloud_config = self.config['providers']['icloud']
        if not icloud_config['enabled']:
            return False

        backup_dir = icloud_config['path']
        if not os.path.exists(backup_dir):
            print(f"⚠️  iCloud path not found: {backup_dir}")
            return False

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"{backup_name}_{timestamp}")
        
        print(f"\n☁️  iCloud Backup: {backup_path}")
        
        success = True
        for source_path in self.config['backup_paths']:
            if os.path.exists(source_path):
                dest_path = os.path.join(backup_path, os.path.basename(source_path))
                try:
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, dest_path,
                                      ignore=shutil.ignore_patterns(
                                          *self.config['exclude_patterns']
                                      ))
                    else:
                        shutil.copy2(source_path, dest_path)
                    
                    size = self.get_backup_size(source_path)
                    print(f"  ✅ {os.path.basename(source_path)}: {self.format_size(size)}")
                    self.backup_stats['backed_up'] += 1
                except Exception as e:
                    print(f"  ❌ {os.path.basename(source_path)}: {e}")
                    self.backup_stats['failed'] += 1
                    success = False
        
        return success

    def backup_to_aws_s3(self, backup_name: str) -> bool:
        """Backup to AWS S3 using AWS CLI"""
        s3_config = self.config['providers']['aws_s3']
        if not s3_config['enabled']:
            return False

        if not s3_config['bucket']:
            print("⚠️  AWS S3 bucket not configured")
            return False

        print(f"\n🟢 AWS S3 Backup: s3://{s3_config['bucket']}/{backup_name}")
        
        # Check if AWS CLI is available
        try:
            subprocess.run(['aws', '--version'], 
                         capture_output=True, check=True)
        except Exception:
            print("❌ AWS CLI not installed. Install with: brew install awscli")
            return False

        success = True
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        for source_path in self.config['backup_paths']:
            if os.path.exists(source_path):
                s3_path = f"s3://{s3_config['bucket']}/{backup_name}_{timestamp}/{os.path.basename(source_path)}"
                try:
                    result = subprocess.run(
                        ['aws', 's3', 'sync', source_path, s3_path,
                         '--exclude', '*.tmp', '--exclude', '*.cache',
                         '--exclude', '.DS_Store', '--exclude', 'node_modules'],
                        capture_output=True, text=True
                    )
                    
                    if result.returncode == 0:
                        size = self.get_backup_size(source_path)
                        print(f"  ✅ {os.path.basename(source_path)}: {self.format_size(size)}")
                        self.backup_stats['backed_up'] += 1
                    else:
                        print(f"  ❌ {os.path.basename(source_path)}: {result.stderr}")
                        self.backup_stats['failed'] += 1
                        success = False
                except Exception as e:
                    print(f"  ❌ {os.path.basename(source_path)}: {e}")
                    self.backup_stats['failed'] += 1
                    success = False
        
        return success

    def run_backup(self, backup_name: str = "SuperMegaBot-Backup") -> Dict:
        """Run backup to all enabled providers"""
        print("=" * 60)
        print("🚀 SuperMegaBot Cloud Backup")
        print("=" * 60)
        print(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Backup Name: {backup_name}")
        
        self.backup_stats['start_time'] = datetime.datetime.now()
        
        # Calculate total size
        print("\n📊 Analyzing backup sources...")
        for source_path in self.config['backup_paths']:
            if os.path.exists(source_path):
                size = self.get_backup_size(source_path)
                self.backup_stats['total_size'] += size
                print(f"  {os.path.basename(source_path)}: {self.format_size(size)}")
        
        print(f"\nTotal size to backup: {self.format_size(self.backup_stats['total_size'])}")
        
        # Run backups to enabled providers
        providers = []
        if self.config['providers']['local']['enabled']:
            providers.append('local')
        if self.config['providers']['dropbox']['enabled']:
            providers.append('dropbox')
        if self.config['providers']['google_drive']['enabled']:
            providers.append('google_drive')
        if self.config['providers']['icloud']['enabled']:
            providers.append('icloud')
        if self.config['providers']['aws_s3']['enabled']:
            providers.append('aws_s3')
        
        print(f"\n🔧 Active providers: {', '.join(providers)}")
        
        results = {}
        if 'local' in providers:
            results['local'] = self.backup_to_local(backup_name)
        if 'dropbox' in providers:
            results['dropbox'] = self.backup_to_dropbox(backup_name)
        if 'google_drive' in providers:
            results['google_drive'] = self.backup_to_google_drive(backup_name)
        if 'icloud' in providers:
            results['icloud'] = self.backup_to_icloud(backup_name)
        if 'aws_s3' in providers:
            results['aws_s3'] = self.backup_to_aws_s3(backup_name)
        
        self.backup_stats['end_time'] = datetime.datetime.now()
        duration = self.backup_stats['end_time'] - self.backup_stats['start_time']
        
        print("\n" + "=" * 60)
        print("📋 Backup Summary")
        print("=" * 60)
        print(f"Duration: {duration}")
        print(f"Total size: {self.format_size(self.backup_stats['total_size'])}")
        print(f"Successful: {self.backup_stats['backed_up']}")
        print(f"Failed: {self.backup_stats['failed']}")
        
        for provider, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"{provider.capitalize()}: {status}")
        
        print("=" * 60)
        
        return self.backup_stats

    def list_backups(self) -> List[Dict]:
        """List all available backups"""
        backups = []
        
        # Check local backups
        local_config = self.config['providers']['local']
        if local_config['enabled'] and os.path.exists(local_config['backup_dir']):
            for item in os.listdir(local_config['backup_dir']):
                item_path = os.path.join(local_config['backup_dir'], item)
                if os.path.isdir(item_path):
                    backups.append({
                        'provider': 'local',
                        'name': item,
                        'path': item_path,
                        'size': self.get_backup_size(item_path),
                        'date': datetime.datetime.fromtimestamp(
                            os.path.getmtime(item_path)
                        ).strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        return sorted(backups, key=lambda x: x['date'], reverse=True)

    def restore_backup(self, backup_path: str, restore_path: str) -> bool:
        """Restore backup from specified path"""
        print(f"\n🔄 Restoring backup: {backup_path}")
        print(f"Target: {restore_path}")
        
        try:
            if os.path.isdir(backup_path):
                if os.path.exists(restore_path):
                    shutil.rmtree(restore_path)
                shutil.copytree(backup_path, restore_path)
                print("✅ Backup restored successfully")
                return True
            else:
                print("❌ Backup path not found")
                return False
        except Exception as e:
            print(f"❌ Restore failed: {e}")
            return False

    def cleanup_old_backups(self, keep_days: int = 30) -> int:
        """Remove backups older than specified days"""
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=keep_days)
        removed_count = 0
        
        local_config = self.config['providers']['local']
        if local_config['enabled'] and os.path.exists(local_config['backup_dir']):
            for item in os.listdir(local_config['backup_dir']):
                item_path = os.path.join(local_config['backup_dir'], item)
                if os.path.isdir(item_path):
                    item_date = datetime.datetime.fromtimestamp(
                        os.path.getmtime(item_path)
                    )
                    if item_date < cutoff_date:
                        try:
                            shutil.rmtree(item_path)
                            print(f"🗑️  Removed old backup: {item}")
                            removed_count += 1
                        except Exception as e:
                            print(f"❌ Failed to remove {item}: {e}")
        
        print(f"\nCleanup complete. Removed {removed_count} old backups.")
        return removed_count

def main():
    parser = argparse.ArgumentParser(description='SuperMegaBot Cloud Backup')
    parser.add_argument('--backup', '-b', action='store_true', 
                       help='Run backup')
    parser.add_argument('--name', '-n', default='SuperMegaBot-Backup',
                       help='Backup name')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available backups')
    parser.add_argument('--restore', '-r', metavar='BACKUP_PATH',
                       help='Restore from backup path')
    parser.add_argument('--restore-to', metavar='DEST_PATH',
                       help='Destination path for restore')
    parser.add_argument('--cleanup', '-c', type=int, default=30,
                       help='Cleanup backups older than N days')
    parser.add_argument('--config', metavar='CONFIG_PATH',
                       help='Custom config file path')
    parser.add_argument('--stats', '-s', action='store_true',
                       help='Show backup statistics')
    
    args = parser.parse_args()
    
    backup = CloudBackup(args.config)
    
    if args.backup:
        backup.run_backup(args.name)
    elif args.list:
        backups = backup.list_backups()
        print("\n📋 Available Backups:")
        print("=" * 60)
        for b in backups:
            print(f"{b['date']} | {b['provider']} | {b['name']} | {backup.format_size(b['size'])}")
    elif args.restore:
        restore_path = args.restore_to or os.path.expanduser('~/Desktop/Restored-Backup')
        backup.restore_backup(args.restore, restore_path)
    elif args.cleanup:
        backup.cleanup_old_backups(args.cleanup)
    elif args.stats:
        print("\n📊 Backup Configuration:")
        print("=" * 60)
        print(f"Backup paths: {len(backup.config['backup_paths'])}")
        print(f"Exclude patterns: {len(backup.config['exclude_patterns'])}")
        print(f"Compression: {'Enabled' if backup.config['compression']['enabled'] else 'Disabled'}")
        print(f"Encryption: {'Enabled' if backup.config['encryption']['enabled'] else 'Disabled'}")
        print(f"Scheduling: {'Enabled' if backup.config['scheduling']['enabled'] else 'Disabled'}")
        print("\nProviders:")
        for provider, config in backup.config['providers'].items():
            status = "✅" if config.get('enabled') else "❌"
            print(f"  {status} {provider}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
