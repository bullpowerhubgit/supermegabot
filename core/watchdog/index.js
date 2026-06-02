/**
 * Watchdog System — Windsurf Integration
 * 
 * Files:
 *   watchdog.js          — MemoryWatchdog v1 (process + memory monitoring)
 *   watchdog-v2.js       — Enhanced watchdog with auto-restart capabilities
 *   watchdog-monitor-server.js — HTTP monitoring server (port 9003)
 *   watchdog-dashboard.js — Dashboard UI for watchdog status
 *
 * Usage:
 *   node watchdog-v2.js              # Recommended production watchdog
 *   node watchdog-monitor-server.js  # Monitoring API at :9003
 */

export { default as WatchdogV2 } from './watchdog-v2.js';
export { default as WatchdogMonitorServer } from './watchdog-monitor-server.js';
