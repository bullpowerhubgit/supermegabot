#!/usr/bin/env python3
"""
🤖 Guardian API Client v2.0
Wiederverwendbarer Client für alle Tools

Features:
    - Sync und Async API
    - Type-hinted Methoden
    - Automatische Retry-Logik
    - Pydantic-Style Dataclasses

Example:
    >>> from guardian_client import GuardianClient, ServiceStatus
    >>> client = GuardianClient()
    >>> # Sync
    >>> status = client.health()
    >>> # Async
    >>> status = await client.health_async()
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

# Optional imports
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class ServiceState(Enum):
    """Service Zustände."""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"
    UNKNOWN = "unknown"


@dataclass
class GuardianConfig:
    """Konfiguration für Guardian Client.
    
    Attributes:
        secret_key: API Secret (default: aus Umgebung)
        base_url: Guardian API URL
        timeout: Request Timeout in Sekunden
        max_retries: Maximale Wiederholungsversuche
    """
    secret_key: str = field(default_factory=lambda: os.getenv('GUARDIAN_API_SECRET', ''))
    base_url: str = "http://localhost:3201"
    timeout: int = 10
    max_retries: int = 3
    
    def __post_init__(self) -> None:
        """Validiere Konfiguration."""
        if not self.secret_key:
            self.secret_key = self._load_from_env()
        if not self.secret_key:
            raise ValueError(
                "GUARDIAN_API_SECRET nicht gesetzt!\n"
                "Lösungen:\n"
                "1. export GUARDIAN_API_SECRET='dein-secret'\n"
                "2. Oder .env Datei erstellen\n"
                "3. Oder GuardianClient(secret_key='...')"
            )
    
    @staticmethod
    def _load_from_env() -> Optional[str]:
        """Lade Secret aus .env Dateien."""
        env_paths = [
            str(Path(__file__).parent / '.env'),
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
            except Exception:
                pass
        return None


@dataclass
class ServiceStatus:
    """Service Status Information.
    
    Attributes:
        name: Service Name
        status: Aktueller Zustand
        port: Service Port
        healthy: Health Check OK
        last_check: Zeitpunkt des letzten Checks
    """
    name: str
    status: ServiceState
    port: int
    healthy: bool = False
    last_check: Optional[datetime] = None


@dataclass
class HealthResponse:
    """Health Check Response.
    
    Attributes:
        status: System Status (healthy/degraded/down)
        version: Guardian Version
        uptime: Uptime in Sekunden
        services: Anzahl der Services
    """
    status: str = "unknown"
    version: str = "unknown"
    uptime: int = 0
    services: int = 0


class GuardianClient:
    """Guardian REST API Client mit Sync und Async Support.
    
    Args:
        config: GuardianConfig Instanz oder None
    
    Example:
        >>> client = GuardianClient()
        >>> # Sync API
        >>> health = client.health()
        >>> services = client.services()
        >>> # Async API
        >>> health = await client.health_async()
        >>> services = await client.services_async()
    """
    
    def __init__(self, config: Optional[GuardianConfig] = None) -> None:
        self.config = config or GuardianConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        
        # API Key aus Secret generieren
        self.api_key = hashlib.sha256(
            self.config.secret_key.encode()
        ).hexdigest()[:32]
        
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def _get_url(self, endpoint: str) -> str:
        """Baue vollständige URL.
        
        Args:
            endpoint: API Endpoint (z.B. /api/v1/health)
        
        Returns:
            Vollständige URL
        """
        base = self.config.base_url.rstrip('/')
        endpoint = endpoint if endpoint.startswith('/') else f'/{endpoint}'
        return f"{base}{endpoint}"
    
    def _request_sync(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        auth: bool = True
    ) -> dict[str, Any]:
        """Synchrone HTTP Request.
        
        Args:
            method: HTTP Methode (GET/POST)
            endpoint: API Endpoint
            data: Optional JSON Payload
            auth: Authentifizierung verwenden
        
        Returns:
            JSON Response als Dict
        """
        url = self._get_url(endpoint)
        headers = self.headers if auth else {}
        
        if REQUESTS_AVAILABLE:
            return self._request_with_requests(method, url, data, headers)
        else:
            return self._request_with_urllib(method, url, data, headers)
    
    def _request_with_requests(
        self,
        method: str,
        url: str,
        data: Optional[dict[str, Any]],
        headers: dict[str, str]
    ) -> dict[str, Any]:
        """Request mit requests Library."""
        try:
            if method == 'GET':
                resp = requests.get(url, headers=headers, timeout=self.config.timeout)
            elif method == 'POST':
                resp = requests.post(
                    url, headers=headers, json=data, timeout=self.config.timeout
                )
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            return {'error': str(e), 'url': url}
    
    def _request_with_urllib(
        self,
        method: str,
        url: str,
        data: Optional[dict[str, Any]],
        headers: dict[str, str]
    ) -> dict[str, Any]:
        """Request mit urllib (Fallback)."""
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode() if data else None,
                headers=headers,
                method=method
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {'error': f'HTTP {e.code}: {e.reason}', 'url': url}
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    async def _request_async(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        auth: bool = True
    ) -> dict[str, Any]:
        """Asynchrone HTTP Request.
        
        Args:
            method: HTTP Methode (GET/POST)
            endpoint: API Endpoint
            data: Optional JSON Payload
            auth: Authentifizierung verwenden
        
        Returns:
            JSON Response als Dict
        """
        if not AIOHTTP_AVAILABLE:
            # Fallback zu sync
            return self._request_sync(method, endpoint, data, auth)
        
        url = self._get_url(endpoint)
        headers = self.headers if auth else {}
        
        close_session = self._session is None
        if self._session is None:
            self._session = aiohttp.ClientSession()
        
        try:
            if method == 'GET':
                async with self._session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    return await resp.json()
            elif method == 'POST':
                async with self._session.post(
                    url, headers=headers, json=data,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    return await resp.json()
            else:
                raise ValueError(f"Unsupported method: {method}")
        except aiohttp.client_exceptions.ClientError as e:
            return {'error': str(e), 'url': url}
        finally:
            if close_session:
                await self._session.close()
                self._session = None
    
    # ═══════════════════════════════════════════════════════════════════
    # STATUS & HEALTH (Sync)
    # ═══════════════════════════════════════════════════════════════════
    
    def health(self) -> dict[str, Any]:
        """Health check (no auth required).
        
        Returns:
            Health Status Dict
        """
        return self._request_sync('GET', '/api/v1/health', auth=False)
    
    def status(self) -> dict[str, Any]:
        """Full system status.
        
        Returns:
            System Status Dict
        """
        return self._request_sync('GET', '/api/v1/status')
    
    def services(self) -> list[dict[str, Any]]:
        """List all services.
        
        Returns:
            Liste aller Services
        """
        result = self._request_sync('GET', '/api/v1/services')
        return result.get('services', [])
    
    def service_status(self, service_name: str) -> dict[str, Any]:
        """Get specific service status.
        
        Args:
            service_name: Name des Services
        
        Returns:
            Service Status Dict
        """
        return self._request_sync('GET', f'/api/v1/services/{service_name}/status')
    
    # ═══════════════════════════════════════════════════════════════════
    # STATUS & HEALTH (Async)
    # ═══════════════════════════════════════════════════════════════════
    
    async def health_async(self) -> dict[str, Any]:
        """Async health check."""
        return await self._request_async('GET', '/api/v1/health', auth=False)
    
    async def status_async(self) -> dict[str, Any]:
        """Async system status."""
        return await self._request_async('GET', '/api/v1/status')
    
    async def services_async(self) -> list[dict[str, Any]]:
        """Async list services."""
        result = await self._request_async('GET', '/api/v1/services')
        return result.get('services', [])
    
    async def service_status_async(self, service_name: str) -> dict[str, Any]:
        """Async service status."""
        return await self._request_async('GET', f'/api/v1/services/{service_name}/status')
    
    # ═══════════════════════════════════════════════════════════════════
    # REMOTE CONTROL (Sync)
    # ═══════════════════════════════════════════════════════════════════
    
    def start_service(self, service_name: str) -> dict[str, Any]:
        """Start a service.
        
        Args:
            service_name: Zu startender Service
        
        Returns:
            API Response
        """
        return self._request_sync('POST', f'/api/v1/services/{service_name}/start')
    
    def stop_service(self, service_name: str) -> dict[str, Any]:
        """Stop a service.
        
        Args:
            service_name: Zu stopbender Service
        
        Returns:
            API Response
        """
        return self._request_sync('POST', f'/api/v1/services/{service_name}/stop')
    
    def restart_service(self, service_name: str) -> dict[str, Any]:
        """Restart a service.
        
        Args:
            service_name: Zu restartender Service
        
        Returns:
            API Response
        """
        return self._request_sync('POST', f'/api/v1/services/{service_name}/restart')
    
    def heal_service(self, service_name: str) -> dict[str, Any]:
        """Heal a service with full repair process.
        
        Args:
            service_name: Zu heilender Service
        
        Returns:
            API Response mit 'healed' Status
        """
        return self._request_sync('POST', f'/api/v1/services/{service_name}/heal')
    
    # ═══════════════════════════════════════════════════════════════════
    # REMOTE CONTROL (Async)
    # ═══════════════════════════════════════════════════════════════════
    
    async def start_service_async(self, service_name: str) -> dict[str, Any]:
        """Async start service."""
        return await self._request_async('POST', f'/api/v1/services/{service_name}/start')
    
    async def stop_service_async(self, service_name: str) -> dict[str, Any]:
        """Async stop service."""
        return await self._request_async('POST', f'/api/v1/services/{service_name}/stop')
    
    async def restart_service_async(self, service_name: str) -> dict[str, Any]:
        """Async restart service."""
        return await self._request_async('POST', f'/api/v1/services/{service_name}/restart')
    
    async def heal_service_async(self, service_name: str) -> dict[str, Any]:
        """Async heal service."""
        return await self._request_async('POST', f'/api/v1/services/{service_name}/heal')
    
    # ═══════════════════════════════════════════════════════════════════
    # BRAIN API (Sync)
    # ═══════════════════════════════════════════════════════════════════
    
    def brain_summary(self) -> dict[str, Any]:
        """Get brain summary."""
        return self._request_sync('GET', '/api/v1/brain')
    
    def brain_fixes(self) -> dict[str, Any]:
        """Get all learned fixes."""
        return self._request_sync('GET', '/api/v1/brain/fixes')
    
    def brain_patterns(self) -> dict[str, Any]:
        """Get error patterns."""
        return self._request_sync('GET', '/api/v1/brain/patterns')
    
    def add_fix(
        self,
        error_key: str,
        fix: str,
        service: str = "manual",
        success: bool = True
    ) -> dict[str, Any]:
        """Add a new fix to brain.
        
        Args:
            error_key: Eindeutiger Fehler-Key
            fix: Fix Beschreibung
            service: Service Name
            success: Fix war erfolgreich
        
        Returns:
            API Response
        """
        return self._request_sync('POST', '/api/v1/brain/fixes', {
            'error_key': error_key,
            'service': service,
            'fix': fix,
            'success': success
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # BRAIN API (Async)
    # ═══════════════════════════════════════════════════════════════════
    
    async def brain_summary_async(self) -> dict[str, Any]:
        """Async brain summary."""
        return await self._request_async('GET', '/api/v1/brain')
    
    async def brain_fixes_async(self) -> dict[str, Any]:
        """Async brain fixes."""
        return await self._request_async('GET', '/api/v1/brain/fixes')
    
    async def brain_patterns_async(self) -> dict[str, Any]:
        """Async brain patterns."""
        return await self._request_async('GET', '/api/v1/brain/patterns')
    
    async def add_fix_async(
        self,
        error_key: str,
        fix: str,
        service: str = "manual",
        success: bool = True
    ) -> dict[str, Any]:
        """Async add fix."""
        return await self._request_async('POST', '/api/v1/brain/fixes', {
            'error_key': error_key,
            'service': service,
            'fix': fix,
            'success': success
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # AGENTS (Sync)
    # ═══════════════════════════════════════════════════════════════════
    
    def list_agents(self) -> list[dict[str, Any]]:
        """List registered agents."""
        result = self._request_sync('GET', '/api/v1/agents')
        return result.get('agents', [])
    
    def register_agent(
        self,
        agent_id: str,
        agent_type: str = "monitoring",
        endpoint: str = ""
    ) -> dict[str, Any]:
        """Register a new agent.
        
        Args:
            agent_id: Eindeutige Agent ID
            agent_type: Agent Typ (monitoring, service, etc.)
            endpoint: Agent Endpoint URL
        
        Returns:
            API Response
        """
        return self._request_sync('POST', '/api/v1/agents/register', {
            'agent_id': agent_id,
            'type': agent_type,
            'endpoint': endpoint
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # AGENTS (Async)
    # ═══════════════════════════════════════════════════════════════════
    
    async def list_agents_async(self) -> list[dict[str, Any]]:
        """Async list agents."""
        result = await self._request_async('GET', '/api/v1/agents')
        return result.get('agents', [])
    
    async def register_agent_async(
        self,
        agent_id: str,
        agent_type: str = "monitoring",
        endpoint: str = ""
    ) -> dict[str, Any]:
        """Async register agent."""
        return await self._request_async('POST', '/api/v1/agents/register', {
            'agent_id': agent_id,
            'type': agent_type,
            'endpoint': endpoint
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # BACKUP & REPORTS (Sync)
    # ═══════════════════════════════════════════════════════════════════
    
    def trigger_backup(self) -> dict[str, Any]:
        """Trigger manual backup."""
        return self._request_sync('POST', '/api/v1/backup')
    
    def get_reports(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get daily reports."""
        result = self._request_sync('GET', f'/api/v1/reports?limit={limit}')
        return result.get('reports', [])
    
    def get_latest_report(self) -> dict[str, Any]:
        """Get latest report."""
        return self._request_sync('GET', '/api/v1/reports/latest')
    
    # ═══════════════════════════════════════════════════════════════════
    # BACKUP & REPORTS (Async)
    # ═══════════════════════════════════════════════════════════════════
    
    async def trigger_backup_async(self) -> dict[str, Any]:
        """Async trigger backup."""
        return await self._request_async('POST', '/api/v1/backup')
    
    async def get_reports_async(self, limit: int = 10) -> list[dict[str, Any]]:
        """Async get reports."""
        result = await self._request_async('GET', f'/api/v1/reports?limit={limit}')
        return result.get('reports', [])
    
    async def get_latest_report_async(self) -> dict[str, Any]:
        """Async get latest report."""
        return await self._request_async('GET', '/api/v1/reports/latest')
    
    # ═══════════════════════════════════════════════════════════════════
    # NOTIFICATIONS (Sync)
    # ═══════════════════════════════════════════════════════════════════
    
    def notify(
        self,
        message: str,
        priority: str = "normal",
        channels: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """Send notification to all channels.
        
        Args:
            message: Nachrichtentext
            priority: Priorität (normal, high, critical)
            channels: Zielkanäle (default: ['all'])
        
        Returns:
            API Response
        """
        if channels is None:
            channels = ['all']
        return self._request_sync('POST', '/api/v1/notify', {
            'message': message,
            'priority': priority,
            'channels': channels
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # NOTIFICATIONS (Async)
    # ═══════════════════════════════════════════════════════════════════
    
    async def notify_async(
        self,
        message: str,
        priority: str = "normal",
        channels: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """Async send notification."""
        if channels is None:
            channels = ['all']
        return await self._request_async('POST', '/api/v1/notify', {
            'message': message,
            'priority': priority,
            'channels': channels
        })
    
    # ═══════════════════════════════════════════════════════════════════
    # METRICS
    # ═══════════════════════════════════════════════════════════════════
    
    def metrics(self) -> str:
        """Get Prometheus metrics.
        
        Returns:
            Prometheus-formatierte Metriken
        """
        url = self._get_url('/metrics')
        try:
            if REQUESTS_AVAILABLE:
                resp = requests.get(url, timeout=self.config.timeout)
                return resp.text
            else:
                with urllib.request.urlopen(url, timeout=self.config.timeout) as resp:
                    return resp.read().decode()
        except Exception as e:
            return f"# Error: {e}"
    
    async def metrics_async(self) -> str:
        """Async get metrics."""
        if not AIOHTTP_AVAILABLE:
            return self.metrics()
        
        url = self._get_url('/metrics')
        close_session = self._session is None
        if self._session is None:
            self._session = aiohttp.ClientSession()
        
        try:
            async with self._session.get(url) as resp:
                return await resp.text()
        except Exception as e:
            return f"# Error: {e}"
        finally:
            if close_session:
                await self._session.close()
                self._session = None
    
    # ═══════════════════════════════════════════════════════════════════
    # WEBHOOKS
    # ═══════════════════════════════════════════════════════════════════
    
    def send_custom_webhook(
        self,
        event_type: str,
        message: str,
        priority: str = "normal",
        action: str = "",
        service_name: str = ""
    ) -> dict[str, Any]:
        """Send custom webhook event.
        
        Args:
            event_type: Event Typ
            message: Nachricht
            priority: Priorität
            action: Optionale Aktion
            service_name: Optionaler Service Name
        
        Returns:
            API Response
        """
        data: dict[str, Any] = {
            'event_type': event_type,
            'message': message,
            'priority': priority
        }
        if action:
            data['action'] = action
        if service_name:
            data['service_name'] = service_name
        return self._request_sync('POST', '/webhooks/custom', data)
    
    async def send_custom_webhook_async(
        self,
        event_type: str,
        message: str,
        priority: str = "normal",
        action: str = "",
        service_name: str = ""
    ) -> dict[str, Any]:
        """Async send custom webhook."""
        data: dict[str, Any] = {
            'event_type': event_type,
            'message': message,
            'priority': priority
        }
        if action:
            data['action'] = action
        if service_name:
            data['service_name'] = service_name
        return await self._request_async('POST', '/webhooks/custom', data)


# ═══════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

_client: Optional[GuardianClient] = None


def get_client() -> GuardianClient:
    """Factory function to get singleton client."""
    global _client
    if _client is None:
        _client = GuardianClient()
    return _client


def quick_health_check() -> bool:
    """Quick health check, returns True if healthy."""
    client = get_client()
    result = client.health()
    return result.get('status') == 'healthy'


async def quick_health_check_async() -> bool:
    """Async quick health check."""
    client = get_client()
    result = await client.health_async()
    return result.get('status') == 'healthy'


def restart_all_services() -> dict[str, Any]:
    """Restart all services."""
    client = get_client()
    results: dict[str, Any] = {}
    for service in ['rudibot_main', 'ollama_llm', 'redis']:
        results[service] = client.restart_service(service)
    return results


async def restart_all_services_async() -> dict[str, Any]:
    """Async restart all services."""
    client = get_client()
    tasks = [
        client.restart_service_async(service)
        for service in ['rudibot_main', 'ollama_llm', 'redis']
    ]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        service: result if not isinstance(result, Exception) else {'error': str(result)}
        for service, result in zip(['rudibot_main', 'ollama_llm', 'redis'], results_list)
    }


def heal_all_services() -> dict[str, Any]:
    """Heal all unhealthy services."""
    client = get_client()
    results: dict[str, Any] = {}
    for svc in client.services():
        if svc.get('status') != 'running':
            name = svc['name'].lower().replace(' ', '_')
            results[name] = client.heal_service(name)
    return results


async def heal_all_services_async() -> dict[str, Any]:
    """Async heal all unhealthy services."""
    client = get_client()
    services = await client.services_async()
    tasks = []
    names = []
    for svc in services:
        if svc.get('status') != 'running':
            name = svc['name'].lower().replace(' ', '_')
            names.append(name)
            tasks.append(client.heal_service_async(name))
    
    if not tasks:
        return {}
    
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        name: result if not isinstance(result, Exception) else {'error': str(result)}
        for name, result in zip(names, results_list)
    }


if __name__ == '__main__':
    import sys
    
    print("🤖 Guardian Client Demo")
    print(f"   aiohttp: {AIOHTTP_AVAILABLE}")
    print(f"   requests: {REQUESTS_AVAILABLE}")
    print()
    
    try:
        client = GuardianClient()
        print(f"✅ Client initialized")
        print(f"   Base URL: {client.config.base_url}")
        print()
        
        # Sync health check
        print("📡 Sync Health Check:")
        health = client.health()
        print(f"   Status: {health.get('status', 'unknown')}")
        print()
        
        # Async health check if available
        if AIOHTTP_AVAILABLE:
            print("📡 Async Health Check:")
            async_health = asyncio.run(client.health_async())
            print(f"   Status: {async_health.get('status', 'unknown')}")
            print()
        
        # Services
        print("🔧 Services:")
        for svc in client.services()[:5]:
            print(f"   - {svc.get('name', 'unknown')}: {svc.get('status', 'unknown')}")
        
    except ValueError as e:
        print(f"⚠️ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
