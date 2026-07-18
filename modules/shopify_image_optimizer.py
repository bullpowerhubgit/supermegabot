"""
Shopify Image Optimizer — Automatische Bildqualitätsprüfung und -verbesserung.
Erkennt unscharfe, kleine oder fehlende Bilder und flaggt sie für Ersatz.
"""
import asyncio
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

@dataclass
class ImageIssue:
    product_id: str
    product_title: str
    image_url: str
    issue: str  # "blurry", "too_small", "missing", "placeholder"
    severity: str  # "high", "medium", "low"

class ShopifyImageOptimizer:
    """Prüft Shopify-Produkte auf Bildqualitätsprobleme."""

    MIN_WIDTH = 600
    MIN_HEIGHT = 600
    PLACEHOLDER_PATTERNS = [
        "placeholder", "no-image", "noimage", "default-image",
        "dummy", "test", "sample", "example",
    ]

    def __init__(self):
        self.store_url = os.getenv("SHOPIFY_STORE_URL", "").rstrip("/")
        self.token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        self.issues: list[ImageIssue] = []

    def _shopify_headers(self) -> dict:
        return {"X-Shopify-Access-Token": self.token, "Content-Type": "application/json"}

    async def scan_products(self, limit: int = 250, fix: bool = False) -> dict:
        """Scanne alle Produkte auf Bildprobleme."""
        import aiohttp

        self.issues = []
        scanned = 0
        page_info = None

        async with aiohttp.ClientSession(headers=self._shopify_headers()) as session:
            while True:
                url = f"{self.store_url}/admin/api/2024-01/products.json?limit={limit}&fields=id,title,images"
                if page_info:
                    url += f"&page_info={page_info}"

                async with session.get(url) as resp:
                    if resp.status != 200:
                        log.error("Shopify API error: %s", resp.status)
                        break
                    data = await resp.json()
                    products = data.get("products", [])
                    if not products:
                        break

                    for product in products:
                        await self._check_product_images(product)
                        scanned += 1

                    # Pagination
                    link_header = resp.headers.get("Link", "")
                    if 'rel="next"' in link_header:
                        import re
                        match = re.search(r'page_info=([^>&"]+)', link_header)
                        page_info = match.group(1) if match else None
                    else:
                        break

                if not page_info:
                    break

        # Gruppiere nach Schweregrad
        high = [i for i in self.issues if i.severity == "high"]
        medium = [i for i in self.issues if i.severity == "medium"]
        low = [i for i in self.issues if i.severity == "low"]

        log.info("Image scan: %d Produkte | %d Issues (H:%d M:%d L:%d)",
                 scanned, len(self.issues), len(high), len(medium), len(low))

        return {
            "scanned": scanned,
            "issues_total": len(self.issues),
            "high": len(high),
            "medium": len(medium),
            "low": len(low),
            "products_with_issues": [
                {"id": i.product_id, "title": i.product_title,
                 "issue": i.issue, "severity": i.severity, "url": i.image_url}
                for i in self.issues[:100]
            ]
        }

    async def _check_product_images(self, product: dict):
        """Prüfe ein einzelnes Produkt auf Bildprobleme."""
        pid = str(product.get("id", ""))
        title = product.get("title", "")
        images = product.get("images", [])

        if not images:
            self.issues.append(ImageIssue(
                product_id=pid, product_title=title,
                image_url="", issue="missing", severity="high"
            ))
            return

        for img in images[:1]:  # Nur Hauptbild prüfen
            src = img.get("src", "")
            width = img.get("width", 0)
            height = img.get("height", 0)

            # Zu klein
            if width and height:
                if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                    self.issues.append(ImageIssue(
                        product_id=pid, product_title=title, image_url=src,
                        issue=f"too_small ({width}x{height})", severity="medium"
                    ))
                    continue

            # Placeholder-Bild
            src_lower = src.lower()
            if any(p in src_lower for p in self.PLACEHOLDER_PATTERNS):
                self.issues.append(ImageIssue(
                    product_id=pid, product_title=title, image_url=src,
                    issue="placeholder", severity="high"
                ))
                continue

            # Bild prüfen ob erreichbar
            try:
                req = urllib.request.Request(src, method="HEAD")
                req.add_header("User-Agent", "Mozilla/5.0")
                with urllib.request.urlopen(req, timeout=5) as r:
                    content_type = r.headers.get("Content-Type", "")
                    if "image" not in content_type:
                        self.issues.append(ImageIssue(
                            product_id=pid, product_title=title, image_url=src,
                            issue="not_an_image", severity="high"
                        ))
            except Exception:
                self.issues.append(ImageIssue(
                    product_id=pid, product_title=title, image_url=src,
                    issue="unreachable", severity="high"
                ))

    async def fix_product_images(self, product_id: str, better_image_url: str) -> bool:
        """Ersetze Hauptbild eines Produkts."""
        import aiohttp
        async with aiohttp.ClientSession(headers=self._shopify_headers()) as session:
            url = f"{self.store_url}/admin/api/2024-01/products/{product_id}/images.json"
            async with session.post(url, json={"image": {"src": better_image_url}}) as resp:
                if resp.status in (200, 201):
                    log.info("Image replaced for product %s", product_id)
                    return True
                log.error("Image replace failed: %s", await resp.text())
                return False


_optimizer = ShopifyImageOptimizer()


async def scan_images(limit: int = 250, fix: bool = False) -> dict:
    return await _optimizer.scan_products(limit=limit, fix=fix)


async def get_image_issues() -> list:
    return [
        {"id": i.product_id, "title": i.product_title,
         "issue": i.issue, "severity": i.severity}
        for i in _optimizer.issues
    ]
