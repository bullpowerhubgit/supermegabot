"""
Autonomes A/B Testing Engine — testet Headlines, CTAs, Preise automatisch.
Wählt den Gewinner per Supabase-Daten, rotiert Varianten nach Conversion-Rate.
"""
import logging
import os
from datetime import datetime

log = logging.getLogger("ABTest")

AB_VARIANTS: dict[str, list[str]] = {
    "headline": [
        "Shopify auf Autopilot — KI macht alles für dich",
        "Verdiene 3x mehr mit deinem Shopify Store — automatisch",
        "Der KI-Bot der deinen Shopify Store 24/7 optimiert",
        "Stop manuell — Start automatisch: Shopify KI-Suite",
    ],
    "cta": [
        "Jetzt kostenlos starten →",
        "14 Tage gratis testen →",
        "Sofort aktivieren (0€) →",
        "Meinen Shop automatisieren →",
    ],
    "price_anchor": [
        "Wert: €997/Jahr — Heute: €49/Monat",
        "Agenturen zahlen €500/h — du zahlst €49/Monat",
        "1 Stunde Berater = Jahresabo bei uns",
        "Spart dir 40h/Monat — kostet nur €49",
    ],
    "urgency": [
        "⚡ Nur noch 3 Plätze zu diesem Preis",
        "🔥 Preis steigt morgen — jetzt sichern",
        "✅ Heute einschalten, morgen automatisiert",
        "🚀 In 5 Min eingerichtet — sofort Ergebnisse",
    ],
}

# Winning variants (updated by analyze_and_select_winner)
_winners: dict[str, str] = {}


async def get_variant(test_name: str, session_id: str) -> str:
    """Gibt konsistent dieselbe Variante für eine Session zurück.
    Nutzt den Gewinner wenn bekannt, sonst hash-basiertes Routing."""
    if test_name in _winners:
        return _winners[test_name]
    variants = AB_VARIANTS.get(test_name, ["default"])
    idx = abs(hash(f"{test_name}_{session_id}")) % len(variants)
    return variants[idx]


async def get_all_variants(session_id: str) -> dict[str, str]:
    """Gibt alle aktuellen Varianten für eine Session zurück."""
    return {
        test: await get_variant(test, session_id)
        for test in AB_VARIANTS
    }


async def record_conversion(test_name: str, variant: str, converted: bool,
                            session_id: str = "") -> None:
    """Speichert Conversion-Event in Supabase ab_tests Tabelle."""
    try:
        from modules.supabase_client import get_client
        client = get_client()
        await client.table("ab_tests").insert({
            "test_name": test_name,
            "variant": variant[:500],
            "converted": converted,
            "session_id": session_id[:100],
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as exc:
        log.warning("AB record failed: %s", exc)


async def analyze_and_select_winner() -> dict:
    """Analysiert alle A/B-Tests, wählt Gewinner, speichert in _winners."""
    global _winners
    try:
        from modules.supabase_client import get_client
        client = get_client()
        results = {}
        for test_name, variants_list in AB_VARIANTS.items():
            data = await client.table("ab_tests").select(
                "variant, converted"
            ).eq("test_name", test_name).execute()
            if not data.data:
                continue
            stats: dict[str, dict] = {}
            for row in data.data:
                v = row.get("variant", "?")
                if v not in stats:
                    stats[v] = {"views": 0, "conversions": 0}
                stats[v]["views"] += 1
                if row.get("converted"):
                    stats[v]["conversions"] += 1
            if not stats:
                continue
            best_variant = max(
                stats.items(),
                key=lambda x: x[1]["conversions"] / max(x[1]["views"], 1),
            )
            winner_name = best_variant[0]
            winner_rate = best_variant[1]["conversions"] / max(best_variant[1]["views"], 1)
            # Only use winner if statistically meaningful (>= 10 views)
            if best_variant[1]["views"] >= 10:
                _winners[test_name] = winner_name
            results[test_name] = {
                "winner": winner_name,
                "conversion_rate": round(winner_rate * 100, 1),
                "stats": stats,
                "active": best_variant[1]["views"] >= 10,
            }
        return results
    except Exception as exc:
        return {"error": str(exc)}


def get_current_winners() -> dict[str, str]:
    """Gibt die aktuell aktiven Gewinner-Varianten zurück."""
    return dict(_winners)
