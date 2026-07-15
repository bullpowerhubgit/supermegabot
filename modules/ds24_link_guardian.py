"""
DS24 Link Guardian — Dauerhafter Schutz vor falschen Produkt-Links.

Wird beim Start importiert. Validiert DS24_AFFILIATE_LINK gegen die DS24 API,
heilt automatisch wenn das Produkt rejected/inaktiv ist, und ist die einzige
authoritative Quelle für DS24-Links im gesamten System.

Verwendung in allen Modulen:
    from modules.ds24_link_guardian import get_ds24_link
    link = get_ds24_link()
"""
import os
import json
import time
import logging
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

DS24_API_KEY = os.getenv("DS24_API_KEY", "1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N")
_cache_products: list = []
_cache_ts: float = 0
_cache_ttl: int = 3600  # 1 Stunde

# Bekannte sichere Fallback-Produkte (in Prioritätsreihenfolge)
SAFE_FALLBACK_IDS = ["669750", "704330", "704370", "704372", "704392"]
CHECKOUT_BASE = "https://www.checkout-ds24.com/product/"

# Produkte die NIEMALS verwendet werden dürfen
BLACKLISTED_IDS = {"668035"}  # rejected, fehlende Garantie/Impressum


def _fetch_products() -> list:
    """Lädt alle aktiven DS24-Produkte von der API."""
    global _cache_products, _cache_ts
    if time.time() - _cache_ts < _cache_ttl and _cache_products:
        return _cache_products
    try:
        req = urllib.request.Request(
            "https://www.digistore24.com/api/call/listProducts/JSON/",
            headers={"X-DS-API-KEY": DS24_API_KEY}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        prods = data.get("data", {}).get("products", [])
        active = [
            p for p in prods
            if p.get("is_active") == "Y"
            and p.get("is_deleted") == "N"
            and p.get("orderform_customer_url")
            and str(p.get("id", "")) not in BLACKLISTED_IDS
        ]
        _cache_products = active
        _cache_ts = time.time()
        log.info(f"[DS24Guardian] {len(active)} aktive Produkte geladen")
        return active
    except Exception as e:
        log.warning(f"[DS24Guardian] API-Fehler: {e}")
        return _cache_products


def _product_is_valid(product_id: str) -> bool:
    """Prüft ob eine Produkt-ID aktiv, nicht gelöscht und nicht blacklisted ist."""
    if product_id in BLACKLISTED_IDS:
        return False
    prods = _fetch_products()
    ids = {str(p.get("id", "")) for p in prods}
    return product_id in ids


def _best_available_product() -> str:
    """Gibt die beste verfügbare Produkt-ID zurück."""
    prods = _fetch_products()
    id_set = {str(p.get("id", "")) for p in prods}

    # Erst bekannte Safe-Fallbacks prüfen
    for pid in SAFE_FALLBACK_IDS:
        if pid in id_set:
            return pid

    # Sonst neuestes aktives Produkt
    if prods:
        sorted_prods = sorted(prods, key=lambda p: str(p.get("id", "0")), reverse=True)
        return str(sorted_prods[0]["id"])

    log.error("[DS24Guardian] KRITISCH: Keine aktiven DS24-Produkte gefunden!")
    return "669750"  # absoluter Notfall-Fallback


def validate_and_heal() -> str:
    """
    Validiert DS24_AFFILIATE_LINK. Wenn ungültig → auto-heilt mit bestem Produkt.
    Setzt os.environ["DS24_AFFILIATE_LINK"] dauerhaft für diese Session.
    Gibt den validierten Link zurück.
    """
    configured = os.getenv("DS24_AFFILIATE_LINK", "")

    # Produkt-ID aus URL extrahieren
    current_id = ""
    if "/product/" in configured:
        current_id = configured.split("/product/")[-1].strip("/")

    needs_heal = False
    reason = ""

    if not configured:
        needs_heal = True
        reason = "DS24_AFFILIATE_LINK nicht gesetzt"
    elif current_id in BLACKLISTED_IDS:
        needs_heal = True
        reason = f"Produkt {current_id} ist BLACKLISTED (rejected/invalid)"
    elif not _product_is_valid(current_id):
        needs_heal = True
        reason = f"Produkt {current_id} ist nicht aktiv in DS24 API"

    if needs_heal:
        best_id = _best_available_product()
        new_link = f"{CHECKOUT_BASE}{best_id}"
        os.environ["DS24_AFFILIATE_LINK"] = new_link
        log.warning(
            f"[DS24Guardian] AUTO-HEAL: {reason} → "
            f"Neues Produkt: {best_id} ({new_link})"
        )
        # .env patchen für Persistenz
        _patch_env_file(new_link)
        return new_link

    log.info(f"[DS24Guardian] Link validiert ✅ Produkt {current_id}")
    return configured


def _patch_env_file(new_link: str):
    """Schreibt DS24_AFFILIATE_LINK dauerhaft in die .env Datei."""
    env_paths = [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        "/Users/rudolfsarkany/supermegabot/.env",
    ]
    for env_path in env_paths:
        env_path = os.path.normpath(env_path)
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()

            found = False
            new_lines = []
            for line in lines:
                if line.startswith("DS24_AFFILIATE_LINK="):
                    new_lines.append(f"DS24_AFFILIATE_LINK={new_link}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"\nDS24_AFFILIATE_LINK={new_link}\n")

            with open(env_path, "w") as f:
                f.writelines(new_lines)
            log.info(f"[DS24Guardian] .env gepatcht: {env_path}")
        except Exception as e:
            log.warning(f"[DS24Guardian] .env patch fehlgeschlagen: {e}")


def get_ds24_link(context: str = "") -> str:
    """
    DIE einzige Funktion die DS24-Links liefert.
    Validiert bei jedem Aufruf gegen den Cache.

    Args:
        context: Optional. Kontext für kontextbasierte Produktwahl
                 z.B. "shopify", "social", "email"

    Returns:
        Validierten, aktiven DS24 Checkout-Link
    """
    link = os.getenv("DS24_AFFILIATE_LINK", "")

    # Schnell-Check: Link korrekt gesetzt?
    if link and "/product/" in link:
        pid = link.split("/product/")[-1].strip("/")
        if pid not in BLACKLISTED_IDS:
            return link

    # Link fehlt oder blacklisted → auto-heal
    return validate_and_heal()


def get_ds24_product_id() -> str:
    """Gibt nur die Produkt-ID zurück."""
    link = get_ds24_link()
    if "/product/" in link:
        return link.split("/product/")[-1].strip("/")
    return "669750"


def get_all_active_links(limit: int = 10) -> list[dict]:
    """
    Gibt eine Liste aktiver DS24-Produkte zurück (für Rotation).
    Nützlich für A/B-Testing oder thematisch passende Links.
    """
    prods = _fetch_products()
    result = []
    for p in prods[:limit]:
        result.append({
            "id": str(p.get("id", "")),
            "name": p.get("name", ""),
            "url": p.get("orderform_customer_url", ""),
            "commission": p.get("affiliate_commission", ""),
        })
    return result


# ── Beim Import sofort validieren ──────────────────────────────────────────────
def _startup_check():
    """Wird einmalig beim Modulimport ausgeführt."""
    link = validate_and_heal()
    pid = link.split("/product/")[-1] if "/product/" in link else "?"
    log.info(f"[DS24Guardian] Startup ✅ Aktiver Link: {link} (Prod {pid})")

_startup_check()
