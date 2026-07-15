"""
Product Gatekeeper — blockiert Fake/Junk-Produkte vor dem Shopify-Import.

Wird aufgerufen von allen Modulen die Shopify-Produkte erstellen.
Gibt True zurück wenn das Produkt OK ist, False wenn es blockiert wird.
"""
import re
import logging

log = logging.getLogger(__name__)

# Nischen die erlaubt sind
ALLOWED_NICHES = {
    "smart home", "solar", "powerstation", "e-bike", "e-mobility",
    "saugroboter", "smart lighting", "smart security", "grow light",
    "3d drucker", "laser engraver", "drone", "audio", "gaming",
    "wearable", "smartwatch", "home office tech", "auto tech",
    "pet tech", "camping tech", "fitness tech", "werkzeug profi",
    "ev charging", "netzwerk tech", "tablets", "smartphones",
    "smart plug", "smart thermostat", "smart display", "smart gadget",
    "elektronik", "camping", "outdoor", "sport", "fitness",
}

# Verbotene Vendor-Namen (generieren Fake-Produkte)
BLOCKED_VENDORS = {
    "SuperMegaBot", "supermegabot", "BullPowerBot", "AutoBot",
    "TestVendor", "Demo", "Fake",
}

# Verbotene Titelpattern (Artikel, Alltagskram ohne Tech-Bezug)
BLOCKED_PATTERNS = [
    # Nachrichten/Artikel
    r'\b(article|news|blog|tutorial|reddit|hackernews|hn\s)\b',
    r'says they regret', r'still running trains', r'owners say',
    r'\byears? later\b.*\bowners?\b',
    # Küche/Haushalt ohne Tech
    r'\b(serviette|taschentuch|wischtuch|windel|windeln)\b',
    r'\b(notizbuch|kalender|planner|ringordner|aktenordner)\b',
    r'\b(frühstücksbrett|schneidebrett|holzbrettchen|servierbrett)\b',
    r'\b(pfannenwender|kochutensilien|besteck.*set|messer.*set(?!.*elektrisch))\b',
    r'\b(bettwäsche|kissenbezug|spannbettlaken|handtuch|badetuch)\b',
    r'\b(babybadewanne|lauflernhilfe|trinklerntasse)\b',
    r'\b(kugelschreiber|füller.*set|stift.*set|marker.*set)\b',
    r'\b(flipchart|moderationswand|whiteboard(?!.*digital|.*smart))\b',
    r'\b(buch|roman|kochbuch|sachbuch)\b',
    # Tastatur-Shortcuts, UI-Tutorials etc.
    r'tastenkürzel.*ausblenden', r'umschalttaste.*option',
    # Kleidung
    r'\b(t-shirt|pullover|jacke|hose(?!.*drucker|.*laser)|socken|unterwäsche)\b',
    r'\b(kleid|bluse|hemd(?!.*bügelstation))\b',
    # Lebensmittel
    r'\b(kaffee.*bohnen|tee.*beutel|schokolade|süßigkeiten|gewürz.*set(?!.*elektrisch|.*smart))\b',
]

_compiled = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

# Mindest-Kriterien
MIN_TITLE_LEN = 12
MAX_TITLE_LEN = 250
MIN_PRICE_EUR = 5.0
MAX_PRICE_EUR = 2000.0


def validate_product(
    title: str,
    vendor: str = "",
    product_type: str = "",
    price: float = 0.0,
    description: str = "",
) -> tuple[bool, str]:
    """
    Prüft ob ein Produkt importiert werden darf.
    Returns: (ok: bool, reason: str)
    """
    # Vendor-Check
    if vendor and vendor in BLOCKED_VENDORS:
        return False, f"Vendor gesperrt: {vendor}"

    # Titel-Länge
    if len(title) < MIN_TITLE_LEN:
        return False, f"Titel zu kurz: '{title}'"
    if len(title) > MAX_TITLE_LEN:
        return False, f"Titel zu lang ({len(title)} Zeichen)"

    # Blacklist-Pattern
    for pattern in _compiled:
        if pattern.search(title):
            return False, f"Titel-Pattern geblockt: '{title[:60]}'"

    # Preis-Check
    if price > 0 and (price < MIN_PRICE_EUR or price > MAX_PRICE_EUR):
        return False, f"Preis außerhalb Rahmen: {price}€"

    # Nischen-Check (wenn product_type gesetzt)
    if product_type:
        pt_lower = product_type.lower()
        if not any(niche in pt_lower for niche in ALLOWED_NICHES):
            # Toleranter Check: schauen ob Titel selbst Nischen-Keywords hat
            title_lower = title.lower()
            niche_keywords = [
                "smart", "wifi", "bluetooth", "led", "solar", "akku", "usb",
                "digital", "elektronik", "tech", "app", "sensor", "automatisch",
                "robot", "drohne", "laser", "3d", "gaming", "cam", "pro",
                "electric", "elektrisch", "power", "lader", "ladegerät",
            ]
            if not any(kw in title_lower for kw in niche_keywords):
                return False, f"Nicht in erlaubter Nische: '{product_type}'"

    return True, "OK"


def filter_products_batch(products: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Filtert eine Liste von Produkten.
    Returns: (approved, rejected)
    """
    approved = []
    rejected = []
    for p in products:
        ok, reason = validate_product(
            title=p.get("title", ""),
            vendor=p.get("vendor", ""),
            product_type=p.get("product_type", ""),
            price=float(p.get("price", 0) or 0),
            description=p.get("body_html", ""),
        )
        if ok:
            approved.append(p)
        else:
            rejected.append({**p, "_rejection_reason": reason})
            log.warning("GATEKEEPER BLOCKIERT: %s — %s", p.get("title", "")[:60], reason)
    log.info("Gatekeeper: %d genehmigt / %d blockiert", len(approved), len(rejected))
    return approved, rejected
