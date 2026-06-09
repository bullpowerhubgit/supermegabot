/**
 * Dodge/Chrysler DTC-Fehlercode Datenbank
 * Open Source, pure JavaScript
 * Speziell fuer Dodge Challenger 2010 V6
 */

const DTC_CODES = {
  // Motor (P0xxx)
  "P0300": { desc: "Random/Multiple Cylinder Misfire", severity: "HIGH", system: "Engine" },
  "P0301": { desc: "Cylinder 1 Misfire", severity: "HIGH", system: "Engine" },
  "P0302": { desc: "Cylinder 2 Misfire", severity: "HIGH", system: "Engine" },
  "P0303": { desc: "Cylinder 3 Misfire", severity: "HIGH", system: "Engine" },
  "P0304": { desc: "Cylinder 4 Misfire", severity: "HIGH", system: "Engine" },
  "P0305": { desc: "Cylinder 5 Misfire", severity: "HIGH", system: "Engine" },
  "P0306": { desc: "Cylinder 6 Misfire", severity: "HIGH", system: "Engine" },
  "P0420": { desc: "Catalyst Efficiency Below Threshold (Bank 1)", severity: "MEDIUM", system: "Emission" },
  "P0432": { desc: "Main Catalyst Efficiency Below Threshold (Bank 2)", severity: "MEDIUM", system: "Emission" },
  "P0456": { desc: "EVAP System Small Leak", severity: "LOW", system: "Emission" },
  "P0457": { desc: "EVAP System Leak (Fuel Cap)", severity: "LOW", system: "Emission" },
  "P1521": { desc: "Incorrect Engine Oil Type", severity: "LOW", system: "Engine" },
  // 3.5L V6 SPEZIFISCH!
  "P1004": { desc: "Short Runner Valve Control Performance", severity: "MEDIUM", system: "Engine", note: "3.5L V6 SPECIFIC!" },
  "P1005": { desc: "Short Runner Valve Control Circuit", severity: "MEDIUM", system: "Engine", note: "3.5L V6 SPECIFIC!" },
  "P1006": { desc: "Short Runner Valve Control Circuit Low", severity: "MEDIUM", system: "Engine", note: "3.5L V6 SPECIFIC!" },
  "P1007": { desc: "Short Runner Valve Control Circuit High", severity: "MEDIUM", system: "Engine", note: "3.5L V6 SPECIFIC!" },
  "P2004": { desc: "Intake Manifold Runner Stuck Open (Bank 1)", severity: "MEDIUM", system: "Engine" },
  "P2008": { desc: "Intake Manifold Runner Circuit Open (Bank 1)", severity: "MEDIUM", system: "Engine" },
  "P2017": { desc: "Intake Manifold Runner Position Sensor Circuit High", severity: "MEDIUM", system: "Engine" },
  // Getriebe (P07xx)
  "P0700": { desc: "Transmission Control System (MIL)", severity: "HIGH", system: "Transmission" },
  "P0731": { desc: "Gear 1 Incorrect Ratio", severity: "HIGH", system: "Transmission" },
  "P0732": { desc: "Gear 2 Incorrect Ratio", severity: "HIGH", system: "Transmission" },
  "P0733": { desc: "Gear 3 Incorrect Ratio", severity: "HIGH", system: "Transmission" },
  "P0868": { desc: "Line Pressure Low", severity: "HIGH", system: "Transmission" },
  "P0882": { desc: "TCM Power Input Signal Low", severity: "HIGH", system: "Transmission" },
  "P0884": { desc: "TCM Power Input Signal Intermittent", severity: "MEDIUM", system: "Transmission" },
  // Kommunikation (U0xxx, U1xxx - Chrysler spezifisch!)
  "U0100": { desc: "Lost Communication With ECM/PCM", severity: "HIGH", system: "Network" },
  "U0101": { desc: "Lost Communication With TCM", severity: "HIGH", system: "Network" },
  "U0140": { desc: "Lost Communication With BCM", severity: "HIGH", system: "Network" },
  "U110C": { desc: "Lost Fuel Level Message", severity: "MEDIUM", system: "Network", note: "CHRYSLER/DODGE SPECIFIC!" },
  "U1110": { desc: "Lost Vehicle Speed Message", severity: "MEDIUM", system: "Network", note: "CHRYSLER/DODGE SPECIFIC!" },
  "U1411": { desc: "Implausible Fuel Volume Signal", severity: "MEDIUM", system: "Network", note: "CHRYSLER/DODGE SPECIFIC!" },
  "U1412": { desc: "Implausible Vehicle Speed Signal", severity: "MEDIUM", system: "Network", note: "CHRYSLER/DODGE SPECIFIC!" },
};

// Challenger 2010 V6 spezifische PIDs
const CHALLENGER_PIDS = {
  "010C": { name: "Engine RPM", unit: "rpm", min: 0, max: 7000, warn: 6500 },
  "010D": { name: "Vehicle Speed", unit: "km/h", min: 0, max: 260, warn: 200 },
  "0105": { name: "Coolant Temperature", unit: "°C", min: -40, max: 150, warn: 110 },
  "0104": { name: "Engine Load", unit: "%", min: 0, max: 100, warn: 95 },
  "0110": { name: "MAF Flow", unit: "g/s", min: 0, max: 300, warn: 250 },
  "012F": { name: "Fuel Level", unit: "%", min: 0, max: 100, warn: 10 },
  "015C": { name: "Engine Oil Temp", unit: "°C", min: -40, max: 200, warn: 130 },
};

function lookupDTC(code) {
  const upper = code.toUpperCase().trim();
  return DTC_CODES[upper] || { desc: "Unknown code", severity: "UNKNOWN", system: "Unknown" };
}

function getAllDTCCodes() {
  return Object.keys(DTC_CODES);
}

function getChallengerPIDs() {
  return CHALLENGER_PIDS;
}

module.exports = { DTC_CODES, CHALLENGER_PIDS, lookupDTC, getAllDTCCodes, getChallengerPIDs };

// CLI Demo
if (require.main === module) {
  console.log("========================================");
  console.log("  DODGE/CHRYSLER DTC DATABASE");
  console.log("  Challenger 2010 V6 Edition");
  console.log("========================================\n");
  console.log("Total DTC Codes:", Object.keys(DTC_CODES).length);
  console.log("Challenger specific:", Object.values(DTC_CODES).filter(c => c.note).length);
  console.log("\nExample lookups:");
  console.log("  P1004:", lookupDTC("P1004"));
  console.log("  U110C:", lookupDTC("U110C"));
  console.log("\nChallenger PIDs:", Object.keys(CHALLENGER_PIDS).length);
  console.log("  RPM PID:", CHALLENGER_PIDS["010C"]);
}
