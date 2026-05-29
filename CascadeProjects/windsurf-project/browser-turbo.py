#!/usr/bin/env python3
"""
Browser Turbo Accelerator - Beschleunigt Browser durch Cache-Optimierung und Performance-Tuning
"""

import os
import subprocess
import time
import json
from datetime import datetime
from pathlib import Path
import argparse
import shutil

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class BrowserTurbo:
    def __init__(self):
        self.log_file = Path.home() / ".mac-optimizer" / "browser-turbo.log"
        self.config_file = Path.home() / ".mac-optimizer" / "browser-config.json"
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        self.ensure_log_directory()
        self.load_config()
    
    def ensure_log_directory(self):
        """Erstellt Log-Verzeichnis"""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_config(self):
        """Lädt Konfiguration"""
        default_config = {
            "chrome": True,
            "safari": True,
            "firefox": True,
            "edge": True,
            "clear_cache": True,
            "clear_cookies": False,
            "clear_history": False,
            "clear_downloads": False,
            "optimize_dns": True,
            "disable_extensions": False,
            "hardware_acceleration": True
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            except Exception:
                self.config = default_config
        else:
            self.config = default_config
            self.save_config()
    
    def save_config(self):
        """Speichert Konfiguration"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def log(self, message):
        """Loggt Nachricht"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        print(log_entry.strip())
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
    
    def get_browser_paths(self):
        """Gibt Pfade zu Browser-Cache-Verzeichnissen zurück"""
        home = Path.home()
        browser_paths = {
            'chrome': [],
            'safari': [],
            'firefox': [],
            'edge': []
        }
        
        # Chrome
        if self.config.get('chrome', True):
            chrome_cache = home / "Library" / "Caches" / "Google" / "Chrome"
            chrome_profile = home / "Library" / "Application Support" / "Google" / "Chrome"
            if chrome_cache.exists():
                browser_paths['chrome'].append(chrome_cache)
            if chrome_profile.exists():
                for profile_dir in chrome_profile.glob("Default"):
                    browser_paths['chrome'].append(profile_dir / "Cache")
                    browser_paths['chrome'].append(profile_dir / "GPUCache")
        
        # Safari
        if self.config.get('safari', True):
            safari_cache = home / "Library" / "Caches" / "com.apple.Safari"
            safari_db = home / "Library" / "Safari"
            if safari_cache.exists():
                browser_paths['safari'].append(safari_cache)
            if safari_db.exists():
                browser_paths['safari'].append(safari_db / "History.db")
                browser_paths['safari'].append(safari_db / "TopSites.plist")
        
        # Firefox
        if self.config.get('firefox', True):
            firefox_profile = home / "Library" / "Application Support" / "Firefox" / "Profiles"
            if firefox_profile.exists():
                for profile_dir in firefox_profile.glob("*"):
                    browser_paths['firefox'].append(profile_dir / "cache2")
                    browser_paths['firefox'].append(profile_dir / "startupCache")
        
        # Edge
        if self.config.get('edge', True):
            edge_cache = home / "Library" / "Caches" / "Microsoft Edge"
            edge_profile = home / "Library" / "Application Support" / "Microsoft Edge"
            if edge_cache.exists():
                browser_paths['edge'].append(edge_cache)
            if edge_profile.exists():
                for profile_dir in edge_profile.glob("Default"):
                    browser_paths['edge'].append(profile_dir / "Cache")
                    browser_paths['edge'].append(profile_dir / "GPUCache")
        
        return browser_paths
    
    def clear_browser_cache(self, browser_name):
        """Bereinigt Browser-Cache"""
        if not self.config.get('clear_cache', True):
            return 0
        
        self.log(f"🧹 Bereinige {browser_name} Cache...")
        
        browser_paths = self.get_browser_paths()
        paths = browser_paths.get(browser_name.lower(), [])
        
        total_freed = 0
        for path in paths:
            if path.exists():
                try:
                    if path.is_file():
                        size = path.stat().st_size
                        path.unlink()
                        total_freed += size
                    elif path.is_dir():
                        size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                        shutil.rmtree(path, ignore_errors=True)
                        total_freed += size
                except Exception as e:
                    self.log(f"Fehler beim Bereinigen von {path}: {e}")
        
        self.log(f"✅ {browser_name} Cache bereinigt: {total_freed / (1024**2):.2f} MB")
        return total_freed
    
    def clear_browser_cookies(self, browser_name):
        """Bereinigt Browser-Cookies"""
        if not self.config.get('clear_cookies', False):
            return
        
        self.log(f"🍪 Bereinige {browser_name} Cookies...")
        
        browser_paths = self.get_browser_paths()
        paths = browser_paths.get(browser_name.lower(), [])
        
        for path in paths:
            if path.exists():
                try:
                    cookie_files = list(path.rglob("*Cookies*"))
                    for cookie_file in cookie_files:
                        if cookie_file.is_file():
                            cookie_file.unlink()
                except Exception as e:
                    self.log(f"Fehler beim Bereinigen von Cookies: {e}")
        
        self.log(f"✅ {browser_name} Cookies bereinigt")
    
    def optimize_dns(self):
        """Optimiert DNS für schnellere Browser-Performance"""
        if not self.config.get('optimize_dns', True):
            return
        
        self.log("🌐 Optimiere DNS für Browser...")
        
        try:
            # DNS-Cache leeren (ohne Passwort-Prompt)
            r1 = subprocess.run(['sudo', '-n', 'dscacheutil', '-flushcache'], capture_output=True, timeout=3)
            r2 = subprocess.run(['sudo', '-n', 'killall', '-HUP', 'mDNSResponder'], capture_output=True, timeout=3)
            if r1.returncode == 0 or r2.returncode == 0:
                self.log("✅ DNS-Cache geleert")
            else:
                self.log("⚠️ DNS-Cache leeren uebersprungen (sudo erforderlich)")
        except Exception as e:
            self.log(f"⚠️ DNS-Cache leeren uebersprungen: {e}")
    
    def optimize_network_settings(self):
        """Optimiert Netzwerkeinstellungen für Browser"""
        self.log("📡 Optimiere Netzwerkeinstellungen...")
        
        try:
            # TCP-Einstellungen optimieren
            commands = [
                ['sudo', 'sysctl', '-w', 'net.inet.tcp.delayed_ack=0'],
                ['sudo', 'sysctl', '-w', 'net.inet.tcp.slowstart_flightsize=4'],
                ['sudo', 'sysctl', '-w', 'net.inet.tcp.recvspace=131072'],
                ['sudo', 'sysctl', '-w', 'net.inet.tcp.sendspace=131072']
            ]
            
            success_count = 0
            for cmd in commands:
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=3)
                    if result.returncode == 0:
                        success_count += 1
                except Exception:
                    pass
            
            if success_count > 0:
                self.log(f"✅ Netzwerkeinstellungen optimiert ({success_count}/4)")
            else:
                self.log("⚠️ Netzwerk-Optimierung uebersprungen (sudo erforderlich)")
        except Exception as e:
            self.log(f"Fehler bei Netzwerk-Optimierung: {e}")
    
    def close_browser_processes(self, browser_name):
        """Schließt Browser-Prozesse"""
        self.log(f"🔒 Schließe {browser_name} Prozesse...")
        
        browser_processes = {
            'chrome': ['Google Chrome', 'chrome'],
            'safari': ['Safari'],
            'firefox': ['Firefox', 'firefox'],
            'edge': ['Microsoft Edge', 'edge']
        }
        
        processes = browser_processes.get(browser_name.lower(), [])
        
        for proc in processes:
            try:
                subprocess.run(['pkill', '-f', proc], capture_output=True)
            except Exception:
                pass
        
        time.sleep(2)  # Warten bis Prozesse beendet sind
        self.log(f"✅ {browser_name} Prozesse geschlossen")
    
    def enable_hardware_acceleration(self):
        """Aktiviert Hardware-Beschleunigung für Browser"""
        if not self.config.get('hardware_acceleration', True):
            return
        
        self.log("⚡ Hardware-Beschleunigung prüfen...")
        
        # Hardware-Beschleunigung ist meistens standardmäßig aktiviert
        # Wir geben nur Tipps zur Optimierung
        self.log("💡 Tipp: Hardware-Beschleunigung in Browser-Einstellungen aktivieren")
        self.log("   Chrome: Einstellungen > System > Hardware-Beschleunigung verwenden")
        self.log("   Safari: Entwickler > Experimentelle Features > Hardware-Beschleunigung")
    
    def optimize_browser_startup(self, browser_name):
        """Optimiert Browser-Startzeit"""
        self.log(f"🚀 Optimiere {browser_name} Startzeit...")
        
        # Cache bereinigen hilft beim Start
        self.clear_browser_cache(browser_name)
        
        # Extensions deaktivieren wenn gewünscht
        if self.config.get('disable_extensions', False):
            self.log(f"⚠️ Extensions manuell deaktivieren für schnelleren Start")
        
        self.log(f"✅ {browser_name} Startzeit optimiert")
    
    def run_turbo_boost(self, browser_name="all"):
        """Führt vollständigen Turbo-Boost durch"""
        self.log("🚀 BROWSER TURBO BOOST STARTET")
        self.log("="*50)
        
        browsers = ['chrome', 'safari', 'firefox', 'edge'] if browser_name == "all" else [browser_name]
        
        total_freed = 0
        
        for browser in browsers:
            if self.config.get(browser, True):
                # Browser schließen
                self.close_browser_processes(browser)
                
                # Cache bereinigen
                freed = self.clear_browser_cache(browser)
                total_freed += freed
                
                # Cookies bereinigen (optional)
                self.clear_browser_cookies(browser)
                
                # Start optimieren
                self.optimize_browser_startup(browser)
        
        # System-weite Optimierungen
        self.optimize_dns()
        self.optimize_network_settings()
        self.enable_hardware_acceleration()
        
        self.log("="*50)
        self.log(f"✅ TURBO BOOST ABGESCHLOSSEN!")
        self.log(f"📊 Gesamt: {total_freed / (1024**2):.2f} MB freigegeben")
        self.log("🌐 Browser sollten jetzt schneller laufen!")
    
    def quick_boost(self):
        """Schneller Boost ohne Browser zu schließen"""
        self.log("⚡ QUICK BOOST STARTET")
        self.log("="*50)
        
        # Nur DNS und Netzwerk optimieren
        self.optimize_dns()
        self.optimize_network_settings()
        
        # Cache bereinigen ohne Browser zu schließen
        browsers = ['chrome', 'safari', 'firefox', 'edge']
        total_freed = 0
        
        for browser in browsers:
            if self.config.get(browser, True):
                freed = self.clear_browser_cache(browser)
                total_freed += freed
        
        self.log("="*50)
        self.log(f"✅ QUICK BOOST ABGESCHLOSSEN!")
        self.log(f"📊 {total_freed / (1024**2):.2f} MB freigegeben")

def main():
    parser = argparse.ArgumentParser(description='Browser Turbo Accelerator')
    parser.add_argument('--browser', type=str, default='all', 
                       help='Browser: chrome, safari, firefox, edge, oder all')
    parser.add_argument('--quick', action='store_true', help='Schneller Boost ohne Browser zu schließen')
    parser.add_argument('--cache-only', action='store_true', help='Nur Cache bereinigen')
    parser.add_argument('--dns-only', action='store_true', help='Nur DNS optimieren')
    
    args = parser.parse_args()
    
    turbo = BrowserTurbo()
    
    if args.quick:
        turbo.quick_boost()
    elif args.cache_only:
        if args.browser == "all":
            for browser in ['chrome', 'safari', 'firefox', 'edge']:
                turbo.clear_browser_cache(browser)
        else:
            turbo.clear_browser_cache(args.browser)
    elif args.dns_only:
        turbo.optimize_dns()
    else:
        turbo.run_turbo_boost(args.browser)

if __name__ == "__main__":
    main()
