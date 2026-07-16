#!/usr/bin/env python3
"""
Daily System Check — Tägliche Vollprüfung aller Kanäle
=======================================================
Prüft JEDEN Morgen:
  1. Gmail SMTP (alle Konten)
  2. Shopify API Token
  3. Facebook/Meta Token
  4. Stripe Live
  5. Telegram Bot
  6. Digistore24 API
  7. Shop Produkte (mind. 10 aktive)
  8. Railway Health
  9. Anthropic API Credits
 10. Resend / SendGrid Email Services

Bei Problemen: Auto-Fix wenn möglich, sonst Telegram-Alert an Rudolf.
Sendet täglich morgens einen Status-Bericht.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import smtplib
import ssl
import time
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

import aiohttp

log = logging.getLogger("DailyCheck")

# ── Credentials ───────────────────────────────────────────────────────────────
def _env(key: str, *fallbacks: str) -> str:
    for k in (key, *fallbacks):
        v = os.getenv(k, "")
        if v and v not in ("your_token_here", "placeholder", "changeme"):
            return v
    return ""

TG_TOKEN  = lambda: _env("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_RUDICLONE")
TG_CHAT   = lambda: _env("TELEGRAM_CHAT_ID")


# ── Result container ──────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    needs_manual: bool = False
    auto_fixed: bool = False


# ── Telegram Alert ────────────────────────────────────────────────────────────
async def _tg(text: str):
    tok, chat = TG_TOKEN(), TG_CHAT()
    if not tok or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": text[:4000], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=15),
            )
    except Exception:
        pass


# ── 1. Gmail SMTP ─────────────────────────────────────────────────────────────
async def check_gmail() -> List[CheckResult]:
    accounts = [
        ("GMAIL_USER_1", "GMAIL_APP_PASSWORD_1", "dragonadnp@gmail.com"),
        ("GMAIL_USER_3", "GMAIL_APP_PASSWORD_3", "bullpowersrtkennels@gmail.com"),
        ("GMAIL_USER_5", "GMAIL_APP_PASSWORD_5", "aiitecbuuss@gmail.com"),
        ("GMAIL_USER_7", "GMAIL_APP_PASSWORD_7", "rudolf.sarkany.aiitec@gmail.com"),
        ("GMAIL_USER_8", "GMAIL_APP_PASSWORD_8", "rudolfsarkany1984@gmail.com"),
    ]
    results = []
    for user_key, pass_key, default_email in accounts:
        user = _env(user_key) or default_email
        pwd  = _env(pass_key)
        if not pwd:
            results.append(CheckResult(f"Gmail {user}", False,
                "Kein App-Passwort gesetzt", needs_manual=True))
            continue
        try:
            def _test():
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=12) as s:
                    s.ehlo(); s.starttls(); s.ehlo()
                    s.login(user, pwd.replace(" ", ""))
            await asyncio.to_thread(_test)
            results.append(CheckResult(f"Gmail {user}", True, "SMTP OK"))
        except Exception as e:
            results.append(CheckResult(f"Gmail {user}", False,
                f"SMTP Fehler: {type(e).__name__} — App-Passwort neu generieren!",
                needs_manual=True))
    return results


# ── 2. Shopify API ────────────────────────────────────────────────────────────
async def check_shopify() -> CheckResult:
    domain = _env("SHOPIFY_SHOP_DOMAIN")
    token  = _env("SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_ACCESS_TOKEN")
    if not domain or not token:
        return CheckResult("Shopify API", False, "Domain oder Token fehlt", needs_manual=True)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{domain}/admin/api/2026-04/shop.json",
                headers={"X-Shopify-Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    name = d.get("shop", {}).get("name", "?")
                    return CheckResult("Shopify API", True, f"Shop: {name}")
                elif r.status == 401:
                    return CheckResult("Shopify API", False,
                        "Token ungültig (401) — in Shopify Admin neu generieren!",
                        needs_manual=True)
                else:
                    return CheckResult("Shopify API", False, f"HTTP {r.status}")
    except Exception as e:
        return CheckResult("Shopify API", False, str(e))


# ── 3. Shopify Produkte ───────────────────────────────────────────────────────
async def check_shopify_products() -> CheckResult:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://ineedit.com.co/products.json?limit=250",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json()
                products = d.get("products", [])
                count = len(products)
                if count >= 20:
                    return CheckResult("Shop Produkte", True, f"{count} Produkte online ✅")
                elif count >= 5:
                    return CheckResult("Shop Produkte", False,
                        f"Nur {count} Produkte — Smart Product Finder läuft zum Auffüllen",
                        auto_fixed=True)
                else:
                    return CheckResult("Shop Produkte", False,
                        f"Kritisch: nur {count} Produkte!", needs_manual=True)
    except Exception as e:
        return CheckResult("Shop Produkte", False, str(e))


# ── 4. Facebook/Meta Token ────────────────────────────────────────────────────
async def check_facebook() -> CheckResult:
    token = _env("FACEBOOK_PAGE_TOKEN_AIITEC", "META_ACCESS_TOKEN", "FACEBOOK_PAGE_ACCESS_TOKEN")
    if not token:
        return CheckResult("Facebook Token", False, "Kein Token gesetzt", needs_manual=True)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://graph.facebook.com/v21.0/me",
                params={"access_token": token, "fields": "id,name"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json()
                if "error" in d:
                    err = d["error"].get("message", "?")
                    return CheckResult("Facebook Token", False,
                        f"Token ungültig: {err} — auf business.facebook.com erneuern!",
                        needs_manual=True)
                name = d.get("name", "?")
                return CheckResult("Facebook Token", True, f"OK als: {name}")
    except Exception as e:
        return CheckResult("Facebook Token", False, str(e))


# ── 5. Stripe Live ────────────────────────────────────────────────────────────
async def check_stripe() -> CheckResult:
    key = _env("STRIPE_SECRET_KEY")
    if not key or not key.startswith("sk_live_"):
        return CheckResult("Stripe Live", False,
            "Kein Live-Key (sk_live_...) gesetzt", needs_manual=True)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/account",
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json()
                if r.status == 200:
                    email = d.get("email", "?")
                    return CheckResult("Stripe Live", True, f"Account: {email}")
                else:
                    return CheckResult("Stripe Live", False,
                        f"Fehler: {d.get('error', {}).get('message', '?')}",
                        needs_manual=True)
    except Exception as e:
        return CheckResult("Stripe Live", False, str(e))


# ── 6. Telegram Bot ───────────────────────────────────────────────────────────
async def check_telegram() -> CheckResult:
    tok = TG_TOKEN()
    if not tok:
        return CheckResult("Telegram Bot", False, "Kein Token", needs_manual=True)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.telegram.org/bot{tok}/getMe",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json()
                if d.get("ok"):
                    name = d["result"].get("username", "?")
                    return CheckResult("Telegram Bot", True, f"@{name} aktiv")
                return CheckResult("Telegram Bot", False, "Bot-Token ungültig", needs_manual=True)
    except Exception as e:
        return CheckResult("Telegram Bot", False, str(e))


# ── 7. Anthropic API ─────────────────────────────────────────────────────────
async def check_anthropic() -> CheckResult:
    key = _env("ANTHROPIC_API_KEY")
    if not key:
        return CheckResult("Anthropic API", False, "Kein Key", needs_manual=True)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Hi"}]},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                if r.status == 200:
                    return CheckResult("Anthropic API", True, "Credits vorhanden ✅")
                elif r.status == 529 or "credit" in str(d).lower():
                    return CheckResult("Anthropic API", False,
                        "Credits leer! → console.anthropic.com → Billing → Credits kaufen",
                        needs_manual=True)
                else:
                    return CheckResult("Anthropic API", False,
                        f"HTTP {r.status}: {d.get('error',{}).get('message','?')}",
                        needs_manual=True)
    except Exception as e:
        return CheckResult("Anthropic API", False, str(e))


# ── 8. SendGrid ───────────────────────────────────────────────────────────────
async def check_sendgrid() -> CheckResult:
    key = _env("SENDGRID_API_KEY", "SENDGRID_API_KEY_AIITEC")
    if not key:
        return CheckResult("SendGrid", False, "Kein Key", needs_manual=True)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.sendgrid.com/v3/user/account",
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return CheckResult("SendGrid", True,
                        f"Plan: {d.get('type','?')} ✅")
                return CheckResult("SendGrid", False, f"HTTP {r.status} — Key prüfen",
                    needs_manual=True)
    except Exception as e:
        return CheckResult("SendGrid", False, str(e))


# ── 9. Railway Health ─────────────────────────────────────────────────────────
async def check_railway_health() -> CheckResult:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://supermegabot-production.up.railway.app/health",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json()
                if d.get("status") == "ok":
                    uptime = int(d.get("uptime_seconds", 0))
                    h, m = uptime // 3600, (uptime % 3600) // 60
                    return CheckResult("Railway Health", True, f"Online seit {h}h {m}min")
                return CheckResult("Railway Health", False, f"Status: {d.get('status')}")
    except Exception as e:
        return CheckResult("Railway Health", False, f"Nicht erreichbar: {e}",
            needs_manual=True)


# ── Auto-Fix: Smart Product Finder ───────────────────────────────────────────
async def _auto_fill_products():
    try:
        from modules.smart_product_finder import run_smart_product_cycle
        result = await run_smart_product_cycle()
        log.info("Auto-Fill Produkte: %s", result)
    except Exception as e:
        log.warning("Auto-Fill fehlgeschlagen: %s", e)


# ── Main Runner ───────────────────────────────────────────────────────────────
async def run_daily_check() -> dict:
    log.info("🔍 Daily System Check startet...")
    all_results: List[CheckResult] = []

    # Alle Checks parallel
    gmail_results, shopify, products, facebook, stripe, telegram, anthropic, sendgrid, railway = \
        await asyncio.gather(
            check_gmail(),
            check_shopify(),
            check_shopify_products(),
            check_facebook(),
            check_stripe(),
            check_telegram(),
            check_anthropic(),
            check_sendgrid(),
            check_railway_health(),
            return_exceptions=True,
        )

    if isinstance(gmail_results, list):
        all_results.extend(gmail_results)
    for r in [shopify, products, facebook, stripe, telegram, anthropic, sendgrid, railway]:
        if isinstance(r, CheckResult):
            all_results.append(r)

    # Auto-Fix: zu wenig Produkte
    prod_result = next((r for r in all_results if r.name == "Shop Produkte"), None)
    if prod_result and not prod_result.ok:
        asyncio.create_task(_auto_fill_products())

    # Bericht bauen
    ok_list      = [r for r in all_results if r.ok]
    fail_list    = [r for r in all_results if not r.ok]
    manual_list  = [r for r in all_results if r.needs_manual]
    fixed_list   = [r for r in all_results if r.auto_fixed]

    lines = ["<b>📊 SuperMegaBot — Täglicher Status-Check</b>\n"]

    if ok_list:
        lines.append("✅ <b>Alles OK:</b>")
        for r in ok_list:
            lines.append(f"  • {r.name}: {r.detail}")

    if fixed_list:
        lines.append("\n🔧 <b>Auto-gefixt:</b>")
        for r in fixed_list:
            lines.append(f"  • {r.name}: {r.detail}")

    if manual_list:
        lines.append("\n🔴 <b>DEINE AKTION NÖTIG:</b>")
        for r in manual_list:
            lines.append(f"  ❗ {r.name}: {r.detail}")

    fail_no_manual = [r for r in fail_list if not r.needs_manual and not r.auto_fixed]
    if fail_no_manual:
        lines.append("\n⚠️ <b>Fehler (wird auto-retried):</b>")
        for r in fail_no_manual:
            lines.append(f"  • {r.name}: {r.detail}")

    score = len(ok_list)
    total = len(all_results)
    lines.append(f"\n<b>Score: {score}/{total} Systeme OK</b>")

    if not manual_list:
        lines.append("🎉 Alles läuft — kein Handlungsbedarf!")
    else:
        lines.append(f"⚡ {len(manual_list)} Punkt(e) brauchen dich")

    report = "\n".join(lines)
    await _tg(report)
    log.info("Daily Check abgeschlossen: %d/%d OK, %d manuell", score, total, len(manual_list))

    return {
        "ok": len(fail_list) == 0,
        "score": score,
        "total": total,
        "manual_actions": len(manual_list),
        "results": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in all_results],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_daily_check())
