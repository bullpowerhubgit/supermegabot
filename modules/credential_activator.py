"""
Credential Activator — Vollautonome Plattform-Aktivierung
==========================================================
Läuft jede Stunde. Sobald ein neuer API-Key in den Env-Vars auftaucht:
  1. Erkennt automatisch welche Plattform damit aktiviert wird
  2. Startet sofort einen ersten Test-Lauf
  3. Sendet Telegram-Bestätigung
  4. Merkt sich den Key-Stand (keine Doppel-Aktivierungen)

Kein Neustart, kein manueller Schritt außer dem Setzen des Keys in Railway.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import aiohttp

log = logging.getLogger("CredentialActivator")

BASE_DIR   = Path(__file__).parent.parent
STATE_FILE = BASE_DIR / "data" / "activated_credentials.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


# ── Plattform-Registry: Key → Aktivierungslogik ──────────────────────────────

PLATFORMS: list[dict] = [
    {
        "name":        "dev.to",
        "env_keys":    ["DEVTO_API_KEY"],
        "description": "dev.to Artikel-Publisher (täglich KI-Artikel)",
        "test_fn":     "modules.dev_to_publisher.run_dev_to_post",
        "schedule":    "daily",
    },
    {
        "name":        "Hashnode",
        "env_keys":    ["HASHNODE_TOKEN", "HASHNODE_PUBLICATION_ID"],
        "description": "Hashnode Blog-Publisher (täglich KI-Artikel)",
        "test_fn":     "modules.hashnode_publisher.run_hashnode_post",
        "schedule":    "daily",
    },
    {
        "name":        "Reddit",
        "env_keys":    ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"],
        "description": "Reddit Viral-Traffic (alle 6h)",
        "test_fn":     "modules.reddit_autoposter.run_reddit_blast",
        "schedule":    "6h",
    },
    {
        "name":        "Gumroad",
        "env_keys":    ["GUMROAD_ACCESS_TOKEN"],
        "description": "Gumroad Revenue-Dashboard + Produkt-Sync",
        "test_fn":     "modules.gumroad_client.get_products",
        "schedule":    "daily",
    },
    {
        "name":        "Medium",
        "env_keys":    ["MEDIUM_INTEGRATION_TOKEN"],
        "description": "Medium Artikel-Publisher (täglich)",
        "test_fn":     None,
        "schedule":    "daily",
    },
    {
        "name":        "TikTok",
        "env_keys":    ["TIKTOK_ACCESS_TOKEN", "TIKTOK_APP_KEY"],
        "description": "TikTok Shop + Produkt-Sync",
        "test_fn":     "modules.tiktok_sync.run_tiktok_sync",
        "schedule":    "6h",
    },
    {
        "name":        "WhatsApp",
        "env_keys":    ["WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN"],
        "description": "WhatsApp Business Broadcast",
        "test_fn":     None,
        "schedule":    "daily",
    },
    {
        "name":        "Pinterest",
        "env_keys":    ["PINTEREST_ACCESS_TOKEN"],
        "description": "Pinterest Produkt-Pins (täglich)",
        "test_fn":     "modules.pinterest_autonomy.run_pinterest_blast",
        "schedule":    "daily",
    },
    {
        "name":        "YouTube",
        "env_keys":    ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
        "description": "YouTube Shorts + Video-Upload",
        "test_fn":     None,
        "schedule":    "daily",
    },
    {
        "name":        "eBay",
        "env_keys":    ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"],
        "description": "eBay Listing-Automation",
        "test_fn":     "modules.ebay_automation.run_ebay_blast",
        "schedule":    "daily",
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _platform_key_snapshot(platform: dict) -> str:
    """Fingerprint der aktuellen Env-Werte für diese Platform."""
    vals = [os.getenv(k, "") for k in platform["env_keys"]]
    return "|".join(v[:10] for v in vals)


def _platform_active(platform: dict) -> bool:
    """True wenn alle Env-Keys nicht leer und nicht Placeholder."""
    for k in platform["env_keys"]:
        v = os.getenv(k, "")
        if not v or v.startswith("BLOCKER") or v in ("YOUR_KEY_HERE", "PLACEHOLDER"):
            return False
    return True


async def _tg(msg: str) -> None:
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def _run_test(fn_path: str) -> dict:
    """Importiert und ruft die Test-Funktion auf."""
    if not fn_path:
        return {"ok": True, "skipped": True}
    try:
        module_path, fn_name = fn_path.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(module_path)
        fn  = getattr(mod, fn_name)
        result = await fn()
        return result if isinstance(result, dict) else {"ok": True, "result": str(result)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


# ── Haupt-Scan ────────────────────────────────────────────────────────────────

async def run_credential_scan() -> dict:
    """
    Prüft alle Plattformen.
    Neu aktivierte Plattformen → sofort Test-Lauf + Telegram-Alert.
    """
    state     = _load_state()
    newly     = []
    still_off = []
    already   = []

    for platform in PLATFORMS:
        name      = platform["name"]
        snapshot  = _platform_key_snapshot(platform)
        active    = _platform_active(platform)
        prev_snap = state.get(name, {}).get("snapshot", "")

        if not active:
            still_off.append({"platform": name, "missing": [
                k for k in platform["env_keys"] if not os.getenv(k, "")
            ]})
            continue

        if snapshot == prev_snap:
            already.append(name)
            continue

        # ─── NEU AKTIVIERT ───────────────────────────────────────────────────
        log.info("Credential Activator: %s NEU AKTIVIERT — starte Test-Lauf", name)
        test_result = await _run_test(platform.get("test_fn", ""))

        state[name] = {
            "snapshot":    snapshot,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_test":   test_result,
        }
        newly.append({"platform": name, "test": test_result})

        status_icon = "✅" if test_result.get("ok") else "⚠️"
        await _tg(
            f"🔑 *Credential Activator: {name} aktiviert!*\n"
            f"{status_icon} Test-Lauf: {'OK' if test_result.get('ok') else 'Fehler'}\n"
            f"Beschreibung: {platform['description']}\n"
            f"Schedule: {platform['schedule']}"
        )

    _save_state(state)

    if not newly:
        log.info("Credential Activator: keine neuen Keys — %d aktiv, %d ausstehend",
                 len(already), len(still_off))

    return {
        "newly_activated": newly,
        "already_active":  already,
        "pending":         still_off,
        "total_platforms": len(PLATFORMS),
        "active_count":    len(already) + len(newly),
    }


def get_activation_status() -> dict:
    """Dashboard: welche Plattformen sind aktiv/inaktiv."""
    state = _load_state()
    result = []
    for p in PLATFORMS:
        active = _platform_active(p)
        result.append({
            "platform":     p["name"],
            "description":  p["description"],
            "active":       active,
            "schedule":     p["schedule"],
            "activated_at": state.get(p["name"], {}).get("activated_at"),
            "missing_keys": [] if active else [k for k in p["env_keys"] if not os.getenv(k, "")],
        })
    active_count = sum(1 for r in result if r["active"])
    return {
        "platforms":    result,
        "active":       active_count,
        "inactive":     len(result) - active_count,
        "total":        len(result),
    }
