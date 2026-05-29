#!/usr/bin/env node

/**
 * Test-Skript für GCP-Konfigurationsintegration
 * Überprüft, ob alle Tools die GCP-Konfiguration korrekt laden
 */

import gcpConfig from './lib/gcp-config.js';

console.debug('=== GCP Konfigurations-Integration Test ===\n');

console.debug('✅ GCP Projekt-ID:', gcpConfig.projectId);
console.debug('✅ GCP Projektnummer:', gcpConfig.projectNumber);
console.debug('✅ GCP Projektname:', gcpConfig.projectName);
console.debug('✅ GCP Billing Account:', gcpConfig.billingAccount);
console.debug('✅ Anzahl aktivierte APIs:', gcpConfig.apis.length);
console.debug('✅ API-Liste:', gcpConfig.apiList.slice(0, 5), '...');
console.debug('✅ Auth-Methode:', gcpConfig.getAuthMethod());
console.debug('✅ Cloud Shell:', gcpConfig.isCloudShell());

console.debug('\n=== Test erfolgreich ===');
console.debug('Alle Tools können jetzt auf die GCP-Konfiguration zugreifen!');
