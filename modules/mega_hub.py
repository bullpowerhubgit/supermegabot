#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MEGA HUB — Master-Kontrollzentrale für das komplette RudiBot-System       ║
║  Verbindet: SuperMegaBot · RudiBot-Army · Eternal-Bot · PasswordSync       ║
║             Geheimwaffe · Autopilot · PM2 · API-Builder · SelfLearner      ║
║             Tailscale DNS                                                   ║
║  Alle Funktionen per Telegram steuerbar                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import aiohttp
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

BASE_DIR  = Path(__file__).parent.parent
HOME_DIR  = Path.home()

try:
    from dotenv import load_dotenv as _ld
    _ld(BASE_DIR / ".env", override=True)
except ImportError:
    pass

# ── Pfade zu allen Sub-Systemen ────────────────────────────────────────────────
PATHS = {
    "supermegabot":    BASE_DIR,
    "rudibot_army":    HOME_DIR / "rudibot-army",
    "rudibot_eternal": HOME_DIR / "rudibot-eternal",
    "password_sync":   HOME_DIR / "password-sync-suite",
    "self_learner":    HOME_DIR,
    "agent_orch":      HOME_DIR,
    "kivo":            HOME_DIR / "kivo",
    "windsurf_autoheal": HOME_DIR / "windsurf-auto-heal",
    "windsurf_api_gw": HOME_DIR / "windsurf-api-gateway",
}

# ── PM2-Prozesse (aus ecosystem.config.js) ────────────────────────────────────
PM2_APPS = [
    {"name": "supermegabot",        "port": 8888,  "url": "http://localhost:8888/health"},
    {"name": "telegram-bot",        "port": 3200,  "url": "http://localhost:3200/api/status"},
    {"name": "cratorhub",           "port": 3000,  "url": "http://localhost:3000"},
    {"name": "windsurf-shopify",    "port": 3001,  "url": "http://localhost:3001"},
    {"name": "password-sync",       "port": 3005,  "url": "http://localhost:3005/health"},
    {"name": "windsurf-autoheal",   "port": 9000,  "url": "http://localhost:9000/health"},
    {"name": "windsurf-api-gateway","port": 8080,  "url": "http://localhost:8080/health"},
    {"name": "windsurf-telegram-bot","port": 8000, "url": "http://localhost:8000/health"},
    {"name": "mega-orchestrator",   "port": None,  "url": None},
    {"name": "rudibot-army",        "port": None,  "url": None},
    {"name": "rudibot-eternal",     "port": None,  "url": None},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Hilfsfunktionen
# ═══════════════════════════════════════════════════════════════════════════════

def _run(cmd: str, cwd: Path = None, timeout: int = 15) -> Dict:
    """Shell-Befehl ausführen, gibt {ok, stdout, stderr} zurück."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(cwd) if cwd else None,
            env={**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", "")}
        )
        return {"ok": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


async def _http_get(url: str, timeout: int = 5) -> Dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.get(url) as r:
                body = (await r.text())[:300]
                return {"ok": r.status < 400, "status": r.status, "body": body}
    except Exception as e:
        return {"ok": False, "status": 0, "body": str(e)[:80]}


def _trunc(text: str, n: int = 200) -> str:
    return text[:n] + "…" if len(text) > n else text


# ═══════════════════════════════════════════════════════════════════════════════
# PM2 Controller
# ═══════════════════════════════════════════════════════════════════════════════

class PM2Controller:

    def status(self) -> str:
        r = _run("pm2 jlist 2>/dev/null || pm2 list --no-color 2>/dev/null")
        if not r["ok"] or not r["stdout"]:
            return "⚠️ PM2 nicht erreichbar oder kein Prozess läuft."

        # Versuche JSON-Parse
        try:
            apps = json.loads(r["stdout"])
            lines = [f"<b>PM2 Prozesse ({len(apps)}):</b>"]
            for a in apps:
                name   = a.get("name", "?")
                status = a.get("pm2_env", {}).get("status", "?")
                uptime = a.get("pm2_env", {}).get("pm_uptime", 0)
                restarts = a.get("pm2_env", {}).get("restart_time", 0)
                icon   = "✅" if status == "online" else ("🔄" if status == "launching" else "❌")
                up_str = self._format_uptime(uptime)
                lines.append(f"  {icon} <code>{name}</code> [{status}] ↑{up_str} 🔄{restarts}×")
            return "\n".join(lines)
        except Exception:
            # Fallback: plain text output
            lines = ["<b>PM2 Status:</b>"]
            for line in r["stdout"].splitlines():
                if "│" in line and ("online" in line or "stopped" in line or "errored" in line):
                    icon = "✅" if "online" in line else "❌"
                    lines.append(f"  {icon} {_trunc(line.replace('│','').strip(), 60)}")
            return "\n".join(lines) if len(lines) > 1 else r["stdout"][:500]

    def _format_uptime(self, ms: int) -> str:
        if not ms: return "?"
        try:
            secs = (time.time() * 1000 - ms) / 1000
            if secs < 60:    return f"{int(secs)}s"
            if secs < 3600:  return f"{int(secs/60)}m"
            if secs < 86400: return f"{int(secs/3600)}h"
            return f"{int(secs/86400)}d"
        except Exception:
            return "?"

    def restart(self, name: str) -> str:
        r = _run(f"pm2 restart {name}")
        return f"✅ <code>{name}</code> neugestartet" if r["ok"] else f"❌ {r['stderr'][:100]}"

    def start(self, name: str) -> str:
        eco = BASE_DIR / "ecosystem.config.js"
        r = _run(f"pm2 start {eco} --only {name}")
        return f"✅ <code>{name}</code> gestartet" if r["ok"] else f"❌ {r['stderr'][:100]}"

    def stop(self, name: str) -> str:
        r = _run(f"pm2 stop {name}")
        return f"✅ <code>{name}</code> gestoppt" if r["ok"] else f"❌ {r['stderr'][:100]}"

    def logs(self, name: str, lines: int = 20) -> str:
        r = _run(f"pm2 logs {name} --lines {lines} --nostream --no-color")
        if r["stdout"]:
            return f"<b>Logs: {name}</b>\n<code>{_trunc(r['stdout'], 800)}</code>"
        return f"Keine Logs für {name}"

    def save(self) -> str:
        r = _run("pm2 save")
        return "✅ PM2 gespeichert" if r["ok"] else f"❌ {r['stderr'][:80]}"

    def startup(self) -> str:
        r = _run("pm2 startup --no-interaction")
        return _trunc(r["stdout"] or r["stderr"], 300)


# ═══════════════════════════════════════════════════════════════════════════════
# System-Status (alle Services auf einmal)
# ═══════════════════════════════════════════════════════════════════════════════

class SystemStatus:

    async def all_status(self) -> str:
        """Kompletter Status aller Systeme."""
        lines = [f"<b>🖥 System-Übersicht</b> ({datetime.now().strftime('%H:%M:%S')})\n"]

        # 1. HTTP-Services
        lines.append("<b>Services:</b>")
        checks = [
            ("SuperMegaBot Dashboard", "http://localhost:8888/health"),
            ("Telegram Bot (Node)",    "http://localhost:3200/api/status"),
            ("Password-Sync",          "http://localhost:3005/health"),
            ("Windsurf Autoheal",      "http://localhost:9000/health"),
            ("API Gateway",            "http://localhost:8080/health"),
            ("CreatorHub",             "http://localhost:3000"),
            ("Ollama",                 "http://localhost:11434/api/tags"),
        ]
        for name, url in checks:
            r = await _http_get(url, timeout=3)
            icon = "✅" if r["ok"] else "❌"
            lines.append(f"  {icon} {name}")

        # 2. Prozesse
        lines.append("\n<b>Prozesse:</b>")
        processes = [
            ("mega_orchestrator.py",    "mega_orchestrator"),
            ("army_commander.py",       "army_commander"),
            ("eternal_immortal_bot.py", "immortal"),
            ("agent_orchestrator.py",   "orchestrator"),
        ]
        for script, label in processes:
            r = _run(f"pgrep -f {script}")
            icon = "✅" if r["ok"] and r["stdout"] else "❌"
            lines.append(f"  {icon} {label}")

        # 3. PM2
        pm2_r = _run("pm2 jlist 2>/dev/null")
        if pm2_r["ok"] and pm2_r["stdout"]:
            try:
                apps = json.loads(pm2_r["stdout"])
                online = sum(1 for a in apps if a.get("pm2_env", {}).get("status") == "online")
                lines.append(f"\n<b>PM2:</b> {online}/{len(apps)} online")
            except Exception:
                lines.append("\n<b>PM2:</b> läuft")

        # 4. Disk/RAM
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            lines.append(f"\n<b>Ressourcen:</b>")
            lines.append(f"  RAM: {mem.percent:.0f}% ({mem.used//1073741824:.1f}/{mem.total//1073741824:.1f} GB)")
            lines.append(f"  Disk: {disk.percent:.0f}% ({disk.free//1073741824:.0f} GB frei)")
        except ImportError:
            pass

        return "\n".join(lines)

    def process_status(self) -> str:
        """Alle Python/Node-Prozesse als Text."""
        r = _run("ps aux | grep -E '(python3|node|npm)' | grep -v grep | awk '{print $11, $12}' | sort -u")
        if r["stdout"]:
            lines = ["<b>Aktive Prozesse:</b>"]
            for line in r["stdout"].splitlines()[:20]:
                lines.append(f"  • {_trunc(line, 80)}")
            return "\n".join(lines)
        return "Keine aktiven Python/Node-Prozesse gefunden."


# ═══════════════════════════════════════════════════════════════════════════════
# Geheimwaffe Controller
# ═══════════════════════════════════════════════════════════════════════════════

class GeheimwaffeController:

    async def run_full(self, niche: str = "General") -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.geheimwaffe import run_full_automation
            results = await run_full_automation(niche)
            products = results.get("winning_products", [])
            prod_lines = []
            for p in products[:3]:
                prod_lines.append(f"  • {p.get('title','?')} ({p.get('competition','?')} Konkurrenz, {p.get('trend_score','?')}/10)")
            forecast = results.get("forecast", {})
            return (
                f"🚀 <b>Geheimwaffe: {niche}</b>\n\n"
                f"<b>Winning Products:</b>\n" + ("\n".join(prod_lines) or "  Keine gefunden") +
                f"\n\n<b>Umsatzprognose:</b>\n"
                f"  Monat 1: {forecast.get('month1_target','?')}\n"
                f"  Monat 3: {forecast.get('month3_target','?')}"
            )
        except Exception as e:
            return f"❌ Geheimwaffe Fehler: {e}"

    async def find_products(self, niche: str = "") -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.geheimwaffe import find_winning_products
            products = await find_winning_products(niche or None)
            if not products:
                return "Keine Winning Products gefunden."
            lines = [f"🔍 <b>Winning Products</b>{f' für {niche}' if niche else ''}:\n"]
            for i, p in enumerate(products[:5], 1):
                lines.append(
                    f"{i}. <b>{p.get('title','?')}</b>\n"
                    f"   📈 Score: {p.get('trend_score','?')}/10 | Konkurrenz: {p.get('competition','?')}\n"
                    f"   💰 Marge: {p.get('profit_margin','?')} | Preis: {p.get('selling_price','?')}\n"
                    f"   🎯 {p.get('why_winning','')[:80]}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Fehler: {e}"

    async def generate_content(self, product: str, platform: str = "tiktok") -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.geheimwaffe import generate_social_content
            content = await generate_social_content(product, platform)
            return (
                f"📣 <b>{platform.title()} Content: {product}</b>\n\n"
                f"<b>Headline:</b> {content.get('headline','')}\n\n"
                f"<b>Content:</b>\n{_trunc(content.get('content',''), 400)}\n\n"
                f"<b>CTA:</b> {content.get('cta','')}\n"
                f"<b>Hook:</b> {content.get('viral_hook','')}"
            )
        except Exception as e:
            return f"❌ Content-Fehler: {e}"

    async def analytics(self) -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.geheimwaffe import get_store_analytics
            data = await get_store_analytics()
            shop = data.get("data", {}).get("shop", {})
            orders = data.get("data", {}).get("orders", {}).get("edges", [])
            products = data.get("data", {}).get("products", {}).get("edges", [])
            revenue = sum(
                float(o["node"]["totalPriceSet"]["shopMoney"]["amount"])
                for o in orders if o.get("node", {}).get("totalPriceSet")
            )
            return (
                f"📊 <b>Shopify Analytics</b>\n\n"
                f"Store: {shop.get('name', '?')}\n"
                f"Letzte 10 Bestellungen: {len(orders)}\n"
                f"Umsatz (letzte Orders): {revenue:.2f} €\n"
                f"Produkte im System: {len(products)}"
            )
        except Exception as e:
            return f"❌ Analytics Fehler: {e}"

    async def seo_optimize(self) -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.geheimwaffe import optimize_all_products_seo
            results = await optimize_all_products_seo()
            lines = [f"🔍 <b>SEO Optimierung</b> ({len(results)} Produkte)\n"]
            for r in results[:5]:
                lines.append(f"  • {r.get('product','?')}: ✅ optimiert")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ SEO Fehler: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# Autopilot Controller
# ═══════════════════════════════════════════════════════════════════════════════

class AutopilotController:

    async def run_agent(self, agent_id: str, task: str) -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.autopilot import AutoPilot, AGENTS
            if agent_id not in AGENTS:
                avail = ", ".join(AGENTS.keys())
                return f"❌ Unbekannter Agent: <code>{agent_id}</code>\nVerfügbar: {avail}"
            ap = AutoPilot()
            result = await ap.run_task(task, agent_id)
            agent_name = result.get("agent_name", agent_id)
            response   = result.get("result", str(result))
            duration   = result.get("duration_ms", 0)
            return (
                f"🤖 <b>{agent_name}</b>\n"
                f"⏱ {duration}ms\n\n"
                f"{_trunc(response, 900)}"
            )
        except Exception as e:
            return f"❌ Agent-Fehler ({agent_id}): {e}"

    async def run_autopilot(self, goal: str) -> str:
        """CEO bricht Ziel in Schritte auf und delegiert an Agenten."""
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.autopilot import AutoPilot
            ap = AutoPilot()
            results = await ap.run_autopilot_mode(goal)
            lines = [f"🚀 <b>Autopilot: {_trunc(goal, 60)}</b>\n"]
            for r in results:
                lines.append(
                    f"{r.get('agent_name','?')} ({r.get('duration_ms',0)}ms):\n"
                    f"{_trunc(r.get('result',''), 300)}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Autopilot Fehler: {e}"

    def list_agents(self) -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.autopilot import AGENTS
            lines = ["<b>Verfügbare Autopilot-Agenten:</b>\n"]
            for aid, a in AGENTS.items():
                lines.append(f"  {a.get('emoji','🤖')} <code>{aid}</code> — {a.get('role','')}")
            lines.append(
                "\n<b>Verwendung:</b>\n"
                "/agent &lt;id&gt; &lt;aufgabe&gt;\n"
                "/autopilot_run &lt;ziel&gt; — CEO plant & delegiert automatisch\n\n"
                "<b>Beispiele:</b>\n"
                "<code>/agent shopify Analysiere meinen Store und gib 5 Tipps</code>\n"
                "<code>/agent marketing Erstelle TikTok-Kampagne für Hundeprodukte</code>\n"
                "<code>/agent coding Schreibe einen Python-Script der Shopify-Bestellungen exportiert</code>\n"
                "<code>/autopilot_run Steigere meinen Shopify-Umsatz um 30% in 30 Tagen</code>"
            )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Fehler: {e}"

    def get_logs(self, limit: int = 10) -> str:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from modules.autopilot import AutoPilot
            ap = AutoPilot()
            logs = ap.get_logs(limit)
            if not logs:
                return "Noch keine Autopilot-Logs."
            lines = [f"<b>Letzte {len(logs)} Aufgaben:</b>\n"]
            for l in logs:
                lines.append(
                    f"  🤖 {l['agent']} | {l['timestamp'][:16]}\n"
                    f"  📋 {_trunc(l['task'], 60)}\n"
                    f"  ✅ {_trunc(l['result'], 80)}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# Army Controller
# ═══════════════════════════════════════════════════════════════════════════════

class ArmyController:

    ARMY_DIR = HOME_DIR / "rudibot-army"

    def status(self) -> str:
        state_file = self.ARMY_DIR / "shared" / "army_state.json"
        if not state_file.exists():
            return "⚠️ Army State-Datei nicht gefunden. Army läuft möglicherweise nicht."
        try:
            state = json.loads(state_file.read_text(errors="ignore"))
            agents = state.get("agents", {})
            lines = [f"<b>🤖 RudiBot Army Status</b>\n"]
            icons = {"ok": "✅", "warning": "⚠️", "error": "❌", "repaired": "🔧"}
            agent_defs = [
                ("monitor",   "🔴 Service Monitor"),
                ("shopify",   "🛒 Shopify Watcher"),
                ("social",    "📱 Social Autopilot"),
                ("finance",   "💰 Finance Tracker"),
                ("learner",   "🧠 Auto Learner"),
                ("security",  "🔐 Security Guard"),
                ("optimizer", "⚡ Optimizer"),
            ]
            for aid, label in agent_defs:
                info = agents.get(aid, {})
                s = icons.get(info.get("status", ""), "❓")
                msg = _trunc(info.get("message", "Keine Daten"), 60)
                ts = info.get("ts", "?")
                lines.append(f"{s} <b>{label}</b>\n   {msg} <i>({ts})</i>")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Army Status Fehler: {e}"

    def start(self) -> str:
        r = _run(
            f"nohup python3 {self.ARMY_DIR}/army_commander.py >> /tmp/rudibot-army.log 2>&1 &",
            cwd=self.ARMY_DIR
        )
        return "✅ RudiBot Army gestartet" if r["ok"] else f"❌ {r['stderr'][:100]}"

    def stop(self) -> str:
        r = _run("pkill -f army_commander.py")
        return "✅ Army gestoppt" if r["ok"] else "ℹ️ Army läuft nicht"

    def events(self) -> str:
        state_file = self.ARMY_DIR / "shared" / "army_state.json"
        if not state_file.exists():
            return "Keine Events (Army nicht aktiv)"
        try:
            state = json.loads(state_file.read_text(errors="ignore"))
            events = state.get("events", [])[-10:]
            lines = [f"<b>Army Events (letzte {len(events)}):</b>\n"]
            for e in reversed(events):
                lines.append(f"  [{e.get('ts','?')}] {e.get('agent','?')}: {e.get('msg','')[:60]}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# ImmortalBot Controller
# ═══════════════════════════════════════════════════════════════════════════════

class ImmortalController:

    ETERNAL_DIR = HOME_DIR / "rudibot-eternal"

    def status(self) -> str:
        r = _run("pgrep -f eternal_immortal_bot.py")
        running = r["ok"] and r["stdout"]

        brain_file = self.ETERNAL_DIR / "brain" / "learned_fixes.json"
        brain_info = ""
        if brain_file.exists():
            try:
                brain = json.loads(brain_file.read_text(errors="ignore"))
                stats = brain.get("stats", {})
                brain_info = (
                    f"\n🧠 Brain: {stats.get('total_repairs',0)} Reparaturen total\n"
                    f"🎓 Permanent gelöst: {len(stats.get('permanently_resolved',[]))} Muster"
                )
            except Exception:
                pass

        icon = "✅" if running else "❌"
        return (
            f"{icon} <b>EternalImmortalBot</b>\n"
            f"Status: {'Läuft' if running else 'Gestoppt'}"
            f"{brain_info}"
        )

    def start(self) -> str:
        script = self.ETERNAL_DIR / "eternal_immortal_bot.py"
        if not script.exists():
            return f"❌ Skript nicht gefunden: {script}"
        r = _run(f"nohup python3 {script} >> /tmp/immortal-bot.log 2>&1 &")
        return "✅ EternalImmortalBot gestartet" if r["ok"] else f"❌ {r['stderr'][:80]}"

    def stop(self) -> str:
        r = _run("pkill -f eternal_immortal_bot.py")
        return "✅ ImmortalBot gestoppt" if r["ok"] else "ℹ️ Läuft nicht"

    def brain_stats(self) -> str:
        brain_file = self.ETERNAL_DIR / "brain" / "learned_fixes.json"
        if not brain_file.exists():
            return "Keine Brain-Daten (ImmortalBot noch nicht gestartet)"
        try:
            brain = json.loads(brain_file.read_text(errors="ignore"))
            stats = brain.get("stats", {})
            fixes = brain.get("fixes", {})
            lines = [
                "<b>🧠 ImmortalBot Brain:</b>\n",
                f"Total Reparaturen: {stats.get('total_repairs',0)}",
                f"Permanent gelöst: {len(stats.get('permanently_resolved',[]))}",
                f"Bekannte Fix-Muster: {len(fixes)}",
                "",
                "<b>Top Fixes:</b>",
            ]
            sorted_fixes = sorted(fixes.values(), key=lambda x: x.get("count", 0), reverse=True)
            for f in sorted_fixes[:5]:
                lines.append(f"  • {f.get('service','?')}: {_trunc(f.get('error','?'), 40)} ({f.get('count',0)}×)")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Brain lesen Fehler: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# Password-Sync Controller
# ═══════════════════════════════════════════════════════════════════════════════

class PasswordSyncController:

    async def status(self) -> str:
        r = await _http_get("http://localhost:3005/health", timeout=4)
        if r["ok"]:
            return (
                "✅ <b>Password-Sync läuft</b>\n"
                "URL: http://localhost:3005\n"
                "Extension: chrome://extensions → entpackt laden → password-sync-suite/browser-extension\n\n"
                "Konten:\n"
                "  • dragonadnp@gmail.com\n"
                "  • aiitecbuuss@gmail.com\n"
                "  • bullpowersrtkennels@gmail.com"
            )
        return (
            "❌ <b>Password-Sync offline</b>\n"
            f"Fehler: {r['body'][:80]}\n\n"
            "Start: /pm2_start password-sync"
        )

    async def sync_stats(self) -> str:
        """Holt Sync-Statistiken vom Password-Sync Server."""
        r = await _http_get("http://localhost:3005/api/dashboard", timeout=5)
        if not r["ok"]:
            return "❌ Password-Sync nicht erreichbar"
        try:
            data = json.loads(r["body"])
            return (
                f"🔐 <b>Password-Sync Stats</b>\n"
                f"Passwörter: {data.get('totalPasswords', 0)}\n"
                f"Browser-Clients: {data.get('clients', 0)}"
            )
        except Exception:
            return f"Password-Sync: {r['body'][:200]}"


# ═══════════════════════════════════════════════════════════════════════════════
# Self-Learner Controller
# ═══════════════════════════════════════════════════════════════════════════════

class SelfLearnerController:

    def status(self) -> str:
        r = _run("pgrep -f self_learner")
        running = r["ok"] and r["stdout"]
        core_exists = (HOME_DIR / "self_learner_core.py").exists()
        return (
            f"{'✅' if running else '❌'} <b>Self-Learner</b>\n"
            f"Status: {'Aktiv' if running else 'Inaktiv'}\n"
            f"Core: {'vorhanden' if core_exists else 'nicht gefunden'}"
        )

    def run_cli(self, cmd: str) -> str:
        cli = HOME_DIR / "self_learner_cli.py"
        if not cli.exists():
            return "❌ self_learner_cli.py nicht gefunden"
        r = _run(f"python3 {cli} {cmd}", timeout=30)
        return _trunc(r["stdout"] or r["stderr"], 400)


# ═══════════════════════════════════════════════════════════════════════════════
# Mega Hub — Haupt-Dispatcher
# ═══════════════════════════════════════════════════════════════════════════════

class MegaHub:
    def __init__(self):
        self.pm2       = PM2Controller()
        self.sys_status = SystemStatus()
        self.waffe     = GeheimwaffeController()
        self.autopilot = AutopilotController()
        self.army      = ArmyController()
        self.immortal  = ImmortalController()
        self.pw_sync   = PasswordSyncController()
        self.learner   = SelfLearnerController()
        from modules.tailscale import TailscaleController
        self.tailscale = TailscaleController()

    async def dispatch(self, text: str) -> str:
        t = text.strip()
        lower = t.lower()

        # ── Übersicht ────────────────────────────────────────────────────────────
        if lower in ("/hub", "/hub_status", "hub status", "alles", "alle systeme"):
            return await self.sys_status.all_status()

        if lower in ("/prozesse", "/procs"):
            return self.sys_status.process_status()

        # ── PM2 ──────────────────────────────────────────────────────────────────
        if lower in ("/pm2", "/pm2_status", "pm2"):
            return self.pm2.status()

        if lower.startswith("/pm2_restart "):
            return self.pm2.restart(t[13:].strip())

        if lower.startswith("/pm2_start "):
            return self.pm2.start(t[11:].strip())

        if lower.startswith("/pm2_stop "):
            return self.pm2.stop(t[10:].strip())

        if lower.startswith("/pm2_logs "):
            return self.pm2.logs(t[10:].strip())

        if lower in ("/pm2_save",):
            return self.pm2.save()

        # ── Geheimwaffe ──────────────────────────────────────────────────────────
        if lower in ("/waffe", "/geheimwaffe", "waffe", "geheimwaffe"):
            return (
                "<b>🗡 Geheimwaffe — Befehle:</b>\n\n"
                "/waffe_run &lt;nische&gt; — Komplette Automatisierung\n"
                "/waffe_produkte [nische] — Winning Products finden\n"
                "/waffe_content &lt;produkt&gt; — TikTok/IG Content\n"
                "/waffe_analytics — Shopify Analytics\n"
                "/waffe_seo — Alle Produkte SEO optimieren"
            )

        if lower.startswith("/waffe_run"):
            niche = t[10:].strip() or "General"
            return await self.waffe.run_full(niche)

        if lower.startswith("/waffe_produkte"):
            niche = t[15:].strip()
            return await self.waffe.find_products(niche)

        if lower.startswith("/waffe_content"):
            parts = t[14:].strip().split(maxsplit=1)
            product  = parts[0] if parts else ""
            platform = parts[1] if len(parts) > 1 else "tiktok"
            if not product:
                return "Verwendung: /waffe_content &lt;produkt&gt; [tiktok|instagram|facebook|email]"
            return await self.waffe.generate_content(product, platform)

        if lower in ("/waffe_analytics", "/shopify_analytics"):
            return await self.waffe.analytics()

        if lower in ("/waffe_seo", "/seo"):
            return await self.waffe.seo_optimize()

        # ── Autopilot Agents ─────────────────────────────────────────────────────
        if lower in ("/autopilot", "/agenten", "autopilot"):
            return self.autopilot.list_agents()

        if lower.startswith("/autopilot_run "):
            goal = t[15:].strip()
            if not goal:
                return "Verwendung: /autopilot_run &lt;ziel&gt;\nBeispiel: /autopilot_run Steigere meinen Shopify-Umsatz um 30%"
            return await self.autopilot.run_autopilot(goal)

        if lower in ("/autopilot_logs",):
            return self.autopilot.get_logs()

        if lower.startswith("/agent "):
            parts = t[7:].strip().split(maxsplit=1)
            if len(parts) < 2:
                return (
                    "Verwendung: /agent &lt;id&gt; &lt;aufgabe&gt;\n\n"
                    "Agenten: ceo | shopify | marketing | coding | research | finance | automation | security\n\n"
                    "Beispiele:\n"
                    "<code>/agent shopify Analysiere meinen Store</code>\n"
                    "<code>/agent coding Schreibe Shopify-Export-Script</code>\n"
                    "<code>/agent marketing TikTok-Kampagne für Hundeprodukte</code>"
                )
            agent_id, task = parts[0], parts[1]
            return await self.autopilot.run_agent(agent_id, task)

        # ── RudiBot Army ─────────────────────────────────────────────────────────
        if lower in ("/army", "/army_status", "army"):
            return self.army.status()

        if lower in ("/army_start",):
            return self.army.start()

        if lower in ("/army_stop",):
            return self.army.stop()

        if lower in ("/army_events",):
            return self.army.events()

        # ── ImmortalBot ──────────────────────────────────────────────────────────
        if lower in ("/immortal", "/immortal_status", "immortal"):
            return self.immortal.status()

        if lower in ("/immortal_start",):
            return self.immortal.start()

        if lower in ("/immortal_stop",):
            return self.immortal.stop()

        if lower in ("/immortal_brain", "/brain"):
            return self.immortal.brain_stats()

        # ── Password-Sync ────────────────────────────────────────────────────────
        if lower in ("/pw", "/pw_status", "/passwortsync", "pw status"):
            return await self.pw_sync.status()

        if lower in ("/pw_stats",):
            return await self.pw_sync.sync_stats()

        # ── Self-Learner ─────────────────────────────────────────────────────────
        if lower in ("/learner", "/learner_status"):
            return self.learner.status()

        if lower.startswith("/learner "):
            return self.learner.run_cli(t[9:].strip())

        # ── Tailscale DNS ─────────────────────────────────────────────────────────
        if lower in ("/ts", "/ts_dns", "tailscale", "ts dns"):
            return await self.tailscale.dns_status()

        if lower in ("/ts_devices", "/ts_geraete"):
            return await self.tailscale.devices()

        if lower in ("/ts_ns", "/ts_nameservers"):
            return await self.tailscale.nameservers_get()

        if lower.startswith("/ts_ns_add "):
            server = t[11:].strip()
            if not server:
                return "Verwendung: /ts_ns_add &lt;ip&gt;  z.B. /ts_ns_add 1.1.1.1"
            return await self.tailscale.nameservers_add(server)

        if lower.startswith("/ts_ns_del "):
            server = t[11:].strip()
            if not server:
                return "Verwendung: /ts_ns_del &lt;ip&gt;"
            return await self.tailscale.nameservers_remove(server)

        if lower.startswith("/ts_ns_set "):
            servers = t[11:].strip().split()
            if not servers:
                return "Verwendung: /ts_ns_set &lt;ip1&gt; [ip2...]"
            return await self.tailscale.nameservers_set(servers)

        if lower in ("/ts_search", "/ts_searchpaths"):
            return await self.tailscale.search_domains_get()

        if lower.startswith("/ts_search_add "):
            domain = t[15:].strip()
            if not domain:
                return "Verwendung: /ts_search_add &lt;domain&gt;"
            return await self.tailscale.search_domains_add(domain)

        if lower.startswith("/ts_search_del "):
            domain = t[15:].strip()
            if not domain:
                return "Verwendung: /ts_search_del &lt;domain&gt;"
            return await self.tailscale.search_domains_remove(domain)

        if lower in ("/ts_magic_on", "/ts_magicdns_on"):
            return await self.tailscale.magicdns_enable()

        if lower in ("/ts_magic_off", "/ts_magicdns_off"):
            return await self.tailscale.magicdns_disable()

        if lower in ("/ts_help", "/ts_hilfe"):
            return self.tailscale.cmd_help()

        # ── Hilfe ────────────────────────────────────────────────────────────────
        if lower in ("/hub_hilfe", "/hub_help", "hub hilfe"):
            return self.cmd_help()

        return self.cmd_help()

    def cmd_help(self) -> str:
        return (
            "<b>🏠 MEGA HUB — Alle Befehle:</b>\n\n"
            "<b>System:</b>\n"
            "/hub — Komplett-Status aller Systeme\n"
            "/prozesse — Alle laufenden Prozesse\n\n"
            "<b>PM2:</b>\n"
            "/pm2 — PM2 Prozesse anzeigen\n"
            "/pm2_restart &lt;name&gt; — Neu starten\n"
            "/pm2_start &lt;name&gt; — Starten\n"
            "/pm2_stop &lt;name&gt; — Stoppen\n"
            "/pm2_logs &lt;name&gt; — Logs anzeigen\n\n"
            "<b>🗡 Geheimwaffe:</b>\n"
            "/waffe_run &lt;nische&gt; — Full Automation\n"
            "/waffe_produkte [nische] — Winning Products\n"
            "/waffe_content &lt;produkt&gt; — Content\n"
            "/waffe_analytics — Store Analytics\n"
            "/waffe_seo — SEO Optimierung\n\n"
            "<b>🤖 Autopilot:</b>\n"
            "/autopilot — Agenten anzeigen\n"
            "/agent &lt;id&gt; &lt;aufgabe&gt; — Agent beauftragen\n\n"
            "<b>Army & Services:</b>\n"
            "/army — Army Status\n"
            "/army_start / /army_stop\n"
            "/immortal — ImmortalBot Status\n"
            "/immortal_brain — Brain-Statistiken\n"
            "/pw — Password-Sync Status\n"
            "/learner — Self-Learner Status\n\n"
            "<b>🌐 Tailscale DNS:</b>\n"
            "/ts — DNS-Übersicht\n"
            "/ts_devices — Geräte im Tailnet\n"
            "/ts_ns — Nameserver anzeigen\n"
            "/ts_ns_add &lt;ip&gt; / /ts_ns_del &lt;ip&gt;\n"
            "/ts_search — Search Domains\n"
            "/ts_search_add &lt;domain&gt; / /ts_search_del &lt;domain&gt;\n"
            "/ts_magic_on / /ts_magic_off — MagicDNS\n"
            "/ts_help — Alle Tailscale Befehle\n"
        )


# ── Singleton ──────────────────────────────────────────────────────────────────
_hub: Optional[MegaHub] = None

def get_hub() -> MegaHub:
    global _hub
    if _hub is None:
        _hub = MegaHub()
    return _hub


async def run_autopilot(goal: str = "Täglicher Business-Autopilot: Status prüfen, Optimierungen anwenden, Revenue maximieren") -> str:
    """Module-level entry point for scheduler: runs MegaHub autopilot with a default daily goal."""
    hub = get_hub()
    return await hub.autopilot.run_autopilot(goal)


# ── CLI-Test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        hub = get_hub()
        print(await hub.sys_status.all_status())
        print()
        print(hub.pm2.status())
        print()
        print(hub.army.status())
        print()
        print(hub.immortal.status())
    asyncio.run(_test())
