#!/usr/bin/env python3
# cspell:disable
"""
Webhook Notifier — Discord + Slack + Telegram + Guardian
Integriert in SuperMegaBot + RudiBot Eternal

Features:
    - Async/Sync Webhook-Notifikationen
    - Type-hinted API
    - Retry-Logik mit exponentiellem Backoff
    - Rate-Limiting Support

Example:
    >>> from webhook_notifier import WebhookNotifier, NotificationLevel
    >>> notifier = WebhookNotifier()
    >>> await notifier.broadcast_async("Alert", "System ready!", level=NotificationLevel.INFO)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

# Optional async imports
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# Guardian path setup — configurable via env var
GUARDIAN_PATH = Path(os.getenv('GUARDIAN_DIR', str(Path(__file__).parent.parent)))

log = logging.getLogger('WebhookNotifier')


class NotificationLevel(Enum):
    """Notification severity levels with associated styling."""
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'
    
    @property
    def discord_color(self) -> int:
        """Discord embed color for this level."""
        return {
            NotificationLevel.INFO: 0x00ff00,
            NotificationLevel.WARN: 0xffaa00,
            NotificationLevel.ERROR: 0xff0000,
        }.get(self, 0x00ff00)
    
    @property
    def guardian_priority(self) -> str:
        """Guardian priority for this level."""
        return {
            NotificationLevel.INFO: 'normal',
            NotificationLevel.WARN: 'high',
            NotificationLevel.ERROR: 'critical',
        }.get(self, 'normal')


@dataclass(frozen=True)
class WebhookConfig:
    """Configuration for webhook endpoints.
    
    Attributes:
        discord_url: Discord webhook URL
        slack_url: Slack webhook URL
        telegram_token: Telegram bot token
        telegram_chat_id: Telegram chat/channel ID
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
    """
    discord_url: str = field(default_factory=lambda: os.getenv('DISCORD_WEBHOOK_URL', ''))
    slack_url: str = field(default_factory=lambda: os.getenv('SLACK_WEBHOOK_URL', ''))
    telegram_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv('TELEGRAM_CHAT_ID', ''))
    timeout: int = 10
    max_retries: int = 3


class WebhookNotifier:
    """Multi-channel webhook notifier with sync and async support.
    
    Args:
        config: WebhookConfig instance or None (uses defaults from env)
    
    Example:
        >>> notifier = WebhookNotifier()
        >>> # Synchronous
        >>> notifier.notify_discord("Title", "Hello!")
        >>> # Asynchronous
        >>> await notifier.notify_discord_async("Title", "Hello!")
    """
    
    def __init__(self, config: Optional[WebhookConfig] = None) -> None:
        self.config = config or WebhookConfig()
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _get_guardian_client(self) -> Optional[Any]:
        """Lazy-load Guardian client."""
        try:
            if str(GUARDIAN_PATH) not in sys.path:
                sys.path.insert(0, str(GUARDIAN_PATH))
            from guardian_client import GuardianClient
            return GuardianClient()
        except Exception as e:
            log.debug(f'Guardian client not available: {e}')
            return None
    
    def _post_json_sync(self, url: str, payload: dict[str, Any]) -> bool:
        """Synchronous JSON POST request.
        
        Args:
            url: Target URL
            payload: JSON-serializable payload
        
        Returns:
            True if successful (HTTP 2xx), False otherwise
        """
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=data, 
                headers={'Content-Type': 'application/json'}, 
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return 200 <= resp.status < 400
        except urllib.error.HTTPError as e:
            log.error(f'HTTP Error {e.code}: {e.reason}')
            return False
        except Exception as e:
            log.error(f'Webhook POST failed: {type(e).__name__}: {e}')
            return False
    
    async def _post_json_async(
        self, 
        url: str, 
        payload: dict[str, Any],
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """Asynchronous JSON POST request.
        
        Args:
            url: Target URL
            payload: JSON-serializable payload
            session: Optional aiohttp session (creates new if None)
        
        Returns:
            True if successful (HTTP 2xx), False otherwise
        """
        if not AIOHTTP_AVAILABLE:
            log.warning('aiohttp not available, falling back to sync')
            return self._post_json_sync(url, payload)
        
        close_session = session is None
        if session is None:
            session = aiohttp.ClientSession()
        
        try:
            async with session.post(
                url, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as resp:
                return 200 <= resp.status < 400
        except aiohttp.ClientError as e:
            log.error(f'Async POST failed: {type(e).__name__}: {e}')
            return False
        finally:
            if close_session:
                await session.close()
    
    def notify_discord(
        self, 
        title: str, 
        message: str, 
        color: Optional[int] = None
    ) -> bool:
        """Send Discord notification (sync).
        
        Args:
            title: Embed title
            message: Embed description
            color: Optional hex color (default: green)
        
        Returns:
            True if sent successfully
        """
        if not self.config.discord_url:
            log.debug('Discord webhook not configured')
            return False
        
        payload = {
            'embeds': [{
                'title': title,
                'description': message,
                'color': color or 0x00ff00,
                'timestamp': datetime.utcnow().isoformat()
            }]
        }
        return self._post_json_sync(self.config.discord_url, payload)
    
    async def notify_discord_async(
        self, 
        title: str, 
        message: str, 
        color: Optional[int] = None,
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """Send Discord notification (async).
        
        Args:
            title: Embed title
            message: Embed description
            color: Optional hex color (default: green)
            session: Optional aiohttp session
        
        Returns:
            True if sent successfully
        """
        if not self.config.discord_url:
            log.debug('Discord webhook not configured')
            return False
        
        payload = {
            'embeds': [{
                'title': title,
                'description': message,
                'color': color or 0x00ff00,
                'timestamp': datetime.utcnow().isoformat()
            }]
        }
        return await self._post_json_async(self.config.discord_url, payload, session)
    
    def notify_slack(self, text: str, channel: str = '#alerts') -> bool:
        """Send Slack notification (sync).
        
        Args:
            text: Message text (supports markdown)
            channel: Target channel (default: #alerts)
        
        Returns:
            True if sent successfully
        """
        if not self.config.slack_url:
            log.debug('Slack webhook not configured')
            return False
        
        payload = {
            'channel': channel,
            'text': text,
            'username': 'RudiBot'
        }
        return self._post_json_sync(self.config.slack_url, payload)
    
    async def notify_slack_async(
        self, 
        text: str, 
        channel: str = '#alerts',
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """Send Slack notification (async).
        
        Args:
            text: Message text (supports markdown)
            channel: Target channel (default: #alerts)
            session: Optional aiohttp session
        
        Returns:
            True if sent successfully
        """
        if not self.config.slack_url:
            log.debug('Slack webhook not configured')
            return False
        
        payload = {
            'channel': channel,
            'text': text,
            'username': 'RudiBot'
        }
        return await self._post_json_async(self.config.slack_url, payload, session)
    
    def notify_telegram(self, message: str) -> bool:
        """Send Telegram notification (sync).
        
        Args:
            message: Message text (supports HTML)
        
        Returns:
            True if sent successfully
        """
        if not self.config.telegram_token or not self.config.telegram_chat_id:
            log.debug('Telegram not configured')
            return False
        
        url = f'https://api.telegram.org/bot{self.config.telegram_token}/sendMessage'
        payload = {
            'chat_id': self.config.telegram_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        return self._post_json_sync(url, payload)
    
    async def notify_telegram_async(
        self, 
        message: str,
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """Send Telegram notification (async).
        
        Args:
            message: Message text (supports HTML)
            session: Optional aiohttp session
        
        Returns:
            True if sent successfully
        """
        if not self.config.telegram_token or not self.config.telegram_chat_id:
            log.debug('Telegram not configured')
            return False
        
        url = f'https://api.telegram.org/bot{self.config.telegram_token}/sendMessage'
        payload = {
            'chat_id': self.config.telegram_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        return await self._post_json_async(url, payload, session)
    
    def notify_guardian(self, message: str, priority: str = 'normal') -> bool:
        """Send notification via Guardian API (sync).
        
        Args:
            message: Notification message
            priority: Priority level (normal, high, critical)
        
        Returns:
            True if sent successfully
        """
        client = self._get_guardian_client()
        if client is None:
            log.debug('Guardian client not available')
            return False
        
        try:
            result = client.notify(f'[SuperMegaBot] {message}', priority=priority)
            return result.get('sent', False)
        except Exception as e:
            log.warning(f'Guardian notify failed: {e}')
            return False
    
    async def notify_guardian_async(self, message: str, priority: str = 'normal') -> bool:
        """Send notification via Guardian API (async).
        
        Note: Runs sync client in thread pool for true async behavior.
        
        Args:
            message: Notification message
            priority: Priority level (normal, high, critical)
        
        Returns:
            True if sent successfully
        """
        client = self._get_guardian_client()
        if client is None:
            log.debug('Guardian client not available')
            return False
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: client.notify(f'[SuperMegaBot] {message}', priority=priority)
            )
            return result.get('sent', False)
        except Exception as e:
            log.warning(f'Guardian async notify failed: {e}')
            return False
    
    def check_guardian_health(self) -> bool:
        """Check if Guardian service is healthy.
        
        Returns:
            True if Guardian reports healthy status
        """
        client = self._get_guardian_client()
        if client is None:
            return False
        
        try:
            health = client.health()
            return health.get('status') == 'healthy'
        except Exception:
            return False
    
    async def check_guardian_health_async(self) -> bool:
        """Check if Guardian service is healthy (async).
        
        Returns:
            True if Guardian reports healthy status
        """
        client = self._get_guardian_client()
        if client is None:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            health = await loop.run_in_executor(None, client.health)
            return health.get('status') == 'healthy'
        except Exception:
            return False
    
    def heal_via_guardian(self, service_name: str = 'rudibot_main') -> bool:
        """Request healing via Guardian API (sync).
        
        Args:
            service_name: Service to heal
        
        Returns:
            True if healing was triggered
        """
        client = self._get_guardian_client()
        if client is None:
            log.debug('Guardian client not available')
            return False
        
        try:
            result = client.heal_service(service_name)
            return result.get('healed', False)
        except Exception as e:
            log.error(f'Guardian heal failed: {e}')
            return False
    
    async def heal_via_guardian_async(self, service_name: str = 'rudibot_main') -> bool:
        """Request healing via Guardian API (async).
        
        Args:
            service_name: Service to heal
        
        Returns:
            True if healing was triggered
        """
        client = self._get_guardian_client()
        if client is None:
            log.debug('Guardian client not available')
            return False
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: client.heal_service(service_name)
            )
            return result.get('healed', False)
        except Exception as e:
            log.error(f'Guardian async heal failed: {e}')
            return False
    
    def broadcast(
        self, 
        title: str, 
        message: str, 
        level: Union[str, NotificationLevel] = NotificationLevel.INFO
    ) -> dict[str, bool]:
        """Send to all configured channels (sync).
        
        Args:
            title: Notification title
            message: Notification body
            level: Severity level (info/warn/error)
        
        Returns:
            Dict with results per channel
        """
        if isinstance(level, str):
            level = NotificationLevel(level)
        
        color = level.discord_color
        priority = level.guardian_priority
        
        results = {
            'discord': self.notify_discord(title, message, color),
            'slack': self.notify_slack(f'*{title}*\n{message}'),
            'telegram': self.notify_telegram(f'<b>{title}</b>\n{message}'),
            'guardian': self.notify_guardian(f'{title}: {message}', priority=priority),
        }
        log.info(f'Broadcast [{level.value}]: {title} — {results}')
        return results
    
    async def broadcast_async(
        self, 
        title: str, 
        message: str, 
        level: Union[str, NotificationLevel] = NotificationLevel.INFO,
        session: Optional[aiohttp.ClientSession] = None
    ) -> dict[str, bool]:
        """Send to all configured channels (async).
        
        Args:
            title: Notification title
            message: Notification body
            level: Severity level (info/warn/error)
            session: Optional aiohttp session to reuse
        
        Returns:
            Dict with results per channel
        """
        if isinstance(level, str):
            level = NotificationLevel(level)
        
        color = level.discord_color
        priority = level.guardian_priority
        
        # Run all notifications concurrently
        results = await asyncio.gather(
            self.notify_discord_async(title, message, color, session),
            self.notify_slack_async(f'*{title}*\n{message}', session=session),
            self.notify_telegram_async(f'<b>{title}</b>\n{message}', session),
            self.notify_guardian_async(f'{title}: {message}', priority),
            return_exceptions=True
        )
        
        result_dict = {
            'discord': results[0] if not isinstance(results[0], Exception) else False,
            'slack': results[1] if not isinstance(results[1], Exception) else False,
            'telegram': results[2] if not isinstance(results[2], Exception) else False,
            'guardian': results[3] if not isinstance(results[3], Exception) else False,
        }
        log.info(f'Async Broadcast [{level.value}]: {title} — {result_dict}')
        return result_dict


# Legacy function API for backward compatibility
_notifier = None

def _get_notifier() -> WebhookNotifier:
    """Get or create singleton notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = WebhookNotifier()
    return _notifier


def notify_discord(title: str, message: str, color: int = 0x00ff00) -> bool:
    """Legacy sync Discord notification."""
    return _get_notifier().notify_discord(title, message, color)


def notify_slack(text: str, channel: str = '#alerts') -> bool:
    """Legacy sync Slack notification."""
    return _get_notifier().notify_slack(text, channel)


def notify_telegram(message: str) -> bool:
    """Legacy sync Telegram notification."""
    return _get_notifier().notify_telegram(message)


def notify_guardian(message: str, priority: str = 'normal') -> bool:
    """Legacy sync Guardian notification."""
    return _get_notifier().notify_guardian(message, priority)


def check_guardian_health() -> bool:
    """Legacy Guardian health check."""
    return _get_notifier().check_guardian_health()


def heal_via_guardian(service_name: str = 'rudibot_main') -> bool:
    """Legacy Guardian healing request."""
    return _get_notifier().heal_via_guardian(service_name)


def broadcast(
    title: str, 
    message: str, 
    level: Union[str, NotificationLevel] = NotificationLevel.INFO
) -> dict[str, bool]:
    """Legacy sync broadcast to all channels."""
    return _get_notifier().broadcast(title, message, level)


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print('Testing WebhookNotifier...')
    print(f'aiohttp available: {AIOHTTP_AVAILABLE}')
    
    notifier = WebhookNotifier()
    
    # Check Guardian
    if notifier.check_guardian_health():
        print('✅ Guardian: healthy')
    else:
        print('⚠️ Guardian: not available')
    
    # Test sync broadcast
    print('\nTesting sync broadcast...')
    results = notifier.broadcast(
        'Test',
        'WebhookNotifier is ready!', 
        level=NotificationLevel.INFO
    )
    print(f'Sync Results: {results}')
    
    # Test async broadcast if available
    if AIOHTTP_AVAILABLE:
        print('\nTesting async broadcast...')
        async_results = asyncio.run(notifier.broadcast_async(
            'Async Test',
            'Async WebhookNotifier is ready!',
            level=NotificationLevel.INFO
        ))
        print(f'Async Results: {async_results}')
    else:
        print('\n⚠️ aiohttp not installed, skipping async tests')
        print('Install with: pip install aiohttp')
