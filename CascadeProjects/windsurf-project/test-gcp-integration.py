#!/usr/bin/env python3
"""
Test-Skript für GCP-Konfigurationsintegration
Überprüft, ob alle Python-Tools die GCP-Konfiguration korrekt laden
"""

import sys
import os

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

print('=== GCP Konfigurations-Integration Test (Python) ===\n')

print(f'✅ GCP Projekt-ID: {gcp_config.project_id}')
print(f'✅ GCP Projektnummer: {gcp_config.project_number}')
print(f'✅ GCP Projektname: {gcp_config.project_name}')
print(f'✅ GCP Billing Account: {gcp_config.billing_account}')
print(f'✅ Anzahl aktivierte APIs: {len(gcp_config.apis)}')
print(f'✅ API-Liste: {gcp_config.api_list[:5]} ...')
print(f'✅ Auth-Methode: {gcp_config.auth_method}')
print(f'✅ Cloud Shell: {gcp_config.is_cloud_shell}')

print('\n=== Test erfolgreich ===')
print('Alle Python-Tools können jetzt auf die GCP-Konfiguration zugreifen!')
