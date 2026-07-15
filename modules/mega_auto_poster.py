#!/usr/bin/env python3
"""
MegaAutoPoster — vollautomatisches Multi-Channel Posting-System.
Posts content simultaneously to: Facebook (2 pages), Instagram, Shopify Blog,
Klaviyo Campaign, Mailchimp Campaign, SendGrid Email, Telegram, Twitter/X.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("MegaAutoPoster")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "auto_poster"))
HASH_FILE  = DATA_DIR / "posted_hashes.json"
IG_PIXEL   = "https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png"
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2026-04")

# ── Env vars ──────────────────────────────────────────────────────────────────
FB_TOKEN_IWIN   = os.getenv("FACEBOOK_PAGE_TOKEN_IWIN", "")
FB_PAGE_IWIN    = os.getenv("FACEBOOK_PAGE_ID_IWIN", "1135864516276500")
FB_TOKEN_AIITEC = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", "")
FB_PAGE_AIITEC  = os.getenv("FACEBOOK_PAGE_ID_AIITEC", "1016738738178786")
IG_ACCOUNT_ID   = os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST    = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
MC_KEY          = os.getenv("MAILCHIMP_API_KEY", "")
MC_LIST         = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
MC_SERVER       = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SENDGRID_KEY    = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM   = os.getenv("SENDGRID_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
SENDGRID_NAME   = os.getenv("SENDGRID_FROM_NAME", "BullPower Hub")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL     = os.getenv("TELEGRAM_CHANNEL_ID", "")   # marketing → public channel
_TG_ALERT       = os.getenv("TELEGRAM_CHAT_ID", "")       # system alerts → private chat
TG_CHAT         = _TG_CHANNEL or ""                        # no private spam if channel not set
TWITTER_KEY     = os.getenv("TWITTER_API_KEY", "")
TWITTER_SECRET  = os.getenv("TWITTER_API_SECRET", "")
TWITTER_TOKEN   = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_TOKEN_S = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
LINKEDIN_TOKEN  = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
_ln_urn         = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
LINKEDIN_URN    = _ln_urn if _ln_urn.startswith("urn:li:") else f"urn:li:person:{_ln_urn}"


# ── Deduplication ─────────────────────────────────────────────────────────────

def _content_hash(content: dict) -> str:
    raw = (content.get("title", "") + content.get("body", ""))[:200]
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_hashes() -> set:
    try:
        return set(json.loads(HASH_FILE.read_text()))
    except Exception:
        return set()


def _save_hash(h: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hashes = _load_hashes()
    hashes.add(h)
    HASH_FILE.write_text(json.dumps(sorted(hashes)[-500:]))  # keep last 500


# ── Content Generator ─────────────────────────────────────────────────────────

async def generate_product_post(product_name: str, price: float, url: str) -> dict:
    """AI generiert Post-Content für ein Produkt via Fallback-Chain."""
    try:
        from modules.ai_client import ai_complete
        prompt = f"""Erstelle einen viralen Social-Media-Post auf Deutsch für dieses Produkt:
Produkt: {product_name}
Preis: €{price:.2f}
URL: {url}

Antworte NUR mit JSON:
{{
  "title": "kurze einprägsame Überschrift (max 60 Zeichen)",
  "body": "überzeugender Post-Text (150-200 Zeichen, mit Emojis)",
  "email_subject": "Email-Betreff (max 50 Zeichen)",
  "email_body": "Email-Text (300-400 Zeichen, mit CTA)",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5"],
  "cta": "Jetzt kaufen für €{price:.2f}",
  "blog_title": "SEO-optimierter Blog-Artikel-Titel",
  "blog_content": "Blog-Artikel-Intro (200-300 Wörter, SEO-optimiert, mit Keywords)"
}}"""
        raw = await ai_complete(prompt, max_tokens=800)
        if not raw:
            return _fallback_content(product_name, price, url)
        start, end = raw.find("{"), raw.rfind("}") + 1
        result = json.loads(raw[start:end]) if start >= 0 else {}
        if not result.get("title") or not result.get("body"):
            return _fallback_content(product_name, price, url)
        result.setdefault("image_url", IG_PIXEL)
        result.setdefault("url", url)
        return result
    except Exception as exc:
        log.warning("Content generation failed: %s", exc)
        return _fallback_content(product_name, price, url)


_FALLBACK_ROTATION = [
    ("🏠 Smart Home Deal",
     "🏠 {n} — Smarter wohnen ab €{p}. Einfache Installation, sofort nutzbar. 👉 {u}",
     "Entdecke {n}: Dein Einstieg in Smart Home Technologie. Preis: nur €{p}."),
    ("⚡ Tech-Highlight",
     "⚡ {n} für €{p} — Modernste Technologie für dein Zuhause. Jetzt bestellen: {u}",
     "{n} — Hochwertige Smart-Tech für jeden Haushalt. Jetzt für €{p} verfügbar."),
    ("🔋 Energie sparen",
     "🔋 Mit {n} Strom sparen und smart wohnen. Ab €{p}. Details: {u}",
     "Energie effizienter nutzen mit {n}. Jetzt für €{p} erhältlich."),
    ("🛡️ Qualitätsprodukt",
     "🛡️ {n} — Geprüfte Qualität, faire Preise. €{p}. Direkt bestellen: {u}",
     "{n}: Qualität die überzeugt. Für nur €{p} jetzt in deinem Smart Home einsetzen."),
    ("📦 Neue Kollektion",
     "📦 Neu bei iNeedit: {n} für €{p}. Smart leben, einfach bestellen. 🔗 {u}",
     "Neu im Sortiment: {n}. Smart Home Technologie zum Preis von €{p}."),
]


def _fallback_content(name: str, price: float, url: str) -> dict:
    import time
    idx = int(time.time() // 1800) % len(_FALLBACK_ROTATION)
    ttl, body_tmpl, email_tmpl = _FALLBACK_ROTATION[idx]
    body  = body_tmpl.format(n=name, p=f"{price:.2f}", u=url)
    email = email_tmpl.format(n=name, p=f"{price:.2f}", u=url)
    return {
        "title":         f"{ttl}: {name}",
        "body":          body,
        "email_subject": f"Neu: {name} für nur €{price:.2f}",
        "email_body":    f"{email}\n\nJetzt bestellen: {url}",
        "hashtags":      ["SmartHome", "Technologie", "Gadgets", "iNeedit", "Haustechnik"],
        "cta":           f"Jetzt für €{price:.2f} kaufen",
        "blog_title":    f"{name} — Testbericht und Kaufratgeber 2026",
        "blog_content":  (
            f"<p><strong>{name}</strong> ist ein hochwertiges Smart-Home-Produkt "
            f"für €{price:.2f}. In diesem Artikel erfährst du alles über Funktionen, "
            f"Installation und Praxiserfahrungen.</p>"
            f"<p><a href='{url}'>➔ Jetzt {name} bestellen</a></p>"
        ),
        "image_url": IG_PIXEL,
        "url":       url,
    }


# ── Channel Poster Functions ───────────────────────────────────────────────────

async def _post_telegram(content: dict) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        from modules.telegram_safe import tg_send
        import aiohttp
        tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:5])
        url  = content.get("url", "").strip()
        text = f"*{content['title']}*\n\n{content['body']}\n\n{tags}"
        if url:
            text += f"\n\n🔗 {url}"
        async with aiohttp.ClientSession() as s:
            return await tg_send(s, text, chat_id=TG_CHAT)
    except Exception as exc:
        log.warning("Telegram post failed: %s", exc)
        return False


async def _post_facebook_page(page_id: str, token: str, content: dict) -> bool:
    """Facebook Post — via Post Gateway (5-Schicht-Prüfung)."""
    tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:5])
    msg = f"{content.get('body','')}\n\n{tags}\n\n{content.get('url', '')}".strip()
    image_url = content.get("image_url", "")
    from modules.post_gateway import safe_post
    result = await safe_post("facebook", msg, image_url=image_url, source_module="mega_auto_poster")
    return result.get("ok", False)


async def _post_instagram(content: dict) -> bool:
    """Instagram Post — via Post Gateway (5-Schicht-Prüfung)."""
    tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:10])
    caption = f"{content.get('body','')}\n\n{tags}"[:2200]
    image_url = content.get("image_url", IG_PIXEL)
    from modules.post_gateway import safe_post
    result = await safe_post("instagram", caption, image_url=image_url, source_module="mega_auto_poster")
    return result.get("ok", False)


async def _post_tiktok(content: dict) -> bool:
    """Post video/photo to TikTok via Content Posting API."""
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        log.warning("TikTok: TIKTOK_ACCESS_TOKEN nicht konfiguriert — Channel wird übersprungen")
        return False
    try:
        import aiohttp
        tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:5])
        caption = f"{content.get('title','')} {tags}"[:150]
        image_url = content.get("image_url", "")
        if not image_url:
            log.debug("TikTok: kein Bild für Post")
            return False
        # TikTok Photo Post API
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://open.tiktokapis.com/v2/post/publish/content/init/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                json={
                    "post_info": {"title": caption, "privacy_level": "PUBLIC_TO_EVERYONE", "disable_duet": False, "disable_comment": False, "disable_stitch": False},
                    "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": [image_url]},
                    "post_mode": "DIRECT_POST",
                    "media_type": "PHOTO",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
                ok = d.get("error", {}).get("code", "error") == "ok"
                if not ok:
                    log.debug("TikTok error: %s", d.get("error", {}))
                return ok
    except Exception as exc:
        log.warning("TikTok post failed: %s", exc)
        return False


async def _post_pinterest(content: dict) -> bool:
    """Create a Pinterest Pin via API v5."""
    token = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    board_id = os.getenv("PINTEREST_BOARD_ID", "")
    if not token or not board_id:
        log.debug("Pinterest: kein Token oder Board ID")
        return False
    try:
        import aiohttp
        tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:10])
        description = f"{content.get('body', '')} {tags}"[:500]
        image_url = content.get("image_url", IG_PIXEL)
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.pinterest.com/v5/pins",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "title": content.get("title", "")[:100],
                    "description": description,
                    "board_id": board_id,
                    "media_source": {"source_type": "image_url", "url": image_url},
                    "link": content.get("url", ""),
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
                return bool(d.get("id"))
    except Exception as exc:
        log.warning("Pinterest post failed: %s", exc)
        return False


async def _get_shopify_blog_id() -> str:
    blog_id = os.getenv("SHOPIFY_BLOG_ID", "")
    if blog_id:
        return blog_id
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return ""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        blogs = d.get("blogs", [])
        return str(blogs[0]["id"]) if blogs else ""
    except Exception as exc:
        log.warning("Shopify blog fetch failed: %s", exc)
        return ""


async def _post_shopify_blog(content: dict) -> bool:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return False
    try:
        import aiohttp
        blog_id = await _get_shopify_blog_id()
        if not blog_id:
            return False
        tags = ", ".join(content.get("hashtags", [])[:8])
        article = {
            "article": {
                "title": content.get("blog_title", content["title"]),
                "body_html": content.get("blog_content", f"<p>{content['body']}</p>"),
                "tags": tags,
                "published": True,
                "image": {"src": content.get("image_url", IG_PIXEL)},
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json=article,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        return bool(d.get("article", {}).get("id"))
    except Exception as exc:
        log.warning("Shopify blog post failed: %s", exc)
        return False


async def _post_klaviyo_campaign(content: dict) -> bool:
    if not KLAVIYO_KEY:
        return False
    try:
        import aiohttp
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
            "revision": "2024-10-15",
            "Content-Type": "application/json",
        }
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        campaign_payload = {
            "data": {
                "type": "campaign",
                "attributes": {
                    "name": f"AutoPost {content['title'][:40]} {now_str[:10]}",
                    "audiences": {"included": [KLAVIYO_LIST]},
                    "send_strategy": {"method": "immediate"},
                    "campaign-messages": {
                        "data": [{
                            "type": "campaign-message",
                            "attributes": {
                                "channel": "email",
                                "label": "AutoPost",
                                "content": {
                                    "subject": content.get("email_subject", content["title"])[:100],
                                    "preview_text": content["body"][:150],
                                    "from_email": SENDGRID_FROM,
                                    "from_label": SENDGRID_NAME,
                                    "reply_to_email": SENDGRID_FROM,
                                },
                            },
                        }]
                    },
                },
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://a.klaviyo.com/api/campaigns/",
                headers=headers, json=campaign_payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
            campaign_id = d.get("data", {}).get("id", "")
            if not campaign_id:
                return False
            # Send campaign — Klaviyo erwartet campaign-id unter relationships, nicht attributes
            async with s.post(
                f"https://a.klaviyo.com/api/campaign-send-jobs/",
                headers=headers,
                json={"data": {"type": "campaign-send-job", "relationships": {"campaign": {"data": {"type": "campaign", "id": campaign_id}}}}},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                send_d = await r.json(content_type=None)
        return bool(send_d.get("data", {}).get("id"))
    except Exception as exc:
        log.warning("Klaviyo campaign failed: %s", exc)
        return False


async def _post_mailchimp_campaign(content: dict) -> bool:
    if not MC_KEY or not MC_LIST:
        return False
    try:
        import aiohttp
        import base64
        auth = base64.b64encode(f"anystring:{MC_KEY}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        base_url = f"https://{MC_SERVER}.api.mailchimp.com/3.0"
        body_html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#333">{content['title']}</h1>
<p style="font-size:16px;line-height:1.6">{content.get('email_body', content['body'])}</p>
<p><a href="{content.get('url','#')}" style="background:#7c6fff;color:white;padding:12px 24px;
text-decoration:none;border-radius:6px">{content.get('cta','Jetzt kaufen')}</a></p>
</body></html>"""
        campaign_data = {
            "type": "regular",
            "recipients": {"list_id": MC_LIST},
            "settings": {
                "subject_line": content.get("email_subject", content["title"])[:150],
                "from_name": SENDGRID_NAME,
                "reply_to": SENDGRID_FROM,
                "from_email": SENDGRID_FROM,
            },
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base_url}/campaigns", headers=headers, json=campaign_data,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json(content_type=None)
            campaign_id = d.get("id", "")
            if not campaign_id:
                return False
            # Set content
            await s.put(
                f"{base_url}/campaigns/{campaign_id}/content",
                headers=headers, json={"html": body_html},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            # Send
            async with s.post(f"{base_url}/campaigns/{campaign_id}/actions/send",
                               headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return r.status in (200, 204)
    except Exception as exc:
        log.warning("Mailchimp campaign failed: %s", exc)
        return False


async def _post_sendgrid(content: dict) -> bool:
    if not SENDGRID_KEY:
        return False
    try:
        import aiohttp
        body_html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#333">{content['title']}</h1>
<p style="font-size:16px;line-height:1.6">{content.get('email_body', content['body'])}</p>
<p><a href="{content.get('url','#')}" style="background:#7c6fff;color:white;padding:12px 24px;
text-decoration:none;border-radius:6px">{content.get('cta','Jetzt kaufen')}</a></p>
</body></html>"""
        payload = {
            "personalizations": [{"to": [{"email": SENDGRID_FROM, "name": SENDGRID_NAME}]}],
            "from": {"email": SENDGRID_FROM, "name": SENDGRID_NAME},
            "subject": content.get("email_subject", content["title"])[:150],
            "content": [{"type": "text/html", "value": body_html}],
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status == 202
    except Exception as exc:
        log.warning("SendGrid post failed: %s", exc)
        return False


def _tw_oauth_header(method: str, url: str) -> str:
    """OAuth 1.0a Authorization header for Twitter API v2 user-context requests."""
    nonce = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    ts = str(int(time.time()))
    oauth_params = {
        "oauth_consumer_key":     TWITTER_KEY,
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        ts,
        "oauth_token":            TWITTER_TOKEN,
        "oauth_version":          "1.0",
    }
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = (urllib.parse.quote(TWITTER_SECRET, safe="") + "&" +
                   urllib.parse.quote(TWITTER_TOKEN_S, safe=""))
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature
    header_parts = ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


async def _post_twitter(content: dict) -> bool:
    """Post tweet via OAuth 1.0a (user-context) — required for POST /2/tweets."""
    if not TWITTER_KEY or not TWITTER_SECRET or not TWITTER_TOKEN or not TWITTER_TOKEN_S:
        if TWITTER_KEY and not TWITTER_TOKEN:
            log.warning("Twitter: TWITTER_ACCESS_TOKEN oder TWITTER_ACCESS_TOKEN_SECRET fehlt — POST /2/tweets benötigt OAuth 1.0a, kein Bearer Token")
        return False
    try:
        import aiohttp
        tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:3])
        tweet = f"{content['body'][:200]}\n{tags}\n{content.get('url','')}".strip()[:280]
        tw_url = "https://api.twitter.com/2/tweets"
        auth = _tw_oauth_header("POST", tw_url)
        async with aiohttp.ClientSession() as s:
            async with s.post(
                tw_url,
                headers={"Authorization": auth, "Content-Type": "application/json"},
                json={"text": tweet},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        ok = bool(d.get("data", {}).get("id"))
        if not ok:
            log.warning("Twitter post fehlgeschlagen: %s", d)
        return ok
    except Exception as exc:
        log.warning("Twitter post failed: %s", exc)
        return False


async def _post_linkedin(content: dict) -> bool:
    if not LINKEDIN_TOKEN:
        return False
    try:
        import aiohttp
        tags = " ".join(f"#{t}" for t in content.get("hashtags", [])[:3])
        text = f"{content['body'][:600]}\n\n{tags}\n\n👉 {content.get('url','https://supermegabot-production.up.railway.app')}".strip()
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {LINKEDIN_TOKEN}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json={
                    "author": LINKEDIN_URN,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {"text": text},
                            "shareMediaCategory": "NONE",
                        }
                    },
                    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        return bool(d.get("id"))
    except Exception as exc:
        log.warning("LinkedIn post failed: %s", exc)
        return False


# ── Master Post Function ───────────────────────────────────────────────────────

async def post_to_all_channels(content: dict, product: dict = None) -> dict:
    """Post content to every available channel simultaneously."""
    # ── QUALITY GATE Layer 1: Regel-Check ────────────────────────────────────
    try:
        from modules.content_quality_gate import sanitize_content, is_content_valid
        product_name = (product or {}).get("title", content.get("title", ""))
        content, problems = sanitize_content(content, product_name)
        if problems:
            log.warning("ContentGate Probleme: %s", problems)
        if not is_content_valid(content, product_name):
            log.error("ContentGate BLOCKIERT Post: %s", problems)
            return {"skipped": True, "reason": f"quality_gate: {problems}"}
    except ImportError:
        pass

    # ── QUALITY GATE Layer 2: AI-Score via PostGuard ─────────────────────────
    try:
        from modules.post_guard import guard
        post_text = content.get("body") or content.get("title") or ""
        ok, reason = await guard.check("social", text=post_text)
        if not ok:
            log.warning("PostGuard BLOCKIERT: %s", reason)
            return {"skipped": True, "reason": f"post_guard: {reason}"}
    except ImportError:
        pass
    # ─────────────────────────────────────────────────────────────────────────

    h = _content_hash(content)
    if h in _load_hashes():
        log.info("Skipping duplicate content: %s", h)
        return {"skipped": True, "reason": "duplicate"}

    # Re-read FB tokens at runtime so updated Railway vars take effect without restart
    fb_token_iwin   = os.getenv("FACEBOOK_PAGE_TOKEN_IWIN",   FB_TOKEN_IWIN)
    fb_token_aiitec = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", FB_TOKEN_AIITEC)

    results = await asyncio.gather(
        _post_telegram(content),
        _post_facebook_page(FB_PAGE_AIITEC, fb_token_aiitec, content),
        _post_instagram(content),
        _post_tiktok(content),
        _post_pinterest(content),
        _post_shopify_blog(content),
        _post_klaviyo_campaign(content),
        _post_mailchimp_campaign(content),
        _post_sendgrid(content),
        _post_twitter(content),
        _post_linkedin(content),
        return_exceptions=True,
    )

    channel_names = [
        "telegram", "facebook_aiitec", "instagram",
        "tiktok", "pinterest",
        "shopify_blog", "klaviyo", "mailchimp", "sendgrid", "twitter", "linkedin",
    ]
    out = {}
    success_count = 0
    for name, res in zip(channel_names, results):
        if isinstance(res, Exception):
            out[name] = {"ok": False, "error": str(res)}
        else:
            out[name] = {"ok": bool(res)}
            if res:
                success_count += 1

    _save_hash(h)
    log.info("AutoPost: %d/%d channels succeeded", success_count, len(channel_names))
    out["_summary"] = {"channels_ok": success_count, "channels_total": len(channel_names), "hash": h}
    return out


# ── Product-specific helpers ───────────────────────────────────────────────────

async def auto_post_ds24_product() -> dict:
    """Fetch DS24 product and post to all channels."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("MegaAutoPoster DS24: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    try:
        from modules.digistore24_automation import get_products
        products = await get_products()
        if not products:
            content = await generate_product_post(
                "AI Income Machine – 90-Day Blueprint", 37.0,
                os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
            )
        else:
            p = products[0]
            name  = p.get("name", p.get("title", "AI Income Machine"))
            price = float(p.get("price", p.get("net_price", 37.0)) or 37.0)
            url   = p.get("checkout_url") or os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
            content = await generate_product_post(name, price, url)
        return await post_to_all_channels(content)
    except Exception as exc:
        log.error("DS24 auto post failed: %s", exc)
        return {"error": str(exc)}


async def auto_post_shopify_products(limit: int = 3) -> dict:
    """Fetch top Shopify products and post them."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"error": "Shopify not configured"}
    results = {}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit * 3, "status": "active", "vendor": "Printify"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        products = d.get("products", [])
        for p in products[:limit]:
            name  = p.get("title", "Shopify Produkt")
            price = float((p.get("variants") or [{}])[0].get("price", 0) or 0)
            handle = p.get("handle", "")
            url   = f"https://{SHOPIFY_DOMAIN}/products/{handle}" if handle else f"https://{SHOPIFY_DOMAIN}"
            content = await generate_product_post(name, price, url)
            results[name] = await post_to_all_channels(content)
            await asyncio.sleep(2)  # Rate limit pause
    except Exception as exc:
        log.error("Shopify auto post failed: %s", exc)
        results["error"] = str(exc)
    return results


async def run_full_auto_post() -> dict:
    """Master function: generate content and post everywhere."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("MegaAutoPoster: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    log.info("MegaAutoPoster: starting full auto post run")
    results = {}
    # Post DS24 product
    try:
        results["ds24"] = await auto_post_ds24_product()
    except Exception as exc:
        results["ds24"] = {"error": str(exc)}
    # Post top 2 Shopify products
    try:
        results["shopify"] = await auto_post_shopify_products(limit=2)
    except Exception as exc:
        results["shopify"] = {"error": str(exc)}

    total_ok = sum(
        r.get("_summary", {}).get("channels_ok", 0)
        for r in [results.get("ds24", {})] + list(results.get("shopify", {}).values())
        if isinstance(r, dict)
    )
    results["_run_summary"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_channels_hit": total_ok,
    }
    log.info("MegaAutoPoster done: %d total channel hits", total_ok)

    # Fire BRUTUS traffic wave after every full post cycle
    try:
        from modules.brutus_traffic_engine import brutus_run
        asyncio.ensure_future(brutus_run(
            niche="shopify automation ecommerce",
            custom_keywords=["AI Income Machine", "Passives Einkommen Online", "KI Business Blueprint"],
        ))
        log.info("BRUTUS traffic wave triggered after MegaPost")
    except Exception as exc:
        log.warning("BRUTUS trigger skipped: %s", exc)

    # Instantly submit all properties to IndexNow after each post
    try:
        from modules.ultra_seo_arsenal import submit_all_properties_to_indexnow
        asyncio.ensure_future(submit_all_properties_to_indexnow())
        log.info("IndexNow instant submission triggered after MegaPost")
    except Exception as exc:
        log.warning("IndexNow trigger skipped: %s", exc)

    return results
