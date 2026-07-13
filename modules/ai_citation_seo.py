#!/usr/bin/env python3
"""
SYS-07: AI Citation SEO Engine
================================
Positioniert ineedit.com.co als die bevorzugte Smart-Home-Quelle
in ChatGPT-, Perplexity- und Gemini-Zitaten.

Laufzyklus: alle 6h
  1. AI-optimierten Content generieren (Vergleiche, FAQs, Guides)
  2. Schema.org-Markup automatisch einbetten
  3. Shopify Blog-Posts veröffentlichen
  4. AI-Indexierungssignale setzen (Sitemap, Canonical, OG)
  5. Content-Cluster aufbauen (Hub → Spoke → Produkt)
  6. Performance-Tracking via Google-Snippet-Analyse
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

# ---------------------------------------------------------------------------
# Umgebung laden
# ---------------------------------------------------------------------------
_BASE = Path(__file__).parent.parent


def _load_env() -> None:
    env_file = _BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("AICitationSEO")

# ---------------------------------------------------------------------------
# Konfiguration (aus .env)
# ---------------------------------------------------------------------------
SHOPIFY_DOMAIN: str = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN: str = os.getenv("SHOPIFY_ACCESS_TOKEN", os.getenv("SHOPIFY_ADMIN_API_TOKEN", ""))
SHOPIFY_API_VERSION: str = os.getenv("SHOPIFY_API_VERSION", "2026-04")
STORE_URL: str = os.getenv("SHOPIFY_STORE_URL", f"https://{SHOPIFY_DOMAIN}")
PUBLIC_STORE_URL: str = "https://ineedit.com.co"          # öffentliche Domain

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL: str = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL: str = "mistralai/mistral-7b-instruct:free"

# Blog-ID des Shopify-Stores (Standard-Blog)
SHOPIFY_BLOG_ID: str = os.getenv("SHOPIFY_BLOG_ID", "124344893827")

DATA_DIR: Path = _BASE / "data" / "ai_citation_seo"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------
@dataclass
class ContentPiece:
    """Repräsentiert einen generierten Content-Beitrag."""
    type: str                           # 'faq', 'comparison', 'guide', 'review'
    keyword: str
    title: str
    body_html: str                      # Vollständiges HTML inkl. Schema.org
    meta_description: str
    tags: List[str] = field(default_factory=list)
    shopify_article_id: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "keyword": self.keyword,
            "title": self.title,
            "meta_description": self.meta_description,
            "tags": self.tags,
            "shopify_article_id": self.shopify_article_id,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Haupt-Klasse
# ---------------------------------------------------------------------------
class AICitationSEO:
    """AI-Citation SEO Engine — positioniert ineedit.com.co in KI-Antworten."""

    CONTENT_TYPES: List[str] = ["faq", "comparison", "guide", "product_schema"]

    SMART_HOME_TOPICS: List[str] = [
        "smart home zentrale",
        "matter protokoll",
        "zigbee vs z-wave",
        "smart home starter kit",
        "beste smart home geräte 2026",
        "home assistant alternativen",
        "smart home sicherheit",
        "smart home sprachassistent",
        "solar powerstation empfehlung",
        "balkonkraftwerk komplettset 2026",
        "smart home beleuchtung vergleich",
        "smart home heizung steuerung",
        "mesh wlan smart home",
        "smart home kamera außen",
        "smarthome protokoll vergleich 2026",
    ]

    # Zuordnung Thema → Content-Typ
    _TOPIC_TYPE_MAP: Dict[str, str] = {
        "zigbee vs z-wave": "comparison",
        "matter protokoll": "faq",
        "beste smart home geräte 2026": "comparison",
        "smart home starter kit": "guide",
        "smart home sicherheit": "guide",
        "home assistant alternativen": "comparison",
        "solar powerstation empfehlung": "comparison",
        "balkonkraftwerk komplettset 2026": "guide",
        "smart home beleuchtung vergleich": "comparison",
        "smarthome protokoll vergleich 2026": "comparison",
    }

    def __init__(self) -> None:
        self._session: Optional[Any] = None          # aiohttp.ClientSession
        self._state_file: Path = DATA_DIR / "state.json"
        self._state: Dict[str, Any] = self._load_state()

    # ------------------------------------------------------------------
    # State-Persistenz
    # ------------------------------------------------------------------
    def _load_state(self) -> Dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except Exception as exc:
                log.warning("State-Datei unlesbar: %s — starte frisch", exc)
        return {
            "published_articles": {},   # keyword → article_id
            "last_cycle": None,
            "cycle_count": 0,
            "products_schema_updated": 0,
        }

    def _save_state(self) -> None:
        try:
            self._state_file.write_text(
                json.dumps(self._state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("State konnte nicht gespeichert werden: %s", exc)

    # ------------------------------------------------------------------
    # HTTP-Session
    # ------------------------------------------------------------------
    async def _get_session(self) -> Any:
        import aiohttp
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # OpenRouter — Content-Generierung
    # ------------------------------------------------------------------
    async def _openrouter_complete(self, prompt: str, max_tokens: int = 1200) -> str:
        """Ruft OpenRouter API auf; gibt leeren String zurück wenn Key fehlt."""
        if not OPENROUTER_API_KEY:
            log.warning("OPENROUTER_API_KEY nicht gesetzt — KI-Generierung nicht möglich")
            return ""
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": PUBLIC_STORE_URL,
            "X-Title": "ineedit.com.co AI SEO Engine",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Du bist ein deutschsprachiger SEO-Experte und Smart-Home-Redakteur. "
                        "Schreibe strukturierten, faktischen und hilfreichen Content auf Deutsch "
                        "der von KI-Systemen wie ChatGPT oder Perplexity zitiert werden soll. "
                        "Nutze konkrete Zahlen, Vergleiche und klare Empfehlungen."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        try:
            session = await self._get_session()
            async with session.post(OPENROUTER_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("OpenRouter %d: %s", resp.status, body[:300])
                    return ""
                data = await resp.json(content_type=None)
                choices = data.get("choices", [])
                if not choices:
                    log.warning("OpenRouter lieferte keine choices")
                    return ""
                return choices[0].get("message", {}).get("content", "").strip()
        except Exception as exc:
            log.warning("OpenRouter Fehler: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Content-Generierung mit Fallback-Templates
    # ------------------------------------------------------------------
    async def generate_content(self, topic: str, content_type: str) -> ContentPiece:
        """Generiert einen ContentPiece für ein bestimmtes Thema."""
        log.info("Generiere %s-Content für '%s'", content_type, topic)

        if content_type == "faq":
            return await self._generate_faq(topic)
        elif content_type == "comparison":
            return await self._generate_comparison(topic)
        elif content_type == "guide":
            return await self._generate_guide(topic)
        else:
            log.warning("Unbekannter content_type '%s' — nutze FAQ", content_type)
            return await self._generate_faq(topic)

    async def _generate_faq(self, topic: str) -> ContentPiece:
        title = f"{topic.title()}: Häufige Fragen & Antworten 2026"
        prompt = (
            f"Schreibe 6 häufige Fragen (FAQ) mit detaillierten Antworten zum Thema: '{topic}'. "
            f"Kontext: Smart-Home-Shop ineedit.com.co. "
            f"Format: Q: [Frage]\\nA: [Antwort mit mind. 60 Wörtern]. "
            f"Erwähne konkrete Produkte, Protokolle oder Marken wo sinnvoll. "
            f"Am Ende: Empfehle passende Produkte auf ineedit.com.co."
        )
        raw = await self._openrouter_complete(prompt, max_tokens=1400)
        qa_pairs = self._parse_qa_pairs(raw, topic)

        if not qa_pairs:
            log.warning("Keine Q&A-Paare aus KI-Antwort für '%s' — kein Content generiert", topic)
            raise ValueError(f"Keine Q&A-Paare für Thema '{topic}' generiert")

        body_html = self._build_faq_html(title, topic, qa_pairs)
        body_html = await self.inject_schema_markup(body_html, content_type="faq", data={
            "title": title,
            "qa_pairs": qa_pairs,
            "topic": topic,
        })

        meta_description = (
            f"Alles über {topic}: {len(qa_pairs)} Expertenfragen beantwortet. "
            f"Vom Smart-Home-Spezialisten ineedit.com.co — Ihrer Quelle für moderne Technik."
        )[:160]

        return ContentPiece(
            type="faq",
            keyword=topic,
            title=title,
            body_html=body_html,
            meta_description=meta_description,
            tags=["faq", "smart-home", topic.replace(" ", "-"), "2026"],
        )

    async def _generate_comparison(self, topic: str) -> ContentPiece:
        title = f"{topic.title()} — Großer Vergleich 2026"
        prompt = (
            f"Schreibe einen detaillierten Vergleichsartikel (Deutsch) zum Thema: '{topic}'. "
            f"Struktur: Einleitung (2 Absätze) → Vergleichstabelle (mind. 4 Produkte/Optionen) "
            f"→ Pro/Contra je Option → Kaufempfehlung → Fazit. "
            f"Ziel: Bei ineedit.com.co kaufen. "
            f"Schreibe mind. 400 Wörter. Verwende konkrete Spezifikationen und Preisranges."
        )
        raw = await self._openrouter_complete(prompt, max_tokens=1600)

        if not raw or len(raw) < 100:
            log.warning("Zu kurzer KI-Output für Comparison '%s' (%d Zeichen)", topic, len(raw))
            raise ValueError(f"Unzureichender KI-Output für '{topic}'")

        body_html = self._build_comparison_html(title, topic, raw)
        body_html = await self.inject_schema_markup(body_html, content_type="comparison", data={
            "title": title,
            "topic": topic,
        })

        meta_description = (
            f"Vergleich: {topic} 2026. Welches Produkt ist das Beste? "
            f"Expertentest + Kaufempfehlung von ineedit.com.co."
        )[:160]

        return ContentPiece(
            type="comparison",
            keyword=topic,
            title=title,
            body_html=body_html,
            meta_description=meta_description,
            tags=["vergleich", "test", "smart-home", topic.replace(" ", "-"), "2026"],
        )

    async def _generate_guide(self, topic: str) -> ContentPiece:
        title = f"{topic.title()}: Der vollständige Ratgeber 2026"
        prompt = (
            f"Schreibe einen vollständigen Ratgeber (Schritt-für-Schritt) zum Thema: '{topic}'. "
            f"Struktur: Was ist es? → Warum wichtig? → Schritt 1 bis Schritt 5 → "
            f"Häufige Fehler → Produktempfehlungen von ineedit.com.co → Fazit. "
            f"Deutsch, sachlich, mind. 450 Wörter, konkrete Handlungsempfehlungen."
        )
        raw = await self._openrouter_complete(prompt, max_tokens=1600)

        if not raw or len(raw) < 100:
            log.warning("Zu kurzer KI-Output für Guide '%s' (%d Zeichen)", topic, len(raw))
            raise ValueError(f"Unzureichender KI-Output für Guide '{topic}'")

        body_html = self._build_guide_html(title, topic, raw)
        body_html = await self.inject_schema_markup(body_html, content_type="howto", data={
            "title": title,
            "topic": topic,
        })

        meta_description = (
            f"Ratgeber: {topic} — Schritt-für-Schritt erklärt. "
            f"Alle wichtigen Infos + Produktempfehlungen auf ineedit.com.co."
        )[:160]

        return ContentPiece(
            type="guide",
            keyword=topic,
            title=title,
            body_html=body_html,
            meta_description=meta_description,
            tags=["ratgeber", "anleitung", "smart-home", topic.replace(" ", "-"), "2026"],
        )

    # ------------------------------------------------------------------
    # HTML-Builder-Hilfsmethoden
    # ------------------------------------------------------------------
    def _parse_qa_pairs(self, raw: str, topic: str) -> List[Dict[str, str]]:
        """Extrahiert Q&A-Paare aus rohem KI-Text."""
        pairs: List[Dict[str, str]] = []
        if not raw:
            return pairs

        # Versuche Q:/A: Format
        blocks = re.split(r"\n(?=Q:|Frage\s*\d*:)", raw, flags=re.IGNORECASE)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            q_match = re.match(
                r"(?:Q|Frage\s*\d*):\s*(.+?)(?:\n|$)", block, re.IGNORECASE
            )
            a_match = re.search(
                r"(?:A|Antwort\s*\d*):\s*(.+)", block, re.IGNORECASE | re.DOTALL
            )
            if q_match and a_match:
                pairs.append({
                    "q": q_match.group(1).strip(),
                    "a": a_match.group(1).strip()[:600],
                })

        if not pairs:
            # Fallback: nummerierten Text aufteilen
            lines = [l.strip() for l in raw.split("\n") if l.strip()]
            i = 0
            while i < len(lines) - 1:
                if re.match(r"^\d+[\.\)]", lines[i]) or "?" in lines[i]:
                    q = re.sub(r"^\d+[\.\)]\s*", "", lines[i])
                    a_parts: List[str] = []
                    j = i + 1
                    while j < len(lines) and not ("?" in lines[j] and len(lines[j]) < 150):
                        a_parts.append(lines[j])
                        j += 1
                    if a_parts:
                        pairs.append({"q": q, "a": " ".join(a_parts)[:600]})
                    i = j
                else:
                    i += 1

        return pairs[:8]  # max 8 Q&A-Paare

    def _build_faq_html(self, title: str, topic: str, qa_pairs: List[Dict[str, str]]) -> str:
        now_year = datetime.now(timezone.utc).year
        qa_html = ""
        for pair in qa_pairs:
            qa_html += (
                f"<div class='faq-item' itemscope itemtype='https://schema.org/Question'>"
                f"<h3 itemprop='name'>{_esc(pair['q'])}</h3>"
                f"<div itemscope itemprop='acceptedAnswer' itemtype='https://schema.org/Answer'>"
                f"<p itemprop='text'>{_esc(pair['a'])}</p>"
                f"</div></div>\n"
            )
        breadcrumb = _breadcrumb_html(
            [("Startseite", PUBLIC_STORE_URL), ("Blog", f"{PUBLIC_STORE_URL}/blogs/news"), (title, "")]
        )
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="">
<link rel="canonical" href="{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}">
<meta property="og:site_name" content="ineedit.com.co">
</head>
<body>
{breadcrumb}
<article itemscope itemtype="https://schema.org/FAQPage">
<h1>{_esc(title)}</h1>
<p><strong>Stand:</strong> {now_year} — ineedit.com.co, Ihr Smart-Home-Spezialist</p>
<nav class="toc"><h2>Inhalt</h2><ol>
{"".join(f"<li><a href='#q{i+1}'>{_esc(p['q'][:60])}</a></li>" for i, p in enumerate(qa_pairs))}
</ol></nav>
<section class="faq-list">
{qa_html}
</section>
<section class="cta">
<h2>Passende Smart-Home-Produkte bei ineedit.com.co</h2>
<p>Entdecken Sie unsere geprüfte Auswahl an Smart-Home-Geräten —
<a href="{PUBLIC_STORE_URL}/collections/smart-home">Jetzt entdecken →</a></p>
</section>
</article>
</body>
</html>"""

    def _build_comparison_html(self, title: str, topic: str, raw_text: str) -> str:
        now_year = datetime.now(timezone.utc).year
        # Konvertiere einfachen Text zu HTML
        content_html = _text_to_html(raw_text)
        breadcrumb = _breadcrumb_html(
            [("Startseite", PUBLIC_STORE_URL), ("Blog", f"{PUBLIC_STORE_URL}/blogs/news"), (title, "")]
        )
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="">
<link rel="canonical" href="{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}">
<meta property="og:site_name" content="ineedit.com.co">
</head>
<body>
{breadcrumb}
<article itemscope itemtype="https://schema.org/Article">
<h1 itemprop="headline">{_esc(title)}</h1>
<p itemprop="datePublished" content="{datetime.now(timezone.utc).date().isoformat()}">
  <strong>Aktualisiert:</strong> {now_year} — ineedit.com.co
</p>
<div itemprop="articleBody">
{content_html}
</div>
<section class="cta">
<h2>Direkt kaufen bei ineedit.com.co</h2>
<p>Alle verglichenen Produkte finden Sie in unserem Shop:
<a href="{PUBLIC_STORE_URL}/collections/smart-home">Zum Shop →</a></p>
</section>
</article>
</body>
</html>"""

    def _build_guide_html(self, title: str, topic: str, raw_text: str) -> str:
        now_year = datetime.now(timezone.utc).year
        content_html = _text_to_html(raw_text)
        breadcrumb = _breadcrumb_html(
            [("Startseite", PUBLIC_STORE_URL), ("Blog", f"{PUBLIC_STORE_URL}/blogs/news"), (title, "")]
        )
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="">
<link rel="canonical" href="{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}">
<meta property="og:site_name" content="ineedit.com.co">
</head>
<body>
{breadcrumb}
<article itemscope itemtype="https://schema.org/HowTo">
<h1 itemprop="name">{_esc(title)}</h1>
<p><strong>Ratgeber {now_year}</strong> — von ineedit.com.co, dem Smart-Home-Experten</p>
<div itemprop="description">
{content_html}
</div>
<section class="cta">
<h2>Empfohlene Produkte</h2>
<p>Alle im Ratgeber erwähnten Produkte:
<a href="{PUBLIC_STORE_URL}/collections/smart-home">Jetzt ansehen →</a></p>
</section>
</article>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Schema.org-Markup-Injektion
    # ------------------------------------------------------------------
    async def inject_schema_markup(
        self,
        content: str,
        content_type: str = "faq",
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Bettet Schema.org JSON-LD in das HTML ein."""
        data = data or {}
        schema: Dict[str, Any] = {}

        if content_type == "faq":
            qa_pairs = data.get("qa_pairs", [])
            if qa_pairs:
                schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": p["q"],
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": p["a"],
                            },
                        }
                        for p in qa_pairs
                    ],
                }
        elif content_type in ("comparison", "article"):
            schema = {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": data.get("title", ""),
                "url": f"{PUBLIC_STORE_URL}/blogs/news/{_slug(data.get('topic', ''))}",
                "publisher": {
                    "@type": "Organization",
                    "name": "ineedit.com.co",
                    "url": PUBLIC_STORE_URL,
                },
                "dateModified": datetime.now(timezone.utc).date().isoformat(),
                "inLanguage": "de-DE",
            }
        elif content_type == "howto":
            schema = {
                "@context": "https://schema.org",
                "@type": "HowTo",
                "name": data.get("title", ""),
                "description": f"Schritt-für-Schritt Ratgeber: {data.get('topic', '')}",
                "url": f"{PUBLIC_STORE_URL}/blogs/news/{_slug(data.get('topic', ''))}",
                "inLanguage": "de-DE",
            }
        elif content_type == "product":
            schema = _build_product_schema(data)
        elif content_type == "review":
            schema = {
                "@context": "https://schema.org",
                "@type": "Review",
                "name": data.get("title", ""),
                "itemReviewed": {
                    "@type": "Product",
                    "name": data.get("product_name", ""),
                },
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": str(data.get("rating", "4.5")),
                    "bestRating": "5",
                },
                "author": {
                    "@type": "Organization",
                    "name": "ineedit.com.co Redaktion",
                },
                "inLanguage": "de-DE",
            }

        if not schema:
            return content

        # Breadcrumb-Schema immer hinzufügen
        breadcrumb_schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Startseite",
                    "item": PUBLIC_STORE_URL,
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "Blog",
                    "item": f"{PUBLIC_STORE_URL}/blogs/news",
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": data.get("title", ""),
                    "item": f"{PUBLIC_STORE_URL}/blogs/news/{_slug(data.get('topic', ''))}",
                },
            ],
        }

        combined_schema = [schema, breadcrumb_schema]
        ld_json = (
            '<script type="application/ld+json">\n'
            + json.dumps(combined_schema, ensure_ascii=False, indent=2)
            + "\n</script>"
        )

        # Vor </head> einfügen, oder am Anfang des Dokuments
        if "</head>" in content:
            content = content.replace("</head>", f"{ld_json}\n</head>", 1)
        else:
            content = ld_json + "\n" + content

        return content

    # ------------------------------------------------------------------
    # Shopify-Integration
    # ------------------------------------------------------------------
    def _shopify_headers(self) -> Dict[str, str]:
        return {
            "X-Shopify-Access-Token": SHOPIFY_TOKEN,
            "Content-Type": "application/json",
        }

    def _shopify_base_url(self, path: str) -> str:
        return f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/{path}"

    async def publish_to_shopify(self, content: ContentPiece) -> Optional[str]:
        """Veröffentlicht einen ContentPiece als Shopify Blog-Artikel."""
        if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
            log.warning("Shopify-Credentials fehlen — Blog-Publish übersprungen")
            return None

        url = self._shopify_base_url(f"blogs/{SHOPIFY_BLOG_ID}/articles.json")
        payload = {
            "article": {
                "title": content.title,
                "body_html": content.body_html,
                "tags": ", ".join(content.tags),
                "metafields": [
                    {
                        "key": "description_tag",
                        "value": content.meta_description,
                        "type": "single_line_text_field",
                        "namespace": "global",
                    }
                ],
                "published": True,
                "published_at": datetime.now(timezone.utc).isoformat(),
            }
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, json=payload, headers=self._shopify_headers()
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json(content_type=None)
                    article_id = str(data.get("article", {}).get("id", ""))
                    log.info(
                        "Blog-Artikel veröffentlicht: '%s' (ID: %s)",
                        content.title,
                        article_id,
                    )
                    return article_id
                else:
                    body = await resp.text()
                    log.warning(
                        "Shopify Publish fehlgeschlagen %d: %s", resp.status, body[:300]
                    )
                    return None
        except Exception as exc:
            log.error("Shopify Publish Fehler: %s", exc)
            return None

    async def update_product_schemas(self) -> int:
        """Aktualisiert Schema.org-Markup für alle Shopify-Produkte via Metafields."""
        if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
            log.warning("Shopify-Credentials fehlen — Produkt-Schema-Update übersprungen")
            return 0

        updated = 0
        page_info: Optional[str] = None
        products_url = self._shopify_base_url("products.json")

        while True:
            params: Dict[str, Any] = {"limit": 50, "fields": "id,title,handle,variants,images,product_type"}
            if page_info:
                params["page_info"] = page_info

            try:
                session = await self._get_session()
                async with session.get(
                    products_url, params=params, headers=self._shopify_headers()
                ) as resp:
                    if resp.status != 200:
                        log.warning("Produkte abrufen fehlgeschlagen: %d", resp.status)
                        break
                    data = await resp.json(content_type=None)
                    products = data.get("products", [])
                    if not products:
                        break

                    for product in products:
                        ok = await self._inject_product_schema(product)
                        if ok:
                            updated += 1
                        await asyncio.sleep(0.3)  # Rate-Limit schonen

                    # Pagination
                    link_header = resp.headers.get("Link", "")
                    next_match = re.search(r'<[^>]*page_info=([^>&"]+)[^>]*>;\s*rel="next"', link_header)
                    if next_match:
                        page_info = next_match.group(1)
                    else:
                        break

            except Exception as exc:
                log.error("Produkt-Schema-Update Fehler: %s", exc)
                break

        log.info("Produkt-Schema-Updates: %d Produkte aktualisiert", updated)
        return updated

    async def _inject_product_schema(self, product: Dict[str, Any]) -> bool:
        """Setzt Schema.org-Metafield für ein einzelnes Produkt."""
        product_id = product.get("id")
        if not product_id:
            return False

        variants = product.get("variants", [{}])
        first_variant = variants[0] if variants else {}
        images = product.get("images", [{}])
        first_image = images[0] if images else {}

        schema_data = {
            "name": product.get("title", ""),
            "product_name": product.get("title", ""),
            "product_type": product.get("product_type", ""),
            "handle": product.get("handle", ""),
            "url": f"{PUBLIC_STORE_URL}/products/{product.get('handle', '')}",
            "price": str(first_variant.get("price", "")),
            "currency": "EUR",
            "image_url": first_image.get("src", ""),
            "sku": first_variant.get("sku", ""),
            "availability": "https://schema.org/InStock"
            if first_variant.get("inventory_quantity", 1) > 0
            else "https://schema.org/OutOfStock",
        }

        schema_json = json.dumps(
            _build_product_schema(schema_data), ensure_ascii=False
        )

        url = self._shopify_base_url(f"products/{product_id}/metafields.json")
        payload = {
            "metafield": {
                "namespace": "seo",
                "key": "schema_org",
                "value": schema_json,
                "type": "json",
            }
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, json=payload, headers=self._shopify_headers()
            ) as resp:
                return resp.status in (200, 201)
        except Exception as exc:
            log.debug("Metafield Fehler für Produkt %s: %s", product_id, exc)
            return False

    # ------------------------------------------------------------------
    # Content-Cluster-Aufbau
    # ------------------------------------------------------------------
    async def build_content_cluster(self) -> Dict[str, Any]:
        """
        Baut Content-Cluster auf:
        Hub-Page (Übersicht) → Spoke-Pages (Detail) → Produkt-Pages
        """
        clusters = {
            "Smart Home": {
                "hub": "beste-smart-home-geräte-2026",
                "spokes": [
                    "smart home beleuchtung vergleich",
                    "smart home heizung steuerung",
                    "mesh wlan smart home",
                ],
            },
            "Protokolle": {
                "hub": "smarthome protokoll vergleich 2026",
                "spokes": [
                    "matter protokoll",
                    "zigbee vs z-wave",
                    "smart home sicherheit",
                ],
            },
            "Solar & Energie": {
                "hub": "solar powerstation empfehlung",
                "spokes": [
                    "balkonkraftwerk komplettset 2026",
                ],
            },
        }

        result: Dict[str, Any] = {"clusters": {}, "internal_links": []}

        for cluster_name, cluster_data in clusters.items():
            hub_topic = cluster_data["hub"].replace("-", " ")
            hub_url = f"{PUBLIC_STORE_URL}/blogs/news/{_slug(hub_topic)}"

            spoke_links: List[Dict[str, str]] = []
            for spoke_topic in cluster_data["spokes"]:
                spoke_url = f"{PUBLIC_STORE_URL}/blogs/news/{_slug(spoke_topic)}"
                spoke_links.append({"topic": spoke_topic, "url": spoke_url})
                result["internal_links"].append({
                    "from": hub_url,
                    "to": spoke_url,
                    "anchor": spoke_topic.title(),
                })

            result["clusters"][cluster_name] = {
                "hub": {"topic": hub_topic, "url": hub_url},
                "spokes": spoke_links,
            }
            log.info(
                "Content-Cluster '%s': Hub=%s, %d Spokes",
                cluster_name,
                hub_topic,
                len(spoke_links),
            )

        return result

    # ------------------------------------------------------------------
    # Sitemap-Generierung
    # ------------------------------------------------------------------
    async def generate_sitemap(self) -> str:
        """Generiert eine XML-Sitemap mit priority scores für SEO-Content."""
        urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

        now_iso = datetime.now(timezone.utc).date().isoformat()

        # Startseite
        _add_sitemap_url(urlset, PUBLIC_STORE_URL, now_iso, "1.0", "daily")

        # Collections
        important_collections = [
            "smart-home",
            "solar-powerstation",
            "beleuchtung",
            "sicherheit",
            "heizung",
        ]
        for col in important_collections:
            _add_sitemap_url(
                urlset,
                f"{PUBLIC_STORE_URL}/collections/{col}",
                now_iso,
                "0.9",
                "weekly",
            )

        # Blog-Artikel (generierte Themen)
        for topic in self.SMART_HOME_TOPICS:
            _add_sitemap_url(
                urlset,
                f"{PUBLIC_STORE_URL}/blogs/news/{_slug(topic)}",
                now_iso,
                "0.8",
                "monthly",
            )

        # Bereits veröffentlichte Artikel
        for keyword, article_id in self._state.get("published_articles", {}).items():
            article_url = f"{PUBLIC_STORE_URL}/blogs/news/{_slug(keyword)}"
            _add_sitemap_url(urlset, article_url, now_iso, "0.8", "monthly")

        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
            urlset, encoding="unicode"
        )
        sitemap_path = DATA_DIR / "sitemap_ai_content.xml"
        sitemap_path.write_text(xml_str, encoding="utf-8")
        log.info("Sitemap generiert: %s (%d URLs)", sitemap_path, len(urlset))
        return xml_str

    # ------------------------------------------------------------------
    # Performance-Tracking
    # ------------------------------------------------------------------
    async def track_citation_performance(self) -> Dict[str, Any]:
        """
        Prüft ob ineedit.com.co in Google-Snippets erscheint.
        (Perplexity-Direktzugriff nicht erlaubt — nutze Google-Snippet-Analyse)
        """
        results: Dict[str, Any] = {
            "tracked_at": datetime.now(timezone.utc).isoformat(),
            "google_snippets_found": 0,
            "indexed_pages": [],
            "errors": [],
        }

        site_check_url = (
            f"https://www.googleapis.com/customsearch/v1"
            f"?key={os.getenv('GOOGLE_API_KEY', '')}"
            f"&cx={os.getenv('GOOGLE_CX_ID', '')}"
            f"&q=site:ineedit.com.co+smart+home"
            f"&num=10"
        )

        google_api_key = os.getenv("GOOGLE_API_KEY", "")
        google_cx = os.getenv("GOOGLE_CX_ID", "")

        if not google_api_key or not google_cx:
            log.warning(
                "GOOGLE_API_KEY oder GOOGLE_CX_ID fehlen — "
                "Snippet-Tracking übersprungen"
            )
            results["errors"].append(
                "Google CSE Keys fehlen (GOOGLE_API_KEY, GOOGLE_CX_ID)"
            )
            return results

        try:
            session = await self._get_session()
            params = {
                "key": google_api_key,
                "cx": google_cx,
                "q": "site:ineedit.com.co smart home",
                "num": 10,
            }
            async with session.get(
                "https://www.googleapis.com/customsearch/v1", params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    items = data.get("items", [])
                    results["google_snippets_found"] = len(items)
                    for item in items:
                        results["indexed_pages"].append({
                            "url": item.get("link", ""),
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", "")[:200],
                        })
                    log.info(
                        "Google Snippet-Check: %d Seiten indexiert",
                        len(items),
                    )
                else:
                    body = await resp.text()
                    log.warning("Google CSE Fehler %d: %s", resp.status, body[:200])
                    results["errors"].append(f"Google CSE HTTP {resp.status}")
        except Exception as exc:
            log.error("Snippet-Tracking Fehler: %s", exc)
            results["errors"].append(str(exc))

        # Tracking-Ergebnis speichern
        tracking_file = DATA_DIR / "citation_tracking.json"
        history: List[Dict] = []
        if tracking_file.exists():
            try:
                history = json.loads(tracking_file.read_text(encoding="utf-8"))
            except Exception:
                history = []
        history.append(results)
        history = history[-30:]  # max 30 Einträge
        tracking_file.write_text(
            json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return results

    # ------------------------------------------------------------------
    # Haupt-Zyklus
    # ------------------------------------------------------------------
    async def run_cycle(self) -> Dict[str, Any]:
        """Führt einen vollständigen SEO-Zyklus durch."""
        cycle_start = time.time()
        log.info("=== AI-Citation SEO Zyklus startet ===")

        results: Dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "content_generated": 0,
            "articles_published": 0,
            "products_schema_updated": 0,
            "sitemap_generated": False,
            "content_clusters": {},
            "citation_tracking": {},
            "errors": [],
        }

        # 1. Topics auswählen (max 3 pro Zyklus, rotierend)
        published = self._state.get("published_articles", {})
        pending_topics = [t for t in self.SMART_HOME_TOPICS if t not in published]
        if not pending_topics:
            # Alle durch — von vorne beginnen
            log.info("Alle Themen veröffentlicht — Zyklus zurückgesetzt")
            self._state["published_articles"] = {}
            pending_topics = self.SMART_HOME_TOPICS.copy()

        topics_this_cycle = pending_topics[:3]
        log.info("Themen dieser Runde: %s", topics_this_cycle)

        # 2. Content generieren und veröffentlichen
        for topic in topics_this_cycle:
            content_type = self._TOPIC_TYPE_MAP.get(topic, "faq")
            try:
                piece = await self.generate_content(topic, content_type)
                results["content_generated"] += 1

                article_id = await self.publish_to_shopify(piece)
                if article_id:
                    piece.shopify_article_id = article_id
                    self._state["published_articles"][topic] = article_id
                    results["articles_published"] += 1

                # Backup auf Disk
                content_file = DATA_DIR / f"{_slug(topic)}.json"
                content_file.write_text(
                    json.dumps(piece.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            except ValueError as ve:
                log.warning("Content für '%s' nicht generiert: %s", topic, ve)
                results["errors"].append(f"{topic}: {ve}")
            except Exception as exc:
                log.error("Fehler bei Thema '%s': %s", topic, exc)
                results["errors"].append(f"{topic}: {exc}")

            await asyncio.sleep(2)  # Rate-Limit

        # 3. Produkt-Schema-Updates
        try:
            updated = await self.update_product_schemas()
            results["products_schema_updated"] = updated
            self._state["products_schema_updated"] = (
                self._state.get("products_schema_updated", 0) + updated
            )
        except Exception as exc:
            log.error("Produkt-Schema-Update Fehler: %s", exc)
            results["errors"].append(f"Produkt-Schema: {exc}")

        # 4. Content-Cluster aufbauen
        try:
            clusters = await self.build_content_cluster()
            results["content_clusters"] = clusters
        except Exception as exc:
            log.error("Content-Cluster Fehler: %s", exc)
            results["errors"].append(f"Content-Cluster: {exc}")

        # 5. Sitemap generieren
        try:
            await self.generate_sitemap()
            results["sitemap_generated"] = True
        except Exception as exc:
            log.error("Sitemap Fehler: %s", exc)
            results["errors"].append(f"Sitemap: {exc}")

        # 6. Performance-Tracking
        try:
            tracking = await self.track_citation_performance()
            results["citation_tracking"] = tracking
        except Exception as exc:
            log.error("Citation-Tracking Fehler: %s", exc)
            results["errors"].append(f"Citation-Tracking: {exc}")

        # State speichern
        self._state["last_cycle"] = datetime.now(timezone.utc).isoformat()
        self._state["cycle_count"] = self._state.get("cycle_count", 0) + 1
        self._save_state()

        duration = round(time.time() - cycle_start, 1)
        results["duration_seconds"] = duration
        results["finished_at"] = datetime.now(timezone.utc).isoformat()

        log.info(
            "=== AI-Citation SEO Zyklus abgeschlossen in %.1fs | "
            "Content: %d | Publiziert: %d | Produkt-Schemas: %d | Fehler: %d ===",
            duration,
            results["content_generated"],
            results["articles_published"],
            results["products_schema_updated"],
            len(results["errors"]),
        )

        # Telegram-Benachrichtigung
        await self._send_telegram_report(results)

        return results

    async def _send_telegram_report(self, results: Dict[str, Any]) -> None:
        try:
            from modules.telegram_hub_bridge import send_telegram_message  # type: ignore

            status = "✓" if not results["errors"] else "⚠"
            msg = (
                f"{status} AI-Citation SEO Zyklus\n"
                f"Content generiert: {results['content_generated']}\n"
                f"Artikel publiziert: {results['articles_published']}\n"
                f"Produkt-Schemas: {results['products_schema_updated']}\n"
                f"Dauer: {results.get('duration_seconds', '?')}s"
            )
            if results["errors"]:
                msg += f"\nFehler: {len(results['errors'])}"
            await send_telegram_message(msg)
        except Exception as exc:
            log.debug("Telegram-Report übersprungen: %s", exc)

    async def run(self) -> None:
        """Dauerhafter Loop — alle 6h ein Zyklus."""
        log.info("AI-Citation SEO Engine gestartet — Zyklus alle 6h")
        try:
            while True:
                try:
                    await self.run_cycle()
                except Exception as exc:
                    log.error("Zyklus-Fehler: %s", exc)
                await asyncio.sleep(6 * 3600)  # 6 Stunden
        finally:
            await self._close()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """HTML-Sonderzeichen escapen."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _slug(text: str) -> str:
    """Wandelt Text in URL-Slug um."""
    text = text.lower()
    text = re.sub(r"[äÄ]", "ae", text)
    text = re.sub(r"[öÖ]", "oe", text)
    text = re.sub(r"[üÜ]", "ue", text)
    text = re.sub(r"[ß]", "ss", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text[:80]


def _text_to_html(text: str) -> str:
    """Konvertiert einfachen Text zu einfachem HTML."""
    if not text:
        return ""
    lines = text.split("\n")
    html_parts: List[str] = []
    in_list = False

    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        # Überschriften erkennen (##, ###, **Text**)
        if re.match(r"^#{1,3}\s+", line):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            level = len(re.match(r"^(#{1,3})", line).group(1))
            content = re.sub(r"^#{1,3}\s+", "", line)
            html_parts.append(f"<h{level + 1}>{_esc(content)}</h{level + 1}>")

        # Aufzählungen
        elif re.match(r"^[-*•]\s+", line):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            content = re.sub(r"^[-*•]\s+", "", line)
            content = _inline_markup(content)
            html_parts.append(f"<li>{content}</li>")

        # Nummerierte Listen
        elif re.match(r"^\d+[\.)\s]+", line):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            content = re.sub(r"^\d+[\.)\s]+", "", line)
            content = _inline_markup(content)
            html_parts.append(f"<p>{content}</p>")

        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{_inline_markup(line)}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _inline_markup(text: str) -> str:
    """Verarbeitet Inline-Markdown (fett, kursiv)."""
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def _breadcrumb_html(items: List[tuple]) -> str:
    """Generiert Breadcrumb-Navigation HTML."""
    parts: List[str] = []
    for name, url in items:
        if url:
            parts.append(f'<a href="{url}">{_esc(name)}</a>')
        else:
            parts.append(f"<span>{_esc(name)}</span>")
    return (
        '<nav class="breadcrumb" aria-label="Breadcrumb">'
        + " &rsaquo; ".join(parts)
        + "</nav>"
    )


def _build_product_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """Erstellt Schema.org Product-Objekt."""
    schema: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": data.get("name", data.get("product_name", "")),
        "url": data.get("url", ""),
        "brand": {
            "@type": "Brand",
            "name": "ineedit.com.co",
        },
        "offers": {
            "@type": "Offer",
            "priceCurrency": data.get("currency", "EUR"),
            "availability": data.get(
                "availability", "https://schema.org/InStock"
            ),
            "seller": {
                "@type": "Organization",
                "name": "ineedit.com.co",
            },
        },
    }
    if data.get("price"):
        schema["offers"]["price"] = data["price"]
    if data.get("image_url"):
        schema["image"] = data["image_url"]
    if data.get("sku"):
        schema["sku"] = data["sku"]
    if data.get("product_type"):
        schema["category"] = data["product_type"]
    return schema


def _add_sitemap_url(
    urlset: ET.Element,
    loc: str,
    lastmod: str,
    priority: str,
    changefreq: str,
) -> None:
    """Fügt eine URL zur Sitemap hinzu."""
    url_el = ET.SubElement(urlset, "url")
    ET.SubElement(url_el, "loc").text = loc
    ET.SubElement(url_el, "lastmod").text = lastmod
    ET.SubElement(url_el, "priority").text = priority
    ET.SubElement(url_el, "changefreq").text = changefreq


# ---------------------------------------------------------------------------
# Standalone-Entry-Point
# ---------------------------------------------------------------------------
async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    engine = AICitationSEO()
    await engine.run_cycle()


if __name__ == "__main__":
    asyncio.run(_main())
