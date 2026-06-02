#!/usr/bin/env python3
"""
🤖 Guardian API Client
Wiederverwendbarer Client für alle Tools
"""

import json
import hashlib
import requests
import os
from typing import Optional, Dict, Any, List
from pathlib import Path

def _load_env_secret():
    """Lade GUARDIAN_API_SECRET aus .env Dateien"""
    env_paths = [
        '/Users/rudolfsarkany/rudibot-eternal/.env',
        './.env',
        '../.env',
        '../../.env',
    ]
    for env_path in env_paths:
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    if 'GUARDIAN_API_SECRET=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            secret = parts[1].strip()
                            if '#' in secret:
                                secret = secret.split('#')[0].strip()
                            return secret
        except:
            pass
    return None

class GuardianClient:
    """Client für Guardian REST API"""
    
    def __init__(self, secret_key: str = None, 
                 base_url: str = "http://localhost:3201"):
        # Secret aus Parameter, Umgebung oder .env laden
        if secret_key is None:
            secret_key = os.getenv('GUARDIAN_API_SECRET', '')
        if not secret_key:
            secret_key = _load_env_secret()
        if not secret_key:
            raise ValueError(
                "GUARDIAN_API_SECRET nicht gesetzt!\n"
                "Lösungen:\n"
                "1. export GUARDIAN_API_SECRET='dein-secret'\n"
                "2. Oder .env Datei erstellen mit GUARDIAN_API_SECRET=...\n"
                "3. Oder GuardianClient(secret_key='...') verwenden"
            )
        
        self.base_url = base_url.rstrip('/')
        self.api_key = hashlib.sha256(secret_key.encode()).hexdigest()[:32]
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def _request(self, method: str, endpoint: str, 
                 data: Optional[Dict] = None, 
                 auth: bool = True) -> Dict[str, Any]:
        """Generic API Request"""
        url = f"{self.base_url}{endpoint}"
        headers = self.headers if auth else {}
        
        try:
            if method == 'GET':
                resp = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                resp = requests.post(url, headers=headers, 
                                   json=data, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            return {'error': str(e), 'endpoint': endpoint}
    
    # ═══════════════════════════════════════════════════════════════════
    # STATUS & HEALTH
    # ═══════════════════════════════════════════════════════════════════
    
    def health(self) -> Dict[str, Any]:
        """Health check (no auth required)"""
        return self._request('GET', '/api/v1/health', auth=False)
    
    def status(self) -> Dict[str, Any]:
        """Full system status"""
        return self._request('GET', '/api/v1/status')
    
    def services(self) -> List[Dict[str, Any]]:
        """List all services"""
        result = self._request('GET', '/api/v1/services')
        return result.get('services', [])
    
    def service_status(self, service_name: str) -> Dict[str, Any]:
        """Get specific service status"""
        return self._request('GET', f'/api/v1/services/{service_name}/status')
    
    # ═══════════════════════════════════════════════════════════════════
    # REMOTE CONTROL
    # ═══════════════════════════════════════════════════════════════════
    
    def start_service(self, service_name: str) -> Dict[str, Any]:
        """Start a service"""
        return self._request('POST', f'/api/v1/services/{service_name}/start')
    
    def stop_service(self, service_name: str) -> Dict[str, Any]:
        """Stop a service"""
        return self._request('POST', f'/api/v1/services/{service_name}/stop')
    
    def restart_service(self, service_name: str) -> Dict[str, Any]:
        """Restart a service"""
        return self._request('POST', f'/api/v1/services/{service_name}/restart')
    
    def heal_service(self, service_name: str) -> Dict[str, Any]:
        """Heal a service with full repair process"""
        return self._request('POST', f'/api/v1/services/{service_name}/heal')
    
    # ═══════════════════════════════════════════════════════════════════
    # BRAIN API
    # ═══════════════════════════════════════════════════════════════════
    
    def brain_summary(self) -> Dict[str, Any]:
        """Get brain summary"""
        return self._request('GET', '/api/v1/brain')
    
    def brain_fixes(self) -> Dict[str, Any]:
        """Get all learned fixes"""
        return self._request('GET', '/api/v1/brain/fixes')
    
    def brain_patterns(self) -> Dict[str, Any]:
        """Get error patterns"""
        return self._request('GET', '/api/v1/brain/patterns')
    
    def add_fix(self, error_key: str, fix: str, 
                service: str = "manual", success: bool = True) -> Dict[str, Any]:
        """Add a new fix to brain"""
        return self._request('POST', '/api/v1/brain/fixes', {
            'error_key': error_key,
            'service': service,
            'fix': fix,
            'success': success
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # AGENTS
    # ═══════════════════════════════════════════════════════════════════
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """List registered agents"""
        result = self._request('GET', '/api/v1/agents')
        return result.get('agents', [])
    
    def register_agent(self, agent_id: str, agent_type: str = "monitoring",
                       endpoint: str = "") -> Dict[str, Any]:
        """Register a new agent"""
        return self._request('POST', '/api/v1/agents/register', {
            'agent_id': agent_id,
            'type': agent_type,
            'endpoint': endpoint
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # BACKUP & REPORTS
    # ═══════════════════════════════════════════════════════════════════
    
    def trigger_backup(self) -> Dict[str, Any]:
        """Trigger manual backup"""
        return self._request('POST', '/api/v1/backup')
    
    def get_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get daily reports"""
        result = self._request('GET', f'/api/v1/reports?limit={limit}')
        return result.get('reports', [])
    
    def get_latest_report(self) -> Dict[str, Any]:
        """Get latest report"""
        return self._request('GET', '/api/v1/reports/latest')
    
    # ═══════════════════════════════════════════════════════════════════
    # NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════════
    
    def notify(self, message: str, priority: str = "normal",
               channels: List[str] = None) -> Dict[str, Any]:
        """Send notification to all channels"""
        if channels is None:
            channels = ['all']
        return self._request('POST', '/api/v1/notify', {
            'message': message,
            'priority': priority,
            'channels': channels
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # METRICS
    # ═══════════════════════════════════════════════════════════════════
    
    def metrics(self) -> str:
        """Get Prometheus metrics"""
        url = f"{self.base_url}/metrics"
        try:
            resp = requests.get(url, timeout=10)
            return resp.text
        except requests.exceptions.RequestException as e:
            return f"# Error: {e}"
    
    # ═══════════════════════════════════════════════════════════════════
    # WEBHOOKS
    # ═══════════════════════════════════════════════════════════════════
    
    def send_custom_webhook(self, event_type: str, message: str,
                           priority: str = "normal", action: str = "",
                           service_name: str = "") -> Dict[str, Any]:
        """Send custom webhook event"""
        data = {
            'event_type': event_type,
            'message': message,
            'priority': priority
        }
        if action:
            data['action'] = action
        if service_name:
            data['service_name'] = service_name
        return self._request('POST', '/webhooks/custom', data)


# ═══════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def get_client() -> GuardianClient:
    """Factory function to get client with default config"""
    return GuardianClient()


def quick_health_check() -> bool:
    """Quick health check, returns True if healthy"""
    client = GuardianClient()
    result = client.health()
    return result.get('status') == 'healthy'


def restart_all_services() -> Dict[str, Any]:
    """Restart all services"""
    client = GuardianClient()
    results = {}
    for service in ['rudibot_main', 'ollama_llm', 'redis']:
        results[service] = client.restart_service(service)
    return results


def heal_all_services() -> Dict[str, Any]:
    """Heal all unhealthy services"""
    client = GuardianClient()
    results = {}
    for svc in client.services():
        if svc.get('status') != 'running':
            name = svc['name'].lower().replace(' ', '_')
            results[name] = client.heal_service(name)
    return results


if __name__ == '__main__':
    # Demo usage
    client = GuardianClient()
    
    print("=== Health Check ===")
    print(json.dumps(client.health(), indent=2))
    
    print("\n=== Services ===")
    for svc in client.services():
        print(f"  {svc['name']}: {svc['status']}")
    
    print("\n=== Brain Summary ===")
    print(json.dumps(client.brain_summary(), indent=2))
    
    print("\n=== Registered Agents ===")
    for agent in client.list_agents():
        print(f"  {agent['agent_id']}: {agent['type']}")
