#!/usr/bin/env python3
"""
API Integration Helper für SuperMegaBot Tools
Ermöglicht jedem Tool einfachen Zugriff auf zentrale API-Konfiguration
"""

import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import sys

# Zentrale API Bridge importieren
sys.path.insert(0, str(Path(__file__).parent))
from api_bridge import CentralAPIBridge

class APIHelper:
    def __init__(self, tool_name: str = "unknown-tool"):
        self.tool_name = tool_name
        self.bridge = CentralAPIBridge()
        self.cache = {}
        self.last_cache_update = None
        self.cache_ttl = 300  # 5 Minuten
    
    def is_api_available(self, service: str) -> bool:
        """Prüft ob eine API verfügbar ist"""
        try:
            return self.bridge.is_api_available(service)
        except Exception as error:
            print(f"⚠️  API-Check fehlgeschlagen für {service}: {error}")
            return False
    
    def get_api_config(self, service: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Gibt API-Konfiguration zurück mit Caching"""
        cache_key = f"{service}_config"
        
        # Cache prüfen
        if (use_cache and 
            cache_key in self.cache and 
            time.time() - self.cache[cache_key]["timestamp"] < self.cache_ttl):
            return self.cache[cache_key]["data"]
        
        try:
            config = self.bridge.get_external_api(service)
            if config:
                # Cache aktualisieren
                self.cache[cache_key] = {
                    "data": config,
                    "timestamp": time.time()
                }
                return config
        except Exception as error:
            print(f"⚠️  Konfiguration nicht gefunden für {service}: {error}")
        
        return None
    
    def create_api_client(self, service: str, custom_options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Erstellt HTTP-Client für eine API"""
        config = self.get_api_config(service)
        if not config:
            raise ValueError(f"API-Konfiguration für {service} nicht verfügbar")
        
        default_options = {
            "base_url": config.get("baseUrl"),
            "headers": {
                "Authorization": f"Bearer {config.get('apiKey')}",
                "Content-Type": "application/json",
                "User-Agent": f"{self.tool_name}/1.0.0"
            },
            "timeout": 30,
            "retries": 3
        }
        
        if custom_options:
            default_options.update(custom_options)
        
        return {
            **default_options,
            "service": service,
            "config": config,
            "is_available": lambda: self.is_api_available(service)
        }
    
    def get_available_apis(self) -> Dict[str, Any]:
        """Gibt alle verfügbaren APIs zurück"""
        try:
            status = self.bridge.get_status()
            return {
                "gcp": self.bridge.get_enabled_gcp_apis(),
                "external": list(self.bridge.config.get("external", {}).keys()),
                "total": len(self.bridge.get_enabled_gcp_apis()) + len(self.bridge.config.get("external", {}))
            }
        except Exception as error:
            print(f"⚠️  API-Liste konnte nicht geladen werden: {error}")
            return {"gcp": [], "external": [], "total": 0}
    
    def check_required_apis(self, required_apis: List[str]) -> Dict[str, Any]:
        """Prüft ob alle benötigten APIs für ein Tool verfügbar sind"""
        results = {
            "available": [],
            "missing": [],
            "total": len(required_apis)
        }
        
        for api in required_apis:
            if self.is_api_available(api):
                results["available"].append(api)
            else:
                results["missing"].append(api)
        
        results["ready"] = len(results["missing"]) == 0
        results["percentage"] = int((len(results["available"]) / results["total"]) * 100)
        
        return results
    
    def log_api_usage(self, service: str, operation: str, success: bool = True, error: Exception = None):
        """Loggt API-Nutzung für Monitoring"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": self.tool_name,
            "service": service,
            "operation": operation,
            "success": success,
            "error": str(error) if error else None
        }
        
        # In Production: Logging Service oder Datei
        status = "✅" if success else "❌"
        print(f"🔗 API Usage: {self.tool_name} → {service} → {operation} ({status})")
        
        if not success and error:
            print(f"   Error: {error}")
        
        return log_entry
    
    async def execute_api_call(self, service: str, operation: str, api_call: Callable, 
                              retries: int = 3, timeout: int = 30) -> Dict[str, Any]:
        """Führt API-Aufruf mit automatischem Retry und Logging aus"""
        last_error = None
        
        # API-Verfügbarkeit prüfen
        if not self.is_api_available(service):
            error = ValueError(f"API {service} ist nicht verfügbar")
            self.log_api_usage(service, operation, False, error)
            raise error
        
        # Retry-Logik
        for attempt in range(1, retries + 1):
            try:
                start_time = time.time()
                
                # Timeout mit asyncio
                result = await asyncio.wait_for(
                    api_call(),
                    timeout=timeout
                )
                
                duration = time.time() - start_time
                self.log_api_usage(service, operation, True)
                
                return {
                    "success": True,
                    "data": result,
                    "duration": duration,
                    "attempts": attempt
                }
                
            except Exception as error:
                last_error = error
                print(f"🔄 API Retry {attempt}/{retries} für {service}: {error}")
                
                if attempt < retries:
                    # Exponential Backoff
                    await asyncio.sleep(2 ** attempt)
        
        # Alle Retries fehlgeschlagen
        self.log_api_usage(service, operation, False, last_error)
        raise last_error
    
    def get_project_info(self) -> Optional[Dict[str, Any]]:
        """Gibt Projekt-Informationen zurück"""
        try:
            return {
                "project_id": self.bridge.get_project_id(),
                "auth_method": self.bridge.get_auth_method(),
                "billing": self.bridge.get_billing_info()
            }
        except Exception as error:
            print(f"⚠️  Projekt-Info konnte nicht geladen werden: {error}")
            return None
    
    @classmethod
    def for_tool(cls, tool_name: str):
        """Erstellt API-Helper für ein spezifisches Tool"""
        return cls(tool_name)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Gibt System-Status zurück"""
        try:
            status = self.bridge.get_status()
            apis = self.get_available_apis()
            
            return {
                "tool": self.tool_name,
                "system": {
                    "loaded": status["loaded"],
                    "last_updated": status["last_updated"],
                    "project_id": status["project_id"]
                },
                "apis": apis,
                "cache": {
                    "entries": len(self.cache),
                    "last_update": self.last_cache_update
                }
            }
        except Exception as error:
            return {
                "tool": self.tool_name,
                "error": str(error),
                "status": "error"
            }
    
    def clear_cache(self):
        """Cache leeren"""
        self.cache.clear()
        self.last_cache_update = time.time()

# Quick-Access Funktionen
def create_helper(tool_name: str) -> APIHelper:
    """Erstellt neuen API Helper"""
    return APIHelper(tool_name)

def is_available(service: str) -> bool:
    """Prüft API-Verfügbarkeit"""
    return APIHelper().is_api_available(service)

def get_config(service: str) -> Optional[Dict[str, Any]]:
    """Gibt API-Konfiguration zurück"""
    return APIHelper().get_api_config(service)

def create_client(service: str, tool_name: str = "default-tool") -> Dict[str, Any]:
    """Erstellt API Client"""
    return APIHelper(tool_name).create_api_client(service)

def check_apis(required_apis: List[str], tool_name: str = "default-tool") -> Dict[str, Any]:
    """Prüft mehrere APIs"""
    return APIHelper(tool_name).check_required_apis(required_apis)

async def execute_call(service: str, operation: str, api_call: Callable, 
                      tool_name: str = "default-tool") -> Dict[str, Any]:
    """Führt API-Aufruf aus"""
    return await APIHelper(tool_name).execute_api_call(service, operation, api_call)

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='API Helper für SuperMegaBot Tools')
    parser.add_argument('--tool', default='cli-tool', help='Tool Name')
    parser.add_argument('--check', help='Prüft spezifische API (Komma getrennt)')
    parser.add_argument('--list', action='store_true', help='Listet alle verfügbaren APIs')
    parser.add_argument('--status', action='store_true', help='Zeigt System-Status')
    parser.add_argument('--project', action='store_true', help='Zeigt Projekt-Info')
    
    args = parser.parse_args()
    
    helper = APIHelper(args.tool)
    
    if args.list:
        apis = helper.get_available_apis()
        print(f"Verfügbare APIs ({apis['total']} total):")
        print(f"  GCP: {len(apis['gcp'])} APIs")
        for api in apis['gcp']:
            print(f"    - {api}")
        print(f"  External: {len(apis['external'])} APIs")
        for api in apis['external']:
            print(f"    - {api}")
    
    elif args.check:
        required_apis = [api.strip() for api in args.check.split(',')]
        result = helper.check_required_apis(required_apis)
        print(f"API-Check für {args.tool}:")
        print(f"  Verfügbar: {len(result['available'])}/{result['total']} ({result['percentage']}%)")
        if result['missing']:
            print(f"  Fehlend: {', '.join(result['missing'])}")
        print(f"  Status: {'✅ Ready' if result['ready'] else '❌ Missing APIs'}")
    
    elif args.status:
        status = helper.get_system_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    
    elif args.project:
        project = helper.get_project_info()
        if project:
            print(json.dumps(project, indent=2, ensure_ascii=False))
        else:
            print("❌ Projekt-Info nicht verfügbar")
    
    else:
        print("API Helper für SuperMegaBot Tools")
        print("Verwende --help für verfügbare Optionen")
