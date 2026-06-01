#!/usr/bin/env python3
"""
Zentrale API Bridge für SuperMegaBot System
Python Bridge für die zentrale API-Konfiguration
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

class CentralAPIBridge:
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            # Automatisch den config Ordner finden
            self.base_dir = Path(__file__).parent.parent
            self.config_dir = self.base_dir / "config"
        else:
            self.config_dir = Path(config_dir)
            
        self.config = {
            'gcp': None,
            'external': {},
            'agent': None,
            'loaded': False,
            'last_updated': None
        }
        
        self.config_paths = {
            'gcp': self.base_dir / "RudiBot-Secure-API" / "gcp-config.json",
            'external': self.base_dir / "api-config.json",
            'agent': self.base_dir / "agent-configs.json"
        }
    
    def load_all_configs(self) -> Dict[str, Any]:
        """Lädt alle Konfigurationen"""
        try:
            # GCP Konfiguration laden
            gcp_path = self.config_paths['gcp']
            if gcp_path.exists():
                with open(gcp_path, 'r', encoding='utf-8') as f:
                    self.config['gcp'] = json.load(f)
                print("✅ GCP Konfiguration geladen")
            
            # Externe API Konfiguration laden
            external_path = self.config_paths['external']
            if external_path.exists():
                with open(external_path, 'r', encoding='utf-8') as f:
                    self.config['external'] = json.load(f)
                print("✅ Externe API Konfiguration geladen")
            
            # Agent Konfiguration laden
            agent_path = self.config_paths['agent']
            if agent_path.exists():
                with open(agent_path, 'r', encoding='utf-8') as f:
                    self.config['agent'] = json.load(f)
                print("✅ Agent Konfiguration geladen")
            
            self.config['loaded'] = True
            self.config['last_updated'] = datetime.now().isoformat()
            
            print(f"🔧 Zentrale API-Konfiguration aktualisiert: {self.config['last_updated']}")
            return self.config
            
        except Exception as error:
            print(f"❌ Fehler beim Laden der Konfiguration: {error}")
            raise
    
    def get_project_id(self) -> Optional[str]:
        """Gibt GCP Projekt-ID zurück"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        # Aus RudiBot-Secure-API
        if self.config['gcp'] and 'project' in self.config['gcp']:
            return self.config['gcp']['project'].get('id')
        
        # Aus api-config.json
        if self.config['external'] and 'gcp' in self.config['external']:
            return self.config['external']['gcp'].get('projectId')
        
        return None
    
    def get_enabled_gcp_apis(self) -> List[str]:
        """Gibt alle aktivierten GCP APIs zurück"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        # Aus RudiBot-Secure-API Konfiguration
        if self.config['gcp'] and 'apis' in self.config['gcp']:
            apis = self.config['gcp']['apis'].get('enabled', [])
            return [api['name'] for api in apis] if isinstance(apis, list) and apis and isinstance(apis[0], dict) else apis
        
        # Aus api-config.json
        if self.config['external'] and 'gcp' in self.config['external']:
            gcp_config = self.config['external']['gcp']
            if 'apis' in gcp_config:
                return gcp_config['apis'].get('enabled', [])
        
        return []
    
    def get_external_api(self, service: str) -> Optional[Dict[str, Any]]:
        """Gibt externe API Konfiguration zurück"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        return self.config['external'].get(service)
    
    def is_api_available(self, service: str) -> bool:
        """Prüft ob eine API verfügbar ist"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        # GCP APIs
        if '.googleapis.com' in service:
            return service in self.get_enabled_gcp_apis()
        
        # Externe APIs
        return service in self.config['external']
    
    def get_billing_info(self) -> Dict[str, Any]:
        """Gibt Billing-Informationen zurück"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        # Aus RudiBot-Secure-API
        if self.config['gcp'] and 'project' in self.config['gcp']:
            project = self.config['gcp']['project']
            return {
                'account': project.get('billing_account'),
                'account_name': project.get('billing_account_name', 'Mein Rechnungskonto'),
                'required_apis': self.config['gcp'].get('apis', {}).get('billing_required', [])
            }
        
        # Aus api-config.json
        if self.config['external'] and 'gcp' in self.config['external']:
            gcp_config = self.config['external']['gcp']
            return {
                'account': gcp_config.get('billingAccount'),
                'account_name': 'Mein Rechnungskonto',
                'required_apis': gcp_config.get('apis', {}).get('billingRequired', [])
            }
        
        return {}
    
    def get_auth_method(self) -> str:
        """Gibt Auth-Methode zurück"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        # Aus RudiBot-Secure-API
        if self.config['gcp'] and 'auth' in self.config['gcp']:
            return self.config['gcp']['auth'].get('method', 'gcloud')
        
        # Aus api-config.json
        if self.config['external'] and 'gcp' in self.config['external']:
            return self.config['external']['gcp'].get('authMethod', 'gcloud')
        
        return 'gcloud'
    
    def create_client_config(self, service: str) -> Dict[str, Any]:
        """Erstellt API Client Konfiguration"""
        config = self.get_external_api(service)
        if not config:
            raise ValueError(f"API Konfiguration für {service} nicht gefunden")
        
        return {
            'base_url': config.get('baseUrl'),
            'headers': {
                'Authorization': f"Bearer {config.get('apiKey')}",
                'Content-Type': 'application/json'
            },
            'timeout': 30000,
            'retries': 3
        }
    
    def validate_config(self) -> Dict[str, Any]:
        """Validiert Konfiguration"""
        errors = []
        
        if not self.config['loaded']:
            errors.append('Konfiguration nicht geladen')
        
        if not self.get_project_id():
            errors.append('Keine GCP Projekt-ID gefunden')
        
        if len(self.get_enabled_gcp_apis()) == 0:
            errors.append('Keine GCP APIs aktiviert')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt Konfigurations-Status zurück"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        return {
            'loaded': self.config['loaded'],
            'last_updated': self.config['last_updated'],
            'project_id': self.get_project_id(),
            'enabled_apis': len(self.get_enabled_gcp_apis()),
            'external_apis': len(self.config['external']),
            'auth_method': self.get_auth_method(),
            'billing': self.get_billing_info()
        }
    
    def export_config(self, output_path: str = None) -> str:
        """Exportiert die gesamte Konfiguration"""
        if not self.config['loaded']:
            self.load_all_configs()
        
        export_data = {
            'metadata': {
                'exported_at': datetime.now().isoformat(),
                'version': '1.0.0',
                'source': 'CentralAPIBridge'
            },
            'status': self.get_status(),
            'config': self.config
        }
        
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            print(f"📁 Konfiguration exportiert nach: {output_path}")
            return str(output_file)
        
        return json.dumps(export_data, indent=2, ensure_ascii=False)

# Singleton Instanz
central_bridge = CentralAPIBridge()

# Automatisch laden beim ersten Import
if __name__ != "__main__":
    central_bridge.load_all_configs()

if __name__ == "__main__":
    # CLI Interface
    import argparse
    
    parser = argparse.ArgumentParser(description='Zentrale API Bridge für SuperMegaBot')
    parser.add_argument('--status', action='store_true', help='Zeigt Status an')
    parser.add_argument('--project-id', action='store_true', help='Zeigt Projekt-ID an')
    parser.add_argument('--apis', action='store_true', help='Zeigt aktivierte APIs an')
    parser.add_argument('--validate', action='store_true', help='Validiert Konfiguration')
    parser.add_argument('--export', help='Exportiert Konfiguration zu Datei')
    
    args = parser.parse_args()
    
    if args.status:
        status = central_bridge.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    
    elif args.project_id:
        project_id = central_bridge.get_project_id()
        print(f"Project ID: {project_id}")
    
    elif args.apis:
        apis = central_bridge.get_enabled_gcp_apis()
        print("Aktivierte GCP APIs:")
        for api in apis:
            print(f"  - {api}")
    
    elif args.validate:
        validation = central_bridge.validate_config()
        if validation['valid']:
            print("✅ Konfiguration ist gültig")
        else:
            print("❌ Konfiguration hat Fehler:")
            for error in validation['errors']:
                print(f"  - {error}")
    
    elif args.export:
        output_path = central_bridge.export_config(args.export)
        print(f"Exportiert nach: {output_path}")
    
    else:
        # Standard: Status anzeigen
        central_bridge.load_all_configs()
        status = central_bridge.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
