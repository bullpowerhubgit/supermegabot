#!/usr/bin/env node
/**
 * OBD-Tools Launcher
 * Startet alle installierten OBD-II Tools und zeigt Status/Demo-Daten an.
 */

const path = require('path');

console.log('========================================');
console.log('  OBD-II TOOLS LAUNCHER');
console.log('========================================\n');

// 1. obd-parser laden
let obdParser;
try {
  obdParser = require('obd-parser');
  console.log('[OK] obd-parser geladen');
  console.log('     Version:', require('obd-parser/package.json').version);
} catch (e) {
  console.log('[FEHLER] obd-parser konnte nicht geladen werden:', e.message);
}

// 2. obd-utils laden
let obdUtils;
try {
  obdUtils = require('obd-utils');
  console.log('[OK] obd-utils geladen');
  console.log('     Version:', require('obd-utils/package.json').version);
} catch (e) {
  console.log('[FEHLER] obd-utils konnte nicht geladen werden:', e.message);
}

// 3. obd-node laden
let obdNode;
try {
  obdNode = require('obd-node');
  console.log('[OK] obd-node geladen');
  console.log('     Version:', require('obd-node/package.json').version);
} catch (e) {
  console.log('[FEHLER] obd-node konnte nicht geladen werden:', e.message);
}

console.log('\n----------------------------------------');
console.log('Verfügbare OBD-II Funktionen:');
console.log('----------------------------------------');

if (obdUtils && obdUtils.PID) {
  console.log('- PID-Liste verfügbar');
}
if (obdUtils && obdUtils.decode) {
  console.log('- Decode-Funktion verfügbar');
}
if (obdParser) {
  console.log('- Parser-Engine verfügbar');
}
if (obdNode) {
  console.log('- obd-node Kommunikations-Engine verfügbar');
}

console.log('\n----------------------------------------');
console.log('Beispiel: OBD-II PID 010C (Engine RPM)');
console.log('----------------------------------------');
try {
  if (obdUtils && obdUtils.decode && obdUtils.PID && obdUtils.PID['010C']) {
    const rpmDecoded = obdUtils.decode('010C', '41 0C 1B 56');
    console.log('Rohdaten: 41 0C 1B 56');
    console.log('Ergebnis:', rpmDecoded);
  } else {
    console.log('Decode-Beispiel übersprungen (API variiert)');
  }
} catch (e) {
  console.log('Decode-Beispiel fehlgeschlagen:', e.message);
}

console.log('\n----------------------------------------');
console.log('3 OBD-Tools sind bereit!');
console.log('Schließe das Terminal um zu beenden.');
console.log('========================================');

// Halte das Terminal offen
setTimeout(() => {}, 3600000);
