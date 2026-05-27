#!/usr/bin/env python3
"""🤖 Micro-AI — Tägliche KI-Trends, E-Commerce Tipps via Ollama"""
import sys, os, time, json, datetime, urllib.request
from pathlib import Path

ARMY_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = ARMY_DIR / "shared"
sys.path.insert(0, str(SHARED_DIR))
from bus import report, notify_telegram

ID = "micro_ai"
INTERVAL = 86400  # Täglich
OLLAMA_URL = "http://localhost:11434/api/generate"

DAILY_TOPICS = [
    "Was sind heute die 3 besten Dropshipping-Produkte zum Verkaufen? Kurz, stichpunktartig.",
    "3 E-Commerce Marketing Tipps für heute. Kurz und konkret.",
    "Welche Shopify-Optimierungen bringen heute den größten ROI? Max 3 Punkte.",
    "3 trending Social-Media Themen für E-Commerce heute.",
    "Welche KI-Tools können heute mein Online-Business am meisten verbessern? Max 3.",
    "3 konkrete SEO-Tipps für einen Shopify-Store heute.",
    "Welche Automatisierungen sparen heute am meisten Zeit im E-Commerce?",
]

def ask_ollama(prompt: str, model: str = "llama3.2") -> str:
    try:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 200, "temperature": 0.7}
        }).encode()
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=60)
        data = json.loads(r.read())
        return data.get("response", "").strip()
    except Exception as e:
        return f"Ollama nicht erreichbar: {e}"

def run():
    print(f"[{ID}] 🤖 Micro-AI gestartet")
    day_index = 0
    # Warte 10min vor erstem Run damit Ollama hochgefahren ist
    time.sleep(600)

    while True:
        topic = DAILY_TOPICS[day_index % len(DAILY_TOPICS)]
        day_index += 1

        answer = ask_ollama(topic)
        today = datetime.date.today().isoformat()

        if answer and "nicht erreichbar" not in answer:
            notify_telegram(
                f"🤖 <b>KI-Tipp des Tages</b> ({today})\n\n"
                f"<i>{topic[:60]}...</i>\n\n"
                f"{answer[:600]}"
            )
            report(ID, "ok", f"KI-Tipp gesendet: {topic[:50]}", {"date": today})
        else:
            report(ID, "warning", "Ollama nicht erreichbar", {"error": answer})

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
