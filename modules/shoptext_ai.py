#!/usr/bin/env python3
"""
ShopText.ai — KI-Produkttexte für deutsche Shopify-Händler
Generiert SEO-optimierte Texte via Claude API, Stripe-Checkout für Abo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import base64
from pathlib import Path

log = logging.getLogger("shoptext")

DB_PATH = Path(__file__).parent.parent / "data" / "shoptext.db"
ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
STRIPE_API_BASE = "https://api.stripe.com/v1"

FREE_LIMIT = 3  # free trial generations per identifier


# ── Database ────────────────────────────────────────────────────────────────

def _init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage (
            identifier TEXT PRIMARY KEY,
            plan        TEXT    DEFAULT 'free',
            used        INTEGER DEFAULT 0,
            stripe_sub  TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS generations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier   TEXT,
            product_name TEXT,
            keywords     TEXT,
            result_json  TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def get_usage(identifier: str) -> dict:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT plan, used FROM usage WHERE identifier=?", (identifier,)
    ).fetchone()
    conn.close()
    if not row:
        return {"plan": "free", "used": 0, "can_generate": True, "remaining": FREE_LIMIT}
    plan, used = row
    if plan == "free":
        can = used < FREE_LIMIT
        return {"plan": "free", "used": used, "can_generate": can, "remaining": max(0, FREE_LIMIT - used)}
    return {"plan": plan, "used": used, "can_generate": True, "remaining": -1}


def record_generation(identifier: str, product_name: str, keywords: str, result: dict):
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO generations (identifier, product_name, keywords, result_json) VALUES (?,?,?,?)",
        (identifier, product_name, keywords, json.dumps(result, ensure_ascii=False))
    )
    conn.execute("""
        INSERT INTO usage (identifier, used) VALUES (?, 1)
        ON CONFLICT(identifier) DO UPDATE SET used = used + 1, updated_at = datetime('now')
    """, (identifier,))
    conn.commit()
    conn.close()


def activate_plan(identifier: str, plan: str, stripe_sub: str = ""):
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO usage (identifier, plan, stripe_sub) VALUES (?, ?, ?)
        ON CONFLICT(identifier) DO UPDATE SET
            plan = ?, stripe_sub = ?, updated_at = datetime('now')
    """, (identifier, plan, stripe_sub, plan, stripe_sub))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    total_gen = conn.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
    paid_users = conn.execute("SELECT COUNT(*) FROM usage WHERE plan != 'free'").fetchone()[0]
    free_users = conn.execute("SELECT COUNT(*) FROM usage WHERE plan = 'free'").fetchone()[0]
    conn.close()
    return {"total_generations": total_gen, "paid_users": paid_users, "free_users": free_users}


# ── Stripe ───────────────────────────────────────────────────────────────────

def _stripe(method: str, path: str, data: dict | None = None) -> dict:
    key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY", "")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY fehlt")
    token = base64.b64encode(f"{key}:".encode()).decode()
    body = urllib.parse.urlencode(data or {}, doseq=True).encode() if data else None
    req = urllib.request.Request(f"{STRIPE_API_BASE}{path}", data=body, method=method)
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Stripe-Version", "2024-12-18.acacia")
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def create_checkout_session(plan: str, email: str, base_url: str) -> str:
    """Returns Stripe Checkout URL."""
    # Use existing price IDs — Starter plan for ShopText
    price_map = {
        "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
        "pro":     os.getenv("STRIPE_PRICE_PRO", ""),
    }
    price_id = price_map.get(plan, price_map["starter"])
    if not price_id:
        raise RuntimeError(f"Kein Stripe Price ID für Plan: {plan}")

    params: dict = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{base_url}/shoptext/success?session_id={{CHECKOUT_SESSION_ID}}&plan={plan}",
        "cancel_url": f"{base_url}/shoptext",
        "metadata[app]": "shoptext",
        "metadata[plan]": plan,
    }
    if email:
        params["customer_email"] = email

    session = _stripe("POST", "/checkout/sessions", params)
    return session["url"]


# ── AI Text Generation ───────────────────────────────────────────────────────

def _build_prompt(product_name: str, ptype_hint: str, kw: str, tone_desc: str) -> str:
    return f"""Du bist ein erfahrener E-Commerce-Texter für deutsche Shopify-Händler.

Erstelle SEO-optimierte Produkttexte für:
Produktname: {product_name}{ptype_hint}
Keywords: {kw}
Tonalität: {tone_desc}

Antworte NUR mit diesem JSON-Objekt, ohne Erklärungen:
{{
  "title": "Produkttitel (max 70 Zeichen, Hauptkeyword am Anfang)",
  "description": "Produktbeschreibung (200-280 Wörter, überzeugend, kundenorientiert, mit 2-3 kurzen Absätzen. Vorteile klar herausstellen. Natürliche Keyword-Integration. Kein HTML.)",
  "meta_title": "SEO Meta-Title (max 58 Zeichen)",
  "meta_description": "SEO Meta-Description (max 155 Zeichen, mit Call-to-Action wie 'Jetzt kaufen' oder 'Kostenloser Versand')",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "bullet_points": ["⚡ Schlüsselvorteil 1", "✅ Schlüsselvorteil 2", "🎯 Schlüsselvorteil 3", "📦 Schlüsselvorteil 4", "💡 Schlüsselvorteil 5"]
}}"""


def _parse_ai_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("Kein JSON in KI-Antwort")


async def _try_anthropic(prompt: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("no key")
    payload = json.dumps({
        "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{ANTHROPIC_API_BASE}/messages", data=payload, method="POST")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    loop = asyncio.get_event_loop()
    def _call():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        resp = await loop.run_in_executor(None, _call)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Anthropic {e.code}: {e.read().decode()[:200]}")
    return _parse_ai_response(resp["content"][0]["text"])


async def _try_openai(prompt: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("no key")
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    loop = asyncio.get_event_loop()
    def _call():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        resp = await loop.run_in_executor(None, _call)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI {e.code}: {e.read().decode()[:200]}")
    return _parse_ai_response(resp["choices"][0]["message"]["content"])


async def _try_deepseek(prompt: str) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("no key")
    payload = json.dumps({
        "model": "deepseek-chat",
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    loop = asyncio.get_event_loop()
    def _call():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        resp = await loop.run_in_executor(None, _call)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DeepSeek {e.code}: {e.read().decode()[:200]}")
    return _parse_ai_response(resp["choices"][0]["message"]["content"])


async def _try_groq(prompt: str) -> dict:
    """Groq Free Tier: 14.400 Anfragen/Tag kostenlos."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("no key")
    payload = json.dumps({
        "model": "llama-3.1-8b-instant",
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": "Du antwortest immer mit einem validen JSON-Objekt ohne Erklärungen."},
            {"role": "user", "content": prompt},
        ],
    }).encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    loop = asyncio.get_event_loop()
    def _call():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        resp = await loop.run_in_executor(None, _call)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Groq {e.code}: {e.read().decode()[:200]}")
    return _parse_ai_response(resp["choices"][0]["message"]["content"])


async def _try_openrouter_free(prompt: str) -> dict:
    """OpenRouter Free Models — mehrere Modelle versuchen."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("no key")
    free_models = [
        "google/gemma-2-9b-it:free",
        "mistralai/mistral-7b-instruct:free",
        "microsoft/phi-3-mini-128k-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
    ]
    last_err: Exception = RuntimeError("no models tried")
    for model in free_models:
        payload = json.dumps({
            "model": model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("HTTP-Referer", "https://supermegabot-production.up.railway.app")
        loop = asyncio.get_event_loop()
        def _make_call(p=payload, r=req):
            with urllib.request.urlopen(r, timeout=45) as resp:
                return json.loads(resp.read())
        try:
            resp = await loop.run_in_executor(None, _make_call)
            content = resp["choices"][0]["message"]["content"]
            return _parse_ai_response(content)
        except Exception as e:
            log.warning("OpenRouter model %s failed: %s", model, str(e)[:80])
            last_err = e
            continue
    raise RuntimeError(f"Alle OpenRouter Free Models fehlgeschlagen: {last_err}")


def _template_fallback(product_name: str, keywords: str, product_type: str, tone: str) -> dict:
    """Template-basierter Generator — funktioniert ohne AI-Credits, immer verfügbar."""
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
    kw_str = ", ".join(kw_list[:3]) if kw_list else product_name
    ptype = product_type or "Produkt"

    tone_intros = {
        "modern": "Entdecke die neue Generation",
        "luxus": "Erlebe kompromisslose Qualität mit",
        "freundlich": "Wir freuen uns, dir vorzustellen:",
        "professionell": "Professionelle Lösung:",
    }
    intro = tone_intros.get(tone, "Entdecke")

    tags = kw_list[:5] if kw_list else [product_name.lower(), ptype.lower(), "shop", "qualität", "kaufen"]

    description = (
        f"{intro} {product_name} — das {ptype} das deinen Alltag vereinfacht.\n\n"
        f"Mit {product_name} bekommst du ein Produkt, das höchste Qualitätsstandards erfüllt "
        f"und speziell für anspruchsvolle Kunden entwickelt wurde. "
        f"{('Highlights: ' + kw_str + '.') if kw_str else ''}\n\n"
        f"Überzeugende Eigenschaften machen {product_name} zur ersten Wahl für alle, "
        f"die Wert auf Zuverlässigkeit und Leistung legen. "
        f"Bestelle jetzt und profitiere von schnellem Versand und erstklassigem Kundenservice."
    )

    return {
        "title": f"{product_name[:60]}",
        "description": description,
        "meta_title": f"{product_name[:55]} kaufen",
        "meta_description": f"{product_name} ✓ Jetzt bestellen ✓ Schneller Versand ✓ Top Qualität | {kw_str[:50]}",
        "tags": tags[:5],
        "bullet_points": [
            f"⚡ {product_name} — erstklassige Qualität",
            f"✅ {kw_list[0] if kw_list else 'Hochwertig'} — für anspruchsvolle Kunden",
            f"🎯 Schneller Versand aus Deutschland",
            f"📦 30 Tage Rückgaberecht",
            f"💡 Kundensupport auf Deutsch",
        ],
        "_provider": "template",
    }


async def generate_product_text(
    product_name: str,
    keywords: str = "",
    product_type: str = "",
    tone: str = "professionell",
) -> dict:
    """Generate SEO-optimized German product text — Anthropic → OpenAI → OpenRouter fallback."""
    kw = ", ".join(k.strip() for k in keywords.split(",") if k.strip()) if keywords else "keine angegeben"
    ptype_hint = f" (Produktkategorie: {product_type})" if product_type else ""
    tone_map = {
        "professionell": "seriös und vertrauenswürdig",
        "modern": "modern, frisch und jugendlich",
        "luxus": "exklusiv, hochwertig und premium",
        "freundlich": "herzlich, nahbar und einladend",
    }
    tone_desc = tone_map.get(tone, "professionell und klar")
    prompt = _build_prompt(product_name, ptype_hint, kw, tone_desc)

    providers = [
        ("DeepSeek",       _try_deepseek),
        ("OpenAI",         _try_openai),
        ("Groq",           _try_groq),
        ("OpenRouter",     _try_openrouter_free),
        ("Anthropic",      _try_anthropic),
    ]
    for name, fn in providers:
        try:
            result = await fn(prompt)
            log.info("ShopText generated via %s", name)
            return result
        except Exception as e:
            log.warning("Provider %s failed: %s — trying next", name, str(e)[:120])

    # Template-Fallback — immer verfügbar, kein API-Key nötig
    log.warning("Alle KI-Provider fehlgeschlagen — Template-Fallback aktiv")
    return _template_fallback(product_name, keywords, product_type, tone)
