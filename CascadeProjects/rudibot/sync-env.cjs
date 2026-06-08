#!/usr/bin/env node
// sync-env.cjs — Synchronisiert .env von Master-Quelle zu allen Bot-Projekten
const fs = require('fs');
const path = require('path');

// Master-Quelle: supermegabot-windsurf-agents/.env
const MASTER_ENV = path.join(__dirname, '..', '..', 'supermegabot-windsurf-agents', '.env');

// Ziel-Projekte für Sync
const TARGET_PROJECTS = [
  { name: 'windsurf-telegram-bot', path: path.join(__dirname, 'windsurf-telegram-bot', '.env') },
  { name: 'telegram-automation-bot', path: path.join(__dirname, 'telegram-automation-bot', '.env') }
];

if (!fs.existsSync(MASTER_ENV)) {
  console.error('❌ Master .env nicht gefunden:', MASTER_ENV);
  process.exit(1);
}

const envContent = fs.readFileSync(MASTER_ENV, 'utf-8');
let copied = 0;
let skipped = 0;
let failed = 0;

console.log('🔄 MASTER-SYNC gestartet...');
console.log(`📂 Quelle: ${MASTER_ENV}`);
console.log('');

for (const project of TARGET_PROJECTS) {
  const targetDir = path.dirname(project.path);
  
  if (!fs.existsSync(targetDir)) {
    console.log(`⚠️  ${project.name} — Verzeichnis nicht gefunden, überspringe`);
    skipped++;
    continue;
  }

  try {
    fs.writeFileSync(project.path, envContent);
    console.log(`✅ ${project.name}/.env synchronisiert`);
    copied++;
  } catch (error) {
    console.log(`❌ ${project.name}/.env — Fehler: ${error.message}`);
    failed++;
  }
}

console.log('');
console.log(`📊 Ergebnis: ${copied} synchronisiert, ${skipped} übersprungen, ${failed} fehlgeschlagen`);
console.log('✨ Alle .env Dateien sind jetzt konsistent mit Master-Quelle');
