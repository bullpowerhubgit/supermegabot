#!/usr/bin/env python3
"""
Guardian News Module
Einfaches News-Modul für SuperMegaBot
"""

import logging
import os
import json
import urllib.request
from typing import List, Dict, Any

log = logging.getLogger(__name__)

def search_news(query: str = "technology", page_size: int = 3) -> List[Dict[str, Any]]:
    """
    Suche nach News (Mock/Demo oder via Guardian API)
    
    Args:
        query: Suchbegriff
        page_size: Anzahl Ergebnisse
    
    Returns:
        Liste von News-Artikeln
    """
    # Prüfe ob Guardian API Key vorhanden
    api_key = os.getenv('GUARDIAN_NEWS_API_KEY', '')
    
    if api_key and api_key != 'guardian_news_api_key_2026_secure':
        # Echte Guardian API
        try:
            url = f"https://content.guardianapis.com/search?q={query}&page-size={page_size}&api-key={api_key}"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                return [
                    {
                        'title': result['webTitle'],
                        'url': result['webUrl'],
                        'date': result.get('webPublicationDate', ''),
                        'section': result.get('sectionName', '')
                    }
                    for result in data.get('response', {}).get('results', [])
                ]
        except Exception as e:
            log.error("Guardian API Fehler: %s", e)
    
    # Fallback: Demo-Daten
    return [
        {
            'title': f'{query.title()} News #{i+1}',
            'url': f'https://example.com/{query}/{i+1}',
            'date': '2026-06-03',
            'section': query.title()
        }
        for i in range(page_size)
    ]

if __name__ == "__main__":
    results = search_news('technology', page_size=3)
    for r in results:
        print(f"📰 {r['title']}")
