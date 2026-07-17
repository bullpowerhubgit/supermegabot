#!/usr/bin/env python3
"""
Autonomous Loop Installer — fügt den kompletten autonomen Loop in JEDES Python-Projekt ein.

Verwendung:
  python3 scripts/install_autonomous_loop.py /pfad/zum/projekt
  python3 scripts/install_autonomous_loop.py .              # aktuelles Verzeichnis

Was installiert wird:
  1. .github/workflows/autonomous_loop.yml  — CI/CD: Test → Deploy → Loop
  2. scripts/autonomous_health.py           — Syntax-Check + Health-Ping
  3. AUTONOMOUS_LOOP.md                     — Docs + Status

Voraussetzungen in .env / GitHub Secrets:
  RAILWAY_TOKEN        — Railway CLI-Token für Deploy
  GITHUB_TOKEN         — Auto-PR und Branch-Push (bereits in Actions gesetzt)
  ANTHROPIC_API_KEY    — Claude für KI-Optimierung
  TELEGRAM_BOT_TOKEN   — Status-Reports
  TELEGRAM_CHAT_ID     — Rudolf's Chat-ID
  RESEND_API_KEY       — Onboarding-Emails
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

LOOP_WORKFLOW = '''\
name: Autonomous Loop

on:
  schedule:
    - cron: "0 */6 * * *"   # alle 6h
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  loop:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: |
          pip install -q aiohttp anthropic requests 2>/dev/null || true
          [ -f requirements.txt ] && pip install -q -r requirements.txt || true

      - name: Syntax check (alle Module)
        run: |
          find . -name "*.py" -not -path "*/.git/*" -not -path "*/node_modules/*" | \\
            xargs -I{} python3 -m py_compile {} && echo "✅ Syntax OK"

      - name: Health check
        run: python3 scripts/autonomous_health.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          STRIPE_SECRET_KEY: ${{ secrets.STRIPE_SECRET_KEY }}

      - name: Deploy to Railway (main only)
        if: github.ref == \'refs/heads/main\'
        run: |
          npm install -g @railway/cli 2>/dev/null || true
          railway up --service ${{ secrets.RAILWAY_SERVICE_NAME }} || echo "Railway deploy skipped (kein Token)"
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
'''

HEALTH_SCRIPT = '''\
#!/usr/bin/env python3
"""Health-Check für Autonomous Loop — wird von GitHub Actions ausgeführt."""
import os, sys, asyncio, json
from pathlib import Path
from datetime import datetime, timezone

async def main() -> int:
    results = {}

    # 1. Python-Dateien prüfen
    errors = []
    import py_compile
    for p in Path(".").rglob("*.py"):
        if ".git" in p.parts or "node_modules" in p.parts:
            continue
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:
            errors.append(f"{p}: {e}")
    results["syntax"] = {"ok": len(errors) == 0, "errors": errors[:5]}

    # 2. Stripe-Key prüfen (falls vorhanden)
    sk = os.getenv("STRIPE_SECRET_KEY", "")
    if sk:
        results["stripe"] = {
            "ok": sk.startswith("sk_live_51Tg1U"),
            "key_prefix": sk[:20],
        }

    # 3. Telegram-Report
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat:
        import aiohttp
        msg = (
            f"⚡ <b>Autonomous Loop Health</b>\\n"
            f"Syntax: {'✅' if results['syntax']['ok'] else '❌'}\\n"
            f"Repo: {Path('.').resolve().name}\\n"
            f"Zeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            results["telegram"] = "sent"
        except Exception as e:
            results["telegram"] = f"skip: {e}"

    print(json.dumps(results, indent=2, default=str))
    return 0 if results["syntax"]["ok"] else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
'''

DOCS = '''\
# Autonomous Loop

Dieses Projekt läuft vollständig autonom:

| Schritt | Tool | Was passiert |
|---|---|---|
| Code schreiben | Claude Code | Autonome Verbesserungen |
| Tests | GitHub Actions | Syntax + Health bei jedem Push |
| Deploy | Railway | Automatisch bei Push auf `main` |
| Zahlungen | Stripe + Lemon Squeezy | Abos + Einmalzahlungen ohne UI |
| Onboarding | Resend | 4-Stufen Email-Sequenz (D0/1/3/7) |
| Analytics | Plausible + PostHog | Daten fließen zurück → Claude optimiert |

## Starten
```bash
# Health-Check lokal
python3 scripts/autonomous_health.py

# Loop manuell ausführen (im supermegabot-Repo)
python3 -m modules.autonomous_loop

# Quick-Mode (ohne schwere KI-Teams)
python3 -m modules.autonomous_loop --quick
```

## GitHub Secrets (einmalig setzen)
```
RAILWAY_TOKEN          — railway.app → Account → Tokens
ANTHROPIC_API_KEY      — console.anthropic.com
TELEGRAM_BOT_TOKEN     — @BotFather
TELEGRAM_CHAT_ID       — deine Chat-ID
STRIPE_SECRET_KEY      — nur bullpowersrtkennels (sk_live_51Tg1U...)
RESEND_API_KEY         — resend.com/api-keys
RAILWAY_SERVICE_NAME   — Railway Service-Name (z.B. "supermegabot")
```

## Wie der Loop tickt
1. GitHub Actions läuft alle 6h + bei jedem Push auf `main`
2. Syntax-Check aller Python-Dateien
3. Railway deployt automatisch (GitHub App muss verbunden sein)
4. Telegram-Report an Rudolf
5. Nächste Iteration: Claude analysiert Analytics → generiert Plan → erstellt PR
'''


def install(target: str = ".") -> None:
    root = Path(target).resolve()
    if not root.exists():
        print(f"❌ Verzeichnis nicht gefunden: {root}")
        sys.exit(1)

    print(f"🔧 Installiere Autonomous Loop in: {root.name}")

    # GitHub Actions Workflow
    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf = wf_dir / "autonomous_loop.yml"
    if not wf.exists():
        wf.write_text(LOOP_WORKFLOW)
        print(f"  ✅ {wf.relative_to(root)}")
    else:
        print(f"  ⏭  {wf.relative_to(root)} existiert bereits")

    # Health-Script
    sc_dir = root / "scripts"
    sc_dir.mkdir(exist_ok=True)
    hs = sc_dir / "autonomous_health.py"
    if not hs.exists():
        hs.write_text(HEALTH_SCRIPT)
        print(f"  ✅ {hs.relative_to(root)}")
    else:
        print(f"  ⏭  {hs.relative_to(root)} existiert bereits")

    # Docs
    docs = root / "AUTONOMOUS_LOOP.md"
    if not docs.exists():
        docs.write_text(DOCS)
        print(f"  ✅ {docs.relative_to(root)}")
    else:
        print(f"  ⏭  {docs.relative_to(root)} existiert bereits")

    print(f"\n✅ Fertig! Nächste Schritte:")
    print(f"  1. GitHub Secrets setzen (siehe AUTONOMOUS_LOOP.md)")
    print(f"  2. Railway GitHub App verbinden: railway.app → dein Projekt → Settings → GitHub")
    print(f"  3. git add . && git commit -m 'feat: autonomous loop' && git push")
    print(f"  4. Loop startet automatisch bei jedem Push + alle 6h")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    install(target)
