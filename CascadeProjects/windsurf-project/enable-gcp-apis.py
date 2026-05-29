#!/usr/bin/env python3
"""
Aktiviert GCP APIs via Service Usage REST API.
Benötigt: google-auth und requests (werden automatisch installiert).
Authentifizierung via OAuth 2.0 oder Service Account.
"""

import subprocess
import sys
import json
import time

APIs = [
    "agentregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "apphub.googleapis.com",
    "apptopology.googleapis.com",
    "cloudapiregistry.googleapis.com",
    "cloudtrace.googleapis.com",
    "compute.googleapis.com",
    "dataform.googleapis.com",
    "iam.googleapis.com",
    "iamconnectors.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "modelarmor.googleapis.com",
    "networksecurity.googleapis.com",
    "networkservices.googleapis.com",
    "notebooks.googleapis.com",
    "observability.googleapis.com",
    "storage-component.googleapis.com",
    "telemetry.googleapis.com",
    "texttospeech.googleapis.com",
]


def install_deps():
    """Installiert benötigte Pakete."""
    deps = ["google-auth", "google-auth-oauthlib", "requests"]
    print("Installiere Abhängigkeiten...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *deps])


DEFAULT_PROJECT = "gen-lang-client-0294112727"

def get_project_id():
    """Fragt nach der GCP Projekt-ID."""
    project = input(f"Gib deine GCP Projekt-ID ein [{DEFAULT_PROJECT}]: ").strip()
    if not project:
        project = DEFAULT_PROJECT
    return project


def get_access_token():
    """
    Versucht, ein Access Token zu bekommen.
    Optionen:
    1. Service Account JSON (empfohlen)
    2. gcloud auth (falls doch installiert)
    3. Manuelle Eingabe
    """
    import os
    import glob

    # Option 1: Service Account JSON Key
    home = os.path.expanduser("~")
    key_files = glob.glob(os.path.join(home, "Downloads", "*.json"))
    key_files += glob.glob(os.path.join(home, "*.json"))
    service_keys = [f for f in key_files if "service" in f.lower() or "key" in f.lower()]

    if service_keys:
        print(f"\nService Account Keys gefunden: {service_keys}")
        use_key = input("Service Account Key verwenden? (y/n): ").strip().lower()
        if use_key == "y":
            key_file = service_keys[0] if len(service_keys) == 1 else input("Pfad zur JSON-Datei: ").strip()
            return get_token_from_service_account(key_file)

    # Option 2: gcloud
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        print("Token via gcloud erhalten.")
        return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Option 3: Manuell
    print("\nKeine automatische Authentifizierung möglich.")
    print("Öffne: https://console.cloud.google.com/apis/credentials")
    print("Erstelle einen Service Account und lade den JSON Key herunter.")
    print("Oder gib einen Access Token manuell ein (gcloud auth print-access-token).")
    token = input("\nAccess Token (oder leer zum Beenden): ").strip()
    if not token:
        sys.exit(0)
    return token


def get_token_from_service_account(key_file):
    """Erzeugt ein Access Token aus einem Service Account Key."""
    from google.oauth2 import service_account
    from google.auth.transport import requests

    credentials = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = requests.Request()
    credentials.refresh(request)
    print(f"Token via Service Account erhalten: {key_file}")
    return credentials.token


def enable_api(project, api, token):
    """Aktiviert eine einzelne API."""
    import requests

    url = f"https://serviceusage.googleapis.com/v1/projects/{project}/services/{api}:enable"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, timeout=30)
        if response.status_code == 200:
            print(f"  ✓ {api}")
            return True
        elif response.status_code == 409:
            print(f"  ✓ {api} (bereits aktiviert)")
            return True
        else:
            print(f"  ✗ {api} — HTTP {response.status_code}: {response.text[:100]}")
            return False
    except Exception as e:
        print(f"  ✗ {api} — Fehler: {e}")
        return False


def main():
    print("=" * 60)
    print("GCP API Aktivierung")
    print("=" * 60)

    install_deps()

    project = get_project_id()
    token = get_access_token()

    print(f"\nAktiviere {len(APIs)} APIs für Projekt: {project}")
    print("-" * 60)

    success = 0
    failed = []

    for i, api in enumerate(APIs, 1):
        print(f"[{i}/{len(APIs)}] {api} ...", end=" ", flush=True)
        if enable_api(project, api, token):
            success += 1
        else:
            failed.append(api)
        # Rate limiting vermeiden
        time.sleep(0.5)

    print("-" * 60)
    print(f"\nErgebnis: {success}/{len(APIs)} APIs aktiviert.")

    if failed:
        print(f"\nFehlgeschlagen ({len(failed)}):")
        for api in failed:
            print(f"  - {api}")
        print("\nFür fehlgeschlagene APIs:")
        print(f"https://console.cloud.google.com/apis/library?project={project}")


if __name__ == "__main__":
    main()
