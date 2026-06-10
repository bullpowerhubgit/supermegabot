#!/usr/bin/env python3
"""
AutoPilot CreatorHub — Multi-Agent AI System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
10 spezialisierte AI-Agenten, vollständig autonom:
  CEO · Shopify · Marketing · Coding · Design
  Research · Automation · Finance · Trend · Security

Jeder Agent: Memory · Task Queue · Logging · Decision Engine
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("AutoPilotAgents")

DATA_DIR = Path(__file__).parent.parent / "data" / "agents"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Shared Event Bus ──────────────────────────────────────────────────────────

_event_subscribers: Dict[str, List] = {}


def subscribe(event: str, handler):
    _event_subscribers.setdefault(event, []).append(handler)


async def emit(event: str, payload: Dict):
    for handler in _event_subscribers.get(event, []):
        try:
            await handler(payload)
        except Exception as e:
            log.warning("Event handler error [%s]: %s", event, e)


# ── Base Agent ─────────────────────────────────────────────────────────────────

class BaseAgent:
    name: str = "base"
    description: str = ""
    capabilities: List[str] = []

    def __init__(self):
        self._memory: List[Dict] = []
        self._task_queue: List[Dict] = []
        self._logs: List[Dict] = []
        self._running = False
        self._mem_file = DATA_DIR / f"{self.name}_memory.json"
        self._load_memory()

    # ── Memory ────────────────────────────────────────────────────────────────

    def _load_memory(self):
        if self._mem_file.exists():
            try:
                self._memory = json.loads(self._mem_file.read_text())
            except Exception:
                self._memory = []

    def _save_memory(self):
        try:
            self._mem_file.write_text(json.dumps(self._memory[-200:], ensure_ascii=False, indent=2))
        except Exception:
            pass

    def remember(self, key: str, value: Any):
        self._memory.append({
            "key": key,
            "value": value,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        self._save_memory()

    def recall(self, key: str, n: int = 5) -> List[Any]:
        return [m["value"] for m in self._memory if m.get("key") == key][-n:]

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, level: str, msg: str, data: Optional[Dict] = None):
        entry = {
            "id": str(uuid.uuid4())[:8],
            "agent": self.name,
            "level": level,
            "msg": msg,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._logs.append(entry)
        if len(self._logs) > 500:
            self._logs = self._logs[-500:]
        log.info("[%s] %s", self.name, msg)

    def info(self, msg: str, data: Optional[Dict] = None):
        self._log("info", msg, data)

    def warn(self, msg: str, data: Optional[Dict] = None):
        self._log("warn", msg, data)

    def error(self, msg: str, data: Optional[Dict] = None):
        self._log("error", msg, data)

    # ── Task Queue ────────────────────────────────────────────────────────────

    def enqueue(self, task: str, params: Optional[Dict] = None, priority: int = 5):
        self._task_queue.append({
            "id": str(uuid.uuid4())[:8],
            "task": task,
            "params": params or {},
            "priority": priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        })
        self._task_queue.sort(key=lambda x: x["priority"])

    def get_status(self) -> Dict:
        return {
            "agent": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "running": self._running,
            "memory_size": len(self._memory),
            "task_queue": len(self._task_queue),
            "recent_logs": self._logs[-10:],
            "pending_tasks": [t for t in self._task_queue if t["status"] == "pending"][:5],
        }

    # ── Claude AI helper ──────────────────────────────────────────────────────

    async def _ask_claude(self, system: str, user: str, max_tokens: int = 800) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return "ANTHROPIC_API_KEY nicht gesetzt"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": max_tokens,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    if r.status != 200:
                        return f"Claude error {r.status}"
                    data = await r.json()
                    return data["content"][0]["text"].strip()
        except Exception as e:
            return f"AI error: {e}"

    # ── Main execute ──────────────────────────────────────────────────────────

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        raise NotImplementedError


# ── CEO Agent ─────────────────────────────────────────────────────────────────

class CEOAgent(BaseAgent):
    name = "ceo"
    description = "Orchestriert alle Agenten · Strategie · Entscheidungen · Priorisierung"
    capabilities = ["strategize", "delegate", "prioritize", "report", "decide"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"CEO Task: {task}")

        if task == "status":
            return {
                "ok": True,
                "agent": self.name,
                "description": self.description,
                "capabilities": self.capabilities,
                "memory_size": len(self._memory),
                "last_strategy": self.recall("last_strategy", 1),
            }

        if task == "strategize":
            context = params.get("context", "E-Commerce Shopify Business")
            strategy = await self._ask_claude(
                "Du bist ein erfahrener CEO einer E-Commerce SaaS-Plattform.",
                f"Entwickle 5 konkrete Maßnahmen für: {context}\n"
                "Fokus: Umsatz steigern, Kosten senken, Automatisierung maximieren.\n"
                "Format: JSON mit Liste von {{action, priority, impact, timeline}}",
                max_tokens=1000,
            )
            self.remember("last_strategy", strategy)
            return {"ok": True, "strategy": strategy, "agent": self.name}

        if task == "delegate":
            agent_name = params.get("agent")
            sub_task = params.get("task")
            sub_params = params.get("params", {})
            agent = _get_agent(agent_name)
            if not agent:
                return {"ok": False, "error": f"Agent {agent_name} nicht gefunden"}
            result = await agent.execute(sub_task, sub_params)
            self.info(f"Delegiert an {agent_name}: {sub_task}")
            return {"ok": True, "delegated_to": agent_name, "result": result}

        if task == "daily_briefing":
            parts = []
            for agent_name in ["shopify", "finance", "marketing", "trend"]:
                a = _get_agent(agent_name)
                if a:
                    try:
                        r = await a.execute("status")
                        parts.append({"agent": agent_name, "status": r})
                    except Exception as e:
                        parts.append({"agent": agent_name, "error": str(e)})
            return {"ok": True, "briefing": parts, "ts": datetime.now(timezone.utc).isoformat()}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Shopify Agent ─────────────────────────────────────────────────────────────

class ShopifyAgent(BaseAgent):
    name = "shopify"
    description = "Produkte · Orders · Analytics · Preise · SEO · Automatisierung"
    capabilities = ["analyze_products", "optimize_prices", "create_product", "get_orders", "seo", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Shopify Task: {task}")

        if task in ("status", "analyze_products"):
            try:
                from modules.shopify_revenue_engine import get_revenue_summary, get_product_performance
                rev = await get_revenue_summary()
                perf = await get_product_performance(days=7)
                result = {
                    "revenue_7d": rev.get("7d", {}),
                    "top_sellers": perf.get("top_sellers", [])[:3],
                    "zero_sellers": perf.get("zero_seller_count", 0),
                    "pending_orders": rev.get("pending_orders", 0),
                }
                self.remember("last_analysis", result)
                return {"ok": True, **result}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        if task == "optimize_prices":
            from modules.shopify_revenue_engine import bulk_price_update
            pct = float(params.get("percent", 5))
            return await bulk_price_update(method="percent", value=pct)

        if task == "seo":
            product_title = params.get("product_title", "Produkt")
            seo = await self._ask_claude(
                "Du bist ein Shopify SEO-Experte.",
                f"Schreibe für '{product_title}' folgendes auf Deutsch:\n"
                "1. SEO-Titel (max 70 Zeichen)\n"
                "2. Meta-Description (max 160 Zeichen)\n"
                "3. 5 Keywords\n"
                "Format: JSON",
            )
            return {"ok": True, "seo": seo}

        if task == "flash_sale":
            from modules.shopify_revenue_engine import create_flash_sale
            return await create_flash_sale(
                discount_pct=int(params.get("discount_pct", 20)),
                duration_hours=int(params.get("hours", 24)),
            )

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Marketing Agent ───────────────────────────────────────────────────────────

class MarketingAgent(BaseAgent):
    name = "marketing"
    description = "Email · Social Media · Ads · Content · Kampagnen · Funnels"
    capabilities = ["email_campaign", "social_content", "ad_copy", "funnel", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Marketing Task: {task}")

        if task == "status":
            return {"ok": True, "campaigns_running": 0, "last_email": self.recall("last_email", 1)}

        if task == "email_campaign":
            product = params.get("product", "")
            discount = params.get("discount", "20%")
            content = await self._ask_claude(
                "Du bist ein E-Mail Marketing Experte für E-Commerce.",
                f"Schreibe eine Verkaufs-E-Mail auf Deutsch:\n"
                f"Produkt: {product}\nAngebot: {discount} Rabatt\n"
                "Format: {{subject, preheader, body_html, cta_text}}. Kurz, überzeugend, professionell.",
                max_tokens=800,
            )
            self.remember("last_email", content)
            return {"ok": True, "email": content}

        if task == "social_content":
            product = params.get("product", "")
            platform = params.get("platform", "Instagram")
            content = await self._ask_claude(
                f"Du bist ein {platform} Content Creator für E-Commerce.",
                f"Erstelle einen viralen Post für '{product}' auf {platform}.\n"
                "Inkl. Caption, Hashtags, Hook, CTA. Auf Deutsch. JSON Format.",
                max_tokens=600,
            )
            return {"ok": True, "platform": platform, "content": content}

        if task == "ad_copy":
            product = params.get("product", "")
            budget = params.get("budget", "€50")
            copy = await self._ask_claude(
                "Du bist ein Performance Marketing Experte für Meta/Google Ads.",
                f"Erstelle 3 Ad-Varianten für '{product}' (Budget: {budget}/Tag).\n"
                "Je: Headline, Description, CTA, Target Audience. JSON Format. Auf Deutsch.",
                max_tokens=800,
            )
            return {"ok": True, "ad_copy": copy}

        if task == "funnel":
            product = params.get("product", "")
            funnel = await self._ask_claude(
                "Du bist ein Conversion-Funnel Experte.",
                f"Entwirf einen 4-Stufen Sales Funnel für '{product}'.\n"
                "Stufen: Awareness → Interest → Decision → Action.\n"
                "Je Stufe: Taktik, Content-Typ, KPI. JSON. Auf Deutsch.",
                max_tokens=800,
            )
            return {"ok": True, "funnel": funnel}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Coding Agent ──────────────────────────────────────────────────────────────

class CodingAgent(BaseAgent):
    name = "coding"
    description = "Code generieren · Bugs fixen · APIs verbinden · GitHub Commits"
    capabilities = ["generate_code", "fix_bug", "review_code", "create_api", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Coding Task: {task}")

        if task == "status":
            return {"ok": True, "language": "Python/TypeScript", "last_commit": self.recall("last_commit", 1)}

        if task == "generate_code":
            spec = params.get("spec", "")
            lang = params.get("language", "Python")
            code = await self._ask_claude(
                f"Du bist ein Senior {lang} Entwickler.",
                f"Schreibe produktionsreifen {lang} Code für:\n{spec}\n\n"
                "Inkl. Error Handling, Logging, Type Hints. Kommentare auf Deutsch.",
                max_tokens=1500,
            )
            self.remember("last_code", {"spec": spec, "code": code[:200]})
            return {"ok": True, "code": code, "language": lang}

        if task == "fix_bug":
            code = params.get("code", "")
            error = params.get("error", "")
            fix = await self._ask_claude(
                "Du bist ein Expert Python/JS Debugger.",
                f"Fehler:\n```\n{error}\n```\n\nCode:\n```\n{code[:1000]}\n```\n\n"
                "Finde und behebe den Bug. Erkläre was falsch war. JSON: {{fix, explanation, fixed_code}}",
                max_tokens=1000,
            )
            return {"ok": True, "fix": fix}

        if task == "review_code":
            code = params.get("code", "")
            review = await self._ask_claude(
                "Du bist ein Senior Code Reviewer.",
                f"Reviewe diesen Code:\n```\n{code[:2000]}\n```\n\n"
                "JSON: {{score_1_10, issues, improvements, security_risks, performance_tips}}",
                max_tokens=800,
            )
            return {"ok": True, "review": review}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Design Agent ──────────────────────────────────────────────────────────────

class DesignAgent(BaseAgent):
    name = "design"
    description = "Shopify Theme · UI/UX · Produktbilder Prompts · Branding"
    capabilities = ["theme_optimize", "image_prompt", "branding", "landing_page", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Design Task: {task}")

        if task == "status":
            return {"ok": True, "specialty": "Shopify Themes + UI Design"}

        if task == "image_prompt":
            product = params.get("product", "")
            style = params.get("style", "minimalist product photography")
            prompt = await self._ask_claude(
                "Du bist ein Midjourney/DALL-E Prompt Engineer.",
                f"Erstelle 3 professionelle Image Prompts für '{product}'.\n"
                f"Stil: {style}\nFormat: JSON Liste mit je prompt + negative_prompt",
                max_tokens=600,
            )
            return {"ok": True, "prompts": prompt}

        if task == "theme_optimize":
            store_type = params.get("store_type", "General")
            tips = await self._ask_claude(
                "Du bist ein Shopify Theme Conversion-Optimierungs-Experte.",
                f"Gib 10 konkrete Optimierungen für ein {store_type} Shopify Theme.\n"
                "Fokus: Conversion Rate, Mobile UX, Ladezeit. JSON Liste. Auf Deutsch.",
                max_tokens=800,
            )
            return {"ok": True, "optimizations": tips}

        if task == "landing_page":
            product = params.get("product", "")
            target = params.get("target_audience", "Allgemein")
            page = await self._ask_claude(
                "Du bist ein Landing Page Conversion Experte.",
                f"Entwirf eine Landing Page Struktur für '{product}' (Zielgruppe: {target}).\n"
                "JSON: {{hero, value_props, social_proof, features, cta, faq, footer_cta}}",
                max_tokens=1000,
            )
            return {"ok": True, "landing_page": page}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Research Agent ────────────────────────────────────────────────────────────

class ResearchAgent(BaseAgent):
    name = "research"
    description = "Marktanalyse · Wettbewerber · Trends · Winning Products · Keywords"
    capabilities = ["market_research", "competitor_analysis", "keyword_research", "trend_analysis", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Research Task: {task}")

        if task == "status":
            return {"ok": True, "specialty": "Market Research & Competitive Intelligence"}

        if task == "market_research":
            niche = params.get("niche", "")
            research = await self._ask_claude(
                "Du bist ein E-Commerce Marktforschungs-Experte.",
                f"Analysiere den Markt für: {niche}\n"
                "JSON: {{market_size, growth_rate, target_audience, pain_points, opportunities, competitors_count, avg_price_range}}",
                max_tokens=800,
            )
            self.remember("market_research", research)
            return {"ok": True, "research": research}

        if task == "competitor_analysis":
            competitor = params.get("competitor", "")
            analysis = await self._ask_claude(
                "Du bist ein Competitive Intelligence Analyst.",
                f"Analysiere den Wettbewerber: {competitor}\n"
                "JSON: {{strengths, weaknesses, pricing, unique_selling_points, marketing_channels, our_advantage}}",
                max_tokens=800,
            )
            return {"ok": True, "analysis": analysis}

        if task == "winning_products":
            niche = params.get("niche", "General E-Commerce")
            products = await self._ask_claude(
                "Du bist ein Dropshipping/E-Commerce Produkt-Experte.",
                f"Finde 5 Winning Products für: {niche}\n"
                "Je Produkt: {{name, why_winning, target_audience, estimated_margin_pct, aliexpress_search, selling_price_eur}}\n"
                "Basierend auf: hohe Nachfrage, niedriger Wettbewerb, gute Marge. JSON.",
                max_tokens=1000,
            )
            return {"ok": True, "winning_products": products}

        if task == "keyword_research":
            product = params.get("product", "")
            keywords = await self._ask_claude(
                "Du bist ein SEO Keyword Research Experte.",
                f"Finde 20 Keywords für: {product}\n"
                "JSON Liste: {{keyword, search_intent, competition, monthly_searches_estimate}}",
                max_tokens=800,
            )
            return {"ok": True, "keywords": keywords}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Automation Agent ──────────────────────────────────────────────────────────

class AutomationAgent(BaseAgent):
    name = "automation"
    description = "Workflows · Trigger · Zapier-Style · Scheduled Tasks · Self-Healing"
    capabilities = ["create_workflow", "list_workflows", "run_workflow", "optimize_automation", "status"]

    def __init__(self):
        super().__init__()
        self._workflows: List[Dict] = []
        self._wf_file = DATA_DIR / "workflows.json"
        if self._wf_file.exists():
            try:
                self._workflows = json.loads(self._wf_file.read_text())
            except Exception:
                self._workflows = []

    def _save_workflows(self):
        self._wf_file.write_text(json.dumps(self._workflows, ensure_ascii=False, indent=2))

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Automation Task: {task}")

        if task == "status":
            return {
                "ok": True,
                "workflows_count": len(self._workflows),
                "active": sum(1 for w in self._workflows if w.get("active")),
                "workflows": self._workflows[:5],
            }

        if task == "create_workflow":
            wf = {
                "id": str(uuid.uuid4())[:8],
                "name": params.get("name", "Neuer Workflow"),
                "trigger": params.get("trigger", "manual"),
                "trigger_value": params.get("trigger_value", ""),
                "actions": params.get("actions", []),
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_run": None,
                "run_count": 0,
            }
            self._workflows.append(wf)
            self._save_workflows()
            return {"ok": True, "workflow": wf}

        if task == "list_workflows":
            return {"ok": True, "workflows": self._workflows}

        if task == "optimize_automation":
            suggestions = await self._ask_claude(
                "Du bist ein Business Process Automation Experte.",
                "Schlage 5 konkrete Automatisierungen für einen Shopify E-Commerce vor.\n"
                "JSON: Liste von {{name, trigger, actions, time_saved_per_week_hours, impact}}",
                max_tokens=800,
            )
            return {"ok": True, "suggestions": suggestions}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Finance Agent ─────────────────────────────────────────────────────────────

class FinanceAgent(BaseAgent):
    name = "finance"
    description = "Revenue · P&L · Stripe · Ausgaben · Cashflow · ROI"
    capabilities = ["revenue_report", "cashflow", "roi_analysis", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Finance Task: {task}")

        if task in ("status", "revenue_report"):
            try:
                from modules.shopify_revenue_engine import get_revenue_summary
                rev = await get_revenue_summary()
                return {"ok": True, "revenue": rev}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        if task == "roi_analysis":
            ad_spend = float(params.get("ad_spend", 0))
            revenue = float(params.get("revenue", 0))
            cogs = float(params.get("cogs", 0))
            profit = revenue - ad_spend - cogs
            roi = (profit / ad_spend * 100) if ad_spend > 0 else 0
            roas = (revenue / ad_spend) if ad_spend > 0 else 0
            analysis = await self._ask_claude(
                "Du bist ein E-Commerce Finance Analyst.",
                f"Analysiere: Werbeausgaben €{ad_spend}, Umsatz €{revenue}, COGS €{cogs}\n"
                f"Profit: €{profit:.2f}, ROI: {roi:.1f}%, ROAS: {roas:.2f}x\n"
                "Ist das gut? Was verbessern? JSON: {{assessment, recommendations, target_roas, break_even}}",
            )
            return {
                "ok": True,
                "profit": round(profit, 2),
                "roi_pct": round(roi, 1),
                "roas": round(roas, 2),
                "analysis": analysis,
            }

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Trend Agent ───────────────────────────────────────────────────────────────

class TrendAgent(BaseAgent):
    name = "trend"
    description = "Markttrends · TikTok Trends · Winning Niches · Seasonality"
    capabilities = ["hot_niches", "seasonal_trends", "tiktok_trends", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Trend Task: {task}")

        if task == "status":
            return {"ok": True, "last_trends": self.recall("trends", 1)}

        if task == "hot_niches":
            niches = await self._ask_claude(
                "Du bist ein E-Commerce Trend Analyst mit Zugriff auf aktuelle Marktdaten.",
                f"Welche 5 E-Commerce Nischen haben gerade (Juni 2026) das höchste Wachstum?\n"
                "JSON: Liste von {{niche, growth_trend, avg_margin, competition_level, why_hot, example_products}}",
                max_tokens=1000,
            )
            self.remember("trends", niches)
            return {"ok": True, "hot_niches": niches}

        if task == "seasonal_trends":
            month = params.get("month", datetime.now().strftime("%B"))
            trends = await self._ask_claude(
                "Du bist ein saisonaler E-Commerce Experte.",
                f"Was sind die Top-Trends und Bestseller im {month}?\n"
                "JSON: {{top_categories, trending_products, events_this_month, ad_recommendations}}",
                max_tokens=800,
            )
            return {"ok": True, "seasonal": trends}

        if task == "tiktok_trends":
            trends = await self._ask_claude(
                "Du bist ein TikTok E-Commerce Trend Analyst.",
                "Was sind aktuelle TikTok Shop Trends die gut verkaufen?\n"
                "JSON Liste: {{product, why_viral, hashtags, target_demo, avg_price}}",
                max_tokens=800,
            )
            return {"ok": True, "tiktok_trends": trends}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Security Agent ────────────────────────────────────────────────────────────

class SecurityAgent(BaseAgent):
    name = "security"
    description = "API Keys · OAuth · Audit Logs · Threat Detection · Backup"
    capabilities = ["audit", "check_keys", "security_report", "status"]

    async def execute(self, task: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        self.info(f"Security Task: {task}")

        if task == "status":
            return {"ok": True, "last_audit": self.recall("audit", 1)}

        if task == "check_keys":
            required = [
                "ANTHROPIC_API_KEY", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN",
                "STRIPE_SECRET_KEY", "SUPABASE_URL", "TELEGRAM_BOT_TOKEN",
            ]
            status = {}
            for key in required:
                val = os.getenv(key, "")
                status[key] = {
                    "set": bool(val),
                    "length": len(val) if val else 0,
                    "preview": val[:6] + "…" if len(val) > 6 else "FEHLT",
                }
            missing = [k for k, v in status.items() if not v["set"]]
            return {
                "ok": len(missing) == 0,
                "keys_status": status,
                "missing": missing,
                "score": round((len(required) - len(missing)) / len(required) * 100),
            }

        if task == "audit":
            result = await self.execute("check_keys")
            recommendations = await self._ask_claude(
                "Du bist ein API Security Experte.",
                f"Security Audit Ergebnis: {json.dumps(result, indent=2)[:500]}\n"
                "Gib 5 Sicherheitsempfehlungen. JSON Liste. Auf Deutsch.",
                max_tokens=500,
            )
            self.remember("audit", {"score": result.get("score"), "ts": datetime.now().isoformat()})
            return {**result, "recommendations": recommendations}

        return {"ok": False, "error": f"Unbekannter Task: {task}"}


# ── Agent Registry ────────────────────────────────────────────────────────────

_agents: Dict[str, BaseAgent] = {
    "ceo":        CEOAgent(),
    "shopify":    ShopifyAgent(),
    "marketing":  MarketingAgent(),
    "coding":     CodingAgent(),
    "design":     DesignAgent(),
    "research":   ResearchAgent(),
    "automation": AutomationAgent(),
    "finance":    FinanceAgent(),
    "trend":      TrendAgent(),
    "security":   SecurityAgent(),
}


def _get_agent(name: str) -> Optional[BaseAgent]:
    return _agents.get(name)


async def get_all_status() -> Dict:
    """Status aller Agenten parallel abrufen."""
    results = {}
    tasks = {name: asyncio.create_task(agent.execute("status")) for name, agent in _agents.items()}
    for name, task in tasks.items():
        try:
            results[name] = await task
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}
    return results


async def run_agent(agent_name: str, task: str, params: Optional[Dict] = None) -> Dict:
    """Einen Agenten ausführen."""
    agent = _get_agent(agent_name)
    if not agent:
        return {"ok": False, "error": f"Agent '{agent_name}' nicht gefunden. Verfügbar: {list(_agents.keys())}"}
    return await agent.execute(task, params)


async def get_all_logs(limit: int = 50) -> List[Dict]:
    """Logs aller Agenten zusammenführen."""
    all_logs = []
    for agent in _agents.values():
        all_logs.extend(agent._logs)
    all_logs.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return all_logs[:limit]
