#!/usr/bin/env python3
"""
BrutusClone — Leichtgewichtiger autonomer Agent für alle Revenue-Module.
Importierbar mit: from modules.brutus_clone import BrutusClone; bc = BrutusClone(__name__)

Jedes Modul das BrutusClone importiert:
  - Kann automatisch Content feuern (fire)
  - Hat self-fix Capability
  - Loggt Ergebnisse nach Supabase
  - Kann sich bei Fehlern selbst heilen
"""
from __future__ import annotations
import os
import asyncio, logging, os, time
from typing import Any

log = logging.getLogger("BrutusClone")

_TELEGRAM_TOKEN   = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")  # never hardcode tokens — run scripts/api_precheck.py first
_TELEGRAM_CHANNEL = lambda: os.getenv("TELEGRAM_CHANNEL_ID", "")   # marketing → channel
_TELEGRAM_CHAT    = lambda: _TELEGRAM_CHANNEL() or ""               # no private spam


class BrutusClone:
    """Mini-BrutusCore für schnelle Integration in jedes Modul."""

    def __init__(self, module_name: str):
        self.name = module_name
        self._errors: list[str] = []
        self._success_count = 0

    async def fire(self, title: str, content: str, link: str = "", urgent: bool = False) -> dict:
        """Feuert Content auf allen verfügbaren Kanälen."""
        results = {}

        # 1. Telegram (immer verfügbar)
        if _TELEGRAM_TOKEN():
            try:
                import aiohttp
                msg = f"{'🔥' if urgent else '📢'} <b>{title}</b>\n\n{content}"
                if link:
                    msg += f"\n\n🔗 {link}"
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                    async with s.post(
                        f"https://api.telegram.org/bot{_TELEGRAM_TOKEN()}/sendMessage",
                        json={"chat_id": _TELEGRAM_CHAT(), "text": msg, "parse_mode": "HTML",
                              "disable_web_page_preview": True}
                    ) as r:
                        results["telegram"] = "ok" if r.status == 200 else f"error:{r.status}"
                        self._success_count += 1
            except Exception as e:
                results["telegram"] = f"error:{e}"
                self._errors.append(str(e))

        # 2. OpenClaw AI-Content generieren wenn kein eigener Content
        if not content:
            try:
                from modules.open_claw import claw_generate_content
                result = await claw_generate_content(title, "post")
                content = result.get("text", content)
            except Exception:
                pass

        # 3. AI-Content generieren und in Shopify Blog posten (wenn verfügbar)
        shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        shopify_shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if shopify_token and shopify_shop and content:
            try:
                import aiohttp
                html = f"<h2>{title}</h2><p>{content}</p>"
                if link:
                    html += f'<p><a href="{link}">Mehr erfahren →</a></p>'
                ver = os.getenv("SHOPIFY_API_VERSION", "2026-04")
                blog_id = os.getenv("SHOPIFY_BLOG_ID", "127011258755")
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        f"https://{shopify_shop}/admin/api/{ver}/blogs/{blog_id}/articles.json",
                        headers={"X-Shopify-Access-Token": shopify_token, "Content-Type": "application/json"},
                        json={"article": {"title": title, "body_html": html, "published": True}}
                    ) as r:
                        results["shopify_blog"] = "ok" if r.status in (200,201) else f"error:{r.status}"
            except Exception as e:
                results["shopify_blog"] = f"error:{e}"

        # 3. Logg nach Supabase
        await self._log_to_supabase(title, results)

        log.info("BrutusClone[%s] fire: %s", self.name, results)
        return results

    async def self_fix(self) -> dict:
        """Prüft dieses Modul und repariert was möglich ist."""
        checks = {"module": self.name, "errors": self._errors, "success_count": self._success_count, "fixed": []}

        # Checke Telegram
        tok = _TELEGRAM_TOKEN()
        if not tok:
            log.warning("[%s] TELEGRAM_BOT_TOKEN fehlt!", self.name)
            checks["errors"].append("TELEGRAM_BOT_TOKEN missing")
        else:
            checks["fixed"].append("telegram_token_present")

        # Checke AI (OpenClaw = Ollama als primärer kostenloser Provider)
        try:
            from modules.open_claw import is_online
            ollama_ok = await is_online()
        except Exception:
            ollama_ok = False
        cloud_ai = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or
                        os.getenv("OPENROUTER_API_KEY") or os.getenv("GROQ_API_KEY"))
        if ollama_ok:
            checks["fixed"].append("openclaw_ollama_online")
        elif cloud_ai:
            checks["fixed"].append("cloud_ai_provider_present")
        else:
            checks["errors"].append("no_ai_provider_available")

        self._errors = []  # Reset nach Check
        return checks

    async def _log_to_supabase(self, title: str, results: dict) -> None:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_key:
            return
        try:
            import aiohttp, json
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                await s.post(
                    f"{supabase_url}/rest/v1/agent_execution_log",
                    headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}",
                             "Content-Type": "application/json", "Prefer": "return=minimal"},
                    json={"agent_role": f"brutus_clone_{self.name}", "action": "fire",
                          "input": title, "output": json.dumps(results), "status": "completed"}
                )
        except Exception:
            pass

    def sync_fire(self, title: str, content: str, link: str = "") -> dict:
        """Synchrone Variante für nicht-async Code."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return {}
            return loop.run_until_complete(self.fire(title, content, link))
        except Exception:
            return asyncio.run(self.fire(title, content, link))
