#!/usr/bin/env python3
"""
SuperMegaBot ↔ Revenue Agent Bridge Server

Läuft auf Port 8890 als Nachrichtenbroker zwischen zwei Claude Code Sessions.
Beide Terminals können Nachrichten senden und empfangen.

Start:
  python3 scripts/bridge_server.py

Senden (aus beiden Terminals):
  python3 scripts/bridge_server.py --send "supermegabot" "Hallo vom SMB!"
  python3 scripts/bridge_server.py --send "revenue_agent" "Analyse fertig"

Lesen (polling):
  python3 scripts/bridge_server.py --listen supermegabot
  python3 scripts/bridge_server.py --listen revenue_agent

Status:
  python3 scripts/bridge_server.py --status

API (HTTP):
  POST http://localhost:8890/send   {"to":"revenue_agent","from":"supermegabot","text":"..."}
  GET  http://localhost:8890/inbox/revenue_agent
  GET  http://localhost:8890/status
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("BridgeServer")

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "agent_sync" / "bridge.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

PORT = int(os.getenv("BRIDGE_PORT", "8890"))

AGENTS = {"supermegabot", "revenue_agent"}


# ── SQLite ────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT NOT NULL,
            to_agent   TEXT NOT NULL,
            text       TEXT NOT NULL,
            extra      TEXT DEFAULT '{}',
            read       INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_to_read ON messages(to_agent, read)")
    conn.commit()
    return conn


def _send_msg(from_agent: str, to_agent: str, text: str, extra: dict | None = None) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO messages(from_agent,to_agent,text,extra) VALUES(?,?,?,?)",
            (from_agent, to_agent, text, json.dumps(extra or {}))
        )
        return cur.lastrowid


def _read_msgs(to_agent: str, limit: int = 20, unread_only: bool = True) -> list[dict]:
    with _db() as c:
        q = "SELECT * FROM messages WHERE to_agent=?"
        if unread_only:
            q += " AND read=0"
        q += " ORDER BY id DESC LIMIT ?"
        rows = c.execute(q, (to_agent, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]


def _mark_read(to_agent: str) -> int:
    with _db() as c:
        cur = c.execute("UPDATE messages SET read=1 WHERE to_agent=? AND read=0", (to_agent,))
        return cur.rowcount


def _status() -> dict:
    with _db() as c:
        total   = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        unread  = {}
        for agent in AGENTS:
            unread[agent] = c.execute(
                "SELECT COUNT(*) FROM messages WHERE to_agent=? AND read=0", (agent,)
            ).fetchone()[0]
        recent = c.execute(
            "SELECT from_agent,to_agent,text,created_at FROM messages ORDER BY id DESC LIMIT 5"
        ).fetchall()
    return {
        "total_messages": total,
        "unread":         unread,
        "recent":         [dict(r) for r in recent],
        "db":             str(_DB_PATH),
        "port":           PORT,
    }


# ── HTTP-Server (aiohttp) ─────────────────────────────────────────────────────

async def _handle_send(req):
    from aiohttp import web
    try:
        body       = await req.json()
        from_agent = str(body.get("from", "unknown"))
        to_agent   = str(body.get("to", ""))
        text       = str(body.get("text", "")).strip()
        extra      = body.get("extra", {})
        if not to_agent or not text:
            return web.json_response({"ok": False, "error": "to + text required"}, status=400)
        msg_id = _send_msg(from_agent, to_agent, text, extra)
        _log_to_console(from_agent, to_agent, text)
        return web.json_response({"ok": True, "id": msg_id})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _handle_inbox(req):
    from aiohttp import web
    agent      = req.match_info.get("agent", "")
    unread_only = req.rel_url.query.get("all") != "1"
    msgs       = _read_msgs(agent, limit=20, unread_only=unread_only)
    if msgs:
        _mark_read(agent)
    return web.json_response({"ok": True, "agent": agent, "messages": msgs, "count": len(msgs)})


async def _handle_status(req):
    from aiohttp import web
    return web.json_response({"ok": True, **_status()})


async def _handle_broadcast(req):
    from aiohttp import web
    try:
        body       = await req.json()
        from_agent = str(body.get("from", "unknown"))
        text       = str(body.get("text", "")).strip()
        if not text:
            return web.json_response({"ok": False, "error": "text required"}, status=400)
        ids = []
        for agent in AGENTS:
            if agent != from_agent:
                ids.append(_send_msg(from_agent, agent, text))
                _log_to_console(from_agent, agent, text)
        return web.json_response({"ok": True, "sent_to": list(AGENTS - {from_agent}), "ids": ids})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def _log_to_console(from_agent: str, to_agent: str, text: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] 📨 {from_agent} → {to_agent}:\n  {text[:200]}\n", flush=True)


async def _run_server() -> None:
    from aiohttp import web
    app = web.Application()
    app.router.add_post("/send",              _handle_send)
    app.router.add_post("/broadcast",         _handle_broadcast)
    app.router.add_get( "/inbox/{agent}",     _handle_inbox)
    app.router.add_get( "/status",            _handle_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()

    print(f"""
╔══════════════════════════════════════════════════════╗
║       SuperMegaBot ↔ Revenue Agent Bridge            ║
║  Port: {PORT}  DB: {_DB_PATH.name}                       ║
╠══════════════════════════════════════════════════════╣
║  POST /send         → Nachricht senden               ║
║  GET  /inbox/<agent>→ Nachrichten lesen              ║
║  POST /broadcast    → An alle senden                 ║
║  GET  /status       → Bridge-Status                  ║
╠══════════════════════════════════════════════════════╣
║  Revenue Agent Terminal:                             ║
║  python3 scripts/bridge_server.py --listen revenue_agent
║  SuperMegaBot Terminal:                              ║
║  python3 scripts/bridge_server.py --listen supermegabot
╚══════════════════════════════════════════════════════╝
""", flush=True)

    # Polling: alle 3s neue Nachrichten für BEIDE Agents ausgeben
    while True:
        await asyncio.sleep(3)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli_send(from_agent: str, to_agent: str, text: str) -> None:
    """Sendet via HTTP wenn Server läuft, sonst direkt in DB."""
    try:
        import urllib.request
        payload = json.dumps({"from": from_agent, "to": to_agent, "text": text}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/send",
            data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            result = json.loads(r.read())
            print(f"✅ Gesendet an {to_agent}: id={result.get('id')}")
    except Exception:
        # Server läuft nicht → direkt in DB
        msg_id = _send_msg(from_agent, to_agent, text)
        print(f"✅ Direkt in DB gespeichert: id={msg_id}")


def _cli_listen(agent: str) -> None:
    """Pollt alle 2s auf neue Nachrichten."""
    print(f"👂 Höre auf Nachrichten für '{agent}' (Ctrl+C zum Beenden)...\n")
    seen = set()
    while True:
        try:
            msgs = _read_msgs(agent, limit=20, unread_only=False)
            for m in msgs:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    ts = datetime.fromtimestamp(m["created_at"]).strftime("%H:%M:%S")
                    print(f"[{ts}] 📨 {m['from_agent']}:\n  {m['text']}\n")
            _mark_read(agent)
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nBridge-Listener beendet.")
            break


def _cli_status() -> None:
    s = _status()
    print(f"\n📊 Bridge Status")
    print(f"  Nachrichten gesamt: {s['total_messages']}")
    for agent, cnt in s["unread"].items():
        print(f"  Ungelesen für {agent}: {cnt}")
    print(f"\n  Letzte 5 Nachrichten:")
    for m in s["recent"]:
        ts = datetime.fromtimestamp(m["created_at"]).strftime("%H:%M:%S")
        print(f"    [{ts}] {m['from_agent']} → {m['to_agent']}: {m['text'][:80]}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="SuperMegaBot ↔ Revenue Agent Bridge")
    parser.add_argument("--send",    nargs=2,  metavar=("TO", "TEXT"), help="Nachricht senden")
    parser.add_argument("--from",    dest="from_agent", default="supermegabot", help="Absender-Name")
    parser.add_argument("--listen",  metavar="AGENT",   help="Auf Nachrichten warten")
    parser.add_argument("--status",  action="store_true", help="Bridge-Status anzeigen")
    parser.add_argument("--server",  action="store_true", help="Bridge-Server starten")
    args = parser.parse_args()

    if args.send:
        to_agent, text = args.send
        _cli_send(args.from_agent, to_agent, text)
    elif args.listen:
        _cli_listen(args.listen)
    elif args.status:
        _cli_status()
    else:
        # Default: Server starten
        asyncio.run(_run_server())
