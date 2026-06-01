#!/usr/bin/env python3
"""
Get API Key String for Google Cloud API Key
Uses Google Cloud API directly to retrieve the key string
"""

import subprocess
import sys
import json
import os

def install_deps():
    """Install required packages"""
    deps = ["google-auth", "google-auth-oauthlib", "requests"]
    print("Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *deps])

def get_access_token():
    """Get access token for authentication"""
    import glob
    
    # Try Service Account JSON Key first
    home = os.path.expanduser("~")
    key_files = glob.glob(os.path.join(home, "Downloads", "*.json"))
    key_files += glob.glob(os.path.join(home, "*.json"))
    service_keys = [f for f in key_files if "service" in f.lower() or "key" in f.lower()]
    
    if service_keys:
        print(f"\nService Account Keys found: {service_keys}")
        use_key = input("Use Service Account Key? (y/n): ").strip().lower()
        if use_key == "y":
            key_file = service_keys[0] if len(service_keys) == 1 else input("Path to JSON file: ").strip()
            return get_token_from_service_account(key_file)
    
    # Try gcloud
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        print("Token obtained via gcloud.")
        return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Manual input
    print("\nNo automatic authentication available.")
    print("Open: https://console.cloud.google.com/apis/credentials")
    print("Create a Service Account and download the JSON Key.")
    token = input("\nAccess Token: ").strip()
    return token

def get_token_from_service_account(key_file):
    """Get access token from service account key"""
    from google.oauth2 import service_account
    from google.auth.transport import requests
    
    credentials = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = requests.Request()
    credentials.refresh(request)
    print(f"Token obtained via Service Account: {key_file}")
    return credentials.token

def get_api_key_string(project_id, key_id, token):
    """Get the actual API key string"""
    import requests
    
    # Convert key format if needed
    if "/" not in key_id:
        key_id = f"projects/{project_id}/locations/global/keys/{key_id}"
    
    url = f"https://apikeys.googleapis.com/v2/{key_id}:getKeyString"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            key_string = result.get("keyString")
            if key_string:
                print(f"\n✓ API Key String retrieved successfully!")
                print(f"Key: {key_string}")
                return key_string
            else:
                print("✗ No keyString in response")
                return None
        else:
            print(f"✗ Error - HTTP {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def main():
    print("=" * 60)
    print("Get API Key String")
    print("=" * 60)
    
    install_deps()
    
    # Load project from central config
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
    from gcp_config import gcp_config
    
    project_id = gcp_config.project_id
    key_id = "abc123def456"  # The key you want to retrieve
    
    print(f"\nProject ID: {project_id}")
    print(f"Key ID: {key_id}")
    
    token = get_access_token()
    key_string = get_api_key_string(project_id, key_id, token)
    
    if key_string:
        print(f"\nSuccess! API Key String: {key_string}")
    else:
        print("\nFailed to retrieve API key string")

if __name__ == "__main__":
    main()
