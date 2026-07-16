"""
BrutusCore — Universal Traffic Engine
Importierbar in JEDEM Modul. Ein Aufruf → alle Kanäle werden bespielt.

Usage:
    from modules.brutus_core import fire
    await fire("Mein Produkt", "Mein Inhalt", link="https://...", niche="ki")
"""
import os
import asyncio
import logging
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Rate-Limit State (in-memory + file) ───────────────────────────────────────
import time as _time
from pathlib import Path as _Path

_RATE_STATE_FILE = _Path(__file__).parent.parent / "data" / "brutus_rate_state.json"

def _load_rate_state() -> dict:
    try:
        import json
        return json.loads(_RATE_STATE_FILE.read_text())
    except Exception:
        return {}

def _save_rate_state(s: dict) -> None:
    import json
    _RATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RATE_STATE_FILE.write_text(json.dumps(s))

def _rate_gate(key: str, min_interval_s: int) -> bool:
    """Returns True if allowed to post, False if rate-limited."""
    state = _load_rate_state()
    last = state.get(key, 0)
    now = _time.time()
    if now - last < min_interval_s:
        remaining = int(min_interval_s - (now - last))
        logger.info("Rate gate %s: throttled — %ds remaining", key, remaining)
        return False
    state[key] = now
    _save_rate_state(state)
    return True

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
MAILCHIMP_KEY   = os.getenv("MAILCHIMP_API_KEY", "")
MAILCHIMP_LIST  = os.getenv("MAILCHIMP_LIST_ID", "")
MAILCHIMP_SRV   = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
LINKEDIN_TOKEN  = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN    = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
INDEXNOW_KEY      = os.getenv("INDEXNOW_KEY", "bullpower2026indexnow")
DS24_BLOG_ID      = "gid://shopify/Blog/127011258755"
TWITTER_API_KEY   = os.getenv("TWITTER_API_KEY", "")
TWITTER_SECRET    = os.getenv("TWITTER_API_SECRET", "")
TWITTER_TOKEN     = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_TSECRET   = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
DISCORD_TOKEN     = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL   = os.getenv("DISCORD_CHANNEL_ID", "")
DISCORD_WEBHOOK   = os.getenv("DISCORD_WEBHOOK_URL", "")
WA_PHONE_ID       = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_ACCESS_TOKEN   = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
AMAZON_TAG        = os.getenv("AMAZON_TRACKING_ID", os.getenv("AMAZON_ASSOCIATES_TAG", "bullpowerhub-21"))
EBAY_CAMPAIGN_ID  = os.getenv("EBAY_CAMPAIGN_ID", "5339107261")
SLACK_WEBHOOK     = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN   = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL     = os.getenv("SLACK_DEFAULT_CHANNEL", "#revenue")


async def _ai_generate(title: str, body: str, link: str, niche: str, session: aiohttp.ClientSession) -> dict:
    """AI generiert alle Content-Formate aus einem Titel+Body"""
    prompt = f"""Du bist ein viral-Marketing-Experte. Erstelle für diesen Content:
Titel: {title}
Thema: {niche}
Link: {link}

Alle Formate auf Deutsch, überzeugend, kein Spam-Feeling:

JSON:
{{
  "telegram": "2-3 Zeilen mit Emoji, persönlich, Link am Ende",
  "linkedin": "200 Wörter, professionell, Story, 3 Hashtags",
  "email_subject": "max 50 Zeichen, neugierig",
  "email_body": "120 Wörter, persönlich, CTA mit Link",
  "blog_title": "SEO-optimiert max 60 Zeichen",
  "blog_body": "300 Wörter, H2-Struktur, CTA am Ende",
  "twitter": "max 250 Zeichen, Emoji, Link am Ende, 1-2 Hashtags",
  "seo_keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

    try:
        from modules.ai_client import ai_complete
        import re, json as _json
        text = await ai_complete(prompt, max_tokens=1500)
        if text:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return _json.loads(m.group())
    except Exception as e:
        logger.warning(f"BrutusCore AI: {e}")
    return {}


async def _telegram(text: str, session: aiohttp.ClientSession) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        async with session.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            return (await r.json()).get("ok", False)
    except Exception as e:
        logger.warning(f"BrutusCore Telegram: {e}")
        return False


async def _shopify_blog(title: str, body: str, tags: list, session: aiohttp.ClientSession) -> bool:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return False
    safe_body = body.replace('"', "'").replace('\n', ' ')
    safe_title = title.replace('"', "'")
    tags_str = ", ".join(tags)
    mutation = f'''mutation {{
  articleCreate(article: {{
    blogId: "{DS24_BLOG_ID}",
    title: "{safe_title}",
    author: {{name: "Rudolf S."}},
    body: "{safe_body}",
    tags: {str(tags).replace("'", '"')},
    isPublished: true
  }}) {{
    article {{ id handle }}
    userErrors {{ field message }}
  }}
}}'''
    try:
        async with session.post(
            f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/graphql.json",
            headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
            json={"query": mutation},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            d = await r.json()
            errs = d.get("data", {}).get("articleCreate", {}).get("userErrors", [])
            return len(errs) == 0
    except Exception as e:
        logger.warning(f"BrutusCore Shopify Blog: {e}")
        return False


async def _linkedin(text: str, session: aiohttp.ClientSession) -> bool:
    if not LINKEDIN_TOKEN:
        return False
    # Max 1 LinkedIn post per 2 hours (429 prevention)
    if not _rate_gate("linkedin", 7200):
        return False
    try:
        async with session.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}", "Content-Type": "application/json",
                     "X-Restli-Protocol-Version": "2.0.0"},
            json={
                "author": LINKEDIN_URN,
                "lifecycleState": "PUBLISHED",
                "specificContent": {"com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"
                }},
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            },
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            return r.status in (200, 201)
    except Exception as e:
        logger.warning(f"BrutusCore LinkedIn: {e}")
        return False


async def _mailchimp(subject: str, body_html: str, session: aiohttp.ClientSession) -> bool:
    if not MAILCHIMP_KEY or not MAILCHIMP_LIST:
        return False
    if os.getenv("MAILCHIMP_AUTOMATION_ENABLED", "true").lower() in ("false", "0", "off"):
        return False
    try:
        auth = aiohttp.BasicAuth("anystring", MAILCHIMP_KEY)
        base = f"https://{MAILCHIMP_SRV}.api.mailchimp.com/3.0"
        async with session.post(f"{base}/campaigns", auth=auth, json={
            "type": "regular",
            "recipients": {"list_id": MAILCHIMP_LIST},
            "settings": {"subject_line": subject, "from_name": "Rudolf Sarkany",
                         "reply_to": "bullpowersrtkennels@gmail.com",
                         "title": f"BrutusCore {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"}
        }, timeout=aiohttp.ClientTimeout(total=10)) as r:
            cid = (await r.json()).get("id")
        if not cid:
            return False
        async with session.put(f"{base}/campaigns/{cid}/content", auth=auth,
            json={"html": body_html}, timeout=aiohttp.ClientTimeout(total=10)) as r:
            pass
        async with session.post(f"{base}/campaigns/{cid}/actions/send", auth=auth,
            timeout=aiohttp.ClientTimeout(total=10)) as r:
            return r.status == 204
    except Exception as e:
        logger.warning(f"BrutusCore Mailchimp: {e}")
        return False


async def _klaviyo_event(title: str, link: str, session: aiohttp.ClientSession) -> bool:
    if not KLAVIYO_KEY:
        return False
    try:
        async with session.post(
            "https://a.klaviyo.com/api/events/",
            headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                     "revision": "2024-10-15", "Content-Type": "application/json"},
            json={"data": {"type": "event", "attributes": {
                "metric": {"data": {"type": "metric", "attributes": {"name": "BrutusCore Fire"}}},
                "properties": {"title": title, "link": link, "ts": datetime.utcnow().isoformat()},
                "profile": {"data": {"type": "profile", "attributes": {"email": "bullpowersrtkennels@gmail.com"}}}
            }}},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            return r.status in (200, 201, 202)
    except Exception as e:
        logger.warning(f"BrutusCore Klaviyo: {e}")
        return False


async def _twitter(text: str, session: aiohttp.ClientSession) -> bool:
    """Tweet via Twitter API v2 + OAuth 1.0a"""
    if not all([TWITTER_API_KEY, TWITTER_SECRET, TWITTER_TOKEN, TWITTER_TSECRET]):
        return False
    try:
        from modules.twitter_auto_poster import post_tweet
        result = await post_tweet(text[:280])
        return bool(result.get("ok") or result.get("data", {}).get("id"))
    except Exception as e:
        logger.warning(f"BrutusCore Twitter: {e}")
        return False


async def _discord(text: str, session: aiohttp.ClientSession) -> bool:
    """Discord Nachricht via Bot oder Webhook"""
    if DISCORD_WEBHOOK:
        try:
            async with session.post(
                DISCORD_WEBHOOK,
                json={"content": text[:2000]},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                return r.status in (200, 204)
        except Exception as e:
            logger.warning(f"BrutusCore Discord webhook: {e}")
            return False
    if DISCORD_TOKEN and DISCORD_CHANNEL:
        try:
            async with session.post(
                f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages",
                headers={"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"},
                json={"content": text[:2000]},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                return r.status == 200
        except Exception as e:
            logger.warning(f"BrutusCore Discord bot: {e}")
    return False


async def _whatsapp(text: str, session: aiohttp.ClientSession) -> bool:
    """WhatsApp Business Cloud API Broadcast"""
    if not WA_PHONE_ID or not WA_ACCESS_TOKEN:
        return False
    wa_to = os.getenv("WHATSAPP_BROADCAST_TO", os.getenv("WHATSAPP_VERIFIED_TO", ""))
    if not wa_to:
        return False
    try:
        async with session.post(
            f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": wa_to,
                  "type": "text", "text": {"body": text[:4096]}},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            d = await r.json()
            return bool(d.get("messages"))
    except Exception as e:
        logger.warning(f"BrutusCore WhatsApp: {e}")
        return False


async def _slack(text: str, session: aiohttp.ClientSession) -> bool:
    """Slack Webhook oder Bot API — Revenue/Marketing Alerts"""
    try:
        if SLACK_WEBHOOK:
            async with session.post(
                SLACK_WEBHOOK,
                json={"text": text[:4000]},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                return r.status == 200
        if SLACK_BOT_TOKEN:
            async with session.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": SLACK_CHANNEL, "text": text[:4000]},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                d = await r.json(content_type=None)
                return d.get("ok", False)
        return False
    except Exception as e:
        logger.warning(f"BrutusCore Slack: {e}")
        return False


async def _amazon_affiliate(title: str, link: str, session: aiohttp.ClientSession) -> bool:
    """Amazon Affiliate Link in Telegram + Blog einbauen"""
    if not AMAZON_TAG:
        return False
    try:
        from urllib.parse import quote
        kw = quote(title[:50])
        aff_link = f"https://www.amazon.de/s?k={kw}&tag={AMAZON_TAG}"
        msg = f"🛒 Amazon: {title[:80]}\n👉 {aff_link}"
        return await _telegram(msg, session)
    except Exception as e:
        logger.warning(f"BrutusCore Amazon: {e}")
        return False


async def _ebay_affiliate(title: str, link: str, session: aiohttp.ClientSession) -> bool:
    """eBay Affiliate Link generieren + in Telegram posten"""
    try:
        from urllib.parse import quote
        ebay_search = f"https://www.ebay.de/sch/i.html?_nkw={quote(title[:50])}"
        aff_link = (f"https://rover.ebay.com/rover/1/707-53477-19255-0/1"
                    f"?campid={EBAY_CAMPAIGN_ID}&toolid=10001&customid=supermegabot"
                    f"&mpre={quote(ebay_search)}")
        msg = f"🏷️ eBay Deal: {title[:80]}\n👉 {aff_link}"
        return await _telegram(msg, session)
    except Exception as e:
        logger.warning(f"BrutusCore eBay: {e}")
        return False


async def _indexnow(url_to_index: str, session: aiohttp.ClientSession) -> bool:
    """Meldet URL sofort bei Bing/IndexNow an"""
    if not url_to_index:
        return False
    try:
        async with session.post(
            "https://api.indexnow.org/indexnow",
            json={"host": "bullpowerhubgit.github.io", "key": INDEXNOW_KEY, "urlList": [url_to_index]},
            timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            return r.status in (200, 202)
    except Exception as e:
        logger.warning(f"BrutusCore IndexNow: {e}")
        return False


def _validate_post(title: str, body: str, link: str) -> tuple:
    """Quality gate — returns (is_valid, reason). Blocks junk before posting."""
    if not title or len(title.strip()) < 3:
        return False, "title too short"
    if link and not link.startswith("http"):
        return False, "invalid link"
    combined = (title + " " + body).lower()
    BLOCKED_CONTENT = [
        "portable charger", "wireless earbuds", "smart home gadget",
        "error code", "traceback", "exception:", "credit balance is too low",
    ]
    for blocked in BLOCKED_CONTENT:
        if blocked in combined:
            return False, f"blocked content: {blocked}"
    return True, "ok"


async def fire(
    title: str,
    body: str = "",
    link: str = "",
    niche: str = "online business",
    tags: list = None,
    channels: list = None,  # None = alle Kanäle
    session: aiohttp.ClientSession = None,
) -> dict:
    """
    Haupt-Entry-Point — ein Aufruf bespielet ALLE Kanäle.

    Args:
        title: Titel/Überschrift des Contents
        body: Hauptinhalt (wird in Blog + Email verwendet)
        link: Produkt/Affiliate/Landingpage Link
        niche: Themen-Nische für AI-Content-Generierung
        tags: Blog-Tags (optional)
        channels: Liste der Kanäle, None = alle
        session: aiohttp Session (wird erstellt wenn None)

    Returns:
        dict mit Ergebnissen pro Kanal
    """
    # Quality gate: validate before posting
    valid, reason = _validate_post(title, body, link)
    if not valid:
        logger.warning("BrutusCore: post BLOCKED (%s): '%s'", reason, title[:60])
        return {"ok": False, "blocked": True, "reason": reason}

    if tags is None:
        tags = ["brutus", niche.replace(" ", "-")]
    if channels is None:
        channels = ["telegram", "shopify_blog", "linkedin", "mailchimp", "klaviyo",
                    "indexnow", "twitter", "discord", "whatsapp", "amazon", "ebay", "slack"]

    results = {c: False for c in channels}
    results["timestamp"] = datetime.utcnow().isoformat()
    results["title"] = title

    async def _run(sess: aiohttp.ClientSession):
        # AI Content generieren
        content = await _ai_generate(title, body, link, niche, sess)

        tg_text = content.get("telegram") or f"🔥 <b>{title}</b>\n\n{body[:200]}\n\n👉 {link}"
        li_text = content.get("linkedin") or f"{title}\n\n{body[:300]}\n\n{link}"
        blog_title = content.get("blog_title") or title
        blog_body = content.get("blog_body") or f"{body}\n\n<a href='{link}'>{link}</a>"
        email_subj = content.get("email_subject") or title[:50]
        email_html = f"<html><body><h2>{title}</h2><p>{content.get('email_body', body)}</p><p><a href='{link}'>Hier klicken</a></p></body></html>"

        # Alle aktiven Kanäle parallel
        tasks = {}
        if "telegram" in channels:
            tasks["telegram"] = _telegram(tg_text, sess)
        if "shopify_blog" in channels:
            tasks["shopify_blog"] = _shopify_blog(blog_title, blog_body, tags, sess)
        if "linkedin" in channels:
            tasks["linkedin"] = _linkedin(li_text, sess)
        if "mailchimp" in channels:
            tasks["mailchimp"] = _mailchimp(email_subj, email_html, sess)
        if "klaviyo" in channels:
            tasks["klaviyo"] = _klaviyo_event(title, link, sess)
        if "indexnow" in channels and link:
            tasks["indexnow"] = _indexnow(link, sess)
        if "twitter" in channels:
            tw_text = content.get("twitter") or f"{title[:200]}\n{link}"
            tasks["twitter"] = _twitter(tw_text, sess)
        if "discord" in channels:
            dc_text = content.get("telegram") or f"🔥 **{title}**\n\n{body[:300]}\n\n👉 {link}"
            tasks["discord"] = _discord(dc_text, sess)
        if "whatsapp" in channels:
            wa_text = content.get("telegram") or f"🔥 {title}\n\n{body[:300]}\n\n👉 {link}"
            tasks["whatsapp"] = _whatsapp(wa_text, sess)
        if "amazon" in channels:
            tasks["amazon"] = _amazon_affiliate(title, link, sess)
        if "ebay" in channels:
            tasks["ebay"] = _ebay_affiliate(title, link, sess)
        if "slack" in channels:
            sl_text = content.get("telegram") or f"🔥 {title}\n\n{body[:300]}\n\n👉 {link}"
            tasks["slack"] = _slack(sl_text, sess)

        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), done):
            results[key] = result if not isinstance(result, Exception) else False

        channels_hit = sum(1 for v in results.values() if v is True)
        results["channels_hit"] = channels_hit
        logger.info(f"BrutusCore.fire '{title[:40]}': {channels_hit}/{len(channels)} Kanäle ✅")

    if session:
        await _run(session)
    else:
        async with aiohttp.ClientSession() as sess:
            await _run(sess)

    return results


async def fire_from_brutus(niche: str = "ki business shopify") -> dict:
    """Startet den vollen Brutus + BrutusCore Doppel-Angriff"""
    results = {"brutus": {}, "brutus_core": {}}
    try:
        from modules.brutus_traffic_engine import brutus_run
        results["brutus"] = await brutus_run(niche=niche)
    except Exception as e:
        logger.error(f"Brutus run failed: {e}")
        results["brutus"] = {"error": str(e)}
    return results


class BrutusCore:
    """Convenience class wrapper around the module-level fire() function."""

    async def fire(self, message: str, channels: list = None, link: str = "", title: str = "") -> dict:
        return await fire(
            title=title or message[:60],
            body=message,
            link=link or os.getenv("DS24_AFFILIATE_LINK", ""),
            channels=channels,
        )
