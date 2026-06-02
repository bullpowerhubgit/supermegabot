#!/usr/bin/env python3
"""
Webhook Notifier — Discord + Slack + Telegram
Integriert in SuperMegaBot + RudiBot Eternal
"""

import os, json, urllib.request, urllib.error, logging
from pathlib import Path

log = logging.getLogger('WebhookNotifier')

DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_URL', '')
SLACK_WEBHOOK   = os.getenv('SLACK_WEBHOOK_URL', '')
TG_TOKEN        = os.getenv('TELEGRAM_BOT_TOKEN', '')
TG_CHAT         = os.getenv('TELEGRAM_CHAT_ID', '')


def _post_json(url, payload):
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as e:
        log.error(f'Webhook POST failed: {e}')
        return False


def notify_discord(title, message, color=0x00ff00):
    if not DISCORD_WEBHOOK:
        return False
    return _post_json(DISCORD_WEBHOOK, {
        'embeds': [{
            'title': title,
            'description': message,
            'color': color,
            'timestamp': __import__('datetime').datetime.utcnow().isoformat()
        }]
    })


def notify_slack(text, channel='#alerts'):
    if not SLACK_WEBHOOK:
        return False
    return _post_json(SLACK_WEBHOOK, {
        'channel': channel,
        'text': text,
        'username': 'RudiBot'
    })


def notify_telegram(message):
    if not TG_TOKEN or not TG_CHAT:
        return False
    url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
    try:
        data = json.dumps({'chat_id': TG_CHAT, 'text': message, 'parse_mode': 'HTML'}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as e:
        log.error(f'Telegram notify failed: {e}')
        return False


def broadcast(title, message, level='info'):
    """Send to all configured channels."""
    color = {'info': 0x00ff00, 'warn': 0xffaa00, 'error': 0xff0000}.get(level, 0x00ff00)
    results = {
        'discord': notify_discord(title, message, color),
        'slack': notify_slack(f'*{title}*\n{message}'),
        'telegram': notify_telegram(f'<b>{title}</b>\n{message}'),
    }
    log.info(f'Broadcast [{level}]: {title} — {results}')
    return results


if __name__ == '__main__':
    broadcast('Test', 'Webhook notifier is ready!', 'info')
