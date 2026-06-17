#!/usr/bin/env python3
"""Bot status check — getMe + getUpdates."""
import json, os, urllib.request
from pathlib import Path

env_file = Path('/Users/rudolfsarkany/supermegabot/.env')
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or ""

def tg(method, payload=None):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

if not TOKEN:
    print("ERROR: No TELEGRAM_BOT_TOKEN found")
    exit(1)

print("=== BOT STATUS ===")
me = tg("getMe")
if me.get("ok"):
    b = me["result"]
    print(f"Bot: @{b['username']} (ID: {b['id']}) — online ✅")
else:
    print(f"Bot offline ❌: {me}")

print("\n=== RECENT UPDATES ===")
updates = tg("getUpdates", {"limit": 10, "allowed_updates": ["message", "callback_query"]})
if updates.get("ok"):
    items = updates["result"]
    if not items:
        print("No recent updates.")
    else:
        users = set()
        for u in items:
            msg = u.get("message") or u.get("callback_query", {}).get("message", {})
            sender = u.get("message", {}).get("from") or u.get("callback_query", {}).get("from", {})
            if sender:
                users.add(f"@{sender.get('username','?')} (ID:{sender.get('id','?')})")
            text = msg.get("text", "") if msg else ""
            print(f"  [{u['update_id']}] {sender.get('username','?')}: {text[:60]}")
        print(f"\nActive users: {users}")
else:
    print(f"getUpdates failed: {updates}")
