#!/usr/bin/env python3
"""
Revenue Agent Bridge — Koordination zwischen zwei Claude Code Sessions.

Kommunikationskanal:
  data/agent_sync/inbox.json   ← Revenue Agent schreibt Kommandos hierein
  data/agent_sync/outbox.json  ← SuperMegaBot schreibt Ergebnisse/Status
  data/agent_sync/coordination.json ← Gemeinsamer Status beider Agents

Unterstützte Kommandos (Revenue Agent → SuperMegaBot):
  revenue_snapshot   — Stripe + DS24 + Shopify Einnahmen abrufen
  trigger_telegram   — Telegram-Promo an Rudolf senden
  create_discount    — Shopify Rabattcode erstellen
  klaviyo_blast      — Klaviyo-Kampagne starten
  smb_outreach       — SMB-Email-Outreach Schritt auslösen
  stripe_poll        — Stripe Events der letzten 24h abfragen
  post_social        — Social-Media-Post auf IG/FB/LinkedIn
  buyer_priority     — Hot-Leads priorisieren und Follow-up triggern
  scheduler_audit    — Scheduler-Abdeckung / nie gelaufene Tasks melden
  full_status        — Kompletter System-Status zurückgeben

API (Dashboard):
  POST /api/revenue-agent/command  — Revenue Agent sendet Kommando
  GET  /api/revenue-agent/status   — Status beider Agents lesen
  GET  /api/revenue-agent/inbox    — Unbearbeitete Kommandos
  GET  /api/revenue-agent/results  — Letzte Ergebnisse lesen

Scheduler: alle 5 Min 'revenue_agent_sync' — liest Inbox + führt aus
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("RevenueAgentBridge")

_BASE      = Path(__file__).resolve().parents[1]
_SYNC_DIR  = _BASE / "data" / "agent_sync"
_INBOX     = _SYNC_DIR / "inbox.json"
_OUTBOX    = _SYNC_DIR / "outbox.json"
_COORD     = _SYNC_DIR / "coordination.json"
_SYNC_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_COMMANDS = frozenset({
    "revenue_snapshot",
    "trigger_telegram",
    "create_discount",
    "klaviyo_blast",
    "smb_outreach",
    "stripe_poll",
    "post_social",
    "buyer_priority",
    "scheduler_audit",
    "full_status",
    "youtube_status",
    "ds24_snapshot",
    "klaviyo_stats",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Koordinationsdatei ────────────────────────────────────────────────────────

def update_my_status(status: str, last_action: str = "") -> None:
    """Aktualisiert SuperMegaBot-Status in coordination.json."""
    coord = _read_json(_COORD, {})
    sessions = coord.setdefault("sessions", {})
    sessions.setdefault("supermegabot_main", {})
    sessions["supermegabot_main"]["current_status"] = status
    sessions["supermegabot_main"]["last_updated"]   = _now()
    if last_action:
        sessions["supermegabot_main"]["last_action"] = last_action
    _write_json(_COORD, coord)


def get_coordination() -> dict:
    return _read_json(_COORD, {})


# ── Inbox / Outbox ────────────────────────────────────────────────────────────

def write_command(command: str, params: dict | None = None, sender: str = "revenue_agent") -> str:
    """Revenue Agent schreibt ein Kommando in die Inbox."""
    if command not in SUPPORTED_COMMANDS:
        raise ValueError(f"Unbekanntes Revenue-Agent-Kommando: {command}")
    inbox   = _read_json(_INBOX, {"commands": []})
    cmd_id  = f"cmd_{int(time.time() * 1000)}"
    inbox["commands"].append({
        "id":        cmd_id,
        "command":   command,
        "params":    params or {},
        "sender":    sender,
        "created_at": _now(),
        "status":    "pending",
    })
    _write_json(_INBOX, inbox)
    log.info("Kommando eingereiht: %s (id=%s)", command, cmd_id)
    return cmd_id


def write_result(cmd_id: str, result: dict) -> None:
    """SuperMegaBot schreibt Ergebnis in Outbox (Revenue Agent liest dort)."""
    outbox = _read_json(_OUTBOX, {"results": []})
    outbox["results"].append({
        "cmd_id":    cmd_id,
        "result":    result,
        "written_at": _now(),
    })
    # Nur letzte 50 Ergebnisse behalten
    outbox["results"] = outbox["results"][-50:]
    _write_json(_OUTBOX, outbox)


def get_pending_commands() -> list[dict]:
    """Gibt alle offenen (pending) Kommandos zurück."""
    inbox = _read_json(_INBOX, {"commands": []})
    return [c for c in inbox.get("commands", []) if c.get("status") == "pending"]


def mark_done(cmd_id: str) -> None:
    inbox = _read_json(_INBOX, {"commands": []})
    for c in inbox.get("commands", []):
        if c["id"] == cmd_id:
            c["status"]    = "done"
            c["done_at"]   = _now()
    _write_json(_INBOX, inbox)


def mark_processing(cmd_id: str, worker: str = "supermegabot_main") -> bool:
    inbox = _read_json(_INBOX, {"commands": []})
    for c in inbox.get("commands", []):
        if c.get("id") != cmd_id:
            continue
        if c.get("status") != "pending":
            return False
        c["status"] = "processing"
        c["worker"] = worker
        c["started_at"] = _now()
        _write_json(_INBOX, inbox)
        return True
    return False


def get_results(limit: int = 10) -> list[dict]:
    """Revenue Agent liest Ergebnisse aus Outbox."""
    outbox = _read_json(_OUTBOX, {"results": []})
    return outbox.get("results", [])[-limit:]


# ── Kommando-Ausführung ───────────────────────────────────────────────────────

async def execute_command(cmd: dict) -> dict[str, Any]:
    """Führt ein Kommando aus und gibt Ergebnis zurück."""
    command = cmd.get("command", "")
    params  = cmd.get("params", {})
    log.info("Ausführe: %s", command)

    try:
        if command == "revenue_snapshot":
            return await _cmd_revenue_snapshot()
        elif command == "trigger_telegram":
            return await _cmd_trigger_telegram(params)
        elif command == "create_discount":
            return await _cmd_create_discount(params)
        elif command == "klaviyo_blast":
            return await _cmd_klaviyo_blast(params)
        elif command == "smb_outreach":
            return await _cmd_smb_outreach()
        elif command == "stripe_poll":
            return await _cmd_stripe_poll()
        elif command == "post_social":
            return await _cmd_post_social(params)
        elif command == "buyer_priority":
            return await _cmd_buyer_priority(params)
        elif command == "scheduler_audit":
            return await _cmd_scheduler_audit()
        elif command == "full_status":
            return await _cmd_full_status()
        elif command == "youtube_status":
            return await _cmd_youtube_status()
        elif command == "ds24_snapshot":
            return await _cmd_ds24_snapshot()
        elif command == "klaviyo_stats":
            return await _cmd_klaviyo_stats()
        else:
            return {"ok": False, "command": command, "error": f"Unbekanntes Kommando: {command}"}
    except Exception as e:
        log.error("Kommando %s fehlgeschlagen: %s", command, e)
        return {"ok": False, "command": command, "error": str(e)[:300]}


# ── Konkrete Kommandos ────────────────────────────────────────────────────────

async def _cmd_revenue_snapshot() -> dict:
    """Stripe + DS24 + Shopify Einnahmen zusammenfassen."""
    result: dict[str, Any] = {"command": "revenue_snapshot", "ok": True}

    # Stripe
    try:
        from modules.stripe_payment_hook import get_payment_stats
        result["stripe"] = await get_payment_stats()
    except Exception as e:
        result["stripe"] = {"error": str(e)[:100]}

    # Shopify (Bestellungen heute)
    try:
        import aiohttp
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        ver    = os.getenv("SHOPIFY_API_VERSION", "2024-01")
        if domain and token:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{domain}/admin/api/{ver}/orders/count.json?status=any&created_at_min={_today()}",
                    headers={"X-Shopify-Access-Token": token},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json()
                    result["shopify_orders_today"] = data.get("count", 0)
    except Exception as e:
        result["shopify"] = {"error": str(e)[:100]}

    # DS24
    try:
        from modules.digistore24_integration import get_recent_sales
        result["ds24"] = await get_recent_sales(days=1)
    except Exception:
        result["ds24"] = {"note": "DS24 Modul nicht verfügbar"}

    result["snapshot_at"] = _now()
    return result


async def _cmd_trigger_telegram(params: dict) -> dict:
    """Sendet eine Telegram-Nachricht an Rudolf."""
    import aiohttp
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return {"ok": False, "error": "Telegram-Credentials fehlen"}

    text = params.get("text", "")
    if not text:
        return {"ok": False, "error": "Kein Text angegeben"}

    msg = f"🤝 <b>Revenue Agent:</b>\n{text}"
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            ok = r.status == 200
    return {"ok": ok, "sent": text[:100]}


async def _cmd_create_discount(params: dict) -> dict:
    """Erstellt einen Shopify-Rabattcode."""
    try:
        from modules.shopify_client import ShopifyClient
        client = ShopifyClient()
        code   = params.get("code", f"REVENUE{int(time.time())%10000}")
        pct    = params.get("percent", 10)
        result = await client.create_discount_code(code=code, percent=pct)
        return {"ok": True, "code": code, "percent": pct, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _cmd_klaviyo_blast(params: dict) -> dict:
    """Startet eine Klaviyo-Kampagne."""
    try:
        from modules.klaviyo_integration import send_campaign
        subject = params.get("subject", "Sonderangebot für dich!")
        body    = params.get("body", "Entdecke unsere neuesten Smart-Home-Deals auf https://ineedit.com.co")
        result  = await send_campaign(subject=subject, body=body)
        return {"ok": True, "subject": subject, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _cmd_smb_outreach() -> dict:
    """Startet einen SMB-Outreach-Durchlauf."""
    try:
        from modules.smb_outreach_auto import task_smb_outreach_daily
        result = await task_smb_outreach_daily()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _cmd_stripe_poll() -> dict:
    """Stripe Events der letzten 24h abfragen."""
    try:
        from modules.stripe_payment_hook import task_stripe_payment_poll
        return await task_stripe_payment_poll()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _cmd_post_social(params: dict) -> dict:
    """Postet auf Social Media."""
    try:
        from modules.post_gateway import safe_post_all
        text     = params.get("text", "")
        platform = params.get("platform", "all")
        if not text:
            return {"ok": False, "error": "Kein Text angegeben"}
        result = await safe_post_all(text=text, platform=platform)
        return {"ok": True, "platform": platform, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _cmd_full_status() -> dict:
    """Vollständiger System-Status."""
    import aiohttp
    status: dict[str, Any] = {"command": "full_status", "ok": True, "at": _now()}

    # Health
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "http://localhost:8888/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                status["dashboard"] = await r.json()
    except Exception:
        status["dashboard"] = {"ok": False}

    # Stripe
    try:
        from modules.stripe_payment_hook import get_payment_stats
        status["stripe"] = await get_payment_stats()
    except Exception as e:
        status["stripe"] = {"error": str(e)[:80]}

    try:
        from modules.buyer_intent_router import get_hot_leads
        hot = await get_hot_leads(limit=3, hours=96)
        status["buyer_pipeline"] = {
            "ok": hot.get("ok", False),
            "count": hot.get("count", 0),
            "top_leads": hot.get("leads", [])[:3],
            "reason": hot.get("reason"),
        }
    except Exception as e:
        status["buyer_pipeline"] = {"ok": False, "error": str(e)[:120]}

    try:
        from core.automation_scheduler import get_scheduler_audit
        status["scheduler_audit"] = get_scheduler_audit(limit=10)
    except Exception as e:
        status["scheduler_audit"] = {"ok": False, "error": str(e)[:120]}

    # Koordination
    status["coordination"] = get_coordination()
    return status


async def _cmd_buyer_priority(params: dict) -> dict:
    """Fuehrt Hot-Lead-Priorisierung sofort aus."""
    try:
        from modules.buyer_intent_router import run_buyer_priority_cycle
        limit = int(params.get("limit", 5) or 5)
        result = await run_buyer_priority_cycle(limit=max(1, min(limit, 20)))
        return {"ok": bool(result.get("ok")), "command": "buyer_priority", "result": result}
    except Exception as e:
        return {"ok": False, "command": "buyer_priority", "error": str(e)[:200]}


async def _cmd_youtube_status() -> dict:
    """Prüft ob YouTube OAuth-Credentials gesetzt sind."""
    yt_id      = bool(os.getenv("YOUTUBE_CLIENT_ID"))
    yt_secret  = bool(os.getenv("YOUTUBE_CLIENT_SECRET"))
    yt_refresh = bool(os.getenv("YOUTUBE_REFRESH_TOKEN"))
    return {
        "ok": True,
        "configured": yt_id and yt_secret and yt_refresh,
        "client_id": yt_id,
        "secret": yt_secret,
        "refresh_token": yt_refresh,
    }


async def _cmd_ds24_snapshot() -> dict:
    """DS24 Einnahmen der letzten 7 Tage."""
    try:
        from modules.digistore24_integration import get_recent_sales
        return await get_recent_sales(days=7)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _cmd_klaviyo_stats() -> dict:
    """Klaviyo Subscriber-Anzahl abfragen."""
    import aiohttp as _aiohttp
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        return {"ok": False, "error": "no key"}
    try:
        async with _aiohttp.ClientSession() as s:
            async with s.get(
                "https://a.klaviyo.com/api/profiles/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {key}",
                    "revision": "2024-10-15",
                },
                params={"page[size]": 1},
                timeout=_aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                count = data.get("meta", {}).get("total", "?")
                return {"ok": True, "total_profiles": count}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


async def _cmd_scheduler_audit() -> dict:
    """Liefert Registry-Abdeckung fuer autonome Reparatur-Loops."""
    try:
        from core.automation_scheduler import get_scheduler_audit
        audit = get_scheduler_audit(limit=25)
        return {"ok": True, "command": "scheduler_audit", "audit": audit}
    except Exception as e:
        return {"ok": False, "command": "scheduler_audit", "error": str(e)[:200]}


# ── Scheduler-Task ────────────────────────────────────────────────────────────

async def task_revenue_agent_sync() -> dict[str, Any]:
    """Läuft alle 5 Min: liest Inbox, führt Kommandos aus, schreibt Ergebnisse."""
    pending = get_pending_commands()
    if not pending:
        update_my_status("idle — keine Kommandos")
        return {"ok": True, "processed": 0}

    processed = 0
    errors    = 0
    for cmd in pending:
        cmd_id = cmd["id"]
        if not mark_processing(cmd_id):
            continue
        update_my_status(f"verarbeite: {cmd['command']}", last_action=cmd["command"])
        result = await execute_command(cmd)
        write_result(cmd_id, result)
        mark_done(cmd_id)
        if result.get("ok"):
            processed += 1
        else:
            errors += 1
        log.info("Kommando %s → %s", cmd["command"], "✅" if result.get("ok") else "❌")

    update_my_status("idle — bereit", last_action=f"{processed} Kommandos verarbeitet")
    return {"ok": True, "processed": processed, "errors": errors}


# ── Öffentliche API (für Dashboard-Routen) ───────────────────────────────────

async def get_bridge_status() -> dict[str, Any]:
    """Gibt vollständigen Bridge-Status zurück (für GET /api/revenue-agent/status)."""
    pending_commands = get_pending_commands()
    return {
        "ok":           True,
        "supported_commands": sorted(SUPPORTED_COMMANDS),
        "coordination": get_coordination(),
        "pending":      len(pending_commands),
        "pending_commands": pending_commands[:10],
        "recent_results": get_results(5),
        "at":           _now(),
    }


async def post_command_from_api(command: str, params: dict) -> dict[str, Any]:
    """Kommando über API einreihen (für POST /api/revenue-agent/command)."""
    try:
        cmd_id = write_command(command, params, sender="api")
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    # Sofort ausführen (nicht auf Scheduler warten)
    pending = get_pending_commands()
    for cmd in pending:
        if cmd["id"] == cmd_id:
            if not mark_processing(cmd_id, worker="api_inline"):
                return {"ok": False, "cmd_id": cmd_id, "error": "Kommando wird bereits verarbeitet"}
            result = await execute_command(cmd)
            write_result(cmd_id, result)
            mark_done(cmd_id)
            return {"ok": bool(result.get("ok")), "cmd_id": cmd_id, "result": result}
    return {"ok": False, "error": "Kommando nicht gefunden"}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    tmp.replace(path)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [BRIDGE] %(message)s")
    parser = argparse.ArgumentParser(description="Revenue Agent Bridge")
    parser.add_argument("--command", help="Kommando senden (revenue_snapshot|full_status|stripe_poll|...)")
    parser.add_argument("--sync",    action="store_true", help="Inbox verarbeiten")
    parser.add_argument("--status",  action="store_true", help="Bridge-Status anzeigen")
    args = parser.parse_args()

    async def main():
        if args.command:
            cmd_id = write_command(args.command, {}, sender="cli")
            print(f"Kommando eingereiht: {args.command} (id={cmd_id})")
            result = await task_revenue_agent_sync()
            results = get_results(1)
            if results:
                print(json.dumps(results[-1], indent=2, ensure_ascii=False, default=str))
        elif args.sync:
            result = await task_revenue_agent_sync()
            print(json.dumps(result, indent=2))
        elif args.status:
            status = await get_bridge_status()
            print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
        else:
            parser.print_help()

    asyncio.run(main())
