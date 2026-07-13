#!/usr/bin/env python3
"""Alias: leitet weiter zu modules.social_autoposter (primär) bzw. modules.mega_auto_poster."""
import logging

_log = logging.getLogger(__name__)

try:
    from modules.social_autoposter import (
        run_social_cycle,
        post_to_all,
        post_to_facebook,
        post_to_instagram,
        post_to_linkedin,
        get_all_stats,
    )
    _log.debug("auto_poster: social_autoposter geladen")
except ImportError as _e:
    _log.warning("auto_poster: social_autoposter nicht verfügbar (%s)", _e)
    async def run_social_cycle() -> dict:
        return {"status": "nicht verfügbar"}
    async def post_to_all(message: str = "", **kw) -> dict:
        return {}
    async def post_to_facebook(message: str = "", **kw) -> dict:
        return {}
    async def post_to_instagram(caption: str = "", **kw) -> dict:
        return {}
    async def post_to_linkedin(text: str = "", **kw) -> dict:
        return {}
    async def get_all_stats() -> dict:
        return {}

try:
    from modules.mega_auto_poster import (
        run_full_auto_post,
        auto_post_shopify_products,
        auto_post_ds24_product,
        post_to_all_channels,
        generate_product_post,
    )
    _log.debug("auto_poster: mega_auto_poster geladen")
except ImportError as _e:
    _log.warning("auto_poster: mega_auto_poster nicht verfügbar (%s)", _e)
    async def run_full_auto_post() -> dict:
        return {"status": "nicht verfügbar"}
    async def auto_post_shopify_products(limit: int = 3) -> dict:
        return {}
    async def auto_post_ds24_product() -> dict:
        return {}
    async def post_to_all_channels(content: dict, product: dict = None) -> dict:
        return {}
    async def generate_product_post(product_name: str, price: float, url: str) -> dict:
        return {}
