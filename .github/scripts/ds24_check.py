#!/usr/bin/env python3
"""
DS24 Revenue Monitor — täglicher Report via Telegram.
Vergleicht aktuelle Transaktionszahl mit letztem Stand.
"""
import os, requests, json
from datetime import datetime, timezone, timedelta

DS24_KEY = os.environ["DIGISTORE24_API_KEY"]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

H = {"X-DS-API-KEY": DS24_KEY}

KNOWN_COUNT_FILE = "/tmp/ds24_last_count.txt"


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def get_transactions():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = "2025-01-01"
    r = requests.get(
        f"https://www.digistore24.com/api/call/listTransactions/JSON/?from={start}&to={today}",
        headers=H,
        timeout=15,
    )
    if r.status_code != 200:
        return None, None
    data = r.json().get("data", {})
    summary = data.get("summary", {})
    amounts = summary.get("amounts", {})
    eur = amounts.get("EUR", {}) if isinstance(amounts, dict) else {}
    count = eur.get("count", 0) if isinstance(eur, dict) else 0
    total = eur.get("total_amount", 0) if isinstance(eur, dict) else 0
    return count, total


if __name__ == "__main__":
    count, total = get_transactions()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if count is None:
        send_telegram(f"⚠️ DS24 API nicht erreichbar [{date}]")
        exit(0)

    # Milestone checks
    milestones = [5, 10, 25, 50, 100]
    milestone_msg = ""
    for m in milestones:
        if count == m:
            milestone_msg = f"\n\n🎉 <b>MEILENSTEIN: {m} Verkäufe erreicht!</b>"

    revenue_emoji = "🟢" if total >= 100 else "🟡" if total >= 50 else "🔴"

    send_telegram(
        f"{revenue_emoji} <b>DS24 Daily Report</b> [{date}]\n\n"
        f"💰 Gesamt-Revenue: <b>€{total:.2f}</b>\n"
        f"🛒 Transaktionen: <b>{count}</b>\n"
        f"📦 Produkt 668035: AI Income Machine (€37)\n"
        f"📦 Produkt 704677: SuperMegaBot (€97)\n"
        f"🎯 Ziel: €1.000/Monat\n"
        f"📈 Fortschritt: {min(100, int(total/10))}%"
        f"{milestone_msg}"
    )
    print(f"Report sent: €{total:.2f} ({count} transactions)")
