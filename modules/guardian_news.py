import os
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

GUARDIAN_API_URL = "https://content.guardianapis.com"


class GuardianNewsClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GUARDIAN_NEWS_API_KEY", "test")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "supermegabot/1.0"

    def _get(self, endpoint, params=None):
        params = params or {}
        params["api-key"] = self.api_key
        params["format"] = "json"
        try:
            r = self.session.get(f"{GUARDIAN_API_URL}/{endpoint}", params=params, timeout=10)
            r.raise_for_status()
            return r.json().get("response", {})
        except requests.RequestException as e:
            logger.error(f"Guardian API error: {e}")
            return {}

    def search(self, query, page_size=10, page=1, section=None, order_by="newest"):
        params = {
            "q": query,
            "page-size": page_size,
            "page": page,
            "order-by": order_by,
            "show-fields": "headline,trailText,byline,thumbnail,wordcount",
        }
        if section:
            params["section"] = section
        response = self._get("search", params)
        results = response.get("results", [])
        return [self._format_article(a) for a in results]

    def get_item(self, item_id, show_fields="all"):
        params = {"show-fields": show_fields}
        response = self._get(item_id, params)
        content = response.get("content", {})
        return self._format_article(content) if content else None

    def search_paged(self, query, max_pages=5, **kwargs):
        all_results = []
        for page in range(1, max_pages + 1):
            results = self.search(query, page=page, **kwargs)
            if not results:
                break
            all_results.extend(results)
        return all_results

    def _format_article(self, article):
        fields = article.get("fields", {})
        return {
            "id": article.get("id", ""),
            "title": fields.get("headline") or article.get("webTitle", ""),
            "section": article.get("sectionName", ""),
            "url": article.get("webUrl", ""),
            "date": article.get("webPublicationDate", ""),
            "author": fields.get("byline", ""),
            "summary": fields.get("trailText", ""),
            "wordcount": fields.get("wordcount", 0),
            "thumbnail": fields.get("thumbnail", ""),
        }

    def status(self):
        response = self._get("search", {"q": "test", "page-size": 1})
        if response.get("status") == "ok":
            return {"status": "OK", "total": response.get("total", 0)}
        return {"status": "FAIL"}


# Singleton für einfachen Import
_client = None


def get_client():
    global _client
    if _client is None:
        _client = GuardianNewsClient()
    return _client


def search_news(query, **kwargs):
    return get_client().search(query, **kwargs)


def get_article(item_id):
    return get_client().get_item(item_id)
