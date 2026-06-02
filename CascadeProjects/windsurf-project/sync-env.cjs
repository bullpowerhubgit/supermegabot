#!/usr/bin/env node

/**
 * A-Z Configuration Sync Script
 * Synchronisiert ALLE Konfigurationen mit Master-Quellen:
 * - .env Dateien
 * - config.json Dateien
 * - MCP Configs
 * - Bot-Konfigurationen
 * - Ecosystem Configs
 */

const fs = require('fs');
const path = require('path');

// Master-Quellen definieren
const MASTERS = {
  env: '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/.env',
  apiConfig: '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/api-config.json',
  gcpConfig: '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/RudiBot-Secure-API/gcp-config.json',
  mcpConfig: '/Users/rudolfsarkany/Downloads/windsurf-mcp-config.json',
  ecosystem: '/Users/rudolfsarkany/supermegabot-windsurf-agents/ecosystem.config.js'
};

const SEARCH_DIRS = [
  '/Users/rudolfsarkany/supermegabot-windsurf-agents',
  '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects'
];

const BACKUP_DIR = '/Users/rudolfsarkany/supermegabot-windsurf-agents/sync-backups';

console.log('🔧 A-Z CONFIGURATION SYNC SCRIPT');
console.log('================================\n');

// Backup Verzeichnis erstellen
if (!fs.existsSync(BACKUP_DIR)) {
  fs.mkdirSync(BACKUP_DIR, { recursive: true });
  console.log('📁 Backup Verzeichnis erstellt:', BACKUP_DIR);
}

// Ergebnisse Tracking
const results = {
  env: { found: 0, synced: 0, skipped: 0 },
  config: { found: 0, synced: 0, skipped: 0 },
  mcp: { found: 0, synced: 0, skipped: 0 },
  ecosystem: { found: 0, synced: 0, skipped: 0 }
};

// Hilfsfunktion: Backup erstellen
function createBackup(filePath, content) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupName = `${path.basename(filePath)}-${timestamp}.backup`;
  const backupPath = path.join(BACKUP_DIR, backupName);
  fs.writeFileSync(backupPath, content);
  return backupPath;
}

// Hilfsfunktion: Datei synchronisieren
function syncFile(masterPath, targetPath, type) {
  try {
    if (!fs.existsSync(masterPath)) {
      console.log(`   ⚠️  Master nicht gefunden: ${masterPath}`);
      results[type].skipped++;
      return;
    }

    if (!fs.existsSync(targetPath)) {
      console.log(`   ⚠️  Target nicht gefunden: ${targetPath}`);
      results[type].skipped++;
      return;
    }

    const masterContent = fs.readFileSync(masterPath, 'utf8');
    const targetContent = fs.readFileSync(targetPath, 'utf8');

    // Prüfen ob bereits identisch
    if (masterContent === targetContent) {
      console.log(`   ℹ️  Bereits identisch: ${targetPath}`);
      results[type].skipped++;
      return;
    }

    // Backup erstellen
    const backupPath = createBackup(targetPath, targetContent);
    console.log(`   💾 Backup: ${backupPath}`);

    // Master Inhalt schreiben
    fs.writeFileSync(targetPath, masterContent);
    console.log(`   ✅ Synchronisiert: ${targetPath}`);
    results[type].synced++;

  } catch (error) {
    console.log(`   ❌ Fehler bei ${targetPath}:`, error.message);
    results[type].skipped++;
  }
}

// .env Dateien synchronisieren
console.log('📋 .env Dateien synchronisieren...\n');
if (fs.existsSync(MASTERS.env)) {
  const masterEnv = fs.readFileSync(MASTERS.env, 'utf8');
  console.log(`✅ Master .env geladen (${masterEnv.split('\n').length} Zeilen)`);

  function findEnvFiles(dir) {
    if (!fs.existsSync(dir)) return;
    const items = fs.readdirSync(dir, { withFileTypes: true });
    
    for (const item of items) {
      const fullPath = path.join(dir, item.name);
      if (item.isDirectory()) {
        if (item.name !== 'node_modules' && item.name !== '.git') {
          findEnvFiles(fullPath);
        }
      } else if (item.name === '.env' && fullPath !== MASTERS.env) {
        results.env.found++;
        syncFile(MASTERS.env, fullPath, 'env');
      }
    }
  }

  SEARCH_DIRS.forEach(dir => findEnvFiles(dir));
}

// config.json Dateien synchronisieren
console.log('\n📋 config.json Dateien synchronisieren...\n');
if (fs.existsSync(MASTERS.apiConfig)) {
  console.log('✅ Master api-config.json geladen');
  
  function findConfigFiles(dir) {
    if (!fs.existsSync(dir)) return;
    const items = fs.readdirSync(dir, { withFileTypes: true });
    
    for (const item of items) {
      const fullPath = path.join(dir, item.name);
      if (item.isDirectory()) {
        if (item.name !== 'node_modules' && item.name !== '.git' && item.name !== 'backups') {
          findConfigFiles(fullPath);
        }
      } else if (item.name === 'api-config.json' && fullPath !== MASTERS.apiConfig) {
        results.config.found++;
        syncFile(MASTERS.apiConfig, fullPath, 'config');
      }
    }
  }

  SEARCH_DIRS.forEach(dir => findConfigFiles(dir));
}

// GCP Config synchronisieren
console.log('\n� GCP Config synchronisieren...\n');
if (fs.existsSync(MASTERS.gcpConfig)) {
  console.log('✅ Master gcp-config.json geladen');
  
  const gcpTargets = [
    '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/gcp-config.json'
  ];

  gcpTargets.forEach(target => {
    if (fs.existsSync(target) && target !== MASTERS.gcpConfig) {
      results.config.found++;
      syncFile(MASTERS.gcpConfig, target, 'config');
    }
  });
}

// MCP Config synchronisieren
console.log('\n📋 MCP Config synchronisieren...\n');
if (fs.existsSync(MASTERS.mcpConfig)) {
  console.log('✅ Master MCP Config geladen');
  
  function findMcpConfigs(dir) {
    if (!fs.existsSync(dir)) return;
    const items = fs.readdirSync(dir, { withFileTypes: true });
    
    for (const item of items) {
      const fullPath = path.join(dir, item.name);
      if (item.isDirectory()) {
        if (item.name !== 'node_modules' && item.name !== '.git') {
          findMcpConfigs(fullPath);
        }
      } else if (item.name.includes('mcp-config.json') && fullPath !== MASTERS.mcpConfig) {
        results.mcp.found++;
        syncFile(MASTERS.mcpConfig, fullPath, 'mcp');
      }
    }
  }

  SEARCH_DIRS.forEach(dir => findMcpConfigs(dir));
}

// Ecosystem Config synchronisieren
console.log('\n📋 Ecosystem Config synchronisieren...\n');
if (fs.existsSync(MASTERS.ecosystem)) {
  console.log('✅ Master ecosystem.config.js geladen');
  
  const ecosystemTargets = [
    '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/ecosystem.config.js'
  ];

  ecosystemTargets.forEach(target => {
    if (fs.existsSync(target) && target !== MASTERS.ecosystem) {
      results.ecosystem.found++;
      syncFile(MASTERS.ecosystem, target, 'ecosystem');
    }
  });
}

// Zusammenfassung
console.log('\n📊 ZUSAMMENFASSUNG');
console.log('==================');
console.log(`.env Dateien: ${results.env.synced} synchronisiert, ${results.env.skipped} übersprungen`);
console.log(`config.json: ${results.config.synced} synchronisiert, ${results.config.skipped} übersprungen`);
console.log(`MCP Configs: ${results.mcp.synced} synchronisiert, ${results.mcp.skipped} übersprungen`);
console.log(`Ecosystem: ${results.ecosystem.synced} synchronisiert, ${results.ecosystem.skipped} übersprungen`);
console.log(`\n💾 Backups gespeichert in: ${BACKUP_DIR}`);

const totalSynced = results.env.synced + results.config.synced + results.mcp.synced + results.ecosystem.synced;
if (totalSynced > 0) {
  console.log('\n✅ A-Z Synchronisation abgeschlossen!');
} else {
  console.log('\nℹ️  Alle Dateien bereits auf dem neuesten Stand.');
}
