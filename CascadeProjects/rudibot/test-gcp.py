#!/usr/bin/env python3
"""
GCP Config Loader & API Tester
Reads gcp-config.json and tests API keys
"""
import json
import urllib.request
import urllib.error

# Load config
with open('/Users/rudolfsarkany/CascadeProjects/rudibot/RudiBot-Secure-API/gcp-config.json') as f:
    config = json.load(f)

project_id = config['project']['id']
print(f"GCP Project ID: {project_id}")

# Test YouTube API
youtube_key = config['apis']['youtube']['api_key']
print(f"\nYouTube API Key: {youtube_key[:20]}...")

try:
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id=UCy5U7UGOMNkvUR2-5Qm4yiA&key={youtube_key}"
    req = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode('utf-8'))
        if 'items' in data:
            print("✅ YouTube API: GÜLTIG")
        else:
            print("❌ YouTube API: UNGÜLTIG -", data.get('error', {}).get('message', 'Unknown error'))
except Exception as e:
    print(f"❌ YouTube API: FEHLER - {str(e)[:60]}")

# Test Google AI API
google_key = config['apis']['google_ai']['api_key']
print(f"\nGoogle AI API Key: {google_key[:20]}...")

try:
    url = f"https://generativelanguage.googleapis.com/v1/models?key={google_key}"
    req = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode('utf-8'))
        if 'models' in data:
            print("✅ Google AI API: GÜLTIG")
        else:
            print("❌ Google AI API: UNGÜLTIG")
except Exception as e:
    print(f"❌ Google AI API: FEHLER - {str(e)[:60]}")

print(f"\n{'='*50}")
print("GCP CONFIG TEST ABGESCHLOSSEN")
