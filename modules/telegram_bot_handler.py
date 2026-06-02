#!/usr/bin/env python3
"""
Telegram Bot Handler
Auto-captures Chat-ID, handles /start /status /help /chatid commands.
Runs as polling loop alongside the dashboard.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import aiohttp

log = logging.getLogger("TelegramBot")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

_CHAT_ID_FILE = DATA_DIR / "telegram_chat_ids.json"
_OFFSET_FILE  = DATA_DIR / "telegram_offset.txt"


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{_token()}/{method}"


def _load_chat_ids() -> Dict:
    if _CHAT_ID_FILE.exists():
        try:
            return json.loads(_CHAT_ID_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_chat_ids(data: Dict):
    _CHAT_ID_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _get_offset() -> int:
    try:
        return int(_OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def _save_offset(offset: int):
    _OFFSET_FILE.write_text(str(offset))


def _save_primary_chat_id(chat_id: int, username: str = ""):
    """Save as TELEGRAM_CHAT_ID in .env if not already set."""
    env_path = BASE_DIR / ".env"
    current = os.getenv("TELEGRAM_CHAT_ID", "")
    if current:
        return  # already set

    os.environ["TELEGRAM_CHAT_ID"] = str(chat_id)

    if env_path.exists():
        lines = env_path.read_text().splitlines()
        updated = False
        for i, line in enumerate(lines):
            if "TELEGRAM_CHAT_ID" in line:
                lines[i] = f"TELEGRAM_CHAT_ID={chat_id}  # {username}"
                updated = True
                break
        if not updated:
            for i, line in enumerate(lines):
                if line.startswith("TELEGRAM_BOT_TOKEN"):
                    lines.insert(i + 1, f"TELEGRAM_CHAT_ID={chat_id}  # {username}")
                    break
        env_path.write_text("\n".join(lines) + "\n")
        log.info(f"TELEGRAM_CHAT_ID={chat_id} in .env gespeichert")


async def _send(chat_id: int, text: str, parse_mode: str = "HTML"):
    if not _token():
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(_api("sendMessage"), json={
                "chat_id":    chat_id,
                "text":       text,
                "parse_mode": parse_mode,
            })
    except Exception as e:
        log.error(f"send error: {e}")


async def _handle_message(msg: Dict):
    chat    = msg.get("chat", {})
    chat_id = chat.get("id")
    user    = msg.get("from", {})
    username = user.get("username", "") or user.get("first_name", "")
    text    = msg.get("text", "")

    if not chat_id:
        return

    # Auto-save chat IDs
    chat_ids = _load_chat_ids()
    if str(chat_id) not in chat_ids:
        chat_ids[str(chat_id)] = {
            "username": username,
            "type":     chat.get("type", ""),
            "first_seen": datetime.now().isoformat(),
        }
        _save_chat_ids(chat_ids)
        _save_primary_chat_id(chat_id, username)
        log.info(f"Neuer Chat gespeichert: {chat_id} (@{username})")

    if not text:
        return

    cmd = text.split()[0].lower().replace("/", "").replace("@dudirudibot", "")

    if cmd in ("start", "hallo", "hello"):
        await _send(chat_id,
            f"👋 <b>SuperMegaBot aktiv!</b>\n\n"
            f"Deine Chat-ID: <code>{chat_id}</code>\n"
            f"Username: @{username}\n\n"
            f"✅ Alle Alerts werden jetzt an dich gesendet.\n\n"
            f"Befehle: /status /revenue /system /help"
        )

    elif cmd == "chatid":
        await _send(chat_id, f"📋 Deine Chat-ID: <code>{chat_id}</code>")

    elif cmd == "status":
        await _handle_status(chat_id)

    elif cmd == "revenue":
        await _handle_revenue(chat_id)

    elif cmd == "system":
        await _handle_system(chat_id)

    elif cmd == "help":
        await _send(chat_id,
            "🤖 <b>SuperMegaBot Befehle</b>\n\n"
            "/status — System-Status\n"
            "/revenue — Umsatz-Übersicht\n"
            "/system — CPU/RAM/Disk\n"
            "/chatid — Deine Chat-ID\n"
            "/help — Diese Hilfe"
        )

    elif cmd == "test":
        await _send(chat_id, "✅ Bot funktioniert!")


async def _handle_status(chat_id: int):
    try:
        from core.bot_clones import get_bot_status
        d = await get_bot_status()
        bots = d.get("bots", [])
        ok   = sum(1 for b in bots if b.get("ok"))
        lines = [f"{'✅' if b.get('ok') else '❌'} {b['icon']} {b['name']} ({b.get('ms',0)}ms)" for b in bots]
        await _send(chat_id,
            f"🤖 <b>Bot-Status</b> — {ok}/{len(bots)} OK\n\n" + "\n".join(lines)
        )
    except Exception as e:
        await _send(chat_id, f"⚠️ Status-Fehler: {e}")


async def _handle_revenue(chat_id: int):
    parts = []
    # Shopify cache
    f = DATA_DIR / "shopify_cache.json"
    if f.exists():
        try:
            d = json.loads(f.read_text())
            parts.append(f"🛍 Shopify: {d.get('orders','?')} Bestellungen")
        except Exception:
            pass
    # Digistore
    f = DATA_DIR / "digistore_orders.json"
    if f.exists():
        try:
            orders = json.loads(f.read_text())
            parts.append(f"🏪 Digistore24: {len(orders)} Bestellungen")
        except Exception:
            pass
    # Stripe cache
    f = DATA_DIR / "stripe_cache.json"
    if f.exists():
        try:
            d = json.loads(f.read_text())
            rev = d.get("revenue", {}).get("revenue", {})
            revstr = " | ".join(f"{v:.2f} {c}" for c, v in rev.items()) if rev else "€0"
            parts.append(f"💳 Stripe (30d): {revstr}")
        except Exception:
            pass
    if not parts:
        parts = ["Noch keine Umsatzdaten gecacht"]
    await _send(chat_id, "💰 <b>Revenue-Übersicht</b>\n\n" + "\n".join(parts))


async def _handle_system(chat_id: int):
    try:
        import psutil
        cpu  = psutil.cpu_percent(interval=0.5)
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        await _send(chat_id,
            f"🖥 <b>System</b>\n\n"
            f"CPU: {cpu:.0f}%\n"
            f"RAM: {mem.percent:.0f}% ({mem.used//1024//1024}MB / {mem.total//1024//1024}MB)\n"
            f"Disk: {disk.percent:.0f}% ({disk.used//1024//1024//1024}GB / {disk.total//1024//1024//1024}GB)"
        )
    except Exception as e:
        await _send(chat_id, f"⚠️ Systeminfo-Fehler: {e}")


# ── Polling loop ──────────────────────────────────────────────────────────────

class TelegramPoller:
    def __init__(self):
        self._running = False

    async def start(self):
        if not _token():
            log.warning("TELEGRAM_BOT_TOKEN nicht gesetzt — Polling deaktiviert")
            return
        self._running = True
        log.info("Telegram Polling gestartet (@DudiRudibot)")
        # Notify on startup if chat ID known
        chat_id_env = os.getenv("TELEGRAM_CHAT_ID", "")
        if chat_id_env:
            try:
                await _send(int(chat_id_env),
                    f"🚀 <b>SuperMegaBot gestartet</b>\n"
                    f"{datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                    f"Dashboard: http://localhost:{os.getenv('DASHBOARD_PORT','8888')}"
                )
            except Exception:
                pass
        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False

    async def _poll_loop(self):
        offset = _get_offset()
        while self._running:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as s:
                    async with s.get(_api("getUpdates"), params={
                        "offset":  offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    }) as r:
                        if r.status == 200:
                            data = await r.json()
                            for update in data.get("result", []):
                                update_id = update.get("update_id", 0)
                                offset = update_id + 1
                                _save_offset(offset)
                                if "message" in update:
                                    await _handle_message(update["message"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Polling Fehler: {e}")
                await asyncio.sleep(5)


_poller: Optional[TelegramPoller] = None


def get_poller() -> TelegramPoller:
    global _poller
    if _poller is None:
        _poller = TelegramPoller()
    return _poller
