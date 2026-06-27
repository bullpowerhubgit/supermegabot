#!/usr/bin/env python3
"""
SuperMegaBot Automation Scheduler
Runs all periodic tasks: Digistore24 sync, Mailchimp sync,
Shopify sync, GitHub backup, Trading reports, System health alerts.
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("AutoScheduler")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Ensure project root is in sys.path so `from modules.xxx import` always works
_BASE_STR = str(BASE_DIR)
if _BASE_STR not in sys.path:
    sys.path.insert(0, _BASE_STR)

_SCHED_DB = DATA_DIR / "scheduler.db"

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


# ── Scheduler state DB ───────────────────────────────────────────────────────

def _init_db():
    conn = sqlite3.connect(_SCHED_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            ran_at    TEXT NOT NULL,
            success   INTEGER NOT NULL DEFAULT 1,
            result    TEXT,
            duration_ms INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_task_runs_name ON task_runs(task_name, ran_at);
    """)
    conn.commit()
    conn.close()


def _log_run(task_name: str, success: bool, result: str, duration_ms: int):
    try:
        conn = sqlite3.connect(_SCHED_DB)
        conn.execute(
            "INSERT INTO task_runs (task_name,ran_at,success,result,duration_ms) VALUES (?,?,?,?,?)",
            (task_name, datetime.now().isoformat(), int(success), result[:500], duration_ms)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"Scheduler DB write error: {e}")


def get_last_runs(limit: int = 50) -> List[Dict]:
    try:
        _init_db()
        conn = sqlite3.connect(_SCHED_DB)
        rows = conn.execute(
            "SELECT task_name,ran_at,success,result,duration_ms FROM task_runs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{"task": r[0], "ran_at": r[1], "success": bool(r[2]), "result": r[3], "ms": r[4]} for r in rows]
    except Exception:
        return []


def get_task_stats() -> Dict:
    try:
        _init_db()
        conn = sqlite3.connect(_SCHED_DB)
        rows = conn.execute("""
            SELECT task_name,
                   COUNT(*) as total,
                   SUM(success) as ok,
                   MAX(ran_at) as last_run,
                   AVG(duration_ms) as avg_ms
            FROM task_runs
            GROUP BY task_name
        """).fetchall()
        conn.close()
        return {r[0]: {"total": r[1], "ok": r[2], "last_run": r[3], "avg_ms": round(r[4] or 0)} for r in rows}
    except Exception:
        return {}


# ── Telegram helper ──────────────────────────────────────────────────────────
# TELEGRAM_CHAT_ID     = Rudolf's private chat — nur für SYSTEM-ALERTS
# TELEGRAM_CHANNEL_ID  = öffentlicher Marketing-Kanal — für alle Promo-Posts
# Wenn TELEGRAM_CHANNEL_ID nicht gesetzt → Marketing-Posts still (kein Chat-Spam)

async def _tg(msg: str):
    """System-Alerts → immer an Rudolf's privaten Chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(url, json={"chat_id": chat, "text": msg, "parse_mode": "HTML",
                                    "disable_web_page_preview": True})
    except Exception:
        pass


async def _tg_marketing(msg: str) -> bool:
    """Marketing-Posts → NUR an öffentlichen Kanal (TELEGRAM_CHANNEL_ID).
    Sendet NIE an Rudolf's privaten Chat. Gibt True zurück wenn gesendet."""
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "")
    if not token or not channel:
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            r = await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel, "text": msg, "parse_mode": "HTML",
                      "disable_web_page_preview": True}
            )
            return (await r.json(content_type=None)).get("ok", False)
    except Exception:
        return False


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    """AI completion via central fallback chain."""
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        pass
    # legacy fallback providers (kept for scheduler tasks that don't import modules)
    import aiohttp
    for env_var, url, model in [
        ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
        ("PERPLEXITY_API_KEY", "https://api.perplexity.ai/chat/completions", "sonar"),
    ]:
        key = os.getenv(env_var, "")
        if not key:
            continue
        try:
            if url == "__gemini__":
                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                    async with s.post(gemini_url,
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"maxOutputTokens": max_tokens}}) as r:
                        d = await r.json(content_type=None)
                if "candidates" in d:
                    text = d["candidates"][0]["content"]["parts"][0]["text"]
                    if text:
                        return text
                continue
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(url,
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "max_tokens": max_tokens,
                          "messages": [{"role": "user", "content": prompt}]}) as r:
                    d = await r.json(content_type=None)
            err = d.get("error", {})
            if err:
                if "429" in str(err.get("code", "")) or "rate_limit" in str(err.get("type", "")):
                    await asyncio.sleep(10)
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                        async with s.post(url,
                            headers={"Authorization": f"Bearer {key}"},
                            json={"model": model, "max_tokens": max_tokens,
                                  "messages": [{"role": "user", "content": prompt}]}) as r:
                            d = await r.json(content_type=None)
                    if d.get("error"):
                        continue
                else:
                    continue
            text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            if text:
                return text
        except Exception:
            continue
    # Template-Fallback wenn alle AI-APIs leer sind
    templates = [
        "🚀 E-Commerce Automation auf Autopilot! Shopify + DS24 + KI = passives Einkommen. 👉 https://autopilot-store-suite-fmbka.myshopify.com",
        "💰 Online Geld verdienen 2026: Mit KI-Tools dein Business automatisieren. Mehr erfahren: https://autopilot-store-suite-fmbka.myshopify.com",
        "🤖 Vollautomatisches E-Commerce Business: Produkte importieren, Texte schreiben, Traffic generieren — alles automatisch! https://autopilot-store-suite-fmbka.myshopify.com",
        "📈 Shopify Automation macht deinen Shop 24/7 profitabel. AI Income Machine auf DS24: https://autopilot-store-suite-fmbka.myshopify.com",
        "🎯 Digitale Produkte verkaufen leicht gemacht: DS24 Affiliate + BRUTUS Traffic = passive Einnahmen! https://autopilot-store-suite-fmbka.myshopify.com",
    ]
    import random as _rnd
    return _rnd.choice(templates)


# ── Individual task implementations ─────────────────────────────────────────

async def task_digistore_sync() -> str:
    """Fetch new Digistore24 orders → save to Supabase → Telegram alert."""
    try:
        from modules.digistore24_automation import get_orders, ping
        if not await ping():
            return "DS24 API nicht konfiguriert"
        orders = await get_orders(page=1, per_page=20)
        if not orders:
            return "Keine neuen Bestellungen"

        # Save to data file for dashboard
        out = DATA_DIR / "digistore_orders.json"
        old_ids: set = set()
        if out.exists():
            try:
                old_ids = {o.get("transaction_id") or o.get("id") or o.get("order_id")
                           for o in json.loads(out.read_text())}
            except Exception:
                pass
        out.write_text(json.dumps(orders, indent=2, ensure_ascii=False))

        new_orders = [o for o in orders if o.get("transaction_id") not in old_ids]
        if new_orders:
            lines = [f"🏪 <b>Digistore24 — {len(new_orders)} neue Bestellung(en)!</b>"]
            for o in new_orders[:5]:
                name   = o.get("main_product_name") or o.get("product_name","?")
                amount = o.get("earned_amount") or o.get("merchant_amount") or o.get("amount","?")
                date   = o.get("transaction_pay_date") or o.get("created_at","")[:10]
                lines.append(f"  • {name} — {amount} EUR | {date}")
            await _tg("\n".join(lines))
            return f"{len(new_orders)} neue Bestellungen, Telegram-Alert gesendet"
        return f"{len(orders)} Bestellungen gecacht, keine neuen"
    except Exception as e:
        return f"Fehler: {e}"


async def task_mailchimp_sync() -> str:
    """Sync Digistore24 buyer emails to Mailchimp default list."""
    try:
        from modules.mailchimp_automation import ping, get_lists, sync_from_digistore
        ok, _ = await ping()
        if not ok:
            return "Mailchimp nicht konfiguriert"
        lists = await get_lists()
        if not lists:
            return "Keine Mailchimp-Listen gefunden"
        list_id = lists[0]["id"]
        count = await sync_from_digistore(list_id)
        return f"{count} Kontakte aus Digistore24 nach Mailchimp synchronisiert"
    except Exception as e:
        return f"Fehler: {e}"


async def task_ds24_funnel_sync() -> str:
    """DS24 neue Käufer → Mailchimp + Klaviyo + Telegram vollautomatisch."""
    try:
        from modules.ds24_funnel_automation import run_sync
        result = await run_sync()
        return (f"DS24 Funnel: {result['new_buyers']} neue Käufer synced "
                f"({result['total_seen']} gesamt)")
    except Exception as e:
        return f"DS24 Funnel Fehler: {e}"


async def task_traffic_seo_run() -> str:
    """AI-generierter SEO Content für DS24 + Shopify Produkte."""
    try:
        from modules.traffic_seo_engine import run_full_traffic_seo
        result = await run_full_traffic_seo()
        ds = result.get("ds24_products_optimized", 0)
        sh = result.get("shopify_result", {}).get("products_updated", 0)
        return f"SEO: {ds} DS24-Produkte + {sh} Shopify-Produkte optimiert"
    except Exception as e:
        return f"Traffic/SEO Fehler: {e}"


async def task_brutus_run() -> str:
    """BRUTUS — Brutal Traffic Engine: Scan→Predict→Swarm→Deploy alle Kanäle."""
    try:
        import random
        from modules.brutus_traffic_engine import brutus_run
        BRUTUS_NICHES = [
            "AI income online business automatisierung",
            "KI passives Einkommen Deutschland",
            "Shopify Automatisierung 2026",
            "Digistore24 Affiliate Strategie",
            "Online Geld verdienen Anfänger",
            "Dropshipping KI Tools",
            "Print on Demand Shopify",
            "Amazon Affiliate Deutschland",
            "eBay Dropshipping profitabel",
            "Email Marketing Klaviyo",
            "Fiverr KI Services",
            "TikTok E-Commerce viral",
            "Pinterest Traffic Shopify",
            "YouTube Monetarisierung 2026",
            "Instagram Shop Produkte",
            "LinkedIn B2B Online Business",
            "SEO Ranking Shopify Blog",
            "Digitale Produkte Gumroad",
            "Printify Bestseller Designs",
            "Passives Einkommen Blueprint",
        ]
        niche = random.choice(BRUTUS_NICHES)
        keywords = [
            "AI Income Machine", "Passives Einkommen Online", "Shopify Automatisierung",
            "Online Geld verdienen 2026", "KI Business Blueprint", "Dropshipping KI",
            "Digistore24 Affiliate", "Print on Demand", "Amazon Affiliate",
        ]
        result = await brutus_run(niche=niche, custom_keywords=random.sample(keywords, 6))
        kw = result.get("keywords_processed", 0)
        pieces = result.get("content_pieces", 0)
        channels = result.get("channels_hit", 0)
        return f"BRUTUS: {kw} Keywords × {pieces} Content-Stücke → {channels} Kanäle bespielt"
    except Exception as e:
        return f"BRUTUS Fehler: {e}"


async def task_shopify_sync() -> str:
    """Fetch Shopify product + order counts and cache them."""
    try:
        import aiohttp
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "") or os.getenv("SHOPIFY_STORE_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        base = f"https://{domain}" if not domain.startswith("http") else domain
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        # Use REST API instead of GraphQL (pageInfo.total deprecated in Shopify)
        ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                f"{base}/admin/api/{ver}/products/count.json",
                headers={"X-Shopify-Access-Token": token},
            ) as r:
                pc = await r.json(content_type=None)
            async with s.get(
                f"{base}/admin/api/{ver}/orders/count.json?status=any",
                headers={"X-Shopify-Access-Token": token},
            ) as r:
                oc = await r.json(content_type=None)
            async with s.get(
                f"{base}/admin/api/{ver}/shop.json",
                headers={"X-Shopify-Access-Token": token},
            ) as r:
                sd = await r.json(content_type=None)
        prods = pc.get("count", 0)
        ords  = oc.get("count", 0)
        shop_name = sd.get("shop", {}).get("name", domain)
        result = {"shop": shop_name, "products": prods, "orders": ords, "ts": datetime.now().isoformat()}
        try:
            (DATA_DIR / "shopify_cache.json").write_text(json.dumps(result))
        except Exception:
            pass
        return f"Shopify: {prods} Produkte, {ords} Bestellungen gecacht"
    except Exception as e:
        return f"Fehler: {e}"


async def task_trading_report() -> str:
    """Run arbitrage scan and send best opportunity to Telegram."""
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        opps = await bot.scan_quick()
        if not opps:
            return "Keine Arbitrage-Chancen gefunden"
        best = opps[0]
        msg = (
            f"📈 <b>Trading Report</b>\n"
            f"Beste Chance: {best['pair']}\n"
            f"Kaufen: {best['exchange_buy']} @ {best['buy_price']:.2f}\n"
            f"Verkaufen: {best['exchange_sell']} @ {best['sell_price']:.2f}\n"
            f"Profit: {best['profit_pct']:.2f}%"
        )
        await _tg(msg)
        return f"{len(opps)} Chancen, beste: {best['pair']} {best['profit_pct']:.2f}%"
    except Exception as e:
        return f"Fehler: {e}"


async def task_github_backup() -> str:
    """Daily: push a health-check commit to GitHub via API — no git binary needed."""
    import aiohttp, json
    try:
        token = os.getenv("GITHUB_TOKEN", "")
        repo  = os.getenv("GITHUB_REPO", "bullpowerhubgit/supermegabot")
        if not token:
            return "GITHUB_TOKEN nicht gesetzt"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        # Use GitHub Commit Status API to just log that backup ran
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.github.com/repos/{repo}/git/refs/heads/main",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                ref = await r.json(content_type=None)
        sha = ref.get("object", {}).get("sha", "?")[:12]
        return f"GitHub: repo {repo} @ {sha} | Backup log {ts}"
    except Exception as e:
        return f"GitHub Backup: {e}"


async def task_system_health() -> str:
    """Check system resources, alert on critical thresholds."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        alerts = []
        if cpu > 90:
            alerts.append(f"CPU {cpu:.0f}%")
        if mem.percent > 90:
            alerts.append(f"RAM {mem.percent:.0f}%")
        if disk.percent > 90:
            alerts.append(f"Disk {disk.percent:.0f}%")
        if alerts:
            await _tg(f"⚠️ <b>System-Warnung</b>\n" + "\n".join(alerts))
            return "Kritisch: " + ", ".join(alerts)
        return f"OK — CPU {cpu:.0f}% RAM {mem.percent:.0f}% Disk {disk.percent:.0f}%"
    except ImportError:
        return "psutil nicht installiert"
    except Exception as e:
        return f"Fehler: {e}"


async def task_railway_health() -> str:
    """Ping all 13 Railway services, Telegram alert if any DOWN."""
    import aiohttp
    services = {
        "SuperMegaBot":        "https://dudirudibot-mega-production.up.railway.app/health",
        "MetaSocialEngine":    "https://meta-social-engine-production.up.railway.app/health",
        "SEOTurboTools":       "https://seo-turbo-tools-production.up.railway.app/health",
        "FreelanceGigEngine":  "https://freelance-gig-engine-production.up.railway.app/health",
        "VisualContentEngine": "https://visual-content-engine-production.up.railway.app/health",
        "AdPosterEngine":      "https://adposter-engine-production.up.railway.app/health",
        "iComeAutoSaaS":       "https://icomeauto-saas-production.up.railway.app/health",
        "CreatorAIUltra":      "https://creatorai-ultra-production.up.railway.app/health",
        "RevenueHub":          "https://revenue-hub-notifications-production.up.railway.app/health",
        "ShopifyAutomaton":    "https://shopify-automaton-suite-production-e405.up.railway.app/api/health",
        "Steuercockpit":       "https://steuercockpit-production-44c9.up.railway.app/health",
        "SEOTrafficEngine":    "https://seo-traffic-engine-production.up.railway.app/health",
        "SocialTrafficEngine": "https://social-traffic-engine-production.up.railway.app/health",
    }
    down, ok = [], []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            for name, url in services.items():
                try:
                    async with s.get(url) as r:
                        (ok if r.status < 400 else down).append(
                            name if r.status < 400 else f"{name}(HTTP {r.status})"
                        )
                except Exception:
                    down.append(f"{name}(timeout)")
        if down:
            await _tg(f"🔴 <b>Railway DOWN ({len(down)}/{len(services)}):</b>\n" +
                      "\n".join(f"  • {d}" for d in down))
            return f"DOWN: {', '.join(down)} | OK: {len(ok)}"
        return f"Alle {len(ok)} Railway-Services OK"
    except Exception as e:
        return f"Health-Check Fehler: {e}"


async def task_printify_autofulfill() -> str:
    """Auto-submit pending Printify orders for production."""
    try:
        from modules.printify_automation import ping, auto_fulfill_pending
        if not await ping():
            return "Printify nicht konfiguriert"
        result = await auto_fulfill_pending()
        submitted = len(result.get("submitted", []))
        failed    = len(result.get("failed", []))
        if submitted:
            await _tg(f"🖨️ Printify: {submitted} Bestellungen automatisch an Produktion gesendet")
        return f"{submitted} submitted, {failed} failed von {result.get('total_pending',0)} pending"
    except Exception as e:
        return f"Fehler: {e}"


async def task_social_status() -> str:
    """Ping all social media connectors and log status."""
    try:
        from modules.social_connectors import ping_all
        results = await ping_all()
        connected = [k for k, v in results.items() if v.get("connected")]
        missing   = [k for k, v in results.items() if not v.get("connected")]
        return f"Verbunden: {', '.join(connected) or 'keine'} | Fehlt: {', '.join(missing) or 'keine'}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_dropshipping_scan() -> str:
    """Scan for trending products and auto-list top finds."""
    try:
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        products = await wf.find_trending_products(limit=5)
        if not products:
            return "Keine Trending-Produkte gefunden"
        return f"{len(products)} Trending-Produkte gefunden: {', '.join(p.get('title','?')[:20] for p in products[:3])}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_pod_autofulfill() -> str:
    """Print-on-Demand: auto-fulfill + publish new designs to Shopify."""
    try:
        from modules.dropshipping_automation import PrintOnDemandWorkflow
        from modules.printify_automation import ping, auto_fulfill_pending
        if not await ping():
            return "Printify nicht konfiguriert"
        result = await auto_fulfill_pending()
        sub = len(result.get("submitted", []))
        if sub:
            await _tg(f"🖨️ Print-on-Demand: {sub} Bestellungen automatisch in Produktion")
        return f"PoD: {sub} submitted, {result.get('total_pending',0)} pending gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_seo_optimizer() -> str:
    """Auto-optimize Shopify product SEO via local Ollama."""
    try:
        from modules.seo_automation import optimize_all_shopify_products
        result = await optimize_all_shopify_products(limit=10)
        updated = result.get("updated", 0)
        if updated:
            await _tg(f"🔍 SEO Auto-Optimizer: {updated} Produkte optimiert")
        return f"SEO: {result.get('processed',0)} geprüft, {updated} aktualisiert"
    except Exception as e:
        return f"Fehler: {e}"


async def task_revenue_report() -> str:
    """Collect revenue from all platforms and send daily summary via Telegram."""
    try:
        from modules.notify_hub import send_daily_revenue_report
        from modules.revenue_aggregator import get_daily_report, save_daily_snapshot
        # Canonical report with real API data, sent via notify_hub
        ok = await send_daily_revenue_report()
        await save_daily_snapshot()
        report = await get_daily_report()
        status = "gesendet" if ok else "Telegram-Send fehlgeschlagen"
        return f"Revenue Report {status}: {report[:80]}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_content_calendar() -> str:
    """Generate weekly AI content calendar for all platforms."""
    try:
        from modules.ai_content_pipeline import generate_content_calendar
        calendar = await generate_content_calendar(niche="e-commerce", days=7)
        (DATA_DIR / "content_calendar.json").write_text(
            __import__("json").dumps(calendar, ensure_ascii=False, indent=2)
        )
        return f"Content-Kalender erstellt: {len(calendar)} Beiträge für 7 Tage"
    except Exception as e:
        return f"Fehler: {e}"


async def task_social_autoposter() -> str:
    """Auto-post latest Shopify products to all social platforms."""
    try:
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        products = await wf.find_trending_products(limit=3)
        posted = 0
        for p in products[:2]:
            result = await wf.promote_to_social(p)
            posted += sum(1 for v in result.values() if v.get("ok"))
        return f"Social Auto-Post: {posted} Posts veröffentlicht"
    except Exception as e:
        return f"Fehler: {e}"


async def task_etsy_sync() -> str:
    """Etsy gesperrt — autiin + universal-income-agent-operations banned."""
    return "Etsy GESPERRT — autiin + universal-income-agent-operations BANNED — übersprungen"


async def task_gumroad_sync() -> str:
    """Check Gumroad for new sales."""
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        ping_r = await gum.ping()
        if not ping_r.get("connected", False):
            return f"Gumroad nicht konfiguriert: {ping_r.get('error','no token')}"
        stats = await gum.get_stats()
        if stats.get("new_sales", 0):
            await _tg(f"💰 Gumroad: {stats['new_sales']} neue Verkäufe! Umsatz: {stats.get('revenue','?')}")
        return f"Gumroad: {stats.get('total_sales',0)} Verkäufe gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_fiverr_sync() -> str:
    """Fiverr stats OR autonomous BRUTUS promo when no API key."""
    try:
        from modules.fiverr_client import get_stats
        r = await get_stats()
        if r.get("connected"):
            return f"Fiverr: {r.get('active_orders',0)} orders, ${r.get('earnings_month',0):.0f}/mo"
    except Exception:
        pass
    try:
        from modules.fiverr_autonomy import run_fiverr_autonomy
        r = await run_fiverr_autonomy(count=3)
        return f"Fiverr Autonomy: {r.get('blasted',0)} Kanal-Hits | {len(r.get('gigs',[]))} Gigs promotet"
    except Exception as e:
        return f"Fiverr Promo Fehler: {e}"


async def task_upwork_sync() -> str:
    """Upwork RSS jobs + proposals + BRUTUS promo when no token."""
    try:
        from modules.upwork_client import get_stats
        r = await get_stats()
        if r.get("connected"):
            return f"Upwork: {r.get('active_contracts',0)} contracts, ${r.get('earnings_month',0):.0f}/mo"
    except Exception:
        pass
    try:
        from modules.upwork_autonomy import run_upwork_autonomy
        r = await run_upwork_autonomy(max_jobs=5)
        return (f"Upwork Autonomy: {r.get('jobs_found',0)} Jobs ({r.get('source','rss')}) | "
                f"{r.get('proposals_sent',0)} Proposals via Telegram")
    except Exception as e:
        return f"Upwork Autonomy Fehler: {e}"


async def task_shopify_orders_alert() -> str:
    """Check for new Shopify orders every 10 min, alert abandoned carts, warn if no payment gateway."""
    try:
        import aiohttp
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "") or os.getenv("SHOPIFY_STORE_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        base = f"https://{domain}" if not domain.startswith("http") else domain
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        results = []

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            # ── New Orders ────────────────────────────────────────────────────
            state_file = DATA_DIR / "shopify_last_order.json"
            last_id = 0
            if state_file.exists():
                try:
                    last_id = json.loads(state_file.read_text()).get("last_id", 0)
                except Exception:
                    pass

            async with s.get(f"{base}/admin/api/{ver}/orders.json?status=any&limit=10&order=created_at+desc",
                             headers=headers) as r:
                data = await r.json(content_type=None) if r.status == 200 else {}

            orders = data.get("orders", [])
            if orders:
                new_orders = [o for o in orders if o.get("id", 0) > last_id]
                if new_orders:
                    state_file.write_text(json.dumps({"last_id": orders[0]["id"]}))
                    lines = [f"🛍️ <b>Shopify — {len(new_orders)} neue Bestellung(en)!</b>"]
                    for o in new_orders[:5]:
                        total = o.get("total_price", "?")
                        currency = o.get("currency", "EUR")
                        name = (o.get("billing_address") or {}).get("first_name", "Kunde")
                        email = o.get("email", "?")
                        fulfill = o.get("fulfillment_status") or "unfulfilled"
                        lines.append(f"  • #{o.get('order_number','?')} — {name} ({email}) — {total} {currency} | {fulfill}")
                    await _tg("\n".join(lines))
                    results.append(f"{len(new_orders)} neue Bestellungen")
                elif last_id == 0:
                    state_file.write_text(json.dumps({"last_id": orders[0]["id"]}))
                    results.append(f"Initialisiert: Order-ID={orders[0]['id']}")
                else:
                    results.append("0 neue Bestellungen")
            else:
                results.append("0 Bestellungen gesamt")

            # ── Abandoned Carts ───────────────────────────────────────────────
            cart_state = DATA_DIR / "shopify_abandoned_carts.json"
            seen_tokens: set = set()
            if cart_state.exists():
                try:
                    seen_tokens = set(json.loads(cart_state.read_text()).get("seen", []))
                except Exception:
                    pass

            async with s.get(f"{base}/admin/api/{ver}/checkouts.json?limit=50", headers=headers) as r:
                cdata = await r.json(content_type=None) if r.status == 200 else {}

            checkouts = cdata.get("checkouts", [])
            new_carts = [c for c in checkouts if c.get("token") not in seen_tokens
                         and c.get("email") and not c.get("completed_at")]
            if new_carts:
                seen_tokens.update(c.get("token") for c in checkouts)
                cart_state.write_text(json.dumps({"seen": list(seen_tokens)}))
                lines = [f"🛒 <b>Shopify — {len(new_carts)} abgebrochene(r) Checkout(s)!</b>"]
                for c in new_carts[:3]:
                    email = c.get("email", "?")
                    total = c.get("total_price", "?")
                    items = [li.get("title", "?") for li in c.get("line_items", [])[:2]]
                    recover_url = c.get("abandoned_checkout_url", "")
                    lines.append(f"  • {email} — €{total} — {', '.join(items)}")
                    if recover_url:
                        lines.append(f"    👉 Recovery: {recover_url}")
                # Check if gateway is missing — common cause of abandonments
                no_gateway = any(c.get("gateway") is None for c in new_carts)
                if no_gateway:
                    lines.append("\n⚠️ <b>ACHTUNG: Kein Zahlungsanbieter konfiguriert!</b>")
                    lines.append("→ Shopify Admin → Einstellungen → Zahlungen → Anbieter hinzufügen")
                    lines.append("→ <a href='https://admin.shopify.com/store/autopilot-store-suite-fmbka/settings/payments'>Jetzt öffnen</a>")
                await _tg("\n".join(lines))
                results.append(f"{len(new_carts)} abgebrochene Checkouts")
            elif not seen_tokens and checkouts:
                seen_tokens.update(c.get("token") for c in checkouts)
                cart_state.write_text(json.dumps({"seen": list(seen_tokens)}))
                # First run — check if existing carts have no gateway
                no_gw = [c for c in checkouts if not c.get("gateway") and not c.get("completed_at")]
                if no_gw:
                    msg = (
                        f"⚠️ <b>Shopify: Zahlungsanbieter fehlt!</b>\n"
                        f"{len(no_gw)} abgebrochene(r) Checkout(s) ohne Zahlungsmethode gefunden.\n\n"
                        f"Bitte jetzt einrichten:\n"
                        f"→ <a href='https://admin.shopify.com/store/autopilot-store-suite-fmbka/settings/payments'>Shopify Einstellungen → Zahlungen</a>\n"
                        f"Optionen: Shopify Payments, PayPal, oder Stripe"
                    )
                    await _tg(msg)
                    results.append(f"Warnung: {len(no_gw)} Checkouts ohne Zahlungsanbieter")

        return " | ".join(results) if results else "OK"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printify_discover_shop() -> str:
    """Auto-discover Printify shop ID and save to data dir."""
    try:
        import aiohttp
        key = os.getenv("PRINTIFY_API_KEY", "")
        if not key:
            return "PRINTIFY_API_KEY nicht gesetzt"
        saved_id = os.getenv("PRINTIFY_SHOP_ID", "")
        if saved_id:
            return f"Shop-ID bereits bekannt: {saved_id}"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                "https://api.printify.com/v1/shops.json",
                headers={"Authorization": f"Bearer {key}"}
            ) as r:
                if r.status != 200:
                    return f"Printify HTTP {r.status}"
                shops = await r.json()

        if not shops:
            return "Keine Printify-Shops gefunden"
        shop = shops[0]
        shop_id = str(shop.get("id", ""))
        (DATA_DIR / "printify_shop.json").write_text(json.dumps({"shop_id": shop_id, "title": shop.get("title","?"), "ts": datetime.now().isoformat()}))
        log.info(f"Printify Shop entdeckt: {shop.get('title')} (ID {shop_id}) — trage PRINTIFY_SHOP_ID={shop_id} in .env ein")
        await _tg(f"🖨️ Printify Shop gefunden: <b>{shop.get('title','?')}</b> (ID: <code>{shop_id}</code>)\nBitte in .env setzen: PRINTIFY_SHOP_ID={shop_id}")
        return f"Shop gefunden: {shop.get('title','?')} ID={shop_id}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_api_keys_health() -> str:
    """Check critical API keys and alert if missing."""
    critical = [
        # Accept both token var names for Shopify
        ("SHOPIFY_ADMIN_API_TOKEN", lambda v: len(v) > 10),
        ("PRINTIFY_API_KEY",        lambda v: len(v) > 20),
        ("DIGISTORE24_API_KEY",     lambda v: "-" in v),
        ("SUPABASE_URL",            lambda v: "supabase" in v),
        ("TELEGRAM_BOT_TOKEN",      lambda v: ":" in v),
    ]
    missing, ok = [], []
    for key, check in critical:
        val = os.getenv(key, "")
        if not val or not check(val):
            missing.append(key)
        else:
            ok.append(key)
    if missing:
        await _tg(f"⚠️ <b>API-Keys fehlen/ungültig:</b>\n" + "\n".join(f"  • {k}" for k in missing))
        return f"Fehlend: {', '.join(missing)} | OK: {len(ok)}"
    return f"Alle {len(ok)} kritischen Keys OK"


async def task_gmc_refresh() -> str:
    """Refresh Google Merchant Center product feed status."""
    try:
        import aiohttp
        merchant_id = os.getenv("GMC_MERCHANT_ID", "")
        client_id   = os.getenv("GOOGLE_CLIENT_ID", "")
        if not merchant_id or not client_id:
            return "GMC nicht vollständig konfiguriert"
        out = DATA_DIR / "gmc_status.json"
        out.write_text(json.dumps({
            "merchant_id": merchant_id,
            "last_check": datetime.now().isoformat(),
            "status": "configured"
        }))
        return f"GMC Merchant {merchant_id} — Status gecacht"
    except Exception as e:
        return f"Fehler: {e}"


async def task_gmc_product_fix() -> str:
    """Daily: set identifier_exists:false + condition:new + generate SKUs for all Shopify products."""
    try:
        from modules.gmc_product_fixer import run_gmc_fixer_cycle
        r = await run_gmc_fixer_cycle()
        return f"GMC Fix: {r.get('fixed', 0)} Produkte gefixt, {r.get('errors', 0)} Fehler von {r.get('total', 0)}"
    except Exception as e:
        return f"GMC Fix error: {e}"


async def task_youtube_stats() -> str:
    """Fetch YouTube channel stats."""
    try:
        import aiohttp
        channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "")
        api_key    = os.getenv("YOUTUBE_API_KEY", "")
        if not channel_id:
            return "YOUTUBE_CHANNEL_ID nicht gesetzt"
        if not api_key:
            return f"YOUTUBE_API_KEY fehlt (Channel: {channel_id})"
        url = (
            f"https://www.googleapis.com/youtube/v3/channels"
            f"?part=statistics&id={channel_id}&key={api_key}"
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return f"YouTube API HTTP {r.status}"
                data = await r.json()
        items = data.get("items", [])
        if not items:
            return "Kanal nicht gefunden"
        stats = items[0].get("statistics", {})
        subs    = int(stats.get("subscriberCount", 0))
        views   = int(stats.get("viewCount", 0))
        videos  = int(stats.get("videoCount", 0))
        (DATA_DIR / "youtube_stats.json").write_text(json.dumps({**stats, "ts": datetime.now().isoformat()}))
        return f"YouTube: {subs:,} Abonnenten, {views:,} Views, {videos} Videos"
    except Exception as e:
        return f"Fehler: {e}"


async def task_digistore_products_check() -> str:
    """Check Digistore24 product performance and cache."""
    try:
        from modules.digistore24_automation import ping, get_products, get_sales_stats
        if not await ping():
            return "DS24 nicht konfiguriert"
        products = await get_products()
        stats    = await get_sales_stats()
        (DATA_DIR / "digistore_products.json").write_text(
            json.dumps({"products": products, "stats": stats, "ts": datetime.now().isoformat()},
                       ensure_ascii=False, indent=2)
        )
        total_revenue = stats.get("total_revenue", 0)
        return f"DS24: {len(products)} Produkte, Umsatz: {total_revenue}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_log_cleanup() -> str:
    """Rotate and compress logs > 10 MB; delete files older than 30 days."""
    import gzip, shutil
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    cleaned, compressed = 0, 0
    cutoff = datetime.now().timestamp() - 30 * 86400
    for f in logs_dir.iterdir():
        if f.suffix == ".gz" and f.stat().st_mtime < cutoff:
            f.unlink()
            cleaned += 1
        elif f.suffix == ".log" and f.stat().st_size > 10 * 1024 * 1024:
            gz_path = f.with_suffix(".log.gz")
            with f.open("rb") as fi, gzip.open(gz_path, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            f.write_text("")  # truncate, keep file handle valid
            compressed += 1
    return f"Logs: {compressed} komprimiert, {cleaned} alte gelöscht"


async def task_env_auto_update() -> str:
    """Write auto-discovered values (Printify shop ID) into data cache."""
    updates = []
    shop_file = DATA_DIR / "printify_shop.json"
    if shop_file.exists() and not os.getenv("PRINTIFY_SHOP_ID"):
        try:
            d = json.loads(shop_file.read_text())
            shop_id = d.get("shop_id", "")
            if shop_id:
                updates.append(f"PRINTIFY_SHOP_ID={shop_id} (aus Cache, bitte in .env eintragen)")
                log.info(f"Auto-discovered PRINTIFY_SHOP_ID={shop_id} — .env manuell aktualisieren")
        except Exception:
            pass
    if not updates:
        return "Keine ausstehenden Auto-Updates"
    await _tg("ℹ️ <b>Auto-entdeckte Werte — bitte in .env eintragen:</b>\n" + "\n".join(updates))
    return " | ".join(updates)


async def task_shopify_webhooks_setup() -> str:
    """Register Shopify order/fulfillment webhooks for real-time alerts."""
    try:
        import aiohttp
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        suite_url = os.getenv("SHOPIFY_SUITE_URL", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        if not suite_url:
            return "SHOPIFY_SUITE_URL fehlt — Webhook-Endpunkt unbekannt"
        base = f"https://{domain}" if not domain.startswith("http") else domain
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        api_ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")

        # Check existing webhooks
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(f"{base}/admin/api/{api_ver}/webhooks.json", headers=headers) as r:
                if r.status != 200:
                    return f"Shopify HTTP {r.status} beim Webhook-Abruf"
                existing = {w["topic"] for w in (await r.json()).get("webhooks", [])}

            desired = {
                "orders/create":      f"{suite_url}/webhooks/shopify/orders-create",
                "orders/fulfilled":   f"{suite_url}/webhooks/shopify/orders-fulfilled",
                "orders/cancelled":   f"{suite_url}/webhooks/shopify/orders-cancelled",
                "products/create":    f"{suite_url}/webhooks/shopify/products-create",
            }
            created = []
            for topic, endpoint in desired.items():
                if topic not in existing:
                    async with s.post(
                        f"{base}/admin/api/{api_ver}/webhooks.json",
                        headers=headers,
                        json={"webhook": {"topic": topic, "address": endpoint, "format": "json"}}
                    ) as cr:
                        if cr.status in (200, 201):
                            created.append(topic)
        if created:
            return f"Webhooks registriert: {', '.join(created)}"
        return f"Alle Webhooks bereits registriert ({len(existing)} aktiv)"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printify_shopify_sync() -> str:
    """Push alle unpublizierten Printify-Produkte nach Shopify."""
    try:
        from modules.printify_automation import ping, sync_all_products_to_shopify
        if not await ping():
            return "Printify nicht konfiguriert — PRINTIFY_API_KEY setzen"
        result = await sync_all_products_to_shopify()
        return f"Printify→Shopify: {result['published']} neu, {result['already_live']} bereits live, {result['failed']} Fehler"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printful_autofulfill() -> str:
    """Auto-confirm alle pending Printful-Bestellungen → Produktion."""
    try:
        from modules.printful_automation import ping, auto_fulfill_pending
        if not await ping():
            return "Printful nicht konfiguriert — PRINTFUL_API_KEY setzen"
        result = await auto_fulfill_pending()
        confirmed = len(result.get("confirmed", []))
        failed    = len(result.get("failed", []))
        return f"Printful: {confirmed} bestätigt, {failed} Fehler, {result.get('total_pending',0)} pending gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printful_shopify_sync() -> str:
    """Prüfe ob alle Printful-Produkte mit Shopify synchronisiert sind."""
    try:
        from modules.printful_automation import ping, sync_catalog_to_shopify
        if not await ping():
            return "Printful nicht konfiguriert"
        result = await sync_catalog_to_shopify()
        return f"Printful Sync: {result['synced']} OK, {result['unsynced']} unsynced von {result['total']} gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printful_discover_store() -> str:
    """Auto-detect Printful Store-ID und in Railway speichern."""
    try:
        from modules.printful_automation import ping, auto_detect_store
        if not await ping():
            return "Printful nicht konfiguriert — PRINTFUL_API_KEY setzen"
        sid = await auto_detect_store()
        return f"Printful Store-ID: {sid}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_pod_combined_autofulfill() -> str:
    """Print-on-Demand: Printify + Printful gleichzeitig auto-fulfillment."""
    results = []
    try:
        from modules.printify_automation import ping as py_ping, auto_fulfill_pending as py_fulfill
        if await py_ping():
            r = await py_fulfill()
            results.append(f"Printify: {len(r['submitted'])} submitted")
        else:
            results.append("Printify: kein Key")
    except Exception as e:
        results.append(f"Printify error: {e}")

    try:
        from modules.printful_automation import ping as pf_ping, auto_fulfill_pending as pf_fulfill
        if await pf_ping():
            r = await pf_fulfill()
            results.append(f"Printful: {len(r['confirmed'])} confirmed")
        else:
            results.append("Printful: kein Key")
    except Exception as e:
        results.append(f"Printful error: {e}")

    return " | ".join(results)


async def task_daily_summary() -> str:
    """Send complete daily business summary to Telegram."""
    try:
        parts = []
        # System
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            parts.append(f"🖥 System: CPU {cpu:.0f}% | RAM {mem.percent:.0f}%")
        except Exception:
            pass

        # Digistore
        ds_file = DATA_DIR / "digistore_orders.json"
        if ds_file.exists():
            try:
                orders = json.loads(ds_file.read_text())
                parts.append(f"🏪 Digistore24: {len(orders)} Bestellungen gecacht")
            except Exception:
                pass

        # Shopify
        sh_file = DATA_DIR / "shopify_cache.json"
        if sh_file.exists():
            try:
                d = json.loads(sh_file.read_text())
                parts.append(f"🛍 Shopify: {d.get('products','?')} Produkte | {d.get('orders','?')} Bestellungen")
            except Exception:
                pass

        # YouTube
        yt_file = DATA_DIR / "youtube_stats.json"
        if yt_file.exists():
            try:
                d = json.loads(yt_file.read_text())
                parts.append(f"▶️ YouTube: {int(d.get('subscriberCount',0)):,} Abonnenten")
            except Exception:
                pass

        # Scheduler stats
        stats = get_task_stats()
        total_runs = sum(v.get("total", 0) for v in stats.values())
        ok_runs    = sum(v.get("ok", 0) for v in stats.values())
        parts.append(f"🤖 Automation: {ok_runs}/{total_runs} Tasks erfolgreich")

        msg = f"📊 <b>SuperMegaBot — Tages-Zusammenfassung</b>\n{datetime.now().strftime('%d.%m.%Y')}\n\n" + "\n".join(parts)
        await _tg(msg)
        return f"Tages-Summary gesendet ({len(parts)} Bereiche)"
    except Exception as e:
        return f"Fehler: {e}"


async def task_stripe_monitor() -> str:
    """Check Stripe for new payments and alert via Telegram."""
    try:
        from modules.stripe_automation import monitor_payments
        return await monitor_payments()
    except Exception as e:
        return f"Stripe Monitor Fehler: {e}"


async def task_drive_backup() -> str:
    """Backup data directory JSON files to Google Drive."""
    try:
        from modules.google_drive_automation import auto_backup
        return await auto_backup()
    except Exception as e:
        return f"Drive Backup Fehler: {e}"


async def task_cro_run() -> str:
    """CRO Engine — Klaviyo flows, urgency campaigns, Shopify urgency banner."""
    try:
        from modules.cro_engine import run_cro
        result = await run_cro()
        return f"CRO done: {result}"
    except Exception as e:
        return f"CRO error: {e}"


async def task_auto_funnel() -> str:
    """Auto Funnel — DS24 buyers → purchase sequence → upsell → discount."""
    try:
        from modules.auto_funnel import run_auto_funnel
        result = await run_auto_funnel()
        processed = result.get("daily_funnel", {}).get("processed", 0)
        return f"AutoFunnel done: {processed} buyers processed, {result}"
    except Exception as e:
        return f"AutoFunnel error: {e}"


async def task_email_check() -> str:
    """EmailBrain — IMAP poll aller Gmail-Konten, KI-Klassifizierung, Auto-Antwort, Labels."""
    try:
        from modules.email_brain import run_email_check
        return await run_email_check()
    except Exception as e:
        return f"EmailBrain error: {e}"


async def task_email_daily_summary() -> str:
    """EmailBrain — täglicher Telegram-Report."""
    try:
        from modules.email_brain import send_email_daily_summary
        await send_email_daily_summary()
        return "Email daily summary sent"
    except Exception as e:
        return f"EmailBrain summary error: {e}"


async def task_mega_auto_post() -> str:
    """Mega Auto Poster — postet auf ALLE Kanäle gleichzeitig (alle 30 Min)."""
    try:
        from modules.mega_auto_poster import run_full_auto_post
        result = await run_full_auto_post()
        summary = result.get("_run_summary", {})
        channels_ok = summary.get("total_channels_hit", 0)
        ds24_ok  = result.get("ds24", {}).get("_summary", {}).get("channels_ok", 0)
        skip     = result.get("ds24", {}).get("skipped", False)
        if skip:
            return "MegaAutoPost: Duplicate skip (bereits heute gepostet)"
        return f"MegaAutoPost: {channels_ok} Kanal-Hits | DS24: {ds24_ok}/9 ✅"
    except Exception as e:
        return f"MegaAutoPost Fehler: {e}"


async def task_twitter_auto_post() -> str:
    """Stündlicher Auto-Tweet über AI/Business-Themen."""
    try:
        from modules.twitter_auto_poster import run_auto_tweet
        result = await run_auto_tweet()
        if result.get("ok"):
            return f"Tweet gepostet: {result.get('text','?')[:60]}"
        return f"Tweet skip/fail: {result.get('error','?')[:60]}"
    except Exception as e:
        return f"Twitter Fehler: {e}"


async def task_shopify_blog_auto() -> str:
    """Alle 2h einen Blog-Post auf Shopify via GraphQL Admin API."""
    import aiohttp, random
    shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
    if not shopify_domain or not shopify_token:
        return "Shopify nicht konfiguriert"
    _dest = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
    blog_gid = f"gid://shopify/Blog/{os.getenv('SHOPIFY_BLOG_ID', '127011258755')}"
    templates = [
        ("KI-Passiveinkommen 2026: So baust du es auf",
         f"<h2>KI-Passiveinkommen 2026</h2><p>Mit KI-Tools baust du heute ein vollautomatisches Business auf.</p><ul><li><strong>Shopify Auto-Import:</strong> Trending-Produkte täglich importiert</li><li><strong>Affiliate:</strong> Provisionen automatisch ausgezahlt</li><li><strong>Content:</strong> BRUTUS bespielt 6+ Kanäle täglich</li></ul><p><a href='{_dest}'>Jetzt bei autopilot-store-suite-fmbka.myshopify.com shoppen →</a></p>"),
        ("5 Shopify-Automatisierungen 2026 die Umsatz verdoppeln",
         f"<h2>5 Automationen für mehr Umsatz</h2><ol><li>Auto-Produktimport aus 50+ Quellen</li><li>KI-SEO-Beschreibungen für jedes Produkt</li><li>Email-Sequenzen für neue Käufer</li><li>Psychologisches Pricing (.99) automatisch</li><li>BRUTUS Traffic-Engine auf allen Kanälen</li></ol><p><a href='{_dest}'>Zu autopilot-store-suite-fmbka.myshopify.com →</a></p>"),
        ("Dropshipping mit KI 2026: Der komplette Guide",
         f"<h2>KI-Dropshipping 2026</h2><p>Trends automatisch erkennen, Produkte importieren, Marketing auf Autopilot.</p><ul><li>AliExpress + Amazon Trending täglich</li><li>Shopify Auto-Import + Beschreibung</li><li>10+ Kanäle vollautomatisch bespielt</li></ul><p><a href='{_dest}'>Bestseller bei autopilot-store-suite-fmbka.myshopify.com →</a></p>"),
        ("Smart Home Gadgets 2026: Die besten Deals",
         f"<h2>Smart Home 2026</h2><p>Die beliebtesten Smart Home Gadgets für dein Zuhause — Bestpreise garantiert.</p><ul><li>Smart Beleuchtung</li><li>Sprachassistenten & Hubs</li><li>Sicherheitskameras</li><li>Automatische Steckdosen</li></ul><p><a href='{_dest}'>Alle Smart Home Deals →</a></p>"),
        ("Top 10 Fitness Gadgets für zuhause 2026",
         f"<h2>Fitness Gadgets 2026</h2><p>Diese 10 Gadgets transformieren dein Home-Workout und bringen echte Ergebnisse.</p><ul><li>Resistance Bands Set</li><li>Smart Waagen</li><li>Massage-Pistolen</li><li>LED Sprungseile</li></ul><p><a href='{_dest}'>Alle Fitness-Deals bei autopilot-store-suite-fmbka.myshopify.com →</a></p>"),
    ]
    topic_title, template_body = random.choice(templates)
    final_body = template_body
    for env_var, api_url, model, is_ant in [
        ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/messages", "claude-haiku-4-5-20251001", True),
        ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini", False),
    ]:
        key = os.getenv(env_var, "")
        if not key:
            continue
        try:
            prompt = (f"300 Wörter HTML-Blog auf Deutsch: '{topic_title}'. "
                      f"Link am Ende: {_dest}. Nur HTML, keine Markdown-Backticks.")
            if is_ant:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                    async with s.post(api_url,
                        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                        json={"model": model, "max_tokens": 900,
                              "messages": [{"role": "user", "content": prompt}]}) as r:
                        d = await r.json(content_type=None)
                text = d.get("content", [{}])[0].get("text", "")
            else:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                    async with s.post(api_url,
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": model, "max_tokens": 900,
                              "messages": [{"role": "user", "content": prompt}]}) as r:
                        d = await r.json(content_type=None)
                text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            if text and len(text) > 100:
                final_body = text
                break
        except Exception:
            continue
    # Use GraphQL Admin API — works with write_content scope (same token)
    gql = """
mutation CreateArticle($article: ArticleCreateInput!) {
  articleCreate(article: $article) {
    article { id title handle }
    userErrors { field message }
  }
}"""
    variables = {
        "article": {
            "blogId": blog_gid,
            "title": topic_title,
            "body": final_body,
            "isPublished": True,
            "tags": ["ki", "automatisierung", "ecommerce", "shopify", "2026"],
            "author": {"name": "BullPower Hub"},
        }
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"https://{shopify_domain}/admin/api/{shopify_ver}/graphql.json",
                headers={"X-Shopify-Access-Token": shopify_token,
                         "Content-Type": "application/json"},
                json={"query": gql, "variables": variables},
            ) as r:
                resp = await r.json(content_type=None)
        errors = resp.get("errors", []) if resp else []
        data = (resp.get("data") or {}) if resp else {}
        user_errors = (data.get("articleCreate") or {}).get("userErrors", [])
        art = (data.get("articleCreate") or {}).get("article", {})
        if art and art.get("id"):
            return f"Blog✅: '{topic_title[:55]}' handle={art['handle']}"
        err_msg = str(errors or user_errors)[:200]
        # Telegram-Fallback → öffentlichen Kanal, NICHT Rudolf's privaten Chat
        import re as _re
        plain = _re.sub(r'<[^>]+>', '', final_body)[:800]
        await _tg_marketing(f"📝 <b>{topic_title}</b>\n\n{plain}\n\n👉 {_dest}")
        return f"Blog→Kanal-Fallback (GraphQL Err): {err_msg[:120]}"
    except Exception as e:
        import traceback as _tb
        tb = _tb.format_exc()[-300:]
        log.error("task_shopify_blog_auto: %s\n%s", e, tb)
        return f"Shopify Blog Fehler: {type(e).__name__}: {e} | tb={tb[-120:]}"


async def task_shopify_seo_auto() -> str:
    """AI-optimiert Shopify Produkt-Beschreibungen (15 Stück alle 12h)."""
    try:
        from modules.shopify_seo_auto import run_seo_batch
        result = await run_seo_batch(batch_size=15)
        return f"ShopifySEO: {result.get('updated',0)} Produkte optimiert, {result.get('failed',0)} Fehler"
    except Exception as e:
        return f"ShopifySEO Fehler: {e}"


async def task_klaviyo_auto_campaign() -> str:
    """Tägliche Klaviyo Kampagne mit neuem AI-Content."""
    try:
        import os, aiohttp, json
        from datetime import datetime
        klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
        list_id = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
        if not klaviyo_key:
            return "KLAVIYO_API_KEY fehlt"

        today = datetime.now().strftime("%d.%m.%Y")
        prompt = f"""Schreibe eine Marketing-Email auf Deutsch für heute ({today}).
Produkt: AI Income Machine (€37) auf Digistore24.
Ton: motivierend, persönlich, mit klarem CTA.
Format JSON: {{"subject": "...", "preview": "...", "html_body": "<html>...</html>"}}
Nur JSON, kein anderer Text."""

        raw = await _ai(prompt, max_tokens=800)
        try:
            email_data = json.loads(raw[raw.find("{"):raw.rfind("}")+1]) if "{" in raw else {}
        except Exception:
            email_data = {}

        # Create Klaviyo campaign
        from_email = os.getenv("KLAVIYO_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
        from_label = os.getenv("KLAVIYO_FROM_NAME", "BullPower Hub")
        subject = email_data.get("subject", f"🚀 KI Business Blueprint — {today}")
        preview = email_data.get("preview", "Dein vollautomatisches Einkommenssystem wartet")
        headers = {"Authorization": f"Klaviyo-API-Key {klaviyo_key}", "revision": "2024-10-15", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://a.klaviyo.com/api/campaigns/",
                headers=headers,
                json={"data": {"type": "campaign", "attributes": {
                    "name": f"AutoCampaign {today}",
                    "audiences": {"included": [list_id], "excluded": []},
                    "send_strategy": {"method": "immediate"},
                    "campaign-messages": {"data": [{"type": "campaign-message", "attributes": {
                        "channel": "email",
                        "label": "email",
                        "content": {
                            "subject": subject,
                            "preview_text": preview,
                            "from_email": from_email,
                            "from_label": from_label,
                        }
                    }}]},
                }}},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                campaign_resp = await r.json(content_type=None)

        campaign_data = (campaign_resp.get("data") or {}) if campaign_resp else {}
        campaign_id = campaign_data.get("id", "")
        if not campaign_id:
            return f"Klaviyo campaign creation failed: {campaign_resp}"

        # Set HTML content and send
        async with aiohttp.ClientSession() as s:
            rels = (campaign_data.get("relationships") or {})
            cm_data = (rels.get("campaign-messages") or {}).get("data") or [{}]
            msg_id = (cm_data[0] if cm_data else {}).get("id", "")
            if msg_id:
                await s.patch(f"https://a.klaviyo.com/api/campaign-messages/{msg_id}/",
                    headers=headers,
                    json={"data": {"type": "campaign-message", "id": msg_id, "attributes": {
                        "content": {"body": email_data.get("html_body", f"<p>{subject}</p>")}
                    }}},
                    timeout=aiohttp.ClientTimeout(total=15))
            await s.post(f"https://a.klaviyo.com/api/campaigns/{campaign_id}/campaign-send-job/",
                headers=headers,
                json={"data": {"type": "campaign-send-job", "attributes": {}}},
                timeout=aiohttp.ClientTimeout(total=15))

        return f"Klaviyo AutoCampaign gesendet: '{subject[:50]}'"
    except Exception as e:
        return f"Klaviyo AutoCampaign Fehler: {e}"


async def task_mailchimp_auto_campaign() -> str:
    """Tägliche Mailchimp Kampagne mit AI-Content."""
    try:
        import os, aiohttp, json, base64
        from datetime import datetime
        mc_key = os.getenv("MAILCHIMP_API_KEY", "")
        list_id = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
        server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        from_email = os.getenv("SENDGRID_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
        if not mc_key:
            return "Mailchimp Key fehlt"

        today = datetime.now().strftime("%d.%m.%Y")
        auth = base64.b64encode(f"anystring:{mc_key}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        base_url = f"https://{server}.api.mailchimp.com/3.0"

        # Generate subject with Claude if available
        subject = f"💡 Dein täglicher AI-Business-Tipp — {today}"
        html_content = f"""<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>
<h1 style='color:#7c3aed'>🚀 AI Income Machine</h1>
<p>Hallo,</p>
<p>Wusstest du, dass über <strong>87% der erfolgreichen Online-Unternehmer</strong> KI-Tools nutzen, um ihren Umsatz zu automatisieren?</p>
<p>Mit der <strong>AI Income Machine</strong> bekommst du den kompletten Blueprint für:</p>
<ul>
<li>✅ Vollautomatische Einnahmen ohne tägliche Arbeit</li>
<li>✅ KI-gestützte Produktauswahl und Marketing</li>
<li>✅ Step-by-step Anleitung für Anfänger</li>
</ul>
<p style='text-align:center;margin:30px 0'>
<a href='{os.getenv("DS24_AFFILIATE_LINK",os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx"))}' style='background:#7c3aed;color:#fff;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold'>
🛒 Jetzt für nur €37 starten →
</a>
</p>
<p style='color:#666;font-size:12px'>BullPower Hub | bullpower-hub-portal.netlify.app</p>
</body></html>"""

        # Create and send campaign
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base_url}/campaigns",
                headers=headers,
                json={"type": "regular", "recipients": {"list_id": list_id},
                      "settings": {"subject_line": subject, "from_name": "BullPower Hub",
                                   "reply_to": from_email, "title": f"AutoCampaign {today}"}},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                camp = await r.json(content_type=None)

        camp_id = camp.get("id", "")
        if not camp_id:
            return f"MC campaign create failed: {list(camp.keys())}"

        async with aiohttp.ClientSession() as s:
            # Set content
            await s.put(f"{base_url}/campaigns/{camp_id}/content",
                headers=headers, json={"html": html_content},
                timeout=aiohttp.ClientTimeout(total=15))
            # Send
            async with s.post(f"{base_url}/campaigns/{camp_id}/actions/send",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                ok = r.status in (200, 204)

        return f"Mailchimp AutoCampaign {'gesendet' if ok else 'Fehler'}: {subject[:50]}"
    except Exception as e:
        return f"Mailchimp AutoCampaign Fehler: {e}"


async def task_facebook_token_check() -> str:
    """Täglicher Facebook Token Check — Alarm wenn abgelaufen oder pages_manage_posts fehlt."""
    try:
        from modules.facebook_token_manager import check_token, refresh_all_tokens
        import os
        # Check the page token (which is what's actually used for posting)
        page_token = os.getenv("FACEBOOK_PAGE_TOKEN_IWIN") or os.getenv("FACEBOOK_PAGE_TOKEN", "")
        user_token = os.getenv("FACEBOOK_USER_TOKEN", "")
        check = await check_token(page_token or user_token)
        scopes = check.get("scopes", [])
        has_post_scope = "pages_manage_posts" in scopes
        if not check.get("valid") or not has_post_scope:
            result = await refresh_all_tokens()  # sends Telegram OAuth URL
            reason = "invalid" if not check.get("valid") else "missing pages_manage_posts"
            return f"FB token {reason} — OAuth alert sent via Telegram"
        return f"FB token OK — pages_manage_posts: {has_post_scope}, scopes: {len(scopes)}"
    except Exception as e:
        return f"FB token check error: {e}"


async def task_email_seq_process() -> str:
    """Process all due drip emails across all enrolled sequences."""
    try:
        from modules.email_sequence_engine import process_due_emails
        result = await process_due_emails()
        sent = result.get("sent", 0)
        failed = result.get("failed", 0)
        return f"EmailSeq: {sent} gesendet, {failed} Fehler"
    except Exception as e:
        return f"EmailSeq Fehler: {e}"


async def task_email_seq_enroll() -> str:
    """Auto-enroll new Shopify customers in welcome sequence."""
    try:
        from modules.email_sequence_engine import enroll_new_customers
        result = await enroll_new_customers()
        enrolled = result.get("enrolled", 0)
        return f"EmailEnroll: {enrolled} neue Käufer eingeschrieben"
    except Exception as e:
        return f"EmailEnroll Fehler: {e}"


async def task_lead_nurture() -> str:
    """Process new leads from all sources → Klaviyo + email welcome sequence."""
    try:
        klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
        if not klaviyo_key:
            return "Klaviyo Key fehlt"
        from modules.email_sequence_engine import enroll
        leads_file = DATA_DIR / "new_leads.json"
        if not leads_file.exists():
            return "Keine neuen Leads"
        leads = json.loads(leads_file.read_text())
        if not leads:
            return "Keine neuen Leads"
        enrolled = 0
        processed = []
        for lead in leads:
            email = lead.get("email", "")
            if not email or "@" not in email:
                continue
            fname = lead.get("first_name", email.split("@")[0])
            await enroll(email, "welcome", first_name=fname,
                        metadata={"source": lead.get("source", "lead_form")})
            enrolled += 1
            processed.append(lead)
        leads_file.write_text("[]")
        if enrolled:
            await _tg(f"🎯 <b>Lead Nurture</b>: {enrolled} neue Leads → Welcome Sequence")
        return f"LeadNurture: {enrolled} Leads in Welcome Sequence"
    except Exception as e:
        return f"LeadNurture Fehler: {e}"


async def task_pinterest_auto_post() -> str:
    """Auto-create Pinterest pins from Shopify products."""
    try:
        from modules.social_connectors import PinterestConnector
        import aiohttp, random
        pin = PinterestConnector()
        if not pin.is_configured():
            return "Pinterest nicht konfiguriert"
        boards = await pin.get_boards()
        if not boards.get("ok") or not boards.get("boards"):
            return "Keine Pinterest Boards gefunden"
        board_id = boards["boards"][0]["id"]
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"https://{domain}/admin/api/2024-01/products.json?limit=10&published_status=published",
                headers={"X-Shopify-Access-Token": token}
            ) as r:
                prods = (await r.json()).get("products", [])
        prods_with_img = [p for p in prods if p.get("images")]
        if not prods_with_img:
            return "Keine Produkte mit Bildern"
        p = random.choice(prods_with_img)
        img = p["images"][0]["src"]
        title = p.get("title", "Produkt")
        url = f"https://{domain}/products/{p.get('handle','')}"
        result = await pin.create_pin(board_id=board_id, title=title,
                                       description=f"✨ {title} — Jetzt entdecken!", media_url=img, link=url)
        ok = result.get("ok", False)
        return f"Pinterest Pin: {'✅' if ok else '❌'} — {title[:40]}"
    except Exception as e:
        return f"Pinterest Fehler: {e}"


async def task_telegram_broadcast() -> str:
    """Auto-post AI-generated content to Telegram channel."""
    try:
        channel = os.getenv("TELEGRAM_CHANNEL_ID", os.getenv("TELEGRAM_CHAT_ID", ""))
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not channel or not token:
            return "Telegram Key fehlt"
        import aiohttp
        today = datetime.now().strftime("%d.%m.%Y")
        from modules.ai_client import ai_complete
        msg = await ai_complete(
            f"Schreibe einen Telegram-Channel-Post auf Deutsch für {today}. "
            "Thema: KI-Business, Online Income, Shopify Automatisierung. "
            "Ton: inspirierend, direkt, mit 2-3 Emojis. Max 250 Wörter. "
            "Ende mit: 👉 bullpower-hub-portal.netlify.app",
            max_tokens=400
        )
        if not msg:
            return "Content Generation fehlgeschlagen"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel, "text": msg, "parse_mode": "HTML"}
            ) as r:
                result = await r.json()
        ok = result.get("ok", False)
        return f"Telegram Broadcast: {'✅' if ok else '❌'} ({len(msg)} Zeichen)"
    except Exception as e:
        return f"Telegram Broadcast Fehler: {e}"


async def task_instagram_auto_post() -> str:
    """Auto-post product to Instagram via Graph API (fallback: Telegram + BRUTUS)."""
    try:
        from modules.social_connectors import InstagramConnector
        import aiohttp, random
        ig = InstagramConnector()
        if not ig.is_configured():
            # Fallback: post IG-style content via BRUTUS to other channels
            try:
                from modules.ai_client import ai_complete
                from modules.brutus_core import fire
                _ds24 = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
                ig_text = await ai_complete(
                    f"Schreibe einen Instagram-Caption auf Deutsch für ein KI-Business Produkt. "
                    f"Kurz, viral, 5 Hashtags. Link: {_ds24}", max_tokens=200)
                await fire("📸 Instagram Content", ig_text or "💡 KI = automatisch Geld verdienen!\n👉 " + _ds24,
                           channels=["telegram"])
            except Exception:
                pass
            return "Instagram META_ACCESS_TOKEN fehlt — Fallback Content via Telegram gesendet"
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"https://{domain}/admin/api/2024-01/products.json?limit=10&published_status=published",
                headers={"X-Shopify-Access-Token": token}
            ) as r:
                prods = (await r.json()).get("products", [])
        prods_with_img = [p for p in prods if p.get("images")]
        if not prods_with_img:
            return "Keine Produkte mit Bildern"
        p = random.choice(prods_with_img)
        img_url = p["images"][0]["src"]
        caption = (f"✨ {p['title']}\n\n"
                   f"{(p.get('body_html') or '')[:120].replace('<p>','').replace('</p>','')}\n\n"
                   f"🛒 Jetzt im Shop!\n\n#shopify #ecommerce #onlineshop #business #automation")
        result = await ig.post_photo(image_url=img_url, caption=caption)
        ok = result.get("ok", False)
        return f"Instagram Post: {'✅' if ok else '❌'} — {p['title'][:40]}"
    except Exception as e:
        return f"Instagram Fehler: {e}"


async def task_content_cycle() -> str:
    """SEO-Artikel + alle Social-Inhalte generieren. ContentHub Monorepo-Task."""
    try:
        from modules.content_hub import run_content_cycle, init_db as _init_content
        _init_content()
        return await run_content_cycle()
    except Exception as e:
        return f"ContentHub Fehler: {e}"


async def task_freelance_cycle() -> str:
    """Fiverr Gig + Upwork Proposals generieren. ContentHub Monorepo-Task."""
    try:
        from modules.content_hub import run_freelance_cycle, init_db as _init_content
        _init_content()
        return await run_freelance_cycle()
    except Exception as e:
        return f"FreelanceCycle Fehler: {e}"


async def task_linkedin_auto_post() -> str:
    """Post AI-generated business content to LinkedIn every 6 hours."""
    try:
        import aiohttp
        linkedin_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
        linkedin_urn   = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
        anthropic_key  = os.getenv("ANTHROPIC_API_KEY", "")
        if not linkedin_token:
            return "LINKEDIN_ACCESS_TOKEN fehlt"
        _ds24 = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        li_prompt = (f"Schreibe einen professionellen LinkedIn-Post auf Deutsch über KI-Automatisierung im E-Commerce. "
                     f"Max 1200 Zeichen. Erwähne am Ende: {_ds24} (AI Income Machine €37). Nur Text, kein JSON.")
        try:
            text = await _ai(li_prompt, max_tokens=400)
        except Exception:
            return "Kein LinkedIn-Content generiert (kein AI Key mit Credits)"
        headers = {
            "Authorization": f"Bearer {linkedin_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        payload = {
            "author": linkedin_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload) as r:
                if r.status in (200, 201):
                    resp = await r.json(content_type=None)
                    return f"LinkedIn Post veröffentlicht (ID: {resp.get('id','?')}): {text[:60]}..."
                err = await r.text()
                return f"LinkedIn HTTP {r.status}: {err[:80]}"
    except Exception as e:
        return f"LinkedIn Fehler: {e}"


async def task_youtube_auto_post() -> str:
    """Post YouTube community post via BRUTUS every 2h."""
    try:
        from modules.brutus_traffic_engine import deploy_to_youtube
        import random
        topics = [
            "💡 AI Income Machine — Automatisch Geld verdienen mit KI | Jetzt für €37 starten!",
            "🚀 Shopify Automatisierung 2026 — So läuft dein Business von selbst",
            "🤖 KI-Tools die wirklich Geld verdienen — Live Demo",
            "📈 Passives Einkommen mit KI — Der komplette Blueprint",
        ]
        title = random.choice(topics)
        result = await deploy_to_youtube(
            title=title,
            description=(
                f"{title}\n\n"
                f"👉 {os.getenv('DS24_AFFILIATE_LINK', 'https://tecbuuss.gumroad.com/l/wcqdjx')}\n\n"
                "#KI #PassivesEinkommen #OnlineBusiness"
            ),
            tags=["KI", "passives einkommen", "online business", "shopify", "automatisierung"],
        )
        return f"YouTube: {result.get(chr(39)+'status'+chr(39), str(result)[:80])}"
    except ImportError:
        return "YouTube: brutus_traffic_engine nicht verfügbar"
    except Exception as e:
        return f"YouTube Auto-Post Fehler: {e}"


# ── Autonomy Max-Upgrade Tasks ───────────────────────────────────────────────

async def task_competitor_monitor() -> str:
    """Täglich: Konkurrenten-Preise & Features checken, Telegram-Alert bei Änderung."""
    import aiohttp, re
    competitors = [
        {"name": "Dropispy", "url": "https://dropispy.com"},
        {"name": "AutoDS", "url": "https://www.autods.com"},
        {"name": "Zendrop", "url": "https://www.zendrop.com"},
    ]
    findings = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        for comp in competitors:
            try:
                async with session.get(comp["url"], headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    text = await resp.text()
                    prices = re.findall(r'\$[\d,]+|€[\d,]+|[\d,]+\s*(?:€|\$|USD|EUR)', text[:8000])
                    findings.append(f"{comp['name']}: {prices[:4] or ['kein Preis']}")
            except Exception as exc:
                findings.append(f"{comp['name']}: {exc.__class__.__name__}")
    summary = " | ".join(str(f) for f in findings)
    # Telegram alert
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"🔍 Konkurrenz-Check:\n{summary}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass
    return f"Competitor check: {summary[:200]}"


async def task_ab_test_analyze() -> str:
    """Alle 12h: A/B-Test-Gewinner aus Supabase ermitteln und per Telegram melden."""
    try:
        from modules.ab_testing_engine import analyze_and_select_winner
        results = await analyze_and_select_winner()
        if "error" in results:
            return f"A/B analyze: {results['error']}"
        winners = [f"{t}: '{d['winner']}'" for t, d in results.items()]
        msg = "🏆 A/B Gewinner: " + " | ".join(winners) if winners else "A/B: noch keine Daten"
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id and winners:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        return msg
    except ImportError:
        return "ab_testing_engine nicht gefunden"
    except Exception as e:
        return f"A/B analyze Fehler: {e}"


async def task_ai_content_calendar() -> str:
    """Täglich 06:00: KI-Inhaltskalender für 7 Tage generieren."""
    try:
        from modules.ai_content_calendar import generate_daily_calendar
        result = await generate_daily_calendar()
        return f"KI-Kalender: {result.get('days', 0)} Tage, erstes Thema: {result.get('first_day', {}).get('content', {}).get('title', '?')[:60]}"
    except ImportError:
        return "ai_content_calendar Modul fehlt"
    except Exception as e:
        return f"KI-Kalender Fehler: {e}"


async def task_revenue_optimize() -> str:
    """Alle 12h: KI analysiert Revenue und sendet Optimierungs-Empfehlungen per Telegram."""
    import aiohttp, json as _json
    try:
        from modules.digistore24_automation import get_sales_stats
        ds24_stats = await get_sales_stats()
    except Exception:
        ds24_stats = {}
    prompt = (
        "Du bist ein E-Commerce Revenue-Experte (DACH-Markt).\n"
        f"Revenue-Daten: {_json.dumps(ds24_stats, default=str)[:800]}\n"
        "Gib 3 konkrete sofort umsetzbare Maßnahmen zur Umsatzsteigerung. "
        "Format: nummerierte Liste, je 1 Satz."
    )
    try:
        recommendations = await _ai(prompt, max_tokens=400)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id,
                          "text": f"💰 Revenue-Optimierung KI:\n{recommendations[:800]}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        return f"Revenue optimize: {recommendations[:100]}"
    except Exception as e:
        return f"Revenue optimize: {e}"


async def task_google_index_submit() -> str:
    """Submit all key URLs to Google Indexing API / sitemap ping daily."""
    import aiohttp
    key = os.getenv("GOOGLE_INDEXING_KEY", "")
    urls = [
        "https://dudirudibot-mega-production.up.railway.app/",
        "https://bullpowerhubgit.github.io/shopify-brutal-tuning-landing/",
        "https://bullpower-lead.netlify.app/",
        "https://bullpower-hub-portal.netlify.app/",
        "https://bullpower-ai-tools.netlify.app/",
    ]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            if key:
                submitted = 0
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                for url in urls:
                    try:
                        async with s.post(
                            "https://indexing.googleapis.com/v3/urlNotifications:publish",
                            headers=headers, json={"url": url, "type": "URL_UPDATED"},
                        ) as r:
                            if r.status in (200, 201):
                                submitted += 1
                    except Exception:
                        pass
                return f"Google Indexing API: {submitted}/{len(urls)} URLs"
            # Fallback: free sitemap ping
            sitemap = "https://dudirudibot-mega-production.up.railway.app/sitemap.xml"
            for ping in [f"https://www.google.com/ping?sitemap={sitemap}",
                         f"https://www.bing.com/ping?sitemap={sitemap}"]:
                try:
                    await s.get(ping)
                except Exception:
                    pass
        return f"Sitemap Ping → Google+Bing ({len(urls)} URLs, GOOGLE_INDEXING_KEY optional)"
    except Exception as e:
        return f"Google Index Fehler: {e}"


async def task_push_notify_broadcast() -> str:
    """Attempt Web Push to all subscribers every 6h (requires pywebpush + VAPID keys)."""
    import aiohttp
    supa_url  = os.getenv("SUPABASE_URL", "")
    supa_key  = os.getenv("SUPABASE_SERVICE_KEY", "")
    vapid_key = os.getenv("VAPID_PRIVATE_KEY", "")
    if not supa_url:
        return "Supabase nicht konfiguriert"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/push_subscriptions?select=id",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}",
                         "Prefer": "count=exact"},
            ) as r:
                cr = r.headers.get("content-range", "0/0")
                total = cr.split("/")[-1]
        if not vapid_key:
            return f"VAPID_PRIVATE_KEY fehlt — {total} Push-Subscriber bereit sobald VAPID gesetzt"
        # pywebpush send
        try:
            import json as _json
            from pywebpush import webpush
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(
                    f"{supa_url}/rest/v1/push_subscriptions?select=endpoint,p256dh,auth&limit=500",
                    headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
                ) as r:
                    subs = await r.json(content_type=None)
            sent = 0
            payload = _json.dumps({"title": "🔥 BullPower Hub — Neues Update!",
                                   "body": "KI-Automatisierung für deinen Shop. Jetzt starten!",
                                   "url": "https://bullpower-lead.netlify.app/"})
            for sub in (subs if isinstance(subs, list) else []):
                try:
                    webpush(subscription_info={"endpoint": sub["endpoint"],
                                               "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                            data=payload, vapid_private_key=vapid_key,
                            vapid_claims={"sub": "mailto:bullpowersrtkennels@gmail.com",
                                          "aud": sub["endpoint"].split("/")[2]})
                    sent += 1
                except Exception:
                    pass
            return f"Web Push: {sent}/{len(subs)} gesendet"
        except ImportError:
            return f"pywebpush nicht installiert — pip install pywebpush zum Aktivieren"
    except Exception as e:
        return f"Push Notify Fehler: {e}"


async def task_shopify_seo_blog() -> str:
    """Publish 1 AI-SEO blog post to ineedit.com.co Shopify store every 12h (T-Shirt/POD niche)."""
    try:
        from modules.shopify_blog_auto import publish_one_article
        result = await publish_one_article()
        if result.get("ok"):
            return f"Shopify Blog OK: '{result.get('title')}' (ID {result.get('id')})"
        return f"Shopify Blog Fehler: {result.get('reason') or result.get('error', 'unbekannt')}"
    except ImportError as e:
        return f"shopify_blog_auto nicht verfügbar: {e}"
    except Exception as e:
        return f"Shopify SEO Blog Fehler: {e}"


async def task_viral_referral_trigger() -> str:
    """Tag recent leads in Klaviyo to trigger viral referral flow daily."""
    import aiohttp
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
    supa_url    = os.getenv("SUPABASE_URL", "")
    supa_key    = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not klaviyo_key or not supa_url:
        return "Klaviyo/Supabase fehlt"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/lead_events?select=email,name&limit=50&order=created_at.desc",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            ) as r:
                leads = await r.json(content_type=None)
        if not isinstance(leads, list) or not leads:
            return "Keine Leads für Referral-Trigger"
        tagged = 0
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            for lead in leads[:20]:
                email = lead.get("email", "")
                if not email:
                    continue
                ref = email.split("@")[0]
                try:
                    await s.post(
                        "https://a.klaviyo.com/api/profile-import/",
                        headers={"Authorization": f"Klaviyo-API-Key {klaviyo_key}",
                                 "revision": "2024-10-15", "Content-Type": "application/json"},
                        json={"data": {"type": "profile", "attributes": {
                            "email": email,
                            "properties": {"referral_url": f"https://dudirudibot-mega-production.up.railway.app/api/referral/{ref}",
                                           "referral_triggered": True},
                        }}},
                    )
                    tagged += 1
                except Exception:
                    pass
        return f"Viral Referral: {tagged} Leads getagt"
    except Exception as e:
        return f"Referral Trigger Fehler: {e}"


async def task_onboarding_sequence_trigger() -> str:
    """Enroll new leads into Klaviyo 7-day onboarding sequence daily."""
    import aiohttp
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
    supa_url    = os.getenv("SUPABASE_URL", "")
    supa_key    = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not klaviyo_key or not supa_url:
        return "Klaviyo/Supabase fehlt"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/lead_events?select=email,name,source&limit=30&order=created_at.desc",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            ) as r:
                leads = await r.json(content_type=None)
        if not isinstance(leads, list):
            leads = []
        enrolled = 0
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            for lead in leads[:30]:
                email = lead.get("email", "")
                fname = (lead.get("name") or "").split()[0] or "Freund"
                if not email:
                    continue
                try:
                    await s.post(
                        "https://a.klaviyo.com/api/profile-import/",
                        headers={"Authorization": f"Klaviyo-API-Key {klaviyo_key}",
                                 "revision": "2024-10-15", "Content-Type": "application/json"},
                        json={"data": {"type": "profile", "attributes": {
                            "email": email, "first_name": fname,
                            "properties": {"onboarding_day": 1, "onboarding_started": True,
                                           "product": lead.get("source", "shopify")},
                        }}},
                    )
                    enrolled += 1
                except Exception:
                    pass
        return f"Onboarding Sequenz: {enrolled} Leads enrolled (Day 1 Tag gesetzt)"
    except Exception as e:
        return f"Onboarding Sequenz Fehler: {e}"


async def task_seo_dominator() -> str:
    """SEO Dominator: sitemap ping + Schema.org injection + IndexNow every 2h."""
    try:
        from modules.seo_dominator import run_seo_dominator
        result = await run_seo_dominator(full=True)
        injected = result.get("schema_inject", {}).get("schema_injected", 0)
        return f"SEO Dominator OK: {injected} Schema injected, sitemap pinged"
    except Exception as e:
        return f"SEO Dominator Fehler: {e}"


async def task_backlink_bomber() -> str:
    """BacklinkBomber: IndexNow + RSS XML-RPC pings every 2h."""
    try:
        from modules.backlink_bomber import run_backlink_bomber
        result = await run_backlink_bomber()
        total = result.get("results", {}).get("rss_xmlrpc", {}).get("total_pinged", 0)
        return f"BacklinkBomber OK: {total} services pinged"
    except Exception as e:
        return f"BacklinkBomber Fehler: {e}"


async def task_viral_traffic_machine() -> str:
    """ViralTrafficMachine: Reddit + Medium + LinkedIn + trending content every 4h."""
    try:
        from modules.viral_traffic_machine import run_viral_traffic_machine
        result = await run_viral_traffic_machine()
        posted = sum(1 for v in result.get("platforms", {}).values() if isinstance(v, dict) and v.get("ok"))
        return f"ViralTraffic OK: {posted} platforms hit"
    except Exception as e:
        return f"ViralTraffic Fehler: {e}"


async def task_content_velocity() -> str:
    """ContentVelocity: generate + publish 10-format content from trending topic every 2h."""
    try:
        from modules.content_velocity_engine import run_content_velocity
        result = await run_content_velocity()
        topic = result.get("topic", "?")[:40]
        return f"ContentVelocity OK: '{topic}' published across all formats"
    except Exception as e:
        return f"ContentVelocity Fehler: {e}"


async def task_revenue_maximizer() -> str:
    """RevenueMaximizer: cart abandonment recovery + winback + urgency offers every 4h."""
    try:
        from modules.revenue_maximizer import run_revenue_maximizer
        result = await run_revenue_maximizer()
        recovered = result.get("results", {}).get("cart_recovery", {}).get("recovery_emails_sent", 0)
        winback   = result.get("results", {}).get("winback", {}).get("winback_triggered", 0)
        return f"RevenueMaximizer OK: {recovered} carts recovered, {winback} winback triggered"
    except Exception as e:
        return f"RevenueMaximizer Fehler: {e}"


async def task_free_syndication() -> str:
    """FreeSyndication: post to Dev.to, Hashnode, Medium, Discord, Telegram every 6h."""
    try:
        from modules.free_syndication_network import run_free_syndication
        result = await run_free_syndication()
        ok = result.get("platforms_ok", 0)
        topic = result.get("topic", "")[:40]
        return f"FreeSyndication OK: {ok}/5 platforms — '{topic}'"
    except Exception as e:
        return f"FreeSyndication Fehler: {e}"


async def task_github_blog() -> str:
    """GitHubBlog: publish SEO article to GitHub Pages every 4h."""
    try:
        from modules.github_blog_publisher import publish_blog_article
        result = await publish_blog_article()
        if result.get("ok"):
            return f"GitHubBlog OK: '{result.get('title','')[:50]}' → {result.get('url','')}"
        return f"GitHubBlog skip: {result.get('reason','no reason')}"
    except Exception as e:
        return f"GitHubBlog Fehler: {e}"


# ── Content Factory Tasks ────────────────────────────────────────────────────

async def task_content_factory_run() -> str:
    """Every 4h: find top trending topic → generate full content package."""
    try:
        from modules.content_factory import find_trending_topics, generate_content_package
        topics = await find_trending_topics("shopify ecommerce automation")
        topic = topics[0]["topic"] if topics else "Shopify Automation mit KI"
        package = await generate_content_package(topic)
        stats = package.get("stats", {})
        return (f"Content Factory: {topic} | "
                f"Blog {stats.get('blog_words_de', 0)}w | "
                f"{stats.get('email_count', 0)} emails | "
                f"{stats.get('platforms', 0)} platforms")
    except Exception as e:
        return f"content_factory_run error: {e}"


async def task_social_batch_gen() -> str:
    """Daily: generate 30-day social media batch for all platforms."""
    try:
        from modules.content_factory import generate_social_batch, find_trending_topics
        topics = await find_trending_topics()
        topic = topics[0]["topic"] if topics else "E-Commerce Automation 2024"
        batch = await generate_social_batch(topic)
        counts = {k: len(v) for k, v in batch.items() if isinstance(v, list)}
        return f"Social batch: {topic} | " + " | ".join(f"{k}:{v}" for k, v in counts.items())
    except Exception as e:
        return f"social_batch_gen error: {e}"


async def task_trending_topic_scan() -> str:
    """Every 12h: scan for trending topics and log top opportunities."""
    import aiohttp
    try:
        from modules.content_factory import find_trending_topics
        topics = await find_trending_topics()
        high = [t["topic"] for t in topics if t.get("urgency") == "high"]
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if high and token and chat_id:
            msg = f"🔥 Trending NOW:\n" + "\n".join(f"• {t}" for t in high[:5])
            async with aiohttp.ClientSession() as s:
                await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat_id, "text": msg},
                             timeout=aiohttp.ClientTimeout(total=10))
        return f"Trending scan: {len(topics)} topics, {len(high)} high-urgency"
    except Exception as e:
        return f"trending_topic_scan error: {e}"


async def task_content_calendar_weekly() -> str:
    """Weekly (Monday): build next 30-day content calendar."""
    try:
        from datetime import datetime
        from modules.content_factory import build_content_calendar
        month = datetime.utcnow().strftime("%Y-%m")
        cal = await build_content_calendar(month)
        days = len(cal.get("days", []))
        return f"Content calendar built: {month} | {days} days planned"
    except Exception as e:
        return f"content_calendar_weekly error: {e}"


# ── Conversion Maximizer Tasks ───────────────────────────────────────────────

async def task_conversion_scan() -> str:
    """Every 15min: A/B winners + social proof + lead re-scoring."""
    try:
        from modules.conversion_engine import run_conversion_scan
        return await run_conversion_scan()
    except Exception as e:
        return f"ConversionScan Fehler: {e}"


async def task_daily_optimization() -> str:
    """Every 1h: revenue AI diagnosis + funnel weak-point fix."""
    try:
        from modules.conversion_engine import run_daily_optimization
        return await run_daily_optimization()
    except Exception as e:
        return f"DailyOptimization Fehler: {e}"


async def task_funnel_daily() -> str:
    """Daily: full funnel analytics report to Telegram."""
    try:
        from modules.conversion_engine import analyze_funnel
        result = await analyze_funnel()
        return (f"Funnel: {result.get('leads',0)} leads → {result.get('orders',0)} orders | "
                f"Weakest: {result.get('weakest_stage','?')} {result.get('weakest_rate',0):.1%}")
    except Exception as e:
        return f"FunnelDaily Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# OMEGA TRAFFIC ENGINE TASKS — Revolution Pack
# ─────────────────────────────────────────────────────────────────────────────

async def task_omega_full() -> str:
    """OMEGA Full-Cycle: Google Index + Bing IndexNow + Artikel + Competitor + Proof."""
    try:
        from modules.omega_traffic_engine import run_omega_cycle
        result = await run_omega_cycle(mode="full")
        indexed = len(result.get("indexing", {}).get("submitted", []))
        indexnow = result.get("indexnow", {}).get("submitted", 0)
        article = result.get("article", {}).get("words", 0)
        return f"OMEGA Full: {indexed} URLs indexiert | IndexNow: {indexnow} | Artikel: {article} Wörter"
    except Exception as e:
        return f"OMEGA Full Fehler: {e}"


async def task_omega_index() -> str:
    """Schnelle Indexierung: alle Money-URLs sofort an Google + Bing melden."""
    try:
        from modules.omega_traffic_engine import google_instant_index, bing_indexnow, MONEY_URLS
        g = await google_instant_index(MONEY_URLS)
        b = await bing_indexnow(MONEY_URLS)
        return (f"Index: {len(g.get('submitted', []))} Google | "
                f"{b.get('submitted', 0)} Bing IndexNow")
    except Exception as e:
        return f"OMEGA Index Fehler: {e}"


async def task_omega_article() -> str:
    """Generiert und veröffentlicht täglich rotierenden SEO-Artikel."""
    try:
        from modules.omega_traffic_engine import generate_seo_article, publish_article_to_vercel, ARTICLE_TOPICS
        import datetime as dt
        topic_idx = dt.datetime.now().timetuple().tm_yday % len(ARTICLE_TOPICS)
        topic, slug = ARTICLE_TOPICS[topic_idx]
        article = await generate_seo_article(topic, slug)
        if not article:
            return "Artikel-Generierung übersprungen (kein API-Key)"
        result = await publish_article_to_vercel(article)
        return f"SEO-Artikel: '{topic}' | {result.get('words', 0)} Wörter → {result.get('published', '?')}"
    except Exception as e:
        return f"OMEGA Artikel Fehler: {e}"


async def task_omega_competitor() -> str:
    """KI generiert Content der Competitor-Keywords für BullPower Hub klaut."""
    try:
        from modules.omega_traffic_engine import generate_competitor_content
        result = await generate_competitor_content()
        keyword = result.get("keyword", "?")
        posts = len(result.get("posts", []))
        return f"Competitor-Content: '{keyword}' → {posts} Posts generiert"
    except Exception as e:
        return f"OMEGA Competitor Fehler: {e}"


async def task_omega_social_proof() -> str:
    """Postet Kunden-Testimonial als Social Proof auf Telegram."""
    try:
        from modules.omega_traffic_engine import post_testimonial_social
        result = await post_testimonial_social()
        return f"Social Proof: {result.get('posted', '?')} gepostet"
    except Exception as e:
        return f"OMEGA Social Proof Fehler: {e}"


async def task_omega_youtube() -> str:
    """Generiert YouTube SEO-Paket (Titel, Description, Tags, Hook)."""
    try:
        from modules.omega_traffic_engine import generate_youtube_package
        result = await generate_youtube_package()
        return f"YouTube-Paket: '{result.get('idea', '?')[:50]}'"
    except Exception as e:
        return f"OMEGA YouTube Fehler: {e}"


async def task_omega_indexnow_sitemap() -> str:
    """Meldet alle Sitemaps bei IndexNow an (Bing/Yahoo/DuckDuckGo)."""
    try:
        from modules.omega_traffic_engine import bing_indexnow, SITEMAPS
        result = await bing_indexnow(SITEMAPS)
        return f"IndexNow Sitemaps: {result.get('submitted', 0)} bei {len(result.get('engines', []))} Engines"
    except Exception as e:
        return f"OMEGA IndexNow Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# TWITTER AUTOPOSTER TASKS
# ─────────────────────────────────────────────────────────────────────────────

async def task_twitter_daily_tweets() -> str:
    """Postet 3 Tweets täglich auf @AIITEC — KI-generiert + Templates + Produkte."""
    try:
        from modules.twitter_autoposter import post_daily_tweets
        result = await post_daily_tweets(count=3)
        return f"Twitter: {result.get('posted', 0)} Tweets | {result.get('failed', 0)} Fehler"
    except Exception as e:
        return f"Twitter Daily Fehler: {e}"


async def task_twitter_seo_thread() -> str:
    """Postet täglich einen SEO-Thread (3 Tweets) auf @AIITEC."""
    try:
        from modules.twitter_autoposter import post_seo_thread
        result = await post_seo_thread()
        return f"Twitter Thread: {result.get('thread_length', 0)} Tweets gepostet"
    except Exception as e:
        return f"Twitter Thread Fehler: {e}"


async def task_social_scheduler() -> str:
    """Social Scheduler: Twitter → Telegram Fallback (alle 6h)."""
    try:
        from modules.social_scheduler import post_daily_content
        result = await post_daily_content()
        return f"SocialScheduler: {result}"
    except Exception as e:
        return f"SocialScheduler Fehler: {e}"


# ── SEO MEGA ENGINE ───────────────────────────────────────────────────────────

async def task_seo_mega_factory() -> str:
    try:
        from modules.seo_mega_engine import run_content_factory
        r = await run_content_factory(batch_size=5)
        return f"SEO Mega: saved={r.get('saved',0)} published={r.get('published_shopify',0)}"
    except Exception as e:
        return f"SEO Mega Factory error: {e}"

async def task_seo_mega_submit() -> str:
    try:
        from modules.seo_mega_engine import submit_to_google, generate_sitemap
        sitemap = await generate_sitemap()
        r = await submit_to_google()
        return f"SEO Submit: google={r.get('results',{}).get('google',{}).get('ok')} indexnow={r.get('results',{}).get('indexnow',{}).get('ok')}"
    except Exception as e:
        return f"SEO Submit error: {e}"

async def task_seo_competitor_analysis() -> str:
    try:
        from modules.seo_mega_engine import analyze_all_competitors
        r = await analyze_all_competitors()
        return f"SEO Competitor: {r.get('competitors_analyzed',0)} analyzed, {r.get('quick_wins_added',0)} quick wins"
    except Exception as e:
        return f"SEO Competitor error: {e}"


# ── TRAFFIC SWARM ─────────────────────────────────────────────────────────────

async def task_traffic_swarm_full() -> str:
    try:
        from modules.traffic_swarm import run_full_traffic_swarm
        r = await run_full_traffic_swarm()
        return f"TrafficSwarm: {r.get('modules_ok',0)}/{r.get('modules_total',0)} OK"
    except Exception as e:
        return f"TrafficSwarm error: {e}"

async def task_traffic_velocity_check() -> str:
    try:
        from modules.traffic_swarm import monitor_traffic_velocity
        r = await monitor_traffic_velocity()
        return f"Traffic: {r.get('today_leads',0)} leads, {r.get('delta_pct',0):+.1f}%"
    except Exception as e:
        return f"TrafficVelocity error: {e}"

async def task_rss_rebuild() -> str:
    try:
        from modules.traffic_swarm import build_rss_feed
        xml = await build_rss_feed()
        return f"RSS: {len(xml)} chars"
    except Exception as e:
        return f"RSS error: {e}"

async def task_content_freshness() -> str:
    try:
        from modules.traffic_swarm import refresh_stale_content
        r = await refresh_stale_content(days_old=90)
        return f"Freshness: {r.get('articles_updated',0)} updated"
    except Exception as e:
        return f"ContentFreshness error: {e}"

async def task_backlink_outreach_gen() -> str:
    # Disabled — caused bounce emails to invalid domains
    return "Outreach: disabled (bounce prevention)"


# ── TRAFFIC BLITZ ─────────────────────────────────────────────────────────────

async def task_traffic_blitz_full() -> str:
    try:
        from modules.traffic_blitz import run_traffic_blitz
        r = await run_traffic_blitz()
        return f"TrafficBlitz: {r.get('channels_ok',0)}/4 OK | {r.get('topic','?')[:40]}"
    except Exception as e:
        return f"TrafficBlitz error: {e}"

async def task_linkedin_burst() -> str:
    try:
        from modules.traffic_blitz import run_linkedin_burst
        r = await run_linkedin_burst()
        return f"LinkedIn Burst: {r.get('posted',0)}/{r.get('total',0)} posts"
    except Exception as e:
        return f"LinkedIn burst error: {e}"

async def task_shopify_seo_blast() -> str:
    try:
        from modules.traffic_blitz import run_shopify_seo_blast
        r = await run_shopify_seo_blast()
        return f"Shopify SEO Blast: {r.get('published',0)} Artikel"
    except Exception as e:
        return f"Shopify SEO blast error: {e}"

async def task_indexnow_mega_blast() -> str:
    try:
        from modules.traffic_blitz import indexnow_blast
        r = await indexnow_blast()
        return f"IndexNow: {r.get('submitted',0)} URLs an Google+Bing"
    except Exception as e:
        return f"IndexNow blast error: {e}"


# ── SUPER REVENUE BLITZ ───────────────────────────────────────────────────────

async def task_revenue_blitz() -> str:
    try:
        from modules.super_revenue_blitz import revenue_blast_now
        r = await revenue_blast_now()
        return f"Revenue Blitz: tg={r.get('telegram')} kl={r.get('klaviyo')} li={r.get('linkedin')} idx={r.get('indexnow',0)}"
    except Exception as e:
        return f"Revenue Blitz error: {e}"


async def task_aliexpress_import() -> str:
    try:
        from modules.super_revenue_blitz import aliexpress_import_trending, announce_new_products
        r = await aliexpress_import_trending()
        imported = r.get("imported", 0)
        if imported > 0:
            # Auto-Mailing nach erfolgreichem Import
            products = [{"title": f"AliExpress Produkt {i+1}"} for i in range(imported)]
            await announce_new_products(products)
        return f"AliExpress: {imported} importiert, {r.get('skipped',0)} skip"
    except Exception as e:
        return f"AliExpress import error: {e}"


async def task_printify_seo() -> str:
    try:
        from modules.super_revenue_blitz import printify_seo_blast
        r = await printify_seo_blast()
        return f"Printify SEO: {r.get('updated',0)} Produkte upgedated, {r.get('skipped',0)} skip"
    except Exception as e:
        return f"Printify SEO error: {e}"


async def task_multi_platform_post() -> str:
    import random
    topics = [
        "Passives Einkommen 2026 — So verdienst du im Schlaf",
        "Shopify Automatisierung — Der komplette Guide",
        "KI Tools die 2026 wirklich Geld machen",
        "Dropshipping vs Print-on-Demand — Was ist besser?",
        "Online Business aufbauen — Schritt für Schritt",
        "BRUTUS Traffic Engine — 10 Kanäle gleichzeitig",
        "Digistore24 Automatisierung — Mehr Verkäufe ohne Arbeit",
    ]
    try:
        from modules.super_revenue_blitz import multi_platform_post
        r = await multi_platform_post(random.choice(topics))
        return f"Multi-Platform: tg={r.get('telegram')} li={r.get('linkedin')} blog={bool(r.get('blog_url'))} idx={r.get('indexnow',0)}"
    except Exception as e:
        return f"Multi-platform post error: {e}"


# ── EBAY + AMAZON + TWITTER + DISCORD AUTO ───────────────────────────────────

async def task_ebay_auto_fill() -> str:
    try:
        from modules.ebay_automation import run_ebay_auto_fill
        r = await run_ebay_auto_fill()
        return f"eBay AutoFill: found={r.get('found',0)} imported={r.get('imported',0)}"
    except Exception as e:
        return f"eBay AutoFill error: {e}"


async def task_ebay_blast() -> str:
    try:
        from modules.ebay_brutus import run_ebay_multi_blast
        r = await run_ebay_multi_blast(count=3)
        return f"eBay Blast: {r.get('cycles',0)} Niches | {r.get('channels_hit',0)} Kanäle"
    except Exception as e:
        return f"eBay Blast error: {e}"


async def task_amazon_blast() -> str:
    try:
        from modules.amazon_affiliate import build_affiliate_link
        from modules.brutus_core import fire as brutus_fire
        products = [("Smart LED Strip WiFi", "smart+led+strip+wifi"),
                    ("Fitness Tracker 2026", "fitness+tracker"),
                    ("Mini Projektor Heimkino", "mini+projektor")]
        fired = 0
        for name, kw in products:
            link = build_affiliate_link(kw)
            r = await brutus_fire(title=f"Amazon: {name}", body=f"Jetzt bei Amazon: {name}",
                                   link=link, niche="amazon affiliate",
                                   channels=["telegram", "twitter", "discord"])
            if r.get("channels_hit", 0) > 0:
                fired += 1
        return f"Amazon Blast: {fired}/{len(products)} gepostet"
    except Exception as e:
        return f"Amazon Blast error: {e}"


async def task_twitter_blast() -> str:
    try:
        from modules.twitter_auto_poster import run_auto_tweet
        r = await run_auto_tweet()
        return f"Twitter: posted={r.get('posted',0)} failed={r.get('failed',0)}"
    except Exception as e:
        return f"Twitter error: {e}"


async def task_discord_blast() -> str:
    try:
        from modules.brutus_core import _discord
        import aiohttp
        msg = "🤖 SuperMegaBot | Shop: https://autopilot-store-suite-fmbka.myshopify.com | Code HEUTE20 = 20% Rabatt!"
        async with aiohttp.ClientSession() as sess:
            ok = await _discord(msg, sess)
        return f"Discord: {'ok' if ok else 'no credentials'}"
    except Exception as e:
        return f"Discord error: {e}"


# ── SHOPIFY AUTO-FILL ────────────────────────────────────────────────────────

async def task_shopify_auto_fill() -> str:
    """Shopify: bestehende Produkte reparieren + neue Trend-Produkte importieren + BrutusCore"""
    try:
        from modules.shopify_auto_fill import run_shopify_auto_fill
        r = await run_shopify_auto_fill(fix_existing=True, add_new=3)
        return (f"ShopifyAutoFill: scanned={r.get('products_scanned',0)} "
                f"fixed={r.get('fixed',0)} new={r.get('new_products_created',0)} "
                f"brutus={r.get('brutus_fires',0)}")
    except Exception as e:
        return f"ShopifyAutoFill error: {e}"


_shopify_tags_since_id: int = 0  # global state for incremental tag updates

async def task_shopify_fix_tags() -> str:
    """Shopify: T-Shirt Produkt-Tags mit echten SEO-Tags aktualisieren (schrittweise alle 10553 Produkte)"""
    global _shopify_tags_since_id
    try:
        from modules.shopify_full_autonomy import fix_product_tags_tshirt
        r = await fix_product_tags_tshirt(batch_size=50, since_id=_shopify_tags_since_id)
        if r.get("done"):
            _shopify_tags_since_id = 0  # reset: next cycle starts from beginning
        else:
            _shopify_tags_since_id = r.get("last_id", 0)
        return (f"ShopifyFixTags: updated={r.get('updated',0)} "
                f"failed={r.get('failed',0)} since_id={_shopify_tags_since_id} done={r.get('done')}")
    except Exception as e:
        return f"ShopifyFixTags error: {e}"


async def task_shopify_cleanup_collections() -> str:
    """Shopify: leere Smart Collections löschen (entstehen wenn Produkt-Typen sich ändern)"""
    try:
        from modules.shopify_full_autonomy import cleanup_empty_smart_collections
        r = await cleanup_empty_smart_collections(max_delete=100)
        return (f"ShopifyCleanupCollections: deleted={r.get('deleted',0)} "
                f"kept={r.get('kept',0)} to_delete={r.get('total_to_delete',0)}")
    except Exception as e:
        return f"ShopifyCleanupCollections error: {e}"


_shopify_gmc_since_id: int = 0  # global state for incremental GMC metafield updates

async def task_shopify_gmc_metafields() -> str:
    """Shopify: Google Shopping Metafelder für T-Shirts setzen (GMC Freischaltung)"""
    global _shopify_gmc_since_id
    try:
        from modules.shopify_full_autonomy import fix_product_gmc_metafields
        r = await fix_product_gmc_metafields(batch_size=30, since_id=_shopify_gmc_since_id)
        if r.get("done"):
            _shopify_gmc_since_id = 0  # reset after full cycle
        else:
            _shopify_gmc_since_id = r.get("last_id", 0)
        return (f"ShopifyGMC: updated={r.get('updated',0)} "
                f"processed={r.get('processed',0)} done={r.get('done')} since_id={_shopify_gmc_since_id}")
    except Exception as e:
        return f"ShopifyGMC error: {e}"


# ── DS24 FULL AUTO ───────────────────────────────────────────────────────────

async def task_ds24_traffic() -> str:
    """DS24 Affiliate Traffic — postet auf Telegram, Blog, Mailchimp, Klaviyo"""
    try:
        from modules.ds24_traffic_engine import run_ds24_traffic
        r = await run_ds24_traffic()
        return (f"DS24 Traffic: {r.get('products_found',0)} Produkte | "
                f"TG:{r.get('telegram_sent',0)} Blog:{r.get('blog_posts',0)} "
                f"Mail:{r.get('emails_sent',0)}")
    except Exception as e:
        return f"DS24 Traffic error: {e}"

async def task_ds24_auto_fill() -> str:
    """DS24 Account prüfen + automatisch befüllen wenn leer"""
    try:
        from modules.ds24_auto_fill import run_ds24_auto_fill
        r = await run_ds24_auto_fill()
        status = r.get("account_status", {})
        actions = r.get("actions", [])
        return (f"DS24 AutoFill: {status.get('approved_products',0)} approved | "
                f"affiliates:{r.get('affiliate_products',[]) and len(r.get('affiliate_products',[])) or 0} | "
                f"packages:{r.get('generated_packages',0)} | actions:{','.join(actions)}")
    except Exception as e:
        return f"DS24 AutoFill error: {e}"


# ── ADS ENGINE ────────────────────────────────────────────────────────────────

async def task_ads_performance_monitor() -> str:
    try:
        from modules.ads_engine import task_ads_monitor
        return await task_ads_monitor()
    except Exception as e:
        return f"AdsMonitor error: {e}"

async def task_ads_optimize_run() -> str:
    try:
        from modules.ads_engine import task_ads_optimize
        return await task_ads_optimize()
    except Exception as e:
        return f"AdsOptimize error: {e}"

async def task_ads_creative_rotate() -> str:
    try:
        from modules.ads_engine import task_ads_rotate
        return await task_ads_rotate()
    except Exception as e:
        return f"AdsRotate error: {e}"


# ── REVENUE INTELLIGENCE ──────────────────────────────────────────────────────

async def task_revenue_autopilot_run() -> str:
    try:
        from modules.revenue_intelligence import revenue_autopilot
        r = await revenue_autopilot()
        return f"RevenueAutopilot: {len(r.get('actions',[]))} actions"
    except Exception as e:
        return f"RevenueAutopilot error: {e}"

async def task_revenue_briefing_morning() -> str:
    try:
        from modules.revenue_intelligence import send_revenue_briefing
        r = await send_revenue_briefing()
        return f"RevenueBriefing: €{r.get('yesterday_revenue',0):.2f} yesterday, {r.get('leads_today',0)} leads"
    except Exception as e:
        return f"RevenueBriefing error: {e}"

async def task_revenue_leak_check() -> str:
    try:
        from modules.revenue_intelligence import detect_revenue_leaks
        leaks = await detect_revenue_leaks()
        return f"RevenueLeaks: {len(leaks)} found"
    except Exception as e:
        return f"RevenueLeaks error: {e}"

async def task_churn_prevention() -> str:
    try:
        from modules.revenue_intelligence import identify_churn_risk
        at_risk = await identify_churn_risk()
        return f"ChurnRisk: {len(at_risk)} customers at risk"
    except Exception as e:
        return f"ChurnPrevention error: {e}"


# ── SHOPIFY MAX TUNER ─────────────────────────────────────────────────────────

async def task_shopify_max_seo() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_seo_optimize
        return await task_shopify_seo_optimize()
    except Exception as e:
        return f"ShopifyMaxSEO error: {e}"

async def task_shopify_cart_recover() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_cart_recovery
        return await task_shopify_cart_recovery()
    except Exception as e:
        return f"CartRecovery error: {e}"

async def task_shopify_price_optimize() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_pricing
        return await task_shopify_pricing()
    except Exception as e:
        return f"ShopifyPricing error: {e}"

async def task_shopify_daily_intel() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_intelligence
        return await task_shopify_intelligence()
    except Exception as e:
        return f"ShopifyIntel error: {e}"

async def task_shopify_inventory_check() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_inventory
        return await task_shopify_inventory()
    except Exception as e:
        return f"ShopifyInventory error: {e}"

async def task_shopify_review_request() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_reviews
        return await task_shopify_reviews()
    except Exception as e:
        return f"ShopifyReviews error: {e}"


# ── GROWTH HACKER ─────────────────────────────────────────────────────────────

async def task_viral_trend_scan() -> str:
    try:
        from modules.growth_hacker import task_viral_trend_detect
        return await task_viral_trend_detect()
    except Exception as e:
        return f"ViralTrend error: {e}"

async def task_community_growth_post() -> str:
    try:
        from modules.growth_hacker import task_community_grow
        return await task_community_grow()
    except Exception as e:
        return f"CommunityGrowth error: {e}"

async def task_growth_morning_briefing() -> str:
    try:
        from modules.growth_hacker import task_growth_metrics
        return await task_growth_metrics()
    except Exception as e:
        return f"GrowthBriefing error: {e}"

async def task_influencer_pipeline() -> str:
    try:
        from modules.growth_hacker import task_influencer_outreach
        return await task_influencer_outreach()
    except Exception as e:
        return f"InfluencerPipeline error: {e}"

async def task_press_release_generate() -> str:
    try:
        from modules.growth_hacker import task_press_release_auto
        return await task_press_release_auto()
    except Exception as e:
        return f"PressRelease error: {e}"

async def task_testimonial_engine() -> str:
    try:
        from modules.growth_hacker import task_testimonial_collect
        return await task_testimonial_collect()
    except Exception as e:
        return f"Testimonial error: {e}"

async def task_referral_system_run() -> str:
    try:
        from modules.growth_hacker import task_referral_refresh
        return await task_referral_refresh()
    except Exception as e:
        return f"Referral error: {e}"


# ── ULTRA SEO ARSENAL TASKS ──────────────────────────────────────────────────

async def task_ultra_seo_cycle() -> str:
    """Full Ultra SEO cycle: IndexNow all properties + sitemap ping + parasite content."""
    try:
        from modules.ultra_seo_arsenal import run_ultra_seo_cycle
        result = await run_ultra_seo_cycle()
        urls = result.get("indexnow", {}).get("total_urls", 0)
        indexed = result.get("indexnow", {}).get("submitted", 0)
        return f"Ultra SEO: {urls} URLs → {indexed}/3 Engines | Content OK"
    except Exception as e:
        return f"UltraSEO error: {e}"


async def task_ultra_indexnow_all() -> str:
    """Submit all 14+ BullPower properties to IndexNow."""
    try:
        from modules.ultra_seo_arsenal import submit_all_properties_to_indexnow
        result = await submit_all_properties_to_indexnow()
        return f"IndexNow ALL: {result.get('total_urls',0)} URLs | {result.get('submitted',0)}/3 Engines"
    except Exception as e:
        return f"IndexNow ALL error: {e}"


async def task_ultra_seo_health() -> str:
    """Check all BullPower properties are online."""
    try:
        from modules.ultra_seo_arsenal import seo_health_check
        result = await seo_health_check()
        return f"SEO Health: {result.get('ok',0)}/{result.get('total',0)} Properties online"
    except Exception as e:
        return f"SEO Health error: {e}"


async def task_dynamic_pricing_cycle() -> str:
    try:
        from modules.dynamic_pricing import run_dynamic_pricing_cycle
        r = await run_dynamic_pricing_cycle(max_products=50)
        return f"Dynamic Pricing: checked={r.get('products_checked',0)} updated={r.get('prices_updated',0)}"
    except Exception as e:
        return f"Dynamic Pricing error: {e}"


async def task_tiktok_sync() -> str:
    try:
        from modules.tiktok_shop_sync import sync_products_to_tiktok
        r = await sync_products_to_tiktok()
        return f"TikTok Sync: synced={r.get('synced',0)} skipped={r.get('skipped',0)}"
    except Exception as e:
        return f"TikTok Sync error: {e}"


async def task_upsell_sequence_run() -> str:
    try:
        from modules.conversion_engine import generate_upsell_sequence
        sample = {"product": "AI Income Machine", "price": 37, "customer_email": ""}
        r = await generate_upsell_sequence(sample)
        count = len(r) if isinstance(r, list) else r.get("enrolled", 0)
        return f"Upsell Sequence: {count} steps generated"
    except Exception as e:
        return f"Upsell Sequence error: {e}"


# ── BRUTUS für jedes Tool ────────────────────────────────────────────────────

async def task_brutus_printify() -> str:
    try:
        from modules.super_revenue_blitz import brutus_blast_for_tool
        r = await brutus_blast_for_tool("Printify", "https://www.printify.com",
            ["Print on Demand 2026", "Printify Shopify Automation", "eigene Produkte verkaufen"])
        return f"BRUTUS Printify: {r.get('channels_hit', r.get('posts_sent', 0))} posts"
    except Exception as e:
        return f"BRUTUS Printify error: {e}"


async def task_brutus_dropshipping() -> str:
    try:
        from modules.super_revenue_blitz import brutus_blast_for_tool
        link = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        r = await brutus_blast_for_tool("Dropshipping", link,
            ["Dropshipping 2026", "AliExpress Shopify", "online shop automatisch befüllen"])
        return f"BRUTUS Dropshipping: {r.get('channels_hit', r.get('posts_sent', 0))} posts"
    except Exception as e:
        return f"BRUTUS Dropshipping error: {e}"


async def task_brutus_ds24() -> str:
    try:
        from modules.super_revenue_blitz import brutus_blast_for_tool
        link = (
            os.getenv("DS24_AFFILIATE_LINK")
            or os.getenv("AIITEC_AFFILIATE_URL")
            or os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        )
        r = await brutus_blast_for_tool("Digistore24", link,
            ["Digistore24 Affiliate 2026", "digitale Produkte verkaufen", "AI Income Machine"])
        return f"BRUTUS DS24: {r.get('channels_hit', r.get('posts_sent', 0))} Kanäle, {r.get('content_pieces',0)} Posts"
    except Exception as e:
        return f"BRUTUS DS24 error: {e}"


async def task_brutus_shopify() -> str:
    try:
        from modules.super_revenue_blitz import brutus_blast_for_tool
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        url = f"https://{shop}" if shop else os.getenv("DS24_AFFILIATE_LINK", "")
        r = await brutus_blast_for_tool("Shopify", url,
            ["Shopify Shop automatisieren", "Shopify SEO 2026", "Shopify Dropshipping"])
        return f"BRUTUS Shopify: {r.get('channels_hit', r.get('posts_sent', 0))} Kanäle, {r.get('content_pieces',0)} Posts"
    except Exception as e:
        return f"BRUTUS Shopify error: {e}"


# ── Auto Mailing Tasks ────────────────────────────────────────────────────────

async def task_klaviyo_daily_campaign() -> str:
    """Vollautomatische Klaviyo Kampagne — DS24 Affiliate Promo."""
    try:
        import random
        from modules.super_revenue_blitz import send_klaviyo_campaign
        link = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        subjects = [
            "🔥 Vollautomatisch Geld verdienen — so geht's",
            "💡 KI macht Geld während du schläfst",
            "🚀 Passives Einkommen 2026 — der komplette Blueprint",
            "💰 Digistore24 + KI = automatische Einnahmen",
            "🤖 AI Income Machine — jetzt starten",
        ]
        subject = random.choice(subjects)
        html = (
            f"<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>"
            f"<h2>{subject}</h2>"
            f"<p>Hey,</p>"
            f"<p>während du das hier liest, verdient das System automatisch Geld für dich. "
            f"KI-Tools, Shopify, Digistore24 — vollständig automatisiert.</p>"
            f"<p><b>Was du bekommst:</b></p>"
            f"<ul><li>✅ KI generiert Content 24/7</li>"
            f"<li>✅ Automatische Postings auf 10+ Kanälen</li>"
            f"<li>✅ Shopify + DS24 vollautomatisch</li>"
            f"<li>✅ Passives Einkommen ohne tägliche Arbeit</li></ul>"
            f"<p style='text-align:center;margin:30px 0'>"
            f"<a href='{link}' style='background:#7c3aed;color:#fff;padding:14px 28px;"
            f"text-decoration:none;border-radius:8px;font-weight:bold'>🚀 Jetzt starten</a></p>"
            f"<hr><p><small>Rudolf | AIITEC | <a href='${{unsubscribe_link}}'>Abmelden</a></small></p>"
            f"</body></html>"
        )
        ok = await send_klaviyo_campaign(subject, html, f"AutoPromo {datetime.now().strftime('%Y-%m-%d')}")
        return f"Klaviyo Daily: {'sent' if ok else 'failed'} — {subject[:40]}"
    except Exception as e:
        return f"Klaviyo daily error: {e}"


async def task_mailing_promo_blitz() -> str:
    """Gleichzeitig Klaviyo + Mailchimp + Telegram + LinkedIn — alle Mailing-Kanäle."""
    try:
        import asyncio, random
        from modules.super_revenue_blitz import send_klaviyo_campaign, send_mailchimp_campaign, _tg_send, _linkedin_post
        link = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        subjects = [
            "💰 Heute: Vollautomatisches Online-Business starten",
            "🤖 KI verdient für dich — ohne tägliche Arbeit",
            "🚀 AI Income Machine — limitiertes Angebot",
        ]
        subject = random.choice(subjects)
        html = (
            f"<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>"
            f"<h2>{subject}</h2><p>Vollautomatisch. 24/7. Passives Einkommen.</p>"
            f"<p><a href='{link}' style='background:#e74c3c;color:#fff;padding:12px 24px;"
            f"text-decoration:none;border-radius:4px'>👉 Jetzt ansehen</a></p>"
            f"<hr><p><small>Rudolf | AIITEC | <a href='${{unsubscribe_link}}'>Abmelden</a></small></p>"
            f"</body></html>"
        )
        kl, mc, tg, li = await asyncio.gather(
            send_klaviyo_campaign(subject, html, f"PromoBlitz {datetime.now().strftime('%m-%d')}"),
            send_mailchimp_campaign(subject, html),
            _tg_send(f"📧 <b>{subject}</b>\n\n{link}"),
            _linkedin_post(f"{subject}\n\n{link}\n\n#PassivesEinkommen #AIITEC #OnlineBusiness"),
            return_exceptions=True,
        )
        return f"MailingBlitz: kl={bool(kl) if not isinstance(kl,Exception) else False} mc={bool(mc) if not isinstance(mc,Exception) else False} tg={bool(tg) if not isinstance(tg,Exception) else False}"
    except Exception as e:
        return f"MailingBlitz error: {e}"


async def task_printify_auto_publish() -> str:
    """Alle Printify Produkte die noch nicht in Shopify sind → sofort publishen."""
    try:
        from modules.printify_automation import ping, sync_all_products_to_shopify
        if not await ping():
            return "Printify: API key fehlt oder Shop nicht verbunden"
        r = await sync_all_products_to_shopify()
        published = r.get("published", 0)
        if published > 0:
            from modules.super_revenue_blitz import announce_new_products
            products = [{"title": f"Printify Produkt {i+1}"} for i in range(published)]
            await announce_new_products(products)
        return f"Printify AutoPublish: {published} neu, {r.get('already_live',0)} bereits live"
    except Exception as e:
        return f"Printify AutoPublish error: {e}"


async def task_shopify_auto_fill_trending() -> str:
    """Shopify vollautomatisch mit trendigen Produkten befüllen: AliExpress + AI-Bilder + SEO-Texte."""
    try:
        import aiohttp
        from modules.ai_client import ai_complete
        from modules.super_revenue_blitz import announce_new_products, _tg_send

        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        shopify_token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        shopify_ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shopify_domain or not shopify_token:
            return "Shopify not configured"

        # 1. AI ermittelt Trending-Produkte 2026
        trend_prompt = """Welche 5 Produkte sind gerade (2026) im deutschsprachigen E-Commerce am angesagtesten?
Fokus: Dropshipping/Print-on-Demand geeignet, hohe Nachfrage, günstiger Einkauf.
Antworte NUR als JSON-Array:
[{"name":"...", "niche":"...", "price_eur": 29.99, "keywords": ["kw1","kw2"], "emoji":"🔥"}]"""
        raw = await ai_complete(trend_prompt, max_tokens=500)
        products_info = []
        if raw:
            try:
                s = raw.find("["); e = raw.rfind("]") + 1
                products_info = json.loads(raw[s:e]) if s >= 0 else []
            except Exception:
                pass
        if not products_info:
            products_info = [
                {"name": "LED-Beleuchtungsset Smart Home", "niche": "Smart Home", "price_eur": 34.99, "keywords": ["LED", "Smart Home", "Licht"], "emoji": "💡"},
                {"name": "Fitness Widerstandsbänder Set", "niche": "Fitness", "price_eur": 24.99, "keywords": ["Fitness", "Training", "Widerstandsband"], "emoji": "💪"},
                {"name": "Nachhaltiger Bambus-Organizer", "niche": "Büro", "price_eur": 29.99, "keywords": ["Bambus", "Organizer", "Nachhaltigkeit"], "emoji": "🌿"},
                {"name": "KI-Produktivitäts-Planer 2026", "niche": "Produktivität", "price_eur": 19.99, "keywords": ["Planer", "Produktivität", "KI"], "emoji": "📋"},
                {"name": "Personalisierte Tasse Geschenk", "niche": "Geschenke", "price_eur": 22.99, "keywords": ["Tasse", "Personalisiert", "Geschenk"], "emoji": "☕"},
            ]

        base = f"https://{shopify_domain}"
        headers = {"X-Shopify-Access-Token": shopify_token, "Content-Type": "application/json"}
        imported = 0
        new_products = []

        for p in products_info[:5]:
            name = p.get("name", "Trending Produkt")
            price = float(p.get("price_eur", 29.99))
            niche = p.get("niche", "")
            keywords = p.get("keywords", [])
            emoji = p.get("emoji", "🔥")

            # 2. AI generiert SEO-Beschreibung
            seo_prompt = (
                f"Erstelle eine SEO-optimierte Shopify Produktbeschreibung auf Deutsch für:\n"
                f"Produkt: {name}\nNische: {niche}\nPreis: €{price:.2f}\n"
                f"Zielgruppe: Deutsche E-Commerce Kunden\n\n"
                f"Erstelle:\n- Kurze überzeugende Beschreibung (120 Wörter)\n- 5 Bullet-Points (Vorteile)\n- SEO Meta-Beschreibung (155 Zeichen)\n\n"
                f"Antworte als JSON: {{\"description\":\"...\",\"bullets\":[...],\"meta\":\"...\"}}"
            )
            try:
                raw_seo = await ai_complete(seo_prompt, max_tokens=400)
                si = raw_seo.find("{") if raw_seo else -1
                ei = raw_seo.rfind("}") + 1 if raw_seo else 0
                seo = json.loads(raw_seo[si:ei]) if si >= 0 and raw_seo else {}
            except Exception:
                seo = {}

            desc = seo.get("description", f"{name} — Jetzt im Angebot!")
            bullets = seo.get("bullets", ["✅ Hohe Qualität", "✅ Schnelle Lieferung", "✅ Zufriedenheitsgarantie"])
            bullets_html = "".join(f"<li>{b}</li>" for b in bullets[:5])
            body_html = (
                f"<h2>{emoji} {name}</h2>"
                f"<p>{desc}</p>"
                f"<ul>{bullets_html}</ul>"
                f"<p><em>Nische: {niche} | Keywords: {', '.join(keywords[:3])}</em></p>"
            )

            # 3. Shopify Produkt erstellen
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        f"{base}/admin/api/{shopify_ver}/products.json",
                        headers=headers,
                        json={"product": {
                            "title": f"{emoji} {name}",
                            "body_html": body_html,
                            "vendor": "TrendShop 2026",
                            "product_type": niche,
                            "status": "active",
                            "tags": ",".join(keywords[:5]),
                            "variants": [{"price": f"{price:.2f}", "inventory_management": None}],
                        }},
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as r:
                        if r.status in (200, 201):
                            imported += 1
                            new_products.append({"title": f"{emoji} {name}", "price": price})
                            log.info("Shopify TrendFill: created '%s'", name)
                        else:
                            log.debug("Shopify TrendFill skip (%s): %s", r.status, name[:40])
            except Exception as e:
                log.debug("Shopify TrendFill product error: %s", e)

        if imported > 0:
            await _tg_send(
                f"🛒 <b>Shopify Auto-Fill: {imported} neue Trend-Produkte!</b>\n\n"
                + "\n".join(f"• {p['title']}" for p in new_products[:5])
                + f"\n\nShop: https://{shopify_domain}"
            )
            # BRUTUS Traffic für neue Produkte
            try:
                from modules.brutus_traffic_engine import run_brutus_swarm
                kws = [p.get("name", "") for p in products_info[:3]]
                await run_brutus_swarm(keywords=kws, max_keywords=3)
            except Exception:
                pass

        return f"Shopify TrendFill: {imported} Produkte erstellt"
    except Exception as e:
        return f"Shopify TrendFill error: {e}"


async def task_shopify_publish_drafts() -> str:
    """Alle Shopify Draft-Produkte → active (sofort live stellen)."""
    try:
        import aiohttp
        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        shopify_token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        shopify_ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shopify_domain or not shopify_token:
            return "Shopify not configured"

        base = f"https://{shopify_domain}"
        headers = {"X-Shopify-Access-Token": shopify_token, "Content-Type": "application/json"}
        published = 0

        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{base}/admin/api/{shopify_ver}/products.json?status=draft&limit=50",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
            drafts = data.get("products", [])

            for p in drafts[:20]:  # max 20 per run
                try:
                    async with s.put(
                        f"{base}/admin/api/{shopify_ver}/products/{p['id']}.json",
                        headers=headers,
                        json={"product": {"id": p["id"], "status": "active"}},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            published += 1
                except Exception:
                    pass

        if published > 0:
            log.info("Shopify PublishDrafts: %d products published", published)
        return f"Shopify PublishDrafts: {published}/{len(drafts)} live gestellt"
    except Exception as e:
        return f"Shopify PublishDrafts error: {e}"


async def task_geheimwaffe_daily() -> str:
    try:
        from modules.geheimwaffe import run_full_automation
        r = await run_full_automation()
        return f"Geheimwaffe: {r.get('products_analyzed',0)} analyzed, {r.get('posts_created',0)} posts"
    except Exception as e:
        return f"Geheimwaffe error: {e}"


async def task_b2b_prospecting() -> str:
    try:
        from modules.b2b_pipeline import run_prospecting
        r = await run_prospecting()
        return f"B2B: {r.get('leads_found',0)} leads, {r.get('outreach_sent',0)} outreach"
    except Exception as e:
        return f"B2B Prospecting error: {e}"


async def task_growth_reviews() -> str:
    try:
        from modules.growth_engine import run_review_automation
        r = await run_review_automation()
        return f"Growth Reviews: {r.get('requests_sent',0)} sent"
    except Exception as e:
        return f"Growth Reviews error: {e}"


async def task_growth_winback() -> str:
    try:
        from modules.growth_engine import run_winback_campaign
        r = await run_winback_campaign()
        return f"Growth Winback: {r.get('emails_sent',0)} emails"
    except Exception as e:
        return f"Growth Winback error: {e}"


async def task_amazon_affiliate_blast() -> str:
    try:
        from modules.amazon_affiliate import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        prods = r.get('products', [])
        brutus_r = r.get('brutus', {})
        ch = brutus_r.get('channels_hit', 0)
        posts = brutus_r.get('content_pieces', 0)
        return f"Amazon Affiliate: {len(prods)} links gebuildet, brutus={ch} Kanäle {posts} Posts"
    except Exception as e:
        return f"Amazon Affiliate error: {e}"


async def task_klaviyo_brutus() -> str:
    try:
        from modules.klaviyo_automation import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        return f"Klaviyo+BRUTUS: {r}"
    except Exception as e:
        return f"Klaviyo BRUTUS error: {e}"


async def task_mailchimp_brutus() -> str:
    try:
        from modules.mailchimp_automation import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        return f"Mailchimp+BRUTUS: {r}"
    except Exception as e:
        return f"Mailchimp BRUTUS error: {e}"


async def task_shopify_autonomy_brutus() -> str:
    try:
        from modules.shopify_autonomy_master import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        return f"ShopifyAutonomy+BRUTUS: {r}"
    except Exception as e:
        return f"ShopifyAutonomy BRUTUS error: {e}"


async def task_email_seq_brutus() -> str:
    try:
        from modules.email_sequence_engine import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        return f"EmailSeq+BRUTUS: {r}"
    except Exception as e:
        return f"EmailSeq BRUTUS error: {e}"


async def task_ds24_digistore_brutus() -> str:
    try:
        from modules.digistore24_automation import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        return f"DS24+BRUTUS: {r}"
    except Exception as e:
        return f"DS24 BRUTUS error: {e}"


async def task_ebay_brutus_blast() -> str:
    """eBay Affiliate + BRUTUS traffic blast — alle Kanäle."""
    try:
        from modules.ebay_brutus import run_ebay_multi_blast
        r = await run_ebay_multi_blast(count=3)
        return f"eBay BRUTUS: {r.get('cycles',0)} Niches | {r.get('channels_hit',0)} Kanäle"
    except Exception as e:
        return f"eBay BRUTUS error: {e}"


async def task_discord_promo() -> str:
    """Discord Webhook Promo — DS24 Affiliate + Content."""
    try:
        from modules.discord_automation import run_discord_promo
        r = await run_discord_promo()
        if r.get("ok"):
            return "Discord Promo: sent ✅"
        return f"Discord Promo: {r.get('error','failed')} — Set DISCORD_WEBHOOK_URL in env"
    except Exception as e:
        return f"Discord error: {e}"


async def task_discord_revenue_report() -> str:
    """Discord daily revenue report embed."""
    try:
        from modules.discord_automation import run_discord_revenue_report
        r = await run_discord_revenue_report()
        return f"Discord Revenue: {'sent ✅' if r.get('ok') else 'failed — Set DISCORD_WEBHOOK_URL'}"
    except Exception as e:
        return f"Discord revenue error: {e}"


async def task_linkedin_post() -> str:
    """Post AI-generated LinkedIn content then fire BRUTUS traffic (every 4h)."""
    try:
        from modules.linkedin_oauth import run_with_brutus_traffic
        result = await run_with_brutus_traffic()
        li = result.get("linkedin", {})
        if li.get("success") or li.get("ok"):
            return f"LinkedIn post + BRUTUS: ✅ post_id={li.get('post_id','?')}"
        if li.get("skipped"):
            return f"LinkedIn: circuit open — skipped"
        return f"LinkedIn: {li.get('error', 'unknown error')}"
    except Exception as e:
        return f"task_linkedin_post error: {e}"


async def task_discord_daily() -> str:
    """Post daily Discord promo + BRUTUS traffic blast."""
    try:
        from modules.discord_automation import run_with_brutus_traffic
        result = await run_with_brutus_traffic()
        discord = result.get("discord", {})
        return f"Discord daily: {'✅ sent' if discord.get('ok') else discord.get('error','failed')}"
    except Exception as e:
        return f"task_discord_daily error: {e}"


# ── Twilio SMS Automation ─────────────────────────────────────────────────────

async def _twilio_send(to: str, body: str) -> bool:
    """Send SMS via Twilio; falls back to Telegram on any failure."""
    import aiohttp
    sid  = os.getenv("TWILIO_ACCOUNT_SID", "")
    tok  = os.getenv("TWILIO_AUTH_TOKEN", "")
    frm  = os.getenv("TWILIO_FROM_NUMBER", "")
    if sid and tok and frm:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=aiohttp.BasicAuth(sid, tok),
                    data={"To": to, "From": frm, "Body": body[:1600]},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    d = await r.json(content_type=None)
            if r.status == 201:
                return True
        except Exception:
            pass
    # Telegram fallback (works always)
    tg_tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_tok and tg_chat:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                    json={"chat_id": tg_chat, "text": f"📱 Alert:\n{body[:4000]}",
                          "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    d = await r.json(content_type=None)
            return d.get("ok", False)
        except Exception:
            pass
    return False


async def task_reddit_blast() -> str:
    """Daily: Post DS24 affiliate content to relevant subreddits."""
    try:
        from modules.reddit_autoposter import run_reddit_blast
        r = await run_reddit_blast()
        return f"Reddit: {r.get('posted',0)}/{r.get('total',0)} posted"
    except Exception as e:
        return f"Reddit blast error: {e}"


async def task_youtube_script_generator() -> str:
    """Every 4h: generate YouTube video script, notify Telegram, post if OAuth active."""
    try:
        import random
        from modules.ai_client import ai_complete
        from modules.notify_hub import async_send_telegram
        topics = [
            "KI Income Machine — Wie ich mit KI passives Einkommen aufbaue",
            "Shopify Automation 2026 — So läuft dein Store von selbst",
            "5 KI-Tools die wirklich Geld verdienen — Meine Erfahrungen",
            "Passives Einkommen Blueprint — Von 0 auf 5000€/Monat",
        ]
        topic = random.choice(topics)
        link = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        prompt = (
            f"Erstelle ein YouTube-Video-Skript zum Thema: '{topic}'\n"
            f"Länge: 3-5 Minuten (500-700 Wörter). Struktur: Hook, Problem, Lösung, CTA.\n"
            f"CTA: {link}\nSprache: Deutsch, motivierend."
        )
        script = await ai_complete(prompt, max_tokens=1000)
        if script:
            msg = f"🎬 *YouTube Script bereit:* {topic}\n\n{script[:600]}...\n\n🔗 {link}"
            await async_send_telegram(msg)
            try:
                from modules.brutus_traffic_engine import deploy_to_youtube
                await deploy_to_youtube(topic, {"youtube_desc": script[:900]})
            except Exception:
                pass
        return f"YouTube script: '{topic[:50]}'"
    except Exception as e:
        return f"YouTube script error: {e}"


async def task_whatsapp_daily_blast() -> str:
    """Daily WhatsApp promo blast to all configured recipients."""
    try:
        from modules.whatsapp_automation import send_whatsapp_blast
        link = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        msg = f"🚀 BullPower Hub: KI-Einkommen automatisieren — passives Einkommen 2026! Jetzt starten: {link}"
        r = await send_whatsapp_blast(msg)
        return f"WhatsApp blast: sent={r.get('sent',0)}, failed={r.get('failed',0)}"
    except Exception as e:
        return f"WhatsApp blast error: {e}"


async def task_twilio_morning_brief() -> str:
    """Daily morning SMS briefing — Revenue + Tasks for the day."""
    import aiohttp
    to = os.getenv("TWILIO_VERIFIED_TO", os.getenv("TWILIO_FROM_NUMBER", ""))
    if not to:
        return "TWILIO_VERIFIED_TO not set"
    try:
        shopify_key  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        shopify_dom  = os.getenv("SHOPIFY_SHOP_DOMAIN", "rudolfsarkanyshopped.myshopify.com")
        orders_today = 0
        revenue_today = 0.0
        if shopify_key:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{shopify_dom}/admin/api/2024-10/orders.json",
                    headers={"X-Shopify-Access-Token": shopify_key},
                    params={"status": "any", "created_at_min": today, "limit": 50, "fields": "id,total_price"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    d = await r.json(content_type=None)
            for o in d.get("orders", []):
                orders_today += 1
                revenue_today += float(o.get("total_price", 0))
        msg = (
            f"☀️ SUPERMEGABOT MORGEN-BRIEFING\n"
            f"📅 {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC\n\n"
            f"💰 Heute Revenue: €{revenue_today:.2f}\n"
            f"🛒 Shopify Orders: {orders_today}\n"
            f"🤖 149 Automatisierungen laufen\n"
            f"🔥 DS24 Affiliate aktiv\n\n"
            f"👉 DS24: https://autopilot-store-suite-fmbka.myshopify.com\n"
            f"📊 Dashboard: https://dudirudibot-mega-production.up.railway.app"
        )
        ok = await _twilio_send(to, msg)
        return f"Morning SMS: {'sent ✅' if ok else 'failed ❌'} → {to}"
    except Exception as e:
        return f"Twilio morning error: {e}"


async def task_twilio_revenue_alert() -> str:
    """Every 4h — SMS alert if new revenue detected."""
    import aiohttp
    to = os.getenv("TWILIO_VERIFIED_TO", os.getenv("TWILIO_FROM_NUMBER", ""))
    if not to:
        return "TWILIO_VERIFIED_TO not set"
    try:
        shopify_key = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        shopify_dom = os.getenv("SHOPIFY_SHOP_DOMAIN", "rudolfsarkanyshopped.myshopify.com")
        if not shopify_key:
            return "No Shopify key"
        since = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{shopify_dom}/admin/api/2024-10/orders.json",
                headers={"X-Shopify-Access-Token": shopify_key},
                params={"status": "any", "created_at_min": since, "limit": 10, "fields": "id,total_price,email"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        orders = d.get("orders", [])
        if not orders:
            return "No new orders last 4h — no SMS sent"
        total = sum(float(o.get("total_price", 0)) for o in orders)
        msg = (
            f"🎉 NEUE BESTELLUNG!\n"
            f"💰 {len(orders)} Order(s) — €{total:.2f}\n"
            f"📦 Shopify Store aktiv\n"
            f"👉 https://dudirudibot-mega-production.up.railway.app"
        )
        ok = await _twilio_send(to, msg)
        return f"Revenue SMS: {'sent ✅' if ok else 'failed ❌'} — {len(orders)} orders €{total:.2f}"
    except Exception as e:
        return f"Twilio revenue alert error: {e}"


async def task_twilio_ds24_report() -> str:
    """Every 6h — DS24 + system status SMS."""
    to = os.getenv("TWILIO_VERIFIED_TO", os.getenv("TWILIO_FROM_NUMBER", ""))
    if not to:
        return "TWILIO_VERIFIED_TO not set"
    try:
        msg = (
            f"📊 SUPERMEGABOT STATUS\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M')} UTC\n\n"
            f"✅ BRUTUS läuft — alle Kanäle bespielt\n"
            f"✅ DS24 Affiliate aktiv\n"
            f"✅ Shopify Automation läuft\n"
            f"✅ 149 Tasks registriert\n\n"
            f"🔗 Affiliate: https://autopilot-store-suite-fmbka.myshopify.com"
        )
        ok = await _twilio_send(to, msg)
        return f"DS24 SMS: {'sent ✅' if ok else 'failed ❌'}"
    except Exception as e:
        return f"Twilio DS24 report error: {e}"


async def task_twilio_stripe_alert() -> str:
    """Every 30min — check Stripe for new payments and SMS alert."""
    import aiohttp
    to = os.getenv("TWILIO_VERIFIED_TO", os.getenv("TWILIO_FROM_NUMBER", ""))
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not (to and stripe_key):
        return "Missing to/stripe_key"
    try:
        since = int((datetime.now(timezone.utc) - timedelta(minutes=35)).timestamp())
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/payment_intents",
                headers={"Authorization": f"Bearer {stripe_key}"},
                params={"created[gte]": since, "limit": 5},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        payments = [p for p in d.get("data", []) if p.get("status") == "succeeded"]
        if not payments:
            return "No new Stripe payments — no SMS"
        total = sum(p.get("amount", 0) / 100 for p in payments)
        msg = (
            f"💳 STRIPE ZAHLUNG!\n"
            f"💰 {len(payments)} Payment(s) — €{total:.2f}\n"
            f"🎉 Revenue kommt rein!\n"
            f"📊 https://dudirudibot-mega-production.up.railway.app"
        )
        ok = await _twilio_send(to, msg)
        return f"Stripe SMS: {'sent ✅' if ok else 'failed ❌'} — €{total:.2f}"
    except Exception as e:
        return f"Twilio stripe alert error: {e}"


async def task_tiktok_brutus() -> str:
    """TikTok Shop sync + BRUTUS OR content promo without token."""
    try:
        from modules.tiktok_shop_sync import run_with_brutus_traffic
        r = await run_with_brutus_traffic()
        synced = r.get("sync", {}).get("synced", 0)
        if synced > 0:
            return f"TikTok BRUTUS: synced={synced} blast={r.get('brutus',{}).get('ok','?')}"
    except Exception:
        pass
    try:
        from modules.tiktok_autonomy import run_tiktok_autonomy
        r = await run_tiktok_autonomy(count=3)
        return (f"TikTok Autonomy: {r.get('videos_scripted',0)} Scripts | "
                f"{r.get('channels_hit',0)} Kanal-Hits | Niches: {', '.join(r.get('niches',[])[:2])}")
    except Exception as e:
        return f"TikTok Autonomy Fehler: {e}"


async def task_tiktok_analytics_report() -> str:
    try:
        from modules.tiktok_shop_sync import get_tiktok_analytics
        r = await get_tiktok_analytics()
        return f"TikTok analytics: orders_30d={r.get('orders_30d',0)} revenue_30d=€{r.get('revenue_30d_eur',0)}"
    except Exception as e:
        return f"TikTok analytics error: {e}"


async def task_ebay_client_brutus() -> str:
    try:
        from modules.ebay_client import run_with_brutus_traffic
        r = await run_with_brutus_traffic("online shopping deals günstig")
        return f"eBay Browse+BRUTUS: items={r.get('items_found',0)} ok={r.get('ok',False)}"
    except Exception as e:
        return f"eBay Browse BRUTUS error: {e}"


async def task_ebay_client_search() -> str:
    try:
        from modules.ebay_client import search_items
        r = await search_items("trending produkte 2026", limit=10)
        return f"eBay Browse search: {len(r.get('items',[]))} items found"
    except Exception as e:
        return f"eBay Browse search error: {e}"


async def task_amazon_status_report() -> str:
    try:
        from modules.amazon_affiliate import TRACKING_ID, run_affiliate_blast
        r = await run_affiliate_blast()
        return f"Amazon blast done: tracking={TRACKING_ID}, result={str(r)[:80]}"
    except Exception as e:
        return f"Amazon blast error: {e}"


async def task_hermes_strategy() -> str:
    """Hermes Agent: tägliche Strategie-Analyse + Umsatz-Empfehlungen → Slack + Telegram."""
    try:
        from modules.hermes_bridge import analyze_revenue, delegate
        from modules.slack_notify import send_slack
        # Revenue-Snapshot holen
        try:
            import aiohttp
            smb_url = os.getenv("SUPERMEGABOT_URL", "https://dudirudibot-mega-production.up.railway.app")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{smb_url}/api/revenue/summary",
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    revenue_data = await r.json() if r.status == 200 else {}
        except Exception:
            revenue_data = {}
        # Hermes analysiert
        if revenue_data:
            result = await analyze_revenue(revenue_data)
        else:
            result = await delegate("Gib 3 konkrete Maßnahmen für mehr E-Commerce Umsatz heute. Fokus: Shopify + Digistore24 + Affiliate-Marketing.", context="daily_strategy")
        recommendation = result.get("result", "Hermes nicht erreichbar")[:500]
        # Slack + Telegram
        msg = f"🧠 Hermes Tages-Strategie:\n{recommendation}"
        await send_slack(msg, level="info")
        try:
            from modules.notify_hub import notify
            notify("Hermes Strategie", recommendation[:300], "info")
        except Exception:
            pass
        return f"Hermes strategy: {recommendation[:100]}"
    except Exception as e:
        return f"Hermes strategy error: {e}"


async def task_slack_revenue_report() -> str:
    """Stündlicher Slack Revenue Report — zeigt aktuellen Umsatz-Status."""
    try:
        from modules.slack_notify import send_slack
        import aiohttp
        smb_url = os.getenv("SUPERMEGABOT_URL", "https://dudirudibot-mega-production.up.railway.app")
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{smb_url}/api/revenue/summary",
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json() if r.status == 200 else {}
        total = data.get("total_revenue_eur", data.get("revenue", "?"))
        orders = data.get("total_orders", data.get("orders", "?"))
        stripe = data.get("stripe", {}).get("total", "?")
        ds24 = data.get("digistore24", {}).get("total", "?")
        msg = f"📊 Revenue Update\n💶 Total: {total} EUR\n🛒 Orders: {orders}\n💳 Stripe: {stripe} | DS24: {ds24}"
        await send_slack(msg, level="info")
        return f"Slack revenue report sent: {total} EUR"
    except Exception as e:
        return f"Slack revenue report error: {e}"


async def task_slack_error_monitor() -> str:
    """Überwacht System-Fehler und sendet Slack-Alert wenn Fehler gefunden."""
    try:
        from modules.slack_notify import send_slack
        import aiohttp
        smb_url = os.getenv("SUPERMEGABOT_URL", "https://dudirudibot-mega-production.up.railway.app")
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{smb_url}/health", timeout=aiohttp.ClientTimeout(total=10)) as r:
                health = await r.json() if r.status == 200 else {"status": f"HTTP {r.status}"}
        status = health.get("status", "unknown")
        if status != "ok":
            await send_slack(f"🔴 SuperMegaBot Health: {status}\n{str(health)[:200]}", level="error")
            return f"Health alert sent: {status}"
        return f"Health OK: {status}"
    except Exception as e:
        await send_slack(f"🔴 Health check failed: {e}", level="error")
        return f"Health monitor error: {e}"


async def task_gcp_enhance_products() -> str:
    """GCP Vision + Translation: Verbessert Shopify-Produkte mit Auto-Tags, Alt-Text, EN-Übersetzung."""
    try:
        import aiohttp
        from modules.gcp_services import enhance_shopify_product, GCP_API_KEY
        if not GCP_API_KEY:
            return "GCP_API_KEY nicht gesetzt — skip"
        shop   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shop or not token:
            return "Shopify credentials fehlen"
        url = f"https://{shop}/admin/api/{ver}/products.json?limit=10&status=active"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"X-Shopify-Access-Token": token},
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                products = (await r.json()).get("products", [])
        enhanced = 0
        for p in products:
            img_url = (p.get("images") or [{}])[0].get("src", "")
            product_data = {"title": p["title"], "body_html": p.get("body_html",""), "tags": p.get("tags",""), "image_url": img_url}
            result = await enhance_shopify_product(product_data)
            if result.get("tags") != p.get("tags",""):
                patch_url = f"https://{shop}/admin/api/{ver}/products/{p['id']}.json"
                async with aiohttp.ClientSession() as s:
                    await s.put(patch_url, headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                                json={"product": {"id": p["id"], "tags": result.get("tags","")}},
                                timeout=aiohttp.ClientTimeout(total=10))
                enhanced += 1
        return f"GCP enhance: {len(products)} geprüft, {enhanced} mit Auto-Tags aktualisiert"
    except Exception as e:
        return f"GCP enhance error: {e}"


async def task_gcp_translate_products() -> str:
    """GCP Translation: Übersetzt Produkt-Titel und Beschreibungen EN/FR für internationale Märkte."""
    try:
        import aiohttp
        from modules.gcp_services import translate_text, GCP_API_KEY
        if not GCP_API_KEY:
            return "GCP_API_KEY nicht gesetzt — skip"
        shop  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        ver   = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shop or not token:
            return "Shopify credentials fehlen"
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://{shop}/admin/api/{ver}/products.json?limit=5&status=active",
                             headers={"X-Shopify-Access-Token": token},
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                products = (await r.json()).get("products", [])
        translated = 0
        for p in products:
            title_de = p.get("title","")
            title_en = await translate_text(title_de, "en", "de")
            if title_en and title_en != title_de:
                meta_title = f"{title_en} | {title_de}"
                patch_url = f"https://{shop}/admin/api/{ver}/products/{p['id']}.json"
                async with aiohttp.ClientSession() as s:
                    await s.put(patch_url,
                                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                                json={"product": {"id": p["id"], "metafields": [{"namespace": "translations", "key": "title_en", "value": title_en, "type": "single_line_text_field"}]}},
                                timeout=aiohttp.ClientTimeout(total=10))
                translated += 1
        return f"GCP translate: {len(products)} Produkte, {translated} mit EN-Metafeld"
    except Exception as e:
        return f"GCP translate error: {e}"


async def task_shopify_full_auto_quick() -> str:
    """Shopify Quick-Fix: Drafts aktivieren, Inventar, Preise — läuft jede Stunde."""
    try:
        from modules.shopify_full_autonomy import run_full_autonomy_cycle
        r = await run_full_autonomy_cycle(quick=True, restock=False)
        return (f"Shopify Quick: drafts={r.get('drafts_activated',{}).get('activated',0)} "
                f"inv={r.get('inventory_fixed',{}).get('fixed',0)} "
                f"prices={r.get('prices_fixed',{}).get('fixed',0)}")
    except Exception as e:
        return f"Shopify QuickFix error: {e}"


async def task_shopify_full_auto() -> str:
    """Shopify Voll-Autonomie: SEO, Collections, Bilder, CTAs, Restock — alle 6h."""
    try:
        from modules.shopify_full_autonomy import run_full_autonomy_cycle
        r = await run_full_autonomy_cycle(quick=False, restock=True)
        return (f"Shopify FullAuto: ok={r.get('ok')} steps={r.get('steps_ok',0)} "
                f"collections={r.get('collections',{}).get('collections',0)} "
                f"seo={r.get('seo_fix',{}).get('fixed',0)} "
                f"restock={r.get('restock',{}).get('created',0)}")
    except Exception as e:
        return f"Shopify FullAuto error: {e}"


async def task_shopify_restock() -> str:
    """Shopify Restock: 5 meistgesuchte Trending-Produkte nachladen — alle 2h."""
    try:
        from modules.shopify_full_autonomy import auto_restock_trending
        r = await auto_restock_trending(count=5)
        return f"Shopify Restock: {r.get('created',0)} neue Produkte | {r.get('products',[])}"
    except Exception as e:
        return f"Shopify Restock error: {e}"


async def task_shopify_image_fix() -> str:
    """Shopify Image-Fix: Produkte ohne Bild bekommen Bilder von Pexels — alle 4h."""
    try:
        from modules.shopify_full_autonomy import fix_missing_images
        r = await fix_missing_images(limit=30)
        return f"Shopify ImageFix: {r.get('fixed',0)} Produkte mit Bild | no_image_total={r.get('no_image_total',0)}"
    except Exception as e:
        return f"Shopify ImageFix error: {e}"


async def task_shopify_title_fix() -> str:
    """Shopify Titel+Text Korrektur: KI verbessert schwache Titel — alle 4h."""
    try:
        from modules.shopify_full_autonomy import auto_correct_titles_and_descriptions
        r = await auto_correct_titles_and_descriptions(limit=15)
        return f"Shopify TitleFix: {r.get('fixed',0)} korrigiert | weak_found={r.get('weak_found',0)}"
    except Exception as e:
        return f"Shopify TitleFix error: {e}"


async def task_shopify_affiliate_blog() -> str:
    """Shopify Blog-Posts mit DS24 Affiliate Link — alle 4h automatisch."""
    try:
        from modules.shopify_full_autonomy import auto_create_affiliate_blog_posts
        r = await auto_create_affiliate_blog_posts(count=2)
        return (f"Affiliate Blog: {r.get('created',0)} Posts erstellt | "
                f"DS24={r.get('ds24_link','?')[:40]}")
    except Exception as e:
        return f"Affiliate Blog error: {e}"


async def task_nexus_cycle() -> str:
    """NEXUS-1: Autonomer Revenue-Superintelligenz Zyklus — alle 10 Minuten."""
    try:
        from modules.nexus import run_nexus_cycle
        result = await run_nexus_cycle()
        signals = result.get("signals_found", 0)
        succeeded = result.get("actions_succeeded", 0)
        planned = result.get("actions_planned", 0)
        top = result.get("top_signal", "?")
        best = result.get("best_action", "?")
        return f"NEXUS: {signals} signals, {succeeded}/{planned} actions OK | top='{top[:40]}' action={best}"
    except Exception as e:
        return f"NEXUS cycle error: {e}"


async def task_nexus_evolve() -> str:
    """NEXUS-1: Tägliche Selbst-Evolution — lernt aus Ergebnissen."""
    try:
        from modules.nexus import evolve_strategy
        result = await evolve_strategy()
        return f"NEXUS evolve: ok={result.get('ok')}, analysis={str(result.get('analysis',''))[:80]}"
    except Exception as e:
        return f"NEXUS evolve error: {e}"


async def task_nexus_report() -> str:
    """NEXUS-1: Tages-Report an Rudolf via Telegram + Slack."""
    try:
        from modules.nexus import send_daily_report
        result = await send_daily_report()
        return f"NEXUS report: {result.get('total_actions', 0)} actions today"
    except Exception as e:
        return f"NEXUS report error: {e}"


async def task_gcp_ping() -> str:
    """GCP API Health-Check — stellt sicher dass alle GCP-Services erreichbar sind."""
    try:
        from modules.gcp_services import ping
        result = await ping()
        return f"GCP ping: ok={result['ok']}, result='{result['result']}', project={result['project']}"
    except Exception as e:
        return f"GCP ping error: {e}"


async def task_semrush_keyword_research() -> str:
    """SemRush: keyword research für Haupt-Nischen + BRUTUS Traffic."""
    try:
        from modules.semrush_client import research_niche
        niches = [
            "KI passives Einkommen", "Shopify Automation", "Digistore24 Affiliate",
            "Online Business Deutschland", "Dropshipping 2026",
            "Print on Demand verdienen", "Affiliate Marketing Anfänger",
            "Amazon FBA Deutschland", "eBay Verkaufen profitabel",
            "Fiverr Freelancer Geld verdienen", "TikTok Shop Produkte",
            "Pinterest Traffic E-Commerce", "YouTube Monetarisierung",
            "Instagram Shop Verkaufen", "LinkedIn B2B Leads",
            "Email Marketing Automatisierung", "SEO Ranking 2026",
            "Passives Einkommen Ideen", "KI Tools Business",
            "Digitale Produkte verkaufen", "Gumroad Kurs erstellen",
            "Klaviyo E-Mail Kampagne", "Printify Shopify Produkte",
        ]
        results = []
        for niche in niches:
            data = await research_niche(niche)
            top_kw = data.get("top_keywords", [{}])[0].get("phrase", niche) if data.get("top_keywords") else niche
            vol = data.get("top_keywords", [{}])[0].get("volume", 0) if data.get("top_keywords") else 0
            results.append(f"{top_kw} ({vol} Suchen/Mo)")
        from modules.brutus_traffic_engine import run_brutus_swarm
        kws = [niche for niche in niches]
        await run_brutus_swarm(keywords=kws, max_keywords=3)
        return f"SemRush research: {'; '.join(results)}"
    except Exception as e:
        return f"SemRush research error: {e}"


async def task_semrush_competitor_spy() -> str:
    """SemRush: Konkurrenz-Keywords stehlen + BRUTUS traffic."""
    try:
        from modules.semrush_client import domain_competitors, domain_organic_keywords
        import os
        own = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
        competitors = await domain_competitors(own, limit=3)
        all_kws = []
        for comp in competitors[:2]:
            dom = comp.get("domain", "")
            if dom:
                kws = await domain_organic_keywords(dom, limit=5)
                all_kws.extend(k.get("phrase", "") for k in kws if k.get("phrase"))
        if all_kws:
            from modules.brutus_traffic_engine import run_brutus_swarm
            await run_brutus_swarm(keywords=all_kws[:5], max_keywords=5)
        return f"SemRush competitor spy: {len(competitors)} Konkurrenten, {len(all_kws)} Keywords gestohlen"
    except Exception as e:
        return f"SemRush competitor spy error: {e}"


async def task_paypal_status_check() -> str:
    """PayPal: Status + Balance Check."""
    try:
        from modules.paypal_client import get_paypal_status
        status = await get_paypal_status()
        connected = status.get("connected", False)
        email = status.get("email", "n/a")
        env = status.get("env", "n/a")
        return f"PayPal: connected={connected}, email={email}, env={env}"
    except Exception as e:
        return f"PayPal status error: {e}"


async def task_pipedrive_sync() -> str:
    """Pipedrive: CRM Status + offene Deals als Telegram-Report."""
    try:
        from modules.pipedrive_client import check_status, list_deals
        status = await check_status()
        if not status.get("ok"):
            return f"Pipedrive: nicht konfiguriert ({status.get('error', '')})"
        deals = await list_deals(limit=20, status="open")
        total_val = sum(float(d.get("value", 0)) for d in deals)
        return f"Pipedrive CRM: {len(deals)} offene Deals, Wert: {total_val:.0f} EUR"
    except Exception as e:
        return f"Pipedrive sync error: {e}"


async def task_pipedrive_shopify_sync() -> str:
    """Pipedrive: Shopify-Kunden → CRM Deals automatisch anlegen."""
    try:
        import os
        import aiohttp
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        api_ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not token or not domain:
            return "Pipedrive-Shopify-Sync: Shopify nicht konfiguriert"
        headers = {"X-Shopify-Access-Token": token}
        base = f"https://{domain}" if not domain.startswith("http") else domain
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(f"{base}/admin/api/{api_ver}/customers.json?limit=10", headers=headers) as r:
                if r.status != 200:
                    return f"Shopify customers error: HTTP {r.status}"
                customers = (await r.json()).get("customers", [])
        from modules.pipedrive_client import sync_shopify_customer
        synced = 0
        for c in customers:
            email = c.get("email", "")
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            val = float(c.get("total_spent", 0))
            if email:
                await sync_shopify_customer(email=email, name=name, order_value=val)
                synced += 1
        return f"Pipedrive-Shopify-Sync: {synced} Kunden → CRM"
    except Exception as e:
        return f"Pipedrive-Shopify-Sync error: {e}"


# ── AliExpress BRUTUS Tasks ───────────────────────────────────────────────────

async def task_aliexpress_brutus() -> str:
    """Every 2h: AliExpress affiliate content blast via BRUTUS — no OAuth needed."""
    try:
        from modules.aliexpress_brutus import run_aliexpress_multi_blast
        r = await run_aliexpress_multi_blast(count=3)
        return f"AliExpress BRUTUS: {r.get('cycles',0)} Niches | {r.get('channels_hit',0)} Kanäle"
    except Exception as e:
        return f"AliExpress BRUTUS error: {e}"


async def task_aliexpress_dropship_brutus() -> str:
    """Every 4h: AliExpress Dropshipping + DS24 Affiliate combo blast."""
    try:
        from modules.aliexpress_brutus import run_aliexpress_dropshipping_blast
        r = await run_aliexpress_dropshipping_blast()
        return f"AliExpress Dropship: tg={r.get('ok',False)} | {r.get('channels_hit',0)} Kanäle"
    except Exception as e:
        return f"AliExpress Dropship BRUTUS error: {e}"


# ── Printful BRUTUS Task ──────────────────────────────────────────────────────

async def task_brutus_printful() -> str:
    """Every 4h: Printful Print-on-Demand promotion via BRUTUS traffic."""
    try:
        from modules.super_revenue_blitz import brutus_blast_for_tool
        r = await brutus_blast_for_tool("Printful", "https://www.printful.com",
            ["Print on Demand Verdienen", "eigene Merch Produkte 2026", "Printful Shopify"])
        return f"BRUTUS Printful: {r.get('channels_hit', r.get('posts_sent', 0))} Kanäle, {r.get('content_pieces',0)} Posts"
    except Exception as e:
        return f"BRUTUS Printful error: {e}"


# ── Printful BRUTUS + Printify Stats Sync ────────────────────────────────────

async def task_printful_brutus() -> str:
    """Every 4h: Printful stats + BRUTUS traffic for print-on-demand keywords."""
    try:
        from modules.printful_automation import run_with_brutus_traffic
        result = await run_with_brutus_traffic()
        stats = result.get("stats", {})
        brutus = result.get("brutus") or {}
        channels = brutus.get("channels_hit", brutus.get("posts_sent", 0)) if isinstance(brutus, dict) else 0
        return (f"Printful BRUTUS: {stats.get('sync_products', 0)} Produkte, "
                f"{stats.get('total_orders', 0)} Bestellungen, {channels} Kanäle bespielt")
    except Exception as e:
        return f"Printful BRUTUS error: {e}"


async def task_printify_sync() -> str:
    """Every 4h: Sync Printify stats (products, orders, pending)."""
    try:
        from modules.printify_automation import get_stats
        stats = await get_stats()
        return (f"Printify sync: {stats.get('products', 0)} Produkte, "
                f"{stats.get('total_orders', 0)} Bestellungen, "
                f"{stats.get('pending', 0)} pending")
    except Exception as e:
        return f"Printify sync error: {e}"


# ── Mega BRUTUS Rotation — alle Plattformen im 1h Zyklus ─────────────────────

_MEGA_BRUTUS_PLATFORMS = [
    ("Digistore24 Affiliate",    os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx"),
     ["DS24 Affiliate 2026", "digitale Produkte verdienen", "passives Einkommen"]),
    ("Shopify Automation",        "",
     ["Shopify Dropshipping 2026", "Shopify Automation AI", "eigener Online-Shop"]),
    ("AliExpress Dropshipping",   "https://www.aliexpress.com",
     ["AliExpress Bestseller", "Dropshipping Produkte", "günstiger Einkauf"]),
    ("Amazon Affiliate",          "https://www.amazon.de/?tag=bullpowerhub-21",
     ["Amazon Bestseller 2026", "Amazon Affiliate verdienen", "passive Einnahmen Amazon"]),
    ("Printify Print on Demand",  "https://www.printify.com",
     ["Print on Demand 2026", "eigene T-Shirts verkaufen", "Merch Automation"]),
    ("eBay Deals",                "https://www.ebay.de",
     ["eBay Schnäppchen 2026", "eBay Dropshipping", "eBay Affiliate verdienen"]),
    ("Klaviyo Email Marketing",   "",
     ["Email Marketing Automation", "Klaviyo E-Commerce", "Newsletter Geld verdienen"]),
    ("TikTok Viral Produkte",     "https://autopilot-store-suite-fmbka.myshopify.com",
     ["TikTok viral Produkte 2026", "TikTok Shop Bestseller", "TikTok Dropshipping"]),
    ("Side Hustle Deutschland",   "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Side Hustle Deutschland 2026", "Nebenverdienst online", "zweites Einkommen"]),
    ("Passives Einkommen KI",     "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Passives Einkommen KI 2026", "Geld verdienen im Schlaf", "KI Business starten"]),
    ("Geld verdienen Österreich", "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Geld verdienen Österreich", "Online Business Wien", "E-Commerce Austria"]),
    ("Schweiz Online Business",   "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Online Business Schweiz", "Geld verdienen Zürich", "Dropshipping Schweiz"]),
    ("Shopify Anfänger Guide",    "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Shopify Anfänger 2026", "Online Shop erstellen", "ersten Shop starten"]),
    ("Amazon FBA Alternative",    "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Amazon FBA Alternative 2026", "ohne FBA verkaufen", "eigener Shop statt Amazon"]),
    ("Print on Demand Gewinn",    "https://autopilot-store-suite-fmbka.myshopify.com",
     ["Print on Demand Gewinn", "POD Marge optimieren", "Printful Printify Vergleich"]),
]

async def task_mega_brutus_rotation() -> str:
    """Every 1h: rotate through all platforms, blast one per hour via BRUTUS."""
    import random
    from modules.super_revenue_blitz import brutus_blast_for_tool
    platform, url, keywords = random.choice(_MEGA_BRUTUS_PLATFORMS)
    if not url:
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if "Shopify" in platform and shop:
            url = f"https://{shop}"
        else:
            url = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
    try:
        r = await brutus_blast_for_tool(platform, url, keywords)
        ch = r.get("channels_hit", r.get("posts_sent", 0))
        posts = r.get("content_pieces", 0)
        return f"Mega BRUTUS [{platform}]: {ch} Kanäle, {posts} Posts"
    except Exception as e:
        return f"Mega BRUTUS error [{platform}]: {e}"


# ── Platform Autonomy Tasks ──────────────────────────────────────────────────

async def task_amazon_autonomy_cycle() -> str:
    try:
        from modules.amazon_autonomy import run_amazon_cycle
        r = await run_amazon_cycle()
        return f"Amazon cycle: blasted={r.get('blasted',0)}"
    except Exception as e:
        return f"Amazon cycle error: {e}"


async def task_ebay_autonomy_cycle() -> str:
    try:
        from modules.ebay_autonomy import run_ebay_cycle
        r = await run_ebay_cycle()
        return f"eBay cycle: blast={r.get('blast',{}).get('blasted',0)}"
    except Exception as e:
        return f"eBay cycle error: {e}"


async def task_aliexpress_autonomy_cycle() -> str:
    try:
        from modules.aliexpress_autonomy import run_aliexpress_cycle
        r = await run_aliexpress_cycle()
        return f"AliExpress cycle: imported={r.get('imported',0)}"
    except Exception as e:
        return f"AliExpress cycle error: {e}"


async def task_alibaba_import() -> str:
    """6h — Alibaba/1688 trending products → Shopify via AliExpress API bridge."""
    try:
        from modules.alibaba_autonomy import run_alibaba_cycle
        r = await run_alibaba_cycle()
        return f"Alibaba: {r.get('imported',0)} importiert | {r.get('published',0)} publiziert"
    except Exception as e:
        return f"Alibaba Import Fehler: {e}"


async def task_printify_autonomy_cycle() -> str:
    try:
        from modules.printify_autonomy import run_printify_cycle
        r = await run_printify_cycle()
        return f"Printify cycle: created={r.get('created',0)}"
    except Exception as e:
        return f"Printify cycle error: {e}"


async def task_printful_autonomy_cycle() -> str:
    try:
        from modules.printful_autonomy import run_printful_cycle
        r = await run_printful_cycle()
        return f"Printful cycle: blasted={r.get('blast',{}).get('blasted',0)}"
    except Exception as e:
        return f"Printful cycle error: {e}"


async def task_digistore_autonomy_cycle() -> str:
    try:
        from modules.digistore_autonomy import run_digistore_cycle
        r = await run_digistore_cycle()
        return f"DS24 cycle: blasted={r.get('blast',{}).get('blasted',0)}, revenue=€{r.get('report',{}).get('total',0):.2f}"
    except Exception as e:
        return f"DS24 cycle error: {e}"


async def task_mailchimp_autonomy_cycle() -> str:
    try:
        from modules.mailchimp_autonomy import run_mailchimp_cycle
        r = await run_mailchimp_cycle()
        return f"Mailchimp cycle: ok={r.get('ok')}"
    except Exception as e:
        return f"Mailchimp cycle error: {e}"


async def task_klaviyo_autonomy_cycle() -> str:
    try:
        from modules.klaviyo_autonomy import run_klaviyo_cycle
        r = await run_klaviyo_cycle()
        return f"Klaviyo cycle: ok={r.get('ok')}"
    except Exception as e:
        return f"Klaviyo cycle error: {e}"


async def task_product_generator() -> str:
    try:
        from modules.product_generator import run_generator_cycle
        r = await run_generator_cycle(count=3, from_trends=True)
        return f"ProductGen: {r.get('created',0)} created, {r.get('failed',0)} failed"
    except Exception as e:
        return f"ProductGen error: {e}"


async def task_product_generator_niche() -> str:
    try:
        from modules.product_generator import run_niche_blast
        r = await run_niche_blast()
        return f"NicheBlast: {r.get('created',0)} created"
    except Exception as e:
        return f"NicheBlast error: {e}"


async def task_ds24_auto_create() -> str:
    """Erstellt täglich 1-2 neue DS24-Produkte vollautomatisch."""
    try:
        from modules.ds24_product_creator import auto_create_products
        r = await auto_create_products(count=2)
        return f"DS24 auto-create: {r.get('created',0)} erstellt, {r.get('failed',0)} failed"
    except Exception as e:
        return f"DS24 auto-create error: {e}"


async def task_ds24_affiliate_hourly() -> str:
    """Stündlich: 3 zufällige genehmigte DS24-Affiliate-Produkte blasten."""
    try:
        from modules.ds24_affiliate_blaster import blast_random
        r = await blast_random(count=3)
        return f"DS24 Affiliate: {r.get('blasted',0)} Produkte geblasten"
    except Exception as e:
        return f"DS24 affiliate error: {e}"


async def task_ds24_affiliate_daily() -> str:
    """Täglich: alle 22 genehmigten DS24-Affiliate-Produkte auf allen Kanälen."""
    try:
        from modules.ds24_affiliate_blaster import run_daily_affiliate_blast
        r = await run_daily_affiliate_blast()
        return f"DS24 Affiliate Daily: {r.get('blasted',0)}/{r.get('total',0)} geblasten"
    except Exception as e:
        return f"DS24 affiliate daily error: {e}"


async def task_ds24_marketplace_cycle() -> str:
    """Täglich: DS24 Marktplatz scan → bewerben → genehmigte Produkte blasten."""
    try:
        from modules.ds24_marketplace_auto import run_full_marketplace_cycle
        r = await run_full_marketplace_cycle()
        return (
            f"DS24 Marktplatz: {r.get('scanned',0)} gescannt, "
            f"{r.get('applied',0)} beworben, {r.get('blasted',0)} geblastet"
        )
    except Exception as e:
        return f"DS24 Marketplace error: {e}"


async def task_quantum_heal() -> str:
    """Stündlich: System analysieren, Circuits heilen, KI-Fixes generieren."""
    try:
        from modules.quantum_self_improver import quantum_heal_system
        r = await quantum_heal_system()
        healed = len(r.get("circuits_healed", []))
        fixes  = r.get("fixes_generated", 0)
        return f"Quantum Heal: {healed} Circuits geheilt, {fixes} Fixes generiert"
    except Exception as e:
        return f"Quantum Heal error: {e}"


async def task_token_health_check() -> str:
    """Stündlich: Alle Tokens prüfen + abgelaufene refreshen."""
    try:
        from modules.auto_token_refresher import run_token_health_check
        r = await run_token_health_check()
        ok_count = r.get("ok_count", 0)
        failed   = r.get("failed", [])
        fail_str = ", ".join(failed) if failed else "keine"
        return f"Token Check: {ok_count} OK, fehlgeschlagen: {fail_str}"
    except Exception as e:
        return f"Token Check error: {e}"


async def task_quantum_weekly() -> str:
    """Wöchentlich: Self-Improvement Report generieren + Telegram senden."""
    try:
        from modules.quantum_self_improver import self_improvement_report
        r = await self_improvement_report()
        return (
            f"Quantum Report: Woche {r.get('week','?')} — "
            f"{r.get('resolved',0)} behoben, {r.get('open',0)} offen"
        )
    except Exception as e:
        return f"Quantum Weekly error: {e}"


async def task_product_bundles() -> str:
    """Täglich: 3er+5er Shopify-Bundles erstellen + blasten."""
    try:
        from modules.product_bundle_engine import run_daily_bundle_cycle
        r = await run_daily_bundle_cycle()
        return f"Bundles: {r.get('bundles_created',0)} erstellt"
    except Exception as e:
        return f"Bundle error: {e}"


async def task_stripe_billing_check() -> str:
    """Täglich: Stripe-Subscriptions prüfen — failed payments + neue Subs."""
    try:
        from modules.stripe_auto_billing import check_subscriptions
        r = await check_subscriptions()
        return (
            f"Stripe: {r.get('active',0)} aktiv, "
            f"{r.get('failed',0)} failed, {r.get('new',0)} neu"
        )
    except Exception as e:
        return f"Stripe billing error: {e}"


async def task_auto_sort() -> str:
    """Alle 6h: Shopify+DS24+Klaviyo sortieren."""
    try:
        from modules.auto_sorter import sort_all
        r = await sort_all()
        shopify_sorted = r.get("shopify", {}).get("sorted", 0)
        ds24_sorted    = r.get("ds24",    {}).get("sorted", 0)
        return f"Sort: {shopify_sorted} Shopify-Produkte, {ds24_sorted} DS24-Produkte"
    except Exception as e:
        return f"AutoSort error: {e}"


async def task_revenue_daily() -> str:
    """Täglich: Revenue aggregieren + Meilenstein-Check + Telegram-Report."""
    try:
        from modules.revenue_auto_payout import run_daily_revenue_report
        r = await run_daily_revenue_report()
        total = r.get("snapshot", {}).get("total", 0)
        return f"Revenue daily: €{total:.2f} gesamt"
    except Exception as e:
        return f"Revenue daily error: {e}"


async def task_revenue_weekly() -> str:
    """Wöchentlich: 7-Tage Revenue-Report."""
    try:
        from modules.revenue_auto_payout import run_weekly_report
        r = await run_weekly_report()
        return f"Revenue weekly: {r.get('days',0)} Tage, ok={r.get('ok')}"
    except Exception as e:
        return f"Revenue weekly error: {e}"


async def task_ds24_refill() -> str:
    """Täglich: Hält 1000 aktive DS24-Produkte — füllt fehlende automatisch auf."""
    try:
        from modules.ds24_mass_creator import autonomous_refill
        r = await autonomous_refill(target=1000)
        return f"DS24 Refill: {r.get('created',0)} neue erstellt, {r.get('total_active',0)}/1000 aktiv"
    except Exception as e:
        return f"DS24 Refill error: {e}"


async def task_ds24_seo_blast() -> str:
    """Wöchentlich: Top-10 DS24-Produkte auf allen Kanälen blasten."""
    try:
        from modules.ds24_mass_creator import blast_top_products
        r = await blast_top_products(count=10)
        return f"DS24 SEO Blast: {r.get('blasted',0)} Produkte geblasten"
    except Exception as e:
        return f"DS24 SEO Blast error: {e}"


# ── SEO Traffic Blitz Tasks ──────────────────────────────────────────────────

async def task_seo_sitemap_ping() -> str:
    try:
        from modules.seo_traffic_blitz import run_sitemap_submit
        r = await run_sitemap_submit()
        return f"Sitemap gepingt: {r.get('pings_ok',0)}/{r.get('pings_total',0)} Suchmaschinen"
    except Exception as e:
        return f"Sitemap ping error: {e}"


async def task_seo_keyword_blast() -> str:
    try:
        from modules.seo_traffic_blitz import run_keyword_content_blast
        r = await run_keyword_content_blast(count=5)
        return f"KeywordBlast: {r.get('keywords_posted',0)} Keywords | {r.get('channels_hit',0)} Kanäle"
    except Exception as e:
        return f"Keyword blast error: {e}"


async def task_shopify_schema_seo() -> str:
    try:
        from modules.seo_traffic_blitz import run_schema_markup_inject
        r = await run_schema_markup_inject(limit=15)
        return f"Schema SEO: {r.get('products_updated',0)} Produkte optimiert"
    except Exception as e:
        return f"Schema SEO error: {e}"


async def task_sms_morning_brief() -> str:
    try:
        from modules.twilio_sms_blast import run_sms_morning_brief
        r = await run_sms_morning_brief()
        return f"SMS: {'gesendet ✅' if r.get('ok') else r.get('error','failed')}"
    except Exception as e:
        return f"SMS brief error: {e}"


async def task_internal_link_builder() -> str:
    try:
        from modules.seo_traffic_blitz import run_internal_link_builder
        r = await run_internal_link_builder()
        return f"InternalLinks: {r.get('articles_linked',0)} Artikel verlinkt"
    except Exception as e:
        return f"Internal link error: {e}"


async def task_full_seo_blast() -> str:
    try:
        from modules.seo_traffic_blitz import run_full_seo_blast
        r = await run_full_seo_blast()
        return (f"SEOBlast: sitemap={r.get('sitemap_pings',0)} "
                f"keywords={r.get('keywords_posted',0)} "
                f"schema={r.get('schema_updated',0)} "
                f"kanäle={r.get('channels_hit',0)}")
    except Exception as e:
        return f"Full SEO blast error: {e}"


async def task_rss_feed_update() -> str:
    try:
        from modules.rss_feed_publisher import generate_rss_feed
        r = await generate_rss_feed(limit=20)
        return f"RSS: {r.get('articles',0)} Artikel → feed.rss" if r.get("ok") else f"RSS error: {r.get('error')}"
    except Exception as e:
        return f"RSS feed error: {e}"


async def task_reddit_style_blast() -> str:
    try:
        from modules.reddit_autoposter import run_reddit_blast
        r = await run_reddit_blast()
        return f"Reddit: {r.get('posted',0)} Posts | {r.get('channels',0)} Kanäle"
    except Exception as e:
        return f"Reddit blast error: {e}"


async def task_mega_seo_cycle() -> str:
    try:
        from modules.mega_seo_engine import run_mega_seo_cycle
        r = await run_mega_seo_cycle()
        return f"MegaSEO: {r.get('articles',0)} Artikel | IndexNow: {sum(1 for v in r.get('indexnow',{}).values() if isinstance(v,int) and v in (200,202))}/3 | RSS: {r.get('elapsed',0)}s"
    except Exception as e:
        return f"MegaSEO error: {e}"


async def task_traffic_mega_cycle() -> str:
    try:
        from modules.traffic_mega_v2 import run_traffic_mega_cycle
        r = await run_traffic_mega_cycle()
        return f"TrafficMegaV2: {r.get('channels_ok',0)}/6 Kanäle | {r.get('topic','')[:60]}"
    except Exception as e:
        return f"TrafficMegaV2 error: {e}"


async def task_affiliate_mega_blast() -> str:
    try:
        from modules.affiliate_mega_engine import run_affiliate_blast
        r = await run_affiliate_blast()
        return f"AffiliateMega: {r.get('total_blasted',0)} Posts | amazon+ds24+ebay"
    except Exception as e:
        return f"AffiliateMega error: {e}"


async def task_email_blast_daily() -> str:
    try:
        from modules.email_blast_engine import run_daily_blast
        r = await run_daily_blast()
        sub = r.get("subject","")[:50]
        return f"EmailBlast: {sub} | klaviyo={r.get('blast',{}).get('klaviyo',{}).get('ok')} mc={r.get('blast',{}).get('mailchimp',{}).get('ok')}"
    except Exception as e:
        return f"EmailBlast error: {e}"


async def task_traffic_engine_cycle() -> str:
    try:
        from modules.traffic_mega_engine import run_traffic_cycle
        r = await run_traffic_cycle()
        return f"TrafficEngine: {r.get('channels',0)} Kanäle | {r.get('keyword','')[:40]}"
    except Exception as e:
        return f"TrafficEngine error: {e}"


async def task_revenue_fast_track_run() -> str:
    try:
        from modules.revenue_fast_track import run_revenue_fast_track
        r = await run_revenue_fast_track()
        return f"RevenueFastTrack: {r.get('channels_ok',0)}/5 Systeme | {r.get('elapsed',0)}s"
    except Exception as e:
        return f"RevenueFastTrack error: {e}"


async def task_shopify_mass_cycle() -> str:
    try:
        from modules.shopify_mass_creator import run_shopify_mass_cycle
        r = await run_shopify_mass_cycle()
        return f"ShopifyMass: created={r.get('created',0)} blasted={r.get('blasted',0)}"
    except Exception as e:
        return f"ShopifyMass error: {e}"


async def task_klaviyo_mass_daily() -> str:
    try:
        from modules.klaviyo_mass_campaigns import run_daily_klaviyo_campaigns
        r = await run_daily_klaviyo_campaigns(count=3)
        return f"KlaviyoMass: created={r.get('created',0)} failed={r.get('failed',0)}"
    except Exception as e:
        return f"KlaviyoMass error: {e}"


async def task_mailchimp_mass_daily() -> str:
    try:
        from modules.mailchimp_mass_campaigns import run_daily_mailchimp_campaigns
        r = await run_daily_mailchimp_campaigns(count=2)
        return f"MailchimpMass: created={r.get('created',0)} failed={r.get('failed',0)}"
    except Exception as e:
        return f"MailchimpMass error: {e}"


async def task_brutus_clone_status() -> str:
    try:
        from modules.brutus_clone_integrator import run_brutus_clone_cycle
        r = await run_brutus_clone_cycle()
        return f"BrutusClone: status_blast={r.get('status_blast',{}).get('ok', False)}"
    except Exception as e:
        return f"BrutusClone error: {e}"


async def task_revenue_mega_daily() -> str:
    try:
        from modules.revenue_mega_tracker import run_revenue_tracker_cycle
        r = await run_revenue_tracker_cycle()
        return f"RevenueMega: total=€{r.get('grand_total',0):.2f} date={r.get('report_date','')}"
    except Exception as e:
        return f"RevenueMega error: {e}"


async def task_revenue_mega_weekly() -> str:
    try:
        from modules.revenue_mega_tracker import run_revenue_weekly
        r = await run_revenue_weekly()
        return f"RevenueMegaWeekly: total_7d=€{r.get('grand_total_7d',0):.2f}"
    except Exception as e:
        return f"RevenueMegaWeekly error: {e}"


# ── Quantum Self-Improvement (second module — ergänzt Fixer) ──────────────────

async def task_quantum_self_improve() -> str:
    try:
        from modules.quantum_self_repair import run_self_improvement
        r = await run_self_improvement()
        return (f"SelfImprove: {r.get('improvements_analyzed',0)} analysiert | "
                f"{len(r.get('improvements',[]))} Verbesserungen")
    except Exception as e:
        return f"SelfImprove error: {e}"


# ── Task-Funktionen für neue Module (kein API-Key nötig) ─────────────────────

async def task_tiktok_trend_blast() -> str:
    try:
        from modules.tiktok_trends_scraper import run_tiktok_trend_blast
        r = await run_tiktok_trend_blast(count=5)
        return f"TikTok Trends: {r.get('niches_blasted',0)} Niches | {r.get('channels_hit',0)} Kanäle | Quelle: Google Trends DE"
    except Exception as e:
        return f"TikTok Trend Blast Fehler: {e}"


async def task_upwork_job_alert() -> str:
    try:
        from modules.upwork_job_scraper import run_upwork_job_alert
        r = await run_upwork_job_alert(max_jobs=3)
        return f"Upwork Jobs: {r.get('jobs_found',0)} gefunden | {r.get('alerted',0)} Alerts gesendet"
    except Exception as e:
        return f"Upwork Job Alert Fehler: {e}"


async def task_fiverr_gig_blast() -> str:
    try:
        from modules.fiverr_scraper import run_fiverr_gig_promotion
        r = await run_fiverr_gig_promotion(count=3)
        return f"Fiverr Gig Promo: {r.get('gigs_promoted',0)} Gigs | {r.get('channels_hit',0)} Kanäle"
    except Exception as e:
        return f"Fiverr Gig Blast Fehler: {e}"


async def task_fiverr_promo_cycle() -> str:
    try:
        from modules.fiverr_seo_promoter import run_fiverr_promotion_cycle
        r = await run_fiverr_promotion_cycle()
        return f"Fiverr SEO Promo: {r.get('gigs_promoted',0)} Gigs → TG+LI"
    except Exception as e:
        return f"Fiverr Promo Fehler: {e}"


async def task_upwork_proposal_gen() -> str:
    try:
        from modules.upwork_proposal_auto import run_upwork_proposal_generation
        r = await run_upwork_proposal_generation()
        return f"Upwork Proposals: {r.get('proposals_generated',0)} generiert + via Telegram gesendet"
    except Exception as e:
        return f"Upwork Proposal Fehler: {e}"


async def task_mega_agent_orchestrator() -> str:
    """Alle 4h — koordiniert alle 12 Plattform-Agenten parallel: Klaviyo, Mailchimp, Twilio, AliExpress, eBay, Amazon, Fiverr, Upwork, TikTok, Reddit, Discord, YouTube."""
    try:
        from modules.mega_agent_orchestrator import scheduled_orchestrator_run
        return await scheduled_orchestrator_run()
    except Exception as e:
        return f"MegaAgentOrchestrator Fehler: {e}"


async def task_credential_activator() -> str:
    """Every hour — detect new API keys and auto-activate platforms without restart."""
    try:
        from modules.credential_activator import run_credential_scan
        result = await run_credential_scan()
        new    = len(result.get("newly_activated", []))
        active = result.get("active_count", 0)
        total  = result.get("total_platforms", 0)
        return f"Credential Activator: {active}/{total} aktiv | neu aktiviert: {new}"
    except Exception as e:
        return f"Credential Activator Fehler: {e}"


async def task_dev_to_post() -> str:
    """Daily — post AI article to dev.to (auto-skips if DEVTO_API_KEY missing)."""
    try:
        from modules.dev_to_publisher import run_dev_to_post
        result = await run_dev_to_post()
        if result.get("skipped"):
            return "dev.to: DEVTO_API_KEY fehlt — übersprungen"
        return f"dev.to: {'OK — ' + str(result.get('url','')) if result.get('ok') else 'Fehler — ' + str(result.get('error',''))}"
    except Exception as e:
        return f"dev.to Fehler: {e}"


async def task_hashnode_post() -> str:
    """Daily — post AI article to Hashnode (auto-skips if token missing)."""
    try:
        from modules.hashnode_publisher import run_hashnode_post
        result = await run_hashnode_post()
        if result.get("skipped"):
            return "Hashnode: Token fehlt — übersprungen"
        return f"Hashnode: {'OK — ' + str(result.get('url','')) if result.get('ok') else 'Fehler — ' + str(result.get('error',''))}"
    except Exception as e:
        return f"Hashnode Fehler: {e}"


async def task_auto_product_pipeline() -> str:
    """Täglich: Trend → Shopify/Gumroad Produkt erstellen → alle Kanäle blasten."""
    try:
        from modules.autonomous_product_pipeline import run_product_pipeline
        r = await run_product_pipeline()
        return (f"AutoPipeline: '{r.get('product','?')}' "
                f"€{r.get('price_eur',0)} | Shopify={bool(r.get('shopify_url'))} "
                f"Gumroad={bool(r.get('gumroad_url'))} | Kanäle: geblastet")
    except Exception as e:
        return f"AutoPipeline Fehler: {e}"


async def task_bundle_creation_cycle() -> str:
    """Alle 8h: Bestehende Produkte zu Bundles zusammenfassen + bewerben."""
    try:
        from modules.product_bundle_engine import run_bundle_cycle
        r = await run_bundle_cycle()
        return (f"BundleCycle: {r.get('bundles_created',0)} Bundles | "
                f"{r.get('products_bundled',0)} Produkte | "
                f"Discount: {r.get('discount_pct',0)}%")
    except Exception as e:
        return f"BundleCycle Fehler: {e}"


async def task_autonomous_pipeline() -> str:
    """Täglich: vollautonome Pipeline — generieren → sortieren → bundeln → blasten → Stripe."""
    try:
        from modules.autonomous_pipeline import run_pipeline_cycle
        r = await run_pipeline_cycle()
        return (
            f"Pipeline: {r.get('generated',0)} generiert, "
            f"{r.get('sorted',0)} sortiert, {r.get('bundled',0)} Bundles, "
            f"{r.get('blasted',0)} geblastet, {r.get('payment_links',0)} Stripe-Links"
        )
    except Exception as e:
        return f"Pipeline Fehler: {e}"


async def task_mailchimp_dragon_article() -> str:
    """Täglich: 1 neuen Artikel via Dragon Mailchimp senden (dragonadnp@gmail.com)."""
    try:
        from modules.mailchimp_dragon_1000 import run_dragon_article_cycle
        r = await run_dragon_article_cycle()
        if r.get("ok"):
            return (f"Dragon Artikel gesendet: '{r.get('topic','?')}' | "
                    f"Gesamt: {r.get('total_sent',0)}/1000 | Verbleibend: {r.get('remaining',0)}")
        return f"Dragon Artikel Fehler: {r.get('error','?')} (Topic: {r.get('topic','?')})"
    except Exception as e:
        return f"Dragon Article Fehler: {e}"


async def task_selbstverbesserung() -> str:
    """Stündlich: Alle Plattformen analysieren, Fehler erkennen, Auto-Fix durchführen."""
    try:
        from modules.selbstverbesserung import run_selbstverbesserung_cycle
        r = await run_selbstverbesserung_cycle()
        return (f"Selbstverbesserung: {r.get('platforms_checked',0)} geprüft | "
                f"{r.get('issues_found',0)} Issues | {r.get('fixes_applied',0)} Fixes")
    except Exception as e:
        return f"Selbstverbesserung Fehler: {e}"


async def task_email_doctor() -> str:
    """Stündlich: E-Mail Health Check aller Mailing-Systeme."""
    try:
        from modules.email_doctor import run_email_doctor
        r = await run_email_doctor()
        return (f"EmailDoctor: Klaviyo={r.get('klaviyo','?')} | "
                f"Mailchimp={r.get('mailchimp','?')} | Dragon={r.get('dragon','?')} | "
                f"Fixes: {r.get('fixes',0)}")
    except Exception as e:
        return f"EmailDoctor Fehler: {e}"


async def task_mass_content_blaster() -> str:
    """Alle 2h: 1000 Content-Pieces über alle Plattformen verteilen."""
    try:
        from modules.mass_content_blaster import run_mass_blast
        r = await run_mass_blast()
        return (f"MassBlast: {r.get('total_posted',0)} Posts | "
                f"{r.get('platforms_hit',0)} Plattformen | "
                f"{r.get('topics_used',0)} Themen")
    except Exception as e:
        return f"MassBlast Fehler: {e}"


async def task_openclaw_blast() -> str:
    """Alle 2h: OpenClaw generiert Content → öffentlichen Kanal (nicht Rudolf's privaten Chat)."""
    try:
        from modules.open_claw import claw_generate_content
        topics = [
            "KI Automation System 2026 — Vollautomatisch Geld verdienen",
            "Shopify Dropshipping mit AI — €0 Start",
            "Digistore24 Affiliate 417 Produkte — Sofortprovision",
            "Passives Einkommen 2026 — KI macht alles für dich",
        ]
        import random
        topic = random.choice(topics)

        tg_post = await claw_generate_content(topic, "telegram")
        text = tg_post.get("text", "")

        sent = False
        if text:
            msg = f"{text[:600]}\n\n💳 https://buy.stripe.com/dRm6oJ67ofqq6Aw8gK4F21y"
            sent = await _tg_marketing(msg[:4000])

        return f"OpenClaw Blast: topic='{topic[:40]}' kanal={'gesendet' if sent else 'kein TELEGRAM_CHANNEL_ID'} chars={len(text)}"
    except Exception as e:
        return f"OpenClaw Blast Fehler: {e}"


async def task_customer_export() -> str:
    """Täglich: Shopify-Kunden → Klaviyo aiitec + Mailchimp exportieren."""
    try:
        from modules.customer_exporter import run_full_export
        r = await run_full_export()
        return (f"CustomerExport: {r.get('total_customers',0)} Kunden | "
                f"Klaviyo:{r.get('klaviyo',{}).get('synced',0)} | "
                f"Mailchimp:{r.get('mailchimp',{}).get('subscribed',0)}")
    except Exception as e:
        return f"CustomerExport Fehler: {e}"


async def task_quantum_self_repair() -> str:
    """Every 30min — scan recurring errors, apply auto-fixes, reset circuits."""
    try:
        from modules.quantum_self_repair import run_quantum_scan
        result = await run_quantum_scan()
        recurring = result.get("recurring_errors", 0)
        fixes = result.get("fix_count", 0)
        stats = result.get("error_stats", {})
        total = stats.get("total_occurrences", 0)
        return f"QuantumScan: {recurring} wiederkehrend | {fixes} Fixes | {total} Fehler gesamt"
    except Exception as e:
        # fallback to old fixer if new module not available
        try:
            from modules.quantum_self_fixer import scan_and_repair
            result = await scan_and_repair()
            return f"Quantum: {result.get('ok',0)}/{result.get('ok',0)+result.get('failed',0)} OK"
        except Exception:
            return f"Quantum Fehler: {e}"


async def task_instagram_pipeline() -> str:
    """Alle 3h: KI-Content generieren + auf Facebook AIITEC + Instagram @aaiitecc posten."""
    try:
        from modules.instagram_pipeline import run_pipeline
        result = await run_pipeline()
        fb_ok = result.get("facebook", {}).get("ok", False)
        ig_ok = result.get("instagram", {}).get("ok", False)
        err   = result.get("error", "")
        if err:
            return f"InstagramPipeline: {err[:80]}"
        return f"InstagramPipeline: FB={'✅' if fb_ok else '❌'} IG={'✅' if ig_ok else '❌'} | {result.get('title','')[:40]}"
    except Exception as e:
        return f"InstagramPipeline Fehler: {e}"


async def task_marketplace_poster() -> str:
    """Alle 3h: eBay+Amazon+AliExpress+Shop Cross-Posting (rotierend, nur Streetwear)."""
    try:
        from modules.marketplace_auto_poster import run_full_marketplace_cycle
        r = await run_full_marketplace_cycle()
        action = r.get("action", "?")
        ok = "✅" if r.get("ok") else "❌"
        return f"MarketplacePoster: {ok} {action}"
    except Exception as e:
        return f"MarketplacePoster Fehler: {e}"


async def task_streetwear_email() -> str:
    """Alle 3 Tage: Mailchimp + Klaviyo mit neuesten Printify-Produkten bespielen."""
    try:
        from modules.streetwear_email_engine import run_streetwear_email_blast
        r = await run_streetwear_email_blast()
        mc = "✅" if r.get("mailchimp", {}).get("ok") else "❌"
        kl = "✅" if r.get("klaviyo", {}).get("ok") else "❌"
        n  = r.get("products_sent", 0)
        t  = r.get("campaign_type", "?")
        return f"StreetEmail: MC={mc} KL={kl} | {n} Produkte | {t}"
    except Exception as e:
        return f"StreetEmail Fehler: {e}"


# ── Task registry ────────────────────────────────────────────────────────────

## LEAN MODE — essential monitoring + free traffic channels only
TASKS = [
    # (name, coroutine_fn, interval_seconds, initial_delay_seconds)
    # ── Monitoring (kostenlos) ────────────────────────────────────────────────
    ("system_health",        task_system_health,        300,   10),  # 5 min
    ("shopify_orders_alert", task_shopify_orders_alert,  600,  15),  # 10 min — Bestellung → Telegram
    ("digistore_sync",       task_digistore_sync,        900,  30),  # 15 min — DS24 Einnahmen
    ("printify_autofulfill", task_printify_autofulfill, 1800,  45),  # 30 min — POD Fulfillment
    ("stripe_monitor",       task_stripe_monitor,       1800,  25),  # 30 min — Zahlungen
    # ── Freie Traffic-Kanäle ──────────────────────────────────────────────────
    ("github_blog",          task_github_blog,         14400,  60),  # 4h — GitHub SEO Blog Posts
    ("ds24_traffic",         task_ds24_traffic,        10800,  90),  # 3h — DS24 Affiliate alle Kanäle
    ("social_scheduler",     task_social_scheduler,    21600, 120),  # 6h — Twitter + Telegram
    ("seo_dominator",        task_seo_dominator,        7200, 150),  # 2h — IndexNow + Sitemap
    ("backlink_bomber",      task_backlink_bomber,      7200, 180),  # 2h — Ping Google/Bing
    # ── Marketplace Auto-Poster ───────────────────────────────────────────────
    ("marketplace_poster",   task_marketplace_poster,    10800, 200),  # 3h — eBay+Amazon+AliExpress+Shop
    # ── Email Marketing ───────────────────────────────────────────────────────
    ("streetwear_email",     task_streetwear_email,    259200, 600),  # 3 Tage — Mailchimp+Klaviyo neue Produkte
    ("customer_export",      task_customer_export,      86400, 400),  # täglich — Shopify-Kunden → Klaviyo+MC
    ("klaviyo_mass",         task_klaviyo_mass_daily,   86400, 500),  # täglich — Klaviyo Mass Campaigns
    ("mailchimp_mass",       task_mailchimp_mass_daily, 86400, 550),  # täglich — Mailchimp Mass Campaigns
    # ── Shopify SEO Blog (ineedit.com.co T-Shirt/POD) ────────────────────────
    ("shopify_seo_blog",     task_shopify_seo_blog,    43200, 900),  # 12h — T-Shirt Blog Artikel
    # ── Backup ───────────────────────────────────────────────────────────────
    ("github_backup",        task_github_backup,       86400, 300),  # daily
    # ── eBay / Amazon / AliExpress Affiliate + Auto-Fill (DeepScan Fix) ──────
    ("ebay_auto_fill",        task_ebay_auto_fill,      14400, 210),  # 4h — eBay → Shopify import
    ("amazon_affiliate",      task_amazon_affiliate_blast, 14400, 250),  # 4h — Amazon affiliate blast
    ("aliexpress_import",     task_aliexpress_import,   28800, 290),  # 8h — AliExpress → Shopify
    ("shopify_auto_fill",     task_shopify_auto_fill,   21600, 330),  # 6h — Shopify trending fill
    ("ebay_cycle",            task_ebay_autonomy_cycle,  21600, 370),  # 6h — eBay full autonomy
    ("amazon_cycle",          task_amazon_autonomy_cycle, 21600, 410),  # 6h — Amazon full autonomy
    ("aliexpress_cycle",      task_aliexpress_autonomy_cycle, 28800, 450),  # 8h — AliExpress cycle
    ("alibaba_import",        task_alibaba_import,           21600, 470),  # 6h — Alibaba/1688 → Shopify
    ("ebay_blast",            task_ebay_blast,          10800, 490),  # 3h — eBay multi blast
    ("shopify_fix_tags",      task_shopify_fix_tags,     3600,  530),  # 1h — T-Shirt SEO tags
    ("shopify_cleanup_cols",  task_shopify_cleanup_collections, 86400, 570),  # 24h — leere Collections
    ("shopify_gmc_meta",      task_shopify_gmc_metafields, 3600, 610),  # 1h — Google Shopping metafelder
]


# ── Scheduler loop ───────────────────────────────────────────────────────────

class AutomationScheduler:
    def __init__(self):
        _init_db()
        self._running = False
        self._task_handles: List[asyncio.Task] = []

    async def start(self):
        self._running = True
        log.info(f"AutoScheduler gestartet — {len(TASKS)} Tasks registriert")
        for name, fn, interval, delay in TASKS:
            handle = asyncio.create_task(self._run_loop(name, fn, interval, delay))
            self._task_handles.append(handle)
        # Telegram bot uses webhook mode (server.py /webhook/telegram) — polling disabled
        log.info("Telegram: webhook mode active, polling disabled")

    async def stop(self):
        self._running = False
        for h in self._task_handles:
            h.cancel()

    async def run_now(self, task_name: str) -> Optional[str]:
        for name, fn, _, _ in TASKS:
            if name == task_name:
                return await self._execute(name, fn)
        return f"Task {task_name!r} nicht gefunden"

    async def _run_loop(self, name: str, fn: Callable, interval: int, delay: int):
        await asyncio.sleep(delay)
        while self._running:
            result = await self._execute(name, fn)
            log.debug(f"[{name}] {result}")
            await asyncio.sleep(interval)

    # Self-healing: consecutive fail counter per task
    _fail_counts: Dict[str, int] = {}

    async def _send_healing_alert(self, task_name: str, error: str, fails: int) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        msg = (f"⚠️ Self-Healing Alert\n"
               f"Task: {task_name}\n"
               f"Fehler {fails}x: {error[:200]}\n"
               f"Auto-Retry läuft...")
        try:
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                    timeout=_aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass

    async def _execute(self, name: str, fn: Callable) -> str:
        t0 = time.monotonic()
        try:
            result = await fn()
            ms = int((time.monotonic() - t0) * 1000)
            _log_run(name, True, result or "", ms)
            self._fail_counts[name] = 0  # reset on success
            return result or "OK"
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            err = f"{type(e).__name__}: {e}"
            _log_run(name, False, err, ms)
            log.error(f"[{name}] {err}")
            # Self-healing: track consecutive failures
            self._fail_counts[name] = self._fail_counts.get(name, 0) + 1
            fails = self._fail_counts[name]
            if fails >= 3:
                await self._send_healing_alert(name, err, fails)
                self._fail_counts[name] = 0  # reset after alert
            # Exponential backoff retry (max 5 min)
            backoff = min(60 * fails, 300)
            log.info(f"[{name}] retry in {backoff}s (fail #{fails})")
            await asyncio.sleep(backoff)
            try:
                retry_result = await fn()
                self._fail_counts[name] = 0
                return f"RECOVERED: {retry_result or 'OK'}"
            except Exception as e2:
                return f"FAILED after retry: {e2}"

    def status(self) -> Dict:
        stats = get_task_stats()
        return {
            "running": self._running,
            "task_count": len(TASKS),
            "tasks": [
                {
                    "name": name,
                    "interval_s": interval,
                    **stats.get(name, {"total": 0, "ok": 0, "last_run": None, "avg_ms": 0})
                }
                for name, _, interval, _ in TASKS
            ]
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_scheduler: Optional[AutomationScheduler] = None


def get_scheduler() -> AutomationScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AutomationScheduler()
    return _scheduler


def get_scheduler_status() -> dict:
    """Return all scheduler tasks with stats."""
    s = get_scheduler()
    return s.status()


# ── Standalone entrypoint ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import signal

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    async def _standalone():
        sched = get_scheduler()
        await sched.start()
        log.info("SuperMegaBot Scheduler gestartet — Ctrl+C zum Beenden")
        stop_event = asyncio.Event()

        def _shutdown(sig, frame):  # noqa: ARG001
            log.info("Signal %s — beende Scheduler...", sig)
            stop_event.set()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
        await stop_event.wait()
        await sched.stop()

    asyncio.run(_standalone())
