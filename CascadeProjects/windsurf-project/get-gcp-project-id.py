#!/usr/bin/env python3
"""
GCP Project ID auslesen
"""

import json
import os
from pathlib import Path

def get_project_id():
    config_path = Path('RudiBot-Secure-API/gcp-config.json')
    
    if not config_path.exists():
        print("❌ GCP-Konfiguration nicht gefunden")
        return None
    
    try:
        with open(config_path) as f:
            config = json.load(f)
        
        project_id = config['project']['id']
        print(f"✅ Projekt-ID: {project_id}")
        return project_id
    except Exception as e:
        print(f"❌ Fehler beim Lesen: {e}")
        return None

if __name__ == "__main__":
    project_id = get_project_id()
    if project_id:
        print(f"export GCP_PROJECT_ID='{project_id}'")
