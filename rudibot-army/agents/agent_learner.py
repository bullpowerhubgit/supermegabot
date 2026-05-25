#!/usr/bin/env python3
"""🧠 Learner Agent — Lernt täglich neue Skills via Ollama, speichert Erkenntnisse lokal"""
import sys, os, time, json, datetime, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram

ID = "learner"
ARMY_DIR   = Path(__file__).parent.parent
LEARN_LOG  = ARMY_DIR / "shared" / "learned_today.json"
SKILLS_LOG = ARMY_DIR / "shared" / "learned_skills.json"
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/generate"

DAILY_SKILLS = [
    ("trending_products", "Was sind die 3 besten Dropshipping-Produkte heute? Stichpunkte, max 5 Zeilen."),
    ("seo_keywords",      "Nenne 5 konkrete SEO-Keywords für einen Shopify-Dropshipping-Store. Nur Keywords, keine Erklärung."),
    ("competitor_check",  "Wie analysiere ich Wettbewerber-Preise automatisch für Shopify? 3 konkrete Methoden."),
    ("social_trends",     "3 aktuell trendende Hashtag-Gruppen für E-Commerce auf Instagram/TikTok."),
    ("automation_tips",   "Welche 3 Automatisierungen bringen im E-Commerce den größten Zeitgewinn?"),
    ("seo_optimization",  "3 konkrete Shopify-SEO-Optimierungen die heute sofort helfen."),
    ("ai_tools",          "3 KI-Tools die 2025 für Online-Shops am nützlichsten sind. Name + 1-Satz Erklärung."),
]


def ask_ollama(prompt: str, model: str = "llama3.2") -> str:
    try:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 250, "temperature": 0.7},
        }).encode()
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        r = urllib.request.urlopen(req, timeout=90)
        data = json.loads(r.read())
        return data.get("response", "").strip()
    except Exception as e:
        return ""


def load_skills() -> dict:
    try:
        if SKILLS_LOG.exists():
            return json.loads(SKILLS_LOG.read_text())
    except Exception:
        pass
    return {"skills": [], "total": 0}


def save_skill(name: str, description: str, content: str):
    db = load_skills()
    today = datetime.date.today().isoformat()
    db["skills"].append({
        "name": name,
        "description": description,
        "content": content[:1000],
        "learned_at": today,
    })
    # Nur letzte 200 Skills behalten
    db["skills"] = db["skills"][-200:]
    db["total"] = len(db["skills"])
    try:
        SKILLS_LOG.write_text(json.dumps(db, indent=2, ensure_ascii=False))
    except Exception:
        pass


def run():
    print(f"[{ID}] 🧠 Learner Agent gestartet")
    last_learn = datetime.date.today() - datetime.timedelta(days=1)
    learned_count = 0

    while True:
        today = datetime.date.today()

        if today > last_learn:
            print(f"[{ID}] 📚 Tägliches Lernen startet ({today})...")
            results = []

            for skill_name, description in DAILY_SKILLS:
                answer = ask_ollama(description)
                if answer:
                    save_skill(skill_name, description, answer)
                    learned_count += 1
                    results.append(skill_name)
                    print(f"[{ID}] ✅ Gelernt: {skill_name}")
                else:
                    print(f"[{ID}] ⚠️ Ollama nicht erreichbar für: {skill_name}")
                time.sleep(3)

            if results:
                notify_telegram(
                    f"🧠 <b>Learner:</b> {len(results)} neue Skills heute\n"
                    + "\n".join(f"• {r}" for r in results)
                )
            last_learn = today

            try:
                LEARN_LOG.write_text(json.dumps({
                    "date": str(today),
                    "learned": results,
                    "total": learned_count,
                }, indent=2))
            except Exception:
                pass

        # Stündlicher Status-Report
        skills_db = load_skills()
        total_skills = skills_db.get("total", 0)
        report(ID, "ok", f"Skills: {total_skills} gespeichert | {learned_count} heute", {
            "total_skills": total_skills,
            "learned_today": learned_count,
            "last_learn": str(last_learn),
        })

        time.sleep(3600)


if __name__ == "__main__":
    run()
