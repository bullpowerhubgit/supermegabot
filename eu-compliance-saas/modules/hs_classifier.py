"""HS Code Classifier — EU Zollfreigrenze abgeschafft ab 1. Juli 2026"""
import logging
import os
import json
import aiohttp

log = logging.getLogger("HSClassifier")

EU_CUSTOMS_FEE_PER_HS = 3.0  # €3 pro HS-Code-Unterposition (VO EU 2026/382)
EU_HANDLING_FEE = 2.0  # €2 geschätzte Bearbeitungsgebühr je Deklarationszeile

# HS Code Lookup-Tabelle (vereinfacht, Hauptkategorien)
HS_QUICK_MAP = {
    "smartphone": "8517.12", "handy": "8517.12", "phone": "8517.12",
    "laptop": "8471.30", "notebook": "8471.30", "computer": "8471.41",
    "kopfhörer": "8518.30", "headphones": "8518.30", "earbuds": "8518.30",
    "smartwatch": "9102.12", "uhr": "9101.11", "watch": "9101.11",
    "kamera": "9006.53", "camera": "9006.53",
    "drucker": "8443.32", "printer": "8443.32",
    "router": "8517.62", "wifi": "8517.62",
    "solarpanel": "8541.40", "solar": "8541.40", "solarmodul": "8541.40",
    "powerstation": "8507.60", "akku": "8507.60", "battery": "8507.60",
    "kleidung": "6211.43", "clothing": "6110.20", "shirt": "6110.20",
    "schuhe": "6404.11", "shoes": "6404.11", "sneaker": "6404.19",
    "spielzeug": "9503.00", "toy": "9503.00", "toys": "9503.00",
    "kosmetik": "3304.99", "cosmetics": "3304.99", "makeup": "3304.91",
    "möbel": "9403.20", "furniture": "9403.20", "chair": "9401.90",
    "lampe": "9405.11", "lamp": "9405.11", "led": "9405.11",
    "werkzeug": "8205.59", "tool": "8205.59", "tools": "8205.59",
    "fahrrad": "8712.00", "bike": "8712.00", "e-bike": "8714.99",
    "default": "9999.99",
}


async def classify_hs_code(product_title: str, product_description: str = "", anthropic_key: str = "") -> dict:
    """Klassifiziert ein Produkt in HS-Code via Claude oder Fallback-Tabelle."""
    title_lower = (product_title + " " + product_description).lower()

    # Schnell-Lookup aus Tabelle
    for keyword, hs in HS_QUICK_MAP.items():
        if keyword in title_lower and keyword != "default":
            return {
                "hs_code": hs,
                "hs_description": f"Klassifiziert via Keyword: {keyword}",
                "method": "keyword_table",
                "confidence": 0.8,
                "customs_fee_eur": EU_CUSTOMS_FEE_PER_HS,
                "handling_fee_eur": EU_HANDLING_FEE,
                "total_eu_fee_eur": EU_CUSTOMS_FEE_PER_HS + EU_HANDLING_FEE,
            }

    # Claude AI Fallback wenn Key vorhanden
    if anthropic_key:
        try:
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Classify this product with the correct 6-digit HS tariff code. "
                        f"Respond ONLY with JSON: {{\"hs_code\": \"XXXX.XX\", \"description\": \"...\"}}\n"
                        f"Product: {product_title[:200]}"
                    )
                }]
            }
            headers = {"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["content"][0]["text"]
                        parsed = json.loads(text)
                        return {
                            "hs_code": parsed.get("hs_code", "9999.99"),
                            "hs_description": parsed.get("description", ""),
                            "method": "claude_ai",
                            "confidence": 0.92,
                            "customs_fee_eur": EU_CUSTOMS_FEE_PER_HS,
                            "handling_fee_eur": EU_HANDLING_FEE,
                            "total_eu_fee_eur": EU_CUSTOMS_FEE_PER_HS + EU_HANDLING_FEE,
                        }
        except Exception as e:
            log.warning("Claude HS classification error: %s", e)

    # Default Fallback
    return {
        "hs_code": "9999.99",
        "hs_description": "Nicht klassifiziert — manuelle Prüfung erforderlich",
        "method": "fallback",
        "confidence": 0.3,
        "customs_fee_eur": EU_CUSTOMS_FEE_PER_HS,
        "handling_fee_eur": EU_HANDLING_FEE,
        "total_eu_fee_eur": EU_CUSTOMS_FEE_PER_HS + EU_HANDLING_FEE,
    }


async def classify_product_catalog(products: list, anthropic_key: str = "") -> list:
    """Klassifiziert eine Produktliste batch-weise."""
    results = []
    for p in products:
        hs = await classify_hs_code(
            p.get("title", ""), p.get("description", ""), anthropic_key
        )
        hs["product_id"] = p.get("id", "")
        hs["product_title"] = p.get("title", "")
        results.append(hs)
    return results


def calculate_customs_impact(num_products: int, monthly_orders: int) -> dict:
    """Berechnet monatliche EU-Zollkosten ohne HS-Automatisierung."""
    total_per_order = EU_CUSTOMS_FEE_PER_HS + EU_HANDLING_FEE
    monthly_cost = monthly_orders * total_per_order
    annual_cost = monthly_cost * 12
    return {
        "products": num_products,
        "monthly_orders": monthly_orders,
        "fee_per_order_eur": total_per_order,
        "monthly_customs_cost_eur": monthly_cost,
        "annual_customs_cost_eur": annual_cost,
        "savings_with_automation_eur": annual_cost * 0.15,
        "regulation": "VO (EU) 2026/382 — ab 1. Juli 2026 in Kraft",
    }
