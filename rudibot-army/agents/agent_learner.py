#!/usr/bin/env python3
"""🧠 Learner Agent — Lernt täglich neue Skills, analysiert was nützlich wäre"""
import sys, os, time, json, datetime, subprocess
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, get_env

ID = "learner"
BOT_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot")
LEARN_LOG = os.path.expanduser("~/rudibot-army/shared/learned_today.json")

DAILY_SKILLS = [
    ("trending_products", "trending produkte für shopify dropshipping heute analysieren"),
    ("seo_keywords",      "aktuelle seo keywords für e-commerce shops analysieren"),
    ("competitor_check",  "wettbewerber preise für online shop vergleichen"),
    ("social_trends",     "trending hashtags und themen für social media posts"),
]

def node_learn(description, name):
    """Ruft den self-learner im bot auf"""
    script = f"""
const sl = require('{BOT_DIR}/modules/self-learner');
sl.learnNewSkill({json.dumps(description)}, {{name: {json.dumps(name)}}})
.then(r => console.log(JSON.stringify(r)))
.catch(e => console.error(e.message));
"""
    try:
        result = subprocess.run(["node", "-e", script], cwd=BOT_DIR, capture_output=True, text=True, timeout=60)
        return json.loads(result.stdout) if result.stdout else {"success": False}
    except: return {"success": False}

def run():
    print(f"[{ID}] 🧠 Learner Agent gestartet")
    last_learn = datetime.date.today() - datetime.timedelta(days=1)
    learned_count = 0
    while True:
        today = datetime.date.today()
        if today > last_learn:
            print(f"[{ID}] 📚 Tägliches Lernen startet...")
            results = []
            for skill_name, description in DAILY_SKILLS:
                r = node_learn(description, skill_name)
                if r.get("success"):
                    learned_count += 1
                    results.append(skill_name)
                    print(f"[{ID}] ✅ Gelernt: {skill_name}")
                time.sleep(5)
            if results:
                notify_telegram(f"🧠 <b>Learner:</b> {len(results)} neue Skills heute gelernt\n" + "\n".join(f"• /{r}" for r in results))
            last_learn = today
            try:
                open(LEARN_LOG,"w").write(json.dumps({"date":str(today),"learned":results,"total":learned_count}))
            except: pass
        
        # Skills-Status reporten
        try:
            skills_file = os.path.join(BOT_DIR, "data", "learned_skills.json")
            skills = json.loads(open(skills_file).read()) if os.path.exists(skills_file) else {}
            total_skills = len(skills.get("skills", []))
            report(ID, "ok", f"Skills: {total_skills} gelernt | {learned_count} heute", {
                "total_skills": total_skills, "learned_today": learned_count,
                "last_learn": str(last_learn)
            })
        except: pass
        time.sleep(3600)  # stündlich prüfen

if __name__ == "__main__":
    run()
