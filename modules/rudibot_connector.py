"""
RudiBot Central Connector (Python)

Verbindet jeden Service mit ~/rudibot für zentrale Datenverwaltung.

Usage:
    from rudibot.connector import rudibot
    rudibot.log('master', 'Server started on :9900')
    rudibot.set_state('master', {'status': 'online', 'port': 9900})
    state = rudibot.get_state('master')
    rudibot.write_data('shopify', 'last_order.json', {...})
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import time
import random
import string

RUDIBOT_HOME = Path(os.environ.get('RUDIBOT_HOME', Path.home() / 'rudibot'))

DIRS = {
    'logs': RUDIBOT_HOME / 'logs',
    'state': RUDIBOT_HOME / 'state',
    'config': RUDIBOT_HOME / 'config',
    'data': RUDIBOT_HOME / 'data',
    'backups': RUDIBOT_HOME / 'backups',
    'shared': RUDIBOT_HOME / 'shared',
    'cache': RUDIBOT_HOME / 'cache',
}


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def _random_id():
    return f"{int(time.time())}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"


class RudiBotConnector:
    def __init__(self):
        self.home = RUDIBOT_HOME
        self.dirs = DIRS
        # Ensure base dirs exist
        for d in DIRS.values():
            _ensure_dir(d)

    # ── Logging ──────────────────────────────────────────────────────────────
    def log(self, service: str, message: str, level: str = 'info'):
        dir_path = DIRS['logs'] / service
        _ensure_dir(dir_path)
        timestamp = datetime.utcnow().isoformat() + 'Z'
        line = f"[{timestamp}] [{level.upper()}] {message}\n"
        file_path = dir_path / f"{datetime.utcnow().strftime('%Y-%m-%d')}.log"
        with open(file_path, 'a') as f:
            f.write(line)
        return line

    # ── State Management ─────────────────────────────────────────────────────
    def set_state(self, service: str, state: dict):
        dir_path = DIRS['state'] / 'services'
        _ensure_dir(dir_path)
        file_path = dir_path / f"{service}.json"
        data = {
            'service': service,
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            **state,
        }
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return data

    def get_state(self, service: str):
        file_path = DIRS['state'] / 'services' / f"{service}.json"
        try:
            with open(file_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def get_all_states(self):
        dir_path = DIRS['state'] / 'services'
        _ensure_dir(dir_path)
        states = {}
        for file in dir_path.glob('*.json'):
            with open(file) as f:
                states[file.stem] = json.load(f)
        return states

    # ── Data Storage ─────────────────────────────────────────────────────────
    def write_data(self, category: str, filename: str, data):
        dir_path = DIRS['data'] / category
        _ensure_dir(dir_path)
        file_path = dir_path / filename
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return str(file_path)

    def read_data(self, category: str, filename: str):
        file_path = DIRS['data'] / category / filename
        try:
            with open(file_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    # ── Config ───────────────────────────────────────────────────────────────
    def get_config(self, service: str):
        file_path = DIRS['config'] / f"{service}.json"
        try:
            with open(file_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def set_config(self, service: str, config: dict):
        _ensure_dir(DIRS['config'])
        file_path = DIRS['config'] / f"{service}.json"
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=2)
        return config

    # ── Shared Events ────────────────────────────────────────────────────────
    def emit(self, event: str, payload: dict = None):
        dir_path = DIRS['shared'] / 'events'
        _ensure_dir(dir_path)
        entry = {
            'event': event,
            'payload': payload or {},
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'id': _random_id(),
        }
        file_path = dir_path / f"{entry['id']}.json"
        with open(file_path, 'w') as f:
            json.dump(entry, f, indent=2)
        return entry

    def get_events(self, limit: int = 50):
        dir_path = DIRS['shared'] / 'events'
        _ensure_dir(dir_path)
        files = sorted(dir_path.glob('*.json'), reverse=True)[:limit]
        events = []
        for file in files:
            with open(file) as f:
                events.append(json.load(f))
        return events

    # ── Cache ────────────────────────────────────────────────────────────────
    def cache_get(self, key: str):
        file_path = DIRS['cache'] / f"{key}.json"
        try:
            with open(file_path) as f:
                content = json.load(f)
            if content.get('expires_at') and datetime.fromisoformat(content['expires_at'].rstrip('Z')) < datetime.utcnow():
                file_path.unlink(missing_ok=True)
                return None
            return content.get('value')
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def cache_set(self, key: str, value, ttl_seconds: int = 3600):
        _ensure_dir(DIRS['cache'])
        file_path = DIRS['cache'] / f"{key}.json"
        data = {
            'value': value,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'expires_at': (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat() + 'Z',
        }
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return data

    # ── Monetization Tracking ────────────────────────────────────────────────
    def track_payment(self, payment: dict):
        dir_path = DIRS['data'] / 'payments'
        _ensure_dir(dir_path)
        entry = {
            **payment,
            'tracked_at': datetime.utcnow().isoformat() + 'Z',
        }
        file_path = dir_path / f"{int(time.time())}-{payment.get('id', 'unknown')}.json"
        with open(file_path, 'w') as f:
            json.dump(entry, f, indent=2)

        # Update revenue summary
        summary_file = dir_path / '_summary.json'
        try:
            with open(summary_file) as f:
                summary = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            summary = {'total_eur': 0, 'count': 0, 'last_payment': None}

        summary['total_eur'] += payment.get('amount_eur', 0)
        summary['count'] += 1
        summary['last_payment'] = entry['tracked_at']
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        return entry

    def get_revenue(self):
        file_path = DIRS['data'] / 'payments' / '_summary.json'
        try:
            with open(file_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'total_eur': 0, 'count': 0, 'last_payment': None}


# Singleton
rudibot = RudiBotConnector()
