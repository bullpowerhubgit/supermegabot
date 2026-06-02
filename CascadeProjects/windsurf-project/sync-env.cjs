#!/usr/bin/env node

/**
 * Environment Sync Script
 * Synchronisiert alle .env Dateien mit der Master-Quelle (windsurf-project/.env)
 * Erstellt Backups vor dem Überschreiben
 */

const fs = require('fs');
const path = require('path');

const MASTER_ENV = '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/.env';
const SEARCH_DIRS = [
  '/Users/rudolfsarkany/supermegabot-windsurf-agents',
  '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects'
];
const BACKUP_DIR = '/Users/rudolfsarkany/supermegabot-windsurf-agents/env-backups';

console.log('🔧 ENVIRONMENT SYNC SCRIPT');
console.log('============================\n');

// Backup Verzeichnis erstellen
if (!fs.existsSync(BACKUP_DIR)) {
  fs.mkdirSync(BACKUP_DIR, { recursive: true });
  console.log('📁 Backup Verzeichnis erstellt:', BACKUP_DIR);
}

// Master .env lesen
if (!fs.existsSync(MASTER_ENV)) {
  console.error('❌ Master .env nicht gefunden:', MASTER_ENV);
  process.exit(1);
}

const masterContent = fs.readFileSync(MASTER_ENV, 'utf8');
console.log('✅ Master .env geladen:', MASTER_ENV);
console.log('   Zeilen:', masterContent.split('\n').length);

// Alle .env Dateien finden
const envFiles = [];

function findEnvFiles(dir) {
  if (!fs.existsSync(dir)) return;
  
  const items = fs.readdirSync(dir, { withFileTypes: true });
  
  for (const item of items) {
    const fullPath = path.join(dir, item.name);
    
    if (item.isDirectory()) {
      // node_modules und .git überspringen
      if (item.name !== 'node_modules' && item.name !== '.git') {
        findEnvFiles(fullPath);
      }
    } else if (item.name === '.env' && fullPath !== MASTER_ENV) {
      envFiles.push(fullPath);
    }
  }
}

SEARCH_DIRS.forEach(dir => findEnvFiles(dir));

console.log('\n📋 Gefundene .env Dateien:', envFiles.length);
envFiles.forEach((file, i) => {
  console.log(`   ${i + 1}. ${file}`);
});

if (envFiles.length === 0) {
  console.log('\nℹ️  Keine weiteren .env Dateien zum Synchronisieren gefunden.');
  process.exit(0);
}

// Synchronisation durchführen
console.log('\n🔄 Starte Synchronisation...\n');

let synced = 0;
let skipped = 0;

envFiles.forEach((envFile) => {
  try {
    const content = fs.readFileSync(envFile, 'utf8');
    
    // Backup erstellen
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupPath = path.join(BACKUP_DIR, `${path.basename(envFile)}-${timestamp}.backup`);
    fs.writeFileSync(backupPath, content);
    console.log(`   💾 Backup erstellt: ${backupPath}`);
    
    // Master Inhalt schreiben
    fs.writeFileSync(envFile, masterContent);
    console.log(`   ✅ Synchronisiert: ${envFile}`);
    synced++;
    
  } catch (error) {
    console.log(`   ❌ Fehler bei ${envFile}:`, error.message);
    skipped++;
  }
});

console.log('\n📊 ZUSAMMENFASSUNG');
console.log('==================');
console.log(`Synchronisiert: ${synced} ✅`);
console.log(`Übersprungen: ${skipped} ❌`);
console.log(`Backups gespeichert in: ${BACKUP_DIR}`);

if (synced > 0) {
  console.log('\n✅ Synchronisation abgeschlossen!');
} else {
  console.log('\n⚠️  Keine Dateien synchronisiert.');
}
