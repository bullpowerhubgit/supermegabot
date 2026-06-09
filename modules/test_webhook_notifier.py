#!/usr/bin/env python3
"""
Unit Tests für WebhookNotifier

Ausführen:
    pytest test_webhook_notifier.py -v
    pytest test_webhook_notifier.py -v --cov=webhook_notifier
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from dataclasses import FrozenInstanceError, asdict
from http import HTTPStatus
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from webhook_notifier import (
    AIOHTTP_AVAILABLE,
    NotificationLevel,
    WebhookConfig,
    WebhookNotifier,
    broadcast,
    check_guardian_health,
    heal_via_guardian,
    notify_discord,
    notify_guardian,
    notify_slack,
    notify_telegram,
)


class TestNotificationLevel(unittest.TestCase):
    """Tests für NotificationLevel Enum."""
    
    def test_enum_values(self) -> None:
        """Test that enum values are correct."""
        self.assertEqual(NotificationLevel.INFO.value, 'info')
        self.assertEqual(NotificationLevel.WARN.value, 'warn')
        self.assertEqual(NotificationLevel.ERROR.value, 'error')
    
    def test_discord_colors(self) -> None:
        """Test Discord colors for each level."""
        self.assertEqual(NotificationLevel.INFO.discord_color, 0x00ff00)
        self.assertEqual(NotificationLevel.WARN.discord_color, 0xffaa00)
        self.assertEqual(NotificationLevel.ERROR.discord_color, 0xff0000)
    
    def test_guardian_priorities(self) -> None:
        """Test Guardian priorities for each level."""
        self.assertEqual(NotificationLevel.INFO.guardian_priority, 'normal')
        self.assertEqual(NotificationLevel.WARN.guardian_priority, 'high')
        self.assertEqual(NotificationLevel.ERROR.guardian_priority, 'critical')


class TestWebhookConfig(unittest.TestCase):
    """Tests für WebhookConfig Dataclass."""
    
    @patch.dict('os.environ', {
        'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test',
        'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test',
        'TELEGRAM_BOT_TOKEN': 'test_token',
        'TELEGRAM_CHAT_ID': '123456',
    })
    def test_from_env(self) -> None:
        """Test config creation from environment variables."""
        config = WebhookConfig()
        self.assertEqual(config.discord_url, 'https://discord.com/api/webhooks/test')
        self.assertEqual(config.slack_url, 'https://hooks.slack.com/test')
        self.assertEqual(config.telegram_token, 'test_token')
        self.assertEqual(config.telegram_chat_id, '123456')
        self.assertEqual(config.timeout, 10)
        self.assertEqual(config.max_retries, 3)
    
    def test_explicit_values(self) -> None:
        """Test explicit config values."""
        config = WebhookConfig(
            discord_url='https://discord.test',
            slack_url='https://slack.test',
            timeout=30,
            max_retries=5
        )
        self.assertEqual(config.discord_url, 'https://discord.test')
        self.assertEqual(config.timeout, 30)
        self.assertEqual(config.max_retries, 5)
    
    def test_immutable(self) -> None:
        """Test that config is frozen/immutable."""
        config = WebhookConfig()
        with self.assertRaises(FrozenInstanceError):
            config.timeout = 20


class TestWebhookNotifierSync(unittest.TestCase):
    """Tests für synchrone WebhookNotifier Methoden."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = WebhookConfig(
            discord_url='https://discord.com/api/webhooks/discord123',
            slack_url='https://hooks.slack.com/services/slack456',
            telegram_token='tg_token_123',
            telegram_chat_id='tg_chat_456',
            timeout=5
        )
        self.notifier = WebhookNotifier(self.config)
    
    @patch('webhook_notifier.urllib.request.urlopen')
    @patch('webhook_notifier.urllib.request.Request')
    def test_post_json_sync_success(self, mock_request: Mock, mock_urlopen: Mock) -> None:
        """Test successful JSON POST."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        
        result = self.notifier._post_json_sync('https://example.com', {'key': 'value'})
        
        self.assertTrue(result)
        mock_request.assert_called_once()
        mock_urlopen.assert_called_once()
    
    @patch('webhook_notifier.urllib.request.urlopen')
    def test_post_json_sync_http_error(self, mock_urlopen: Mock) -> None:
        """Test POST with HTTP error."""
        from urllib.error import HTTPError
        
        mock_urlopen.side_effect = HTTPError(
            'https://example.com',
            404,
            'Not Found',
            {},
            None
        )
        
        result = self.notifier._post_json_sync('https://example.com', {'key': 'value'})
        self.assertFalse(result)
    
    @patch('webhook_notifier.urllib.request.urlopen')
    def test_post_json_sync_connection_error(self, mock_urlopen: Mock) -> None:
        """Test POST with connection error."""
        mock_urlopen.side_effect = ConnectionError('Connection failed')
        
        result = self.notifier._post_json_sync('https://example.com', {'key': 'value'})
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_post_json_sync')
    def test_notify_discord_success(self, mock_post: Mock) -> None:
        """Test Discord notification success."""
        mock_post.return_value = True
        
        result = self.notifier.notify_discord('Test Title', 'Test Message', color=0xff0000)
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0]
        self.assertIn('discord.com/api/webhooks/discord123', call_args[0])
    
    def test_notify_discord_no_config(self) -> None:
        """Test Discord notification without config."""
        config = WebhookConfig()  # No URLs
        notifier = WebhookNotifier(config)
        
        result = notifier.notify_discord('Test', 'Message')
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_post_json_sync')
    def test_notify_slack_success(self, mock_post: Mock) -> None:
        """Test Slack notification success."""
        mock_post.return_value = True
        
        result = self.notifier.notify_slack('Test message', channel='#general')
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0]
        self.assertIn('hooks.slack.com', call_args[0])
    
    def test_notify_slack_no_config(self) -> None:
        """Test Slack notification without config."""
        config = WebhookConfig()  # No URLs
        notifier = WebhookNotifier(config)
        
        result = notifier.notify_slack('Test message')
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_post_json_sync')
    def test_notify_telegram_success(self, mock_post: Mock) -> None:
        """Test Telegram notification success."""
        mock_post.return_value = True
        
        result = self.notifier.notify_telegram('<b>Test</b> message')
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0]
        self.assertIn('api.telegram.org', call_args[0])
        self.assertIn('tg_token_123', call_args[0])
    
    def test_notify_telegram_no_config(self) -> None:
        """Test Telegram notification without config."""
        config = WebhookConfig()  # No tokens
        notifier = WebhookNotifier(config)
        
        result = notifier.notify_telegram('Test message')
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_notify_guardian_success(self, mock_get_client: Mock) -> None:
        """Test Guardian notification success."""
        mock_client = MagicMock()
        mock_client.notify.return_value = {'sent': True}
        mock_get_client.return_value = mock_client
        
        result = self.notifier.notify_guardian('Test message', priority='high')
        
        self.assertTrue(result)
        mock_client.notify.assert_called_once_with('[SuperMegaBot] Test message', priority='high')
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_notify_guardian_no_client(self, mock_get_client: Mock) -> None:
        """Test Guardian notification without client."""
        mock_get_client.return_value = None
        
        result = self.notifier.notify_guardian('Test message')
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_notify_guardian_exception(self, mock_get_client: Mock) -> None:
        """Test Guardian notification with exception."""
        mock_client = MagicMock()
        mock_client.notify.side_effect = Exception('Guardian error')
        mock_get_client.return_value = mock_client
        
        result = self.notifier.notify_guardian('Test message')
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_check_guardian_health_healthy(self, mock_get_client: Mock) -> None:
        """Test Guardian health check - healthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {'status': 'healthy'}
        mock_get_client.return_value = mock_client
        
        result = self.notifier.check_guardian_health()
        self.assertTrue(result)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_check_guardian_health_unhealthy(self, mock_get_client: Mock) -> None:
        """Test Guardian health check - unhealthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {'status': 'degraded'}
        mock_get_client.return_value = mock_client
        
        result = self.notifier.check_guardian_health()
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_heal_via_guardian_success(self, mock_get_client: Mock) -> None:
        """Test Guardian healing - success."""
        mock_client = MagicMock()
        mock_client.heal_service.return_value = {'healed': True}
        mock_get_client.return_value = mock_client
        
        result = self.notifier.heal_via_guardian('test_service')
        self.assertTrue(result)
        mock_client.heal_service.assert_called_once_with('test_service')
    
    @patch.object(WebhookNotifier, 'notify_discord')
    @patch.object(WebhookNotifier, 'notify_slack')
    @patch.object(WebhookNotifier, 'notify_telegram')
    @patch.object(WebhookNotifier, 'notify_guardian')
    def test_broadcast_all_success(
        self,
        mock_guardian: Mock,
        mock_telegram: Mock,
        mock_slack: Mock,
        mock_discord: Mock
    ) -> None:
        """Test broadcast to all channels - all successful."""
        mock_discord.return_value = True
        mock_slack.return_value = True
        mock_telegram.return_value = True
        mock_guardian.return_value = True
        
        result = self.notifier.broadcast('Test Title', 'Test Message', level='info')
        
        self.assertEqual(result['discord'], True)
        self.assertEqual(result['slack'], True)
        self.assertEqual(result['telegram'], True)
        self.assertEqual(result['guardian'], True)
        
        mock_discord.assert_called_once_with('Test Title', 'Test Message', 0x00ff00)
        mock_slack.assert_called_once_with('*Test Title*\nTest Message')
        mock_telegram.assert_called_once_with('<b>Test Title</b>\nTest Message')
        mock_guardian.assert_called_once_with('Test Title: Test Message', priority='normal')
    
    @patch.object(WebhookNotifier, 'notify_discord')
    @patch.object(WebhookNotifier, 'notify_slack')
    @patch.object(WebhookNotifier, 'notify_telegram')
    @patch.object(WebhookNotifier, 'notify_guardian')
    def test_broadcast_with_level_enum(
        self,
        mock_guardian: Mock,
        mock_telegram: Mock,
        mock_slack: Mock,
        mock_discord: Mock
    ) -> None:
        """Test broadcast with NotificationLevel enum."""
        mock_discord.return_value = True
        mock_slack.return_value = True
        mock_telegram.return_value = True
        mock_guardian.return_value = True
        
        result = self.notifier.broadcast(
            'Warning',
            'Something happened',
            level=NotificationLevel.WARN
        )
        
        mock_discord.assert_called_once_with('Warning', 'Something happened', 0xffaa00)
        mock_guardian.assert_called_once_with('Warning: Something happened', priority='high')
    
    @patch.object(WebhookNotifier, 'notify_discord')
    @patch.object(WebhookNotifier, 'notify_slack')
    @patch.object(WebhookNotifier, 'notify_telegram')
    @patch.object(WebhookNotifier, 'notify_guardian')
    def test_broadcast_partial_failure(
        self,
        mock_guardian: Mock,
        mock_telegram: Mock,
        mock_slack: Mock,
        mock_discord: Mock
    ) -> None:
        """Test broadcast with some failures."""
        mock_discord.return_value = True
        mock_slack.return_value = False
        mock_telegram.return_value = True
        mock_guardian.return_value = False
        
        result = self.notifier.broadcast('Test', 'Message', level='error')
        
        self.assertEqual(result['discord'], True)
        self.assertEqual(result['slack'], False)
        self.assertEqual(result['telegram'], True)
        self.assertEqual(result['guardian'], False)


class TestWebhookNotifierAsync(unittest.TestCase):
    """Tests für asynchrone WebhookNotifier Methoden."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = WebhookConfig(
            discord_url='https://discord.com/api/webhooks/discord123',
            slack_url='https://hooks.slack.com/services/slack456',
            telegram_token='tg_token_123',
            telegram_chat_id='tg_chat_456',
            timeout=5
        )
        self.notifier = WebhookNotifier(self.config)
    
    def run_async(self, coro: Any) -> Any:
        """Helper to run async functions."""
        return asyncio.run(coro)
    
    @unittest.skipUnless(AIOHTTP_AVAILABLE, "aiohttp not installed")
    @patch('aiohttp.ClientSession.post')
    async def test_post_json_async_success(self, mock_post: Mock) -> None:
        """Test async POST success."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__ = MagicMock(return_value=mock_response)
        mock_post.return_value.__aexit__ = MagicMock(return_value=False)
        
        result = await self.notifier._post_json_async(
            'https://example.com',
            {'key': 'value'}
        )
        
        self.assertTrue(result)
    
    @unittest.skipUnless(AIOHTTP_AVAILABLE, "aiohttp not installed")
    @patch('aiohttp.ClientSession.post')
    async def test_post_json_async_failure(self, mock_post: Mock) -> None:
        """Test async POST failure."""
        from aiohttp import ClientError
        mock_post.side_effect = ClientError('Connection failed')
        
        result = await self.notifier._post_json_async(
            'https://example.com',
            {'key': 'value'}
        )
        
        self.assertFalse(result)
    
    @patch.object(WebhookNotifier, '_post_json_sync')
    def test_post_json_async_fallback(self, mock_sync_post: Mock) -> None:
        """Test async fallback to sync when aiohttp unavailable."""
        # Temporarily disable aiohttp
        original_available = AIOHTTP_AVAILABLE
        try:
            import webhook_notifier
            webhook_notifier.AIOHTTP_AVAILABLE = False
            
            mock_sync_post.return_value = True
            
            result = self.run_async(
                self.notifier._post_json_async('https://example.com', {})
            )
            
            self.assertTrue(result)
            mock_sync_post.assert_called_once()
        finally:
            webhook_notifier.AIOHTTP_AVAILABLE = original_available
    
    @patch.object(WebhookNotifier, 'notify_discord_async')
    @patch.object(WebhookNotifier, 'notify_slack_async')
    @patch.object(WebhookNotifier, 'notify_telegram_async')
    @patch.object(WebhookNotifier, 'notify_guardian_async')
    def test_broadcast_async_all_success(
        self,
        mock_guardian: Mock,
        mock_telegram: Mock,
        mock_slack: Mock,
        mock_discord: Mock
    ) -> None:
        """Test async broadcast - all successful."""
        async def mock_coro(*args: Any, **kwargs: Any) -> bool:
            return True
        
        mock_discord.side_effect = mock_coro
        mock_slack.side_effect = mock_coro
        mock_telegram.side_effect = mock_coro
        mock_guardian.side_effect = mock_coro
        
        result = self.run_async(
            self.notifier.broadcast_async('Test', 'Message', level='info')
        )
        
        self.assertEqual(result['discord'], True)
        self.assertEqual(result['slack'], True)
        self.assertEqual(result['telegram'], True)
        self.assertEqual(result['guardian'], True)
    
    @patch.object(WebhookNotifier, 'notify_discord_async')
    @patch.object(WebhookNotifier, 'notify_slack_async')
    @patch.object(WebhookNotifier, 'notify_telegram_async')
    @patch.object(WebhookNotifier, 'notify_guardian_async')
    def test_broadcast_async_with_exception(
        self,
        mock_guardian: Mock,
        mock_telegram: Mock,
        mock_slack: Mock,
        mock_discord: Mock
    ) -> None:
        """Test async broadcast with exceptions."""
        async def mock_coro_true(*args: Any, **kwargs: Any) -> bool:
            return True
        
        async def mock_coro_exception(*args: Any, **kwargs: Any) -> bool:
            raise Exception('Test error')
        
        mock_discord.side_effect = mock_coro_true
        mock_slack.side_effect = mock_coro_exception
        mock_telegram.side_effect = mock_coro_true
        mock_guardian.side_effect = mock_coro_exception
        
        result = self.run_async(
            self.notifier.broadcast_async('Test', 'Message', level='info')
        )
        
        self.assertEqual(result['discord'], True)
        self.assertEqual(result['slack'], False)
        self.assertEqual(result['telegram'], True)
        self.assertEqual(result['guardian'], False)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_check_guardian_health_async(self, mock_get_client: Mock) -> None:
        """Test async Guardian health check."""
        mock_client = MagicMock()
        mock_client.health.return_value = {'status': 'healthy'}
        mock_get_client.return_value = mock_client
        
        result = self.run_async(self.notifier.check_guardian_health_async())
        self.assertTrue(result)
    
    @patch.object(WebhookNotifier, '_get_guardian_client')
    def test_heal_via_guardian_async(self, mock_get_client: Mock) -> None:
        """Test async Guardian healing."""
        mock_client = MagicMock()
        mock_client.heal_service.return_value = {'healed': True}
        mock_get_client.return_value = mock_client
        
        result = self.run_async(self.notifier.heal_via_guardian_async('test_service'))
        self.assertTrue(result)


class TestLegacyFunctions(unittest.TestCase):
    """Tests für Legacy-Funktions-API."""
    
    def setUp(self) -> None:
        """Reset singleton before each test."""
        import webhook_notifier
        webhook_notifier._notifier = None
    
    @patch.object(WebhookNotifier, 'notify_discord')
    def test_notify_discord_legacy(self, mock_notify: Mock) -> None:
        """Test legacy notify_discord function."""
        mock_notify.return_value = True
        
        result = notify_discord('Title', 'Message', 0xff0000)
        
        self.assertTrue(result)
        mock_notify.assert_called_once_with('Title', 'Message', 0xff0000)
    
    @patch.object(WebhookNotifier, 'notify_slack')
    def test_notify_slack_legacy(self, mock_notify: Mock) -> None:
        """Test legacy notify_slack function."""
        mock_notify.return_value = True
        
        result = notify_slack('Test message', '#general')
        
        self.assertTrue(result)
        mock_notify.assert_called_once_with('Test message', '#general')
    
    @patch.object(WebhookNotifier, 'notify_telegram')
    def test_notify_telegram_legacy(self, mock_notify: Mock) -> None:
        """Test legacy notify_telegram function."""
        mock_notify.return_value = True
        
        result = notify_telegram('<b>Test</b>')
        
        self.assertTrue(result)
        mock_notify.assert_called_once_with('<b>Test</b>')
    
    @patch.object(WebhookNotifier, 'notify_guardian')
    def test_notify_guardian_legacy(self, mock_notify: Mock) -> None:
        """Test legacy notify_guardian function."""
        mock_notify.return_value = True
        
        result = notify_guardian('Test message', 'high')
        
        self.assertTrue(result)
        mock_notify.assert_called_once_with('Test message', 'high')
    
    @patch.object(WebhookNotifier, 'check_guardian_health')
    def test_check_guardian_health_legacy(self, mock_check: Mock) -> None:
        """Test legacy check_guardian_health function."""
        mock_check.return_value = True
        
        result = check_guardian_health()
        self.assertTrue(result)
    
    @patch.object(WebhookNotifier, 'heal_via_guardian')
    def test_heal_via_guardian_legacy(self, mock_heal: Mock) -> None:
        """Test legacy heal_via_guardian function."""
        mock_heal.return_value = True
        
        result = heal_via_guardian('my_service')
        self.assertTrue(result)
        mock_heal.assert_called_once_with('my_service')
    
    @patch.object(WebhookNotifier, 'broadcast')
    def test_broadcast_legacy(self, mock_broadcast: Mock) -> None:
        """Test legacy broadcast function."""
        mock_broadcast.return_value = {
            'discord': True,
            'slack': True,
            'telegram': True,
            'guardian': True
        }
        
        result = broadcast('Title', 'Message', 'warn')
        
        self.assertEqual(result['discord'], True)
        mock_broadcast.assert_called_once()


class TestIntegration(unittest.TestCase):
    """Integration-Tests mit Mock-Server."""
    
    def test_full_notification_flow(self) -> None:
        """Test complete notification flow without actual HTTP calls."""
        config = WebhookConfig(
            discord_url='https://discord.test/webhook',
            slack_url='https://slack.test/webhook',
            telegram_token='test_token',
            telegram_chat_id='123456'
        )
        notifier = WebhookNotifier(config)
        
        with patch.object(notifier, '_post_json_sync') as mock_post:
            mock_post.return_value = True
            
            # Test all sync methods
            discord_result = notifier.notify_discord('Test', 'Message')
            slack_result = notifier.notify_slack('Test message')
            telegram_result = notifier.notify_telegram('<b>Test</b>')
            
            self.assertTrue(discord_result)
            self.assertTrue(slack_result)
            self.assertTrue(telegram_result)
            self.assertEqual(mock_post.call_count, 3)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:
    """Load tests with proper ordering."""
    return tests


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
