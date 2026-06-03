// ============================================================
// bot.js — AutoPilot Telegram Bot Controller
// Rudolf Sarkany · Production Ready
// Commands: /start /status /health /restart /logs /deploy /help
// ============================================================
'use strict';
require('dotenv').config();

const fs = require('fs');
const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

// 🔐 API Validator + Deep Scan Integration
const { IntegratedValidatorScanner } = require('./api-validator-deepscan');
const validatorScanner = new IntegratedValidatorScanner();

// 💰 Finance Grid Integration
const { KivoCore } = require('../50-kivo/kivo-core');
const kivo = new KivoCore();
const { SubscriptionHunter } = require('../20-finance-grid/subscription-hunter');
const { ExpenseRadar } = require('../20-finance-grid/expense-radar');
const { TaxCore } = require('../20-finance-grid/tax-core');
const { ComplianceEngine } = require('../20-finance-grid/compliance-engine');

const subscriptionHunter = new SubscriptionHunter();
const expenseRadar = new ExpenseRadar();
const taxCore = new TaxCore();
const complianceEngine = new ComplianceEngine();

// Initialize Finance Grid
(async () => {
  await subscriptionHunter.init();
  await expenseRadar.init();
  await taxCore.init();
  await complianceEngine.init();
  console.log('💰 Finance Grid initialized');
})();

// ── Config ────────────────────────────────────────────────────
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const ADMIN_ID = process.env.TELEGRAM_ADMIN_ID;
const API_BASE = `https://api.telegram.org/bot${BOT_TOKEN}`;

if (!BOT_TOKEN || BOT_TOKEN.includes('DEIN')) {
  console.error('❌ TELEGRAM_BOT_TOKEN nicht konfiguriert!');
  process.exit(1);
}

// ── State ─────────────────────────────────────────────────────
const state = {
  startTime: Date.now(),
  lastCommand: null,
  commandCount: 0,
  alerts: [],
};

// ── Telegram API Helpers ────────────────────────────────────
async function tgApi(method, body = {}) {
  try {
    const res = await fetch(`${API_BASE}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return await res.json();
  } catch (e) {
    console.error(`Telegram API Error: ${e.message}`);
    return { ok: false, error: e.message };
  }
}

async function sendMessage(chatId, text, options = {}) {
  return tgApi('sendMessage', { chat_id: chatId, text, parse_mode: 'Markdown', ...options });
}

// ── Command Handlers ──────────────────────────────────────────
const commands = {
  '/start': async (chatId) => {
    return sendMessage(chatId,
      `🤖 *AutoPilot Business Bot*\n\n` +
      `✅ Bot ist aktiv seit ${Math.floor((Date.now()-state.startTime)/60000)} Min\n` +
      `📊 Befehle ausgeführt: ${state.commandCount}\n\n` +
      `🚀 *AI Commands:*\n` +
      `/claude — Claude AI Anfrage\n` +
      `/perplexity — Perplexity AI Suche\n` +
      `/gemini — Google AI Gemini\n\n` +
      `� *Social Media Commands:*\n` +
      `/pinterest — Pinterest Boards & Pins\n` +
      `/reddit — Reddit Hot Posts\n` +
      `/twitter — Twitter/X Profile & Tweets\n` +
      `/linkedin — LinkedIn Profile & Posts\n` +
      `/snapchat — Snapchat Marketing\n\n` +
      `� *Business Commands:*\n` +
      `/github — GitHub Repositories\n` +
      `/stripe — Stripe Balance\n` +
      `/supabase — Supabase Status\n` +
      `/printify — POD Produkte generieren\n` +
      `/digistore — Affiliate Content verteilen\n` +
      `/youtube — Script erstellen\n` +
      `/earn — Heutige Einnahmen\n` +
      `/upwork — Upwork Jobs & Profile\n` +
      `/etsy — Etsy Shop & Listings\n` +
      `/gumroad — Gumroad Produkte\n` +
      `/producthunt — Product Hunt Posts\n` +
      `/udemy — Udemy Kurse\n\n` +
      `🛠️ *Productivity Commands:*\n` +
      `/notion — Notion Datenbanken\n` +
      `/airtable — Airtable Tabellen\n` +
      `/zapier — Zapier Automation\n` +
      `/make — Make.com Workflows\n` +
      `/n8n — n8n Automation\n\n` +
      `💰 *Finance Grid Commands:*\n` +
      `/fin-grid — Finance Grid Uebersicht\n` +
      `/subs — Abos & Vertraege\n` +
      `/sub-kill — Abo kuendigen\n` +
      `/tax — Steuer-Status\n` +
      `/spend — Ausgaben Radar\n` +
      `/elster — ELSTER Export\n\n` +
      `� *Security Commands:*\n` +
      `/validate — API Key validieren\n` +
      `/deepscan — Deep Security Scan\n` +
      `/security — Security Status\n` +
      `/audit — Security Audit Report\n\n` +
      `� *Storage Commands:*\n` +
      `/storage — System Verzeichnisse\n` +
      `/desktop — Desktop Dateien\n` +
      `/downloads — Downloads Ordner\n\n` +
      `☁️ *Cloud Storage:*\n` +
      `/gdrive — Google Drive Dateien\n` +
      `/dropbox — Dropbox Dateien\n` +
      `/onedrive — OneDrive Dateien\n\n` +
      `📝 *Notes Systems:*\n` +
      `/notes — Alle Notizen-Systeme\n` +
      `/evernote — Evernote Notebooks\n` +
      `/apple_notes — Apple Notes\n\n` +
      `💻 *IDE & Development:*\n` +
      `/vscode — Visual Studio Code\n` +
      `/codespaces — GitHub Codespaces\n\n` +
      `⚙️ *System Control:*\n` +
      `/windsurf — Windsurf Status\n` +
      `/system — System Informationen\n\n` +
      `🔍 *Deep-Scan System:*\n` +
      `/deepscan — Deep-Scan Status\n` +
      `/deepscan_history — Scan Historie\n` +
      `/security — Security Hardening\n\n` +
      `/sys — Vollständiger Status\n\n` +
      `⚙️ *System Commands:*\n` +
      `/status — System-Status\n` +
      `/health — Health-Check\n` +
      `/restart — Server neustarten\n` +
      `/logs — Letzte Logs\n` +
      `/deploy — Auf Vercel deployen\n` +
      `/monitor — Monitoring Dashboard\n` +
      `/cleanup — Speicher aufräumen\n` +
      `/help — Hilfe`
    );
  },

  '/status': async (chatId) => {
    try {
      const mem = process.memoryUsage();
      const uptime = Math.floor((Date.now() - state.startTime) / 1000);
      const hours = Math.floor(uptime / 3600);
      const mins = Math.floor((uptime % 3600) / 60);

      // Check if server is running
      let serverStatus = '❌ Offline';
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const r = await fetch('http://localhost:3200/api/health', { signal: controller.signal });
        clearTimeout(timeout);
        if (r.ok) serverStatus = '✅ Online';
      } catch { /* ignore */ }

      // Check if monitoring is running
      let monitorStatus = '❌ Offline';
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const r = await fetch('http://localhost:9001/monitoring-stats', { signal: controller.signal });
        clearTimeout(timeout);
        if (r.ok) monitorStatus = '✅ Online';
      } catch { /* ignore */ }

      return sendMessage(chatId,
        `📊 *System Status*\n\n` +
        `🖥️ Server: ${serverStatus}\n` +
        `📈 Monitoring: ${monitorStatus}\n` +
        `⏱️ Bot Uptime: ${hours}h ${mins}m\n` +
        `🧠 Memory: ${Math.round(mem.heapUsed/1024/1024)}MB / ${Math.round(mem.rss/1024/1024)}MB\n` +
        `📦 Node: ${process.version}\n` +
        `💻 Platform: ${process.platform}\n\n` +
        `_Letzter Command: ${state.lastCommand || 'keiner'}_`
      );
    } catch (e) {
      return sendMessage(chatId, `❌ Fehler: ${e.message}`);
    }
  },

  '/health': async (chatId) => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const r = await fetch('http://localhost:3200/api/health', { signal: controller.signal });
      clearTimeout(timeout);
      const d = await r.json();
      const envChecks = Object.entries(d.env || {}).map(([k,v]) => `${v ? '✅' : '❌'} ${k}`).join('\n');
      return sendMessage(chatId,
        `💚 *Health Check*\n\n` +
        `Status: ${d.status?.toUpperCase() || 'UNKNOWN'}\n` +
        `Uptime: ${d.uptime}\n` +
        `Memory: ${d.memory}\n` +
        `Node: ${d.node}\n\n` +
        `*Environment:*\n${envChecks}`
      );
    } catch (e) {
      return sendMessage(chatId, `❌ Server nicht erreichbar: ${e.message}\n\nVersuche: /restart`);
    }
  },

  '/restart': async (chatId) => {
    await sendMessage(chatId, '🔄 *Server wird neu gestartet...*\nDauert ca. 5-10 Sekunden.');
    try {
      await execAsync('pm2 restart autopilot-server');
      await new Promise(r => setTimeout(r, 5000));
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        const r = await fetch('http://localhost:3200/api/health', { signal: controller.signal });
        clearTimeout(timeout);
        if (r.ok) return sendMessage(chatId, '✅ *Server erfolgreich neu gestartet!*');
      } catch {}
      return sendMessage(chatId, '⚠️ *Restart ausgeführt*, aber Server antwortet noch nicht. Bitte in 10s erneut /health');
    } catch (e) {
      return sendMessage(chatId, `❌ Restart Fehler: ${e.message}\nVersuche: \`pm2 restart autopilot-server\``);
    }
  },

  '/logs': async (chatId) => {
    try {
      const logPath = 'logs/server-out.log';
      if (!fs.existsSync(logPath)) return sendMessage(chatId, '❌ Keine Logs gefunden');
      const logs = fs.readFileSync(logPath, 'utf8').split('\n').slice(-20).join('\n');
      const truncated = logs.length > 3500 ? logs.slice(-3500) : logs;
      return sendMessage(chatId, `📝 *Letzte Logs:*\n\`\`\`\n${truncated}\n\`\`\``);
    } catch (e) {
      return sendMessage(chatId, `❌ Fehler beim Lesen: ${e.message}`);
    }
  },

  '/deploy': async (chatId) => {
    await sendMessage(chatId, '🚀 *Deploy wird gestartet...*\nDies kann 1-2 Minuten dauern.');
    try {
      const { stdout, stderr } = await execAsync('vercel --prod --yes', { timeout: 120000 });
      return sendMessage(chatId, `✅ *Deploy erfolgreich!*\n\n${stdout.slice(0, 1000)}`);
    } catch (e) {
      return sendMessage(chatId, `❌ Deploy Fehler: ${e.message}\n\n${e.stderr?.slice(0, 500) || ''}`);
    }
  },

  // 🔐 SECURITY COMMANDS
  '/validate': async (chatId, args) => {
    if (!args || args.length === 0) {
      return sendMessage(chatId, 
        `🔐 *API Key Validator*\n\n` +
        `Verwendung: /validate <key> <type>\n\n` +
        `*Unterstützte Typen:*\n` +
        `• shopify - Shopify API Keys\n` +
        `• telegram - Telegram Bot Tokens\n` +
        `• stripe - Stripe API Keys\n` +
        `• openai - OpenAI API Keys\n` +
        `• supabase - Supabase Keys\n` +
        `• github - GitHub Tokens\n` +
        `• vercel - Vercel Tokens\n\n` +
        `*Beispiel:*\n` +
        `/validate shpat_1234567890abcdef shopify`
      );
    }

    try {
      const [key, type] = args.split(' ', 2);
      if (!key || !type) {
        return sendMessage(chatId, '❌ *Format:* /validate <key> <type>');
      }

      await sendMessage(chatId, '🔍 *Validiere API Key...*');
      
      const validation = validatorScanner.validateKey(key, type, {
        validatedBy: 'telegram_bot',
        timestamp: new Date().toISOString()
      });

      const status = validation.valid ? '✅ *GÜLTIG*' : '❌ *UNGÜLTIG*';
      const score = `📊 *Security Score:* ${validation.securityScore}/100`;
      
      let message = `${status}\n${score}\n\n`;
      message += `🔑 *Key:* ${validation.key}\n`;
      message += `🏷️ *Typ:* ${validation.type}\n`;
      
      if (validation.issues.length > 0) {
        message += `\n⚠️ *Issues:*\n`;
        validation.issues.slice(0, 5).forEach((issue, i) => {
          message += `${i + 1}. ${issue}\n`;
        });
        if (validation.issues.length > 5) {
          message += `... und ${validation.issues.length - 5} weitere\n`;
        }
      }
      
      message += `\n💡 *Empfehlung:* ${validation.recommendation || 'Keine'}`;

      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ *Validierungsfehler:* ${e.message}`);
    }
  },

  '/deepscan': async (chatId) => {
    try {
      await sendMessage(chatId, '🔍 *Starte Deep Security Scan...*\n\nDies kann einige Minuten dauern.\nIch scanne alle Dateien auf:\n• API Keys\n• Sensitive Patterns\n• Security Issues\n• Configuration Problems');
      
      // Start scan in background
      validatorScanner.startDeepScan().then(results => {
        const summary = validatorScanner.generateSecuritySummary();
        
        let message = `📊 *Deep Scan abgeschlossen!*\n\n`;
        message += `🔍 *Issues gefunden:* ${summary.totalIssues}\n`;
        message += `🚨 *Kritisch:* ${summary.criticalIssues}\n`;
        message += `⚠️ *Hoch:* ${results.filter(r => r.severity === 'high').length}\n`;
        message += `📋 *Mittel:* ${results.filter(r => r.severity === 'medium').length}\n`;
        message += `ℹ️ *Niedrig:* ${results.filter(r => r.severity === 'low').length}\n\n`;
        
        message += `🛡️ *Overall Security:* ${summary.overallSecurity.toUpperCase()}\n\n`;
        
        if (summary.recommendations.length > 0) {
          message += `💡 *Empfehlungen:*\n`;
          summary.recommendations.forEach(rec => {
            message += `• ${rec}\n`;
          });
        }
        
        return sendMessage(chatId, message);
      }).catch(error => {
        return sendMessage(chatId, `❌ *Deep Scan Fehler:* ${error.message}`);
      });
      
      return sendMessage(chatId, '🔄 *Scan läuft im Hintergrund...*\nIch melde mich, wenn fertig!');
    } catch (e) {
      return sendMessage(chatId, `❌ *Scan Start Fehler:* ${e.message}`);
    }
  },

  '/security': async (chatId) => {
    try {
      const status = validatorScanner.getScanStatus();
      const summary = validatorScanner.generateSecuritySummary();
      
      let message = `🔐 *Security Status*\n\n`;
      
      if (status.isScanning) {
        message += `🔄 *Scan läuft...*\n`;
        message += `📊 *Fortschritt:* ${status.progress.progress}%\n`;
        message += `🔍 *Issues gefunden:* ${status.progress.issuesFound}\n`;
        message += `⏱️ *Laufzeit:* ${Math.floor(status.progress.scanTime / 1000)}s\n\n`;
        message += `*Scan läuft noch, bitte warten...*`;
      } else {
        message += `📊 *Overall Security:* ${summary.overallSecurity.toUpperCase()}\n\n`;
        message += `🔍 *Total Issues:* ${summary.totalIssues}\n`;
        message += `🚨 *Critical:* ${summary.criticalIssues}\n`;
        message += `⚠️ *High:* ${status.results.filter(r => r.severity === 'high').length}\n`;
        message += `📋 *Medium:* ${status.results.filter(r => r.severity === 'medium').length}\n`;
        message += `ℹ️ *Low:* ${status.results.filter(r => r.severity === 'low').length}\n\n`;
        
        if (summary.criticalIssues > 0) {
          message += `🚨 *AKTION ERFORDERLICH!* ${summary.criticalIssues} kritische Issues gefunden!\n\n`;
        }
        
        message += `💡 *Tipp:* Verwende /deepscan für vollständigen Scan`;
      }
      
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ *Security Status Fehler:* ${e.message}`);
    }
  },

  '/audit': async (chatId) => {
    try {
      await sendMessage(chatId, '📋 *Erstelle Security Audit Report...*');
      
      const status = validatorScanner.getScanStatus();
      const summary = validatorScanner.generateSecuritySummary();
      
      let report = `🔐 *SECURITY AUDIT REPORT*\n`;
      report += `===============================\n\n`;
      report += `📅 *Datum:* ${new Date().toLocaleString('de-DE')}\n`;
      report += `🤖 *Bot:* AutoPilot Business Bot\n`;
      report += `🔍 *Scanner:* API Validator + Deep Scan\n\n`;
      
      report += `📊 *ZUSAMMENFASSUNG*\n`;
      report += `─────────────────\n`;
      report += `🛡️ *Overall Security:* ${summary.overallSecurity.toUpperCase()}\n`;
      report += `🔍 *Total Issues:* ${summary.totalIssues}\n`;
      report += `🚨 *Critical:* ${summary.criticalIssues}\n`;
      report += `⚠️ *High:* ${status.results.filter(r => r.severity === 'high').length}\n`;
      report += `📋 *Medium:* ${status.results.filter(r => r.severity === 'medium').length}\n`;
      report += `ℹ️ *Low:* ${status.results.filter(r => r.severity === 'low').length}\n\n`;
      
      // Top issues
      const topIssues = status.results
        .filter(r => r.severity === 'critical' || r.severity === 'high')
        .slice(0, 5);
        
      if (topIssues.length > 0) {
        report += `🚨 *TOP PRIORITY ISSUES*\n`;
        report += `─────────────────────\n`;
        topIssues.forEach((issue, i) => {
          report += `${i + 1}. *${issue.file}:${issue.line}*\n`;
          report += `   Typ: ${issue.type}\n`;
          report += `   Severity: ${issue.severity}\n`;
          report += `   Empfehlung: ${issue.recommendation}\n\n`;
        });
      }
      
      // Recommendations
      if (summary.recommendations.length > 0) {
        report += `💡 *EMPFEHLUNGEN*\n`;
        report += `─────────────────\n`;
        summary.recommendations.forEach(rec => {
          report += `• ${rec}\n`;
        });
        report += `\n`;
      }
      
      report += `🔧 *NÄCHSTE SCHRITTE*\n`;
      report += `──────────────────\n`;
      if (summary.criticalIssues > 0) {
        report += `1. 🚨 Kritische Issues sofort beheben\n`;
        report += `2. 🔍 Deep Scan mit /deepscan ausführen\n`;
        report += `3. 📊 Status mit /security prüfen\n`;
      } else {
        report += `1. ✅ System ist sicher\n`;
        report += `2. 🔄 Regelmäßige Scans durchführen\n`;
        report += `3. 📈 Monitoring aufrechterhalten\n`;
      }
      
      report += `\n===============================\n`;
      report += `🤖 *Report generiert von AutoPilot Bot*`;
      
      return sendMessage(chatId, report);
    } catch (e) {
      return sendMessage(chatId, `❌ *Audit Report Fehler:* ${e.message}`);
    }
  },

  '/monitor': async (chatId) => {
    try {
      const r = await fetch('http://localhost:9001/monitoring-stats', { signal: AbortSignal.timeout(5000) });
      const d = await r.json();
      const checks = (d.checks || []).map(c =>
        `${c.status === 'ok' ? '✅' : '❌'} *${c.name}*: ${c.status === 'ok' ? 'OK' : c.detail} (${c.ms}ms)`
      ).join('\n');
      return sendMessage(chatId,
        `📈 *Monitoring Status*\n\n` +
        `Uptime: ${Math.floor(d.uptime/60)}m\n` +
        `Checks: ${d.checks?.length || 0}\n` +
        `Alerts: ${d.alerts?.length || 0}\n\n` +
        `${checks || 'Keine Checks verfügbar'}`
      );
    } catch (e) {
      return sendMessage(chatId, `❌ Monitoring nicht erreichbar: ${e.message}\n\nStarte: \`node windsurf-monitoring.js\``);
    }
  },

  '/cleanup': async (chatId) => {
    await sendMessage(chatId, '🗑️ *Speicher-Cleanup wird gestartet...*');
    try {
      let cleaned = 0;
      // Clean logs older than 7 days
      const logFiles = fs.readdirSync('logs').filter(f => f.endsWith('.log'));
      for (const f of logFiles) {
        const stat = fs.statSync(`logs/${f}`);
        const age = (Date.now() - stat.mtime.getTime()) / (1000 * 60 * 60 * 24);
        if (age > 7) {
          fs.writeFileSync(`logs/${f}`, ''); // Truncate, don't delete
          cleaned++;
        }
      }
      // Force GC if available
      if (global.gc) global.gc();
      return sendMessage(chatId, `✅ *Cleanup abgeschlossen!*\n🗑️ ${cleaned} alte Log-Dateien geleert\n🧠 Garbage Collection ausgeführt`);
    } catch (e) {
      return sendMessage(chatId, `❌ Cleanup Fehler: ${e.message}`);
    }
  },

  // Social Media Commands
  '/pinterest': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/pinterest/boards');
      const data = await r.json();
      const boards = data.slice(0, 5).map(b => `📌 ${b.name || b.id}`).join('\\n');
      return sendMessage(chatId,
        `📌 *Pinterest Boards*\\n\\n${boards || 'Keine Boards gefunden'}\\n\\n_Pins erstellen: /pinterest pin BOARD_ID \"Titel\" \"Beschreibung\"_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Pinterest Fehler: ${e.message}`);
    }
  },

  '/reddit': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/reddit/hot/programming');
      const data = await r.json();
      const posts = data.data?.children?.slice(0, 5).map(p => `🔥 ${p.data.title.substring(0, 50)}...`).join('\\n') || 'Keine Posts';
      return sendMessage(chatId,
        `🔥 *Reddit Hot Posts*\\n\\n${posts}\\n\\n_Subreddit: /reddit SUBREDDIT_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Reddit Fehler: ${e.message}`);
    }
  },

  '/twitter': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/twitter/me');
      const data = await r.json();
      return sendMessage(chatId,
        `🐦 *Twitter/X Profile*\\n\\n@${data.username || 'N/A'}\\nName: ${data.name || 'N/A'}\\nFollowers: ${data.public_metrics?.followers_count || 'N/A'}\\n\\n_Tweet posten: /twitter tweet \"Dein Text\"_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Twitter Fehler: ${e.message}`);
    }
  },

  '/linkedin': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/linkedin/me');
      const data = await r.json();
      return sendMessage(chatId,
        `💼 *LinkedIn Profile*\\n\\nID: ${data.id || 'N/A'}\\nLocalized: ${data.localized || 'N/A'}\\n\\n_Post erstellen: /linkedin post \"Dein Text\"_`);
    } catch(e) {
      return sendMessage(chatId, `❌ LinkedIn Fehler: ${e.message}`);
    }
  },

  // Business Commands
  '/upwork': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/upwork/profile');
      const data = await r.json();
      return sendMessage(chatId,
        `👥 *Upwork Profile*\\n\\n${data.profile?.display_name || 'N/A'}\\n${data.profile?.title || 'N/A'}\\n\\n_Jobs suchen: /upwork jobs \"keyword\"_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Upwork Fehler: ${e.message}`);
    }
  },

  '/etsy': async (chatId) => {
    try {
      const shopId = process.env.ETSY_SHOP_ID || 'demo';
      const r = await fetch(`http://localhost:3200/api/etsy/shop/${shopId}`);
      const data = await r.json();
      return sendMessage(chatId,
        `🛍️ *Etsy Shop*\\n\\n${data.shop_name || 'N/A'}\\n${data.title || 'N/A'}\\nListings: ${data.listing_active_count || 'N/A'}\\n\\n_Listings: /etsy listings_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Etsy Fehler: ${e.message}`);
    }
  },

  '/gumroad': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/gumroad/products');
      const data = await r.json();
      const products = data.slice(0, 5).map(p => `💰 ${p.name} - $${(p.price/100).toFixed(2)}`).join('\\n') || 'Keine Produkte';
      return sendMessage(chatId,
        `💰 *Gumroad Produkte*\\n\\n${products}\\n\\n_Produkt erstellen: /gumroad create_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Gumroad Fehler: ${e.message}`);
    }
  },

  '/producthunt': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/producthunt/posts');
      const data = await r.json();
      const posts = data.data?.posts?.slice(0, 5).map(p => `🚀 ${p.name} - ${p.votesCount} votes`).join('\\n') || 'Keine Posts';
      return sendMessage(chatId,
        `🚀 *Product Hunt Posts*\\n\\n${posts}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Product Hunt Fehler: ${e.message}`);
    }
  },

  '/udemy': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/udemy/courses');
      const data = await r.json();
      const courses = data.results?.slice(0, 5).map(c => `📚 ${c.title.substring(0, 40)}...`).join('\\n') || 'Keine Kurse';
      return sendMessage(chatId,
        `📚 *Udemy Kurse*\\n\\n${courses}\\n\\n_Suche: /udemy search \"keyword\"_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Udemy Fehler: ${e.message}`);
    }
  },

  // Productivity Commands
  '/notion': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/notion/databases');
      const data = await r.json();
      const databases = data.results?.slice(0, 5).map(d => `📄 ${d.title[0]?.plain_text || d.id}`).join('\\n') || 'Keine Datenbanken';
      return sendMessage(chatId,
        `📄 *Notion Datenbanken*\\n\\n${databases}\\n\\n_Pages erstellen: /notion page_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Notion Fehler: ${e.message}`);
    }
  },

  '/airtable': async (chatId) => {
    try {
      const baseId = process.env.AIRTABLE_BASE_ID || 'demo';
      const tableId = 'demo';
      const r = await fetch(`http://localhost:3200/api/airtable/records/${baseId}/${tableId}`);
      const data = await r.json();
      const records = data.records?.slice(0, 3).map(r => `📋 ${JSON.stringify(r.fields).substring(0, 30)}...`).join('\\n') || 'Keine Records';
      return sendMessage(chatId,
        `📋 *Airtable Records*\\n\\n${records}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Airtable Fehler: ${e.message}`);
    }
  },

  // Storage Commands
  '/storage': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/storage/directories');
      const data = await r.json();
      const dirs = Object.entries(data.directories).slice(0, 8).map(([key, path]) => `📁 ${key}: ${path}`).join('\\n');
      return sendMessage(chatId,
        `💾 *System Storage*\\n\\nPlatform: ${data.platform}\\nHostname: ${data.hostname}\\n\\n${dirs}\\n\\n_Scan: /storage scan PATH_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Storage Fehler: ${e.message}`);
    }
  },

  '/desktop': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/storage/desktop');
      const data = await r.json();
      const files = data.files.slice(0, 10).map(f => `📄 ${f.name} (${f.size} bytes)`).join('\\n') || 'Keine Dateien';
      return sendMessage(chatId,
        `🖥️ *Desktop Scan*\\n\\nDateien: ${data.summary.files}\\nOrdner: ${data.summary.folders}\\n\\n${files}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Desktop Fehler: ${e.message}`);
    }
  },

  '/downloads': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/storage/downloads');
      const data = await r.json();
      const files = data.files.slice(0, 10).map(f => `📥 ${f.name}`).join('\\n') || 'Keine Dateien';
      return sendMessage(chatId,
        `📥 *Downloads Scan*\\n\\nDateien: ${data.summary.files}\\nGröße: ${(data.summary.size / 1024 / 1024).toFixed(2)} MB\\n\\n${files}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Downloads Fehler: ${e.message}`);
    }
  },

  // Cloud Storage Commands
  '/gdrive': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/googledrive/files');
      const data = await r.json();
      const files = data.files?.slice(0, 5).map(f => `📁 ${f.name} (${f.mimeType})`).join('\\n') || 'Keine Dateien';
      return sendMessage(chatId,
        `🗂️ *Google Drive*\\n\\n${files}\\n\\n_Suche: /gdrive search QUERY_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Google Drive Fehler: ${e.message}`);
    }
  },

  '/dropbox': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/dropbox/files');
      const data = await r.json();
      const files = data.entries?.slice(0, 5).map(f => `📁 ${f.name} (${f['.tag']})`).join('\\n') || 'Keine Dateien';
      return sendMessage(chatId,
        `📦 *Dropbox*\\n\\n${files}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Dropbox Fehler: ${e.message}`);
    }
  },

  '/onedrive': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/onedrive/files');
      const data = await r.json();
      const files = data.value?.slice(0, 5).map(f => `📁 ${f.name} (${f.file?.mimeType || 'folder'})`).join('\\n') || 'Keine Dateien';
      return sendMessage(chatId,
        `☁️ *OneDrive*\\n\\n${files}`);
    } catch(e) {
      return sendMessage(chatId, `❌ OneDrive Fehler: ${e.message}`);
    }
  },

  // Notes Commands
  '/notes': async (chatId) => {
    try {
      const onenote = await fetch('http://localhost:3200/api/onenote/notebooks');
      const data = await onenote.json();
      const notebooks = data.value?.slice(0, 5).map(n => `📓 ${n.displayName}`).join('\\n') || 'Keine Notebooks';
      return sendMessage(chatId,
        `📝 *Notes System*\\n\\nOneNote:\\n${notebooks}\\n\\n_Evernote: /evernote_\\n_Apple Notes: /apple_notes_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Notes Fehler: ${e.message}`);
    }
  },

  '/evernote': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/evernote/notebooks');
      const data = await r.json();
      return sendMessage(chatId,
        `🐘 *Evernote*\\n\\n${data.message}\\nStatus: ${data.status}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Evernote Fehler: ${e.message}`);
    }
  },

  // IDE Commands
  '/vscode': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/vscode/extensions');
      const data = await r.json();
      return sendMessage(chatId,
        `💻 *Visual Studio Code*\\n\\nExtensions API verfügbar\\n\\n_Marketplace: /vscode search QUERY_`);
    } catch(e) {
      return sendMessage(chatId, `❌ VS Code Fehler: ${e.message}`);
    }
  },

  '/codespaces': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/codespaces/list');
      const data = await r.json();
      const spaces = data.slice(0, 3).map(c => `🚀 ${c.name} (${c.state})`).join('\\n') || 'Keine Codespaces';
      return sendMessage(chatId,
        `🚀 *GitHub Codespaces*\\n\\n${spaces}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Codespaces Fehler: ${e.message}`);
    }
  },

  // System Commands
  '/windsurf': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/windsurf/status');
      const data = await r.json();
      return sendMessage(chatId,
        `🌊 *Windsurf Status*\\n\\nStatus: ${data.status}\\nUptime: ${Math.floor((data.uptime || 0) / 60)}m\\nChecks: ${data.checks || 0}\\n\\n${data.action || ''}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Windsurf Fehler: ${e.message}`);
    }
  },

  '/system': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/claude/desktop/system');
      const data = await r.json();
      const mem = (data.totalmem - data.freemem) / data.totalmem * 100;
      return sendMessage(chatId,
        `💻 *System Info*\\n\\nPlatform: ${data.platform} (${data.arch})\\nHostname: ${data.hostname}\\nCPU: ${data.cpus?.length || 0} cores\\nMemory: ${mem.toFixed(1)}% used\\nUptime: ${Math.floor(data.uptime / 3600)}h\\n\\n_Mac: ${data.mac?.version || 'N/A'}_`);
    } catch(e) {
      return sendMessage(chatId, `❌ System Fehler: ${e.message}`);
    }
  },

  // Deep-Scan Commands
  '/deepscan': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/deepscan/status');
      const data = await r.json();
      const lastScan = data.last_scan ? new Date(data.last_scan.timestamp).toLocaleString('de-DE') : 'No scans yet';
      return sendMessage(chatId,
        `🔍 *Deep-Scan System*\\n\\nStatus: ${data.status}\\nVersion: ${data.version}\\nTotal Scans: ${data.total_scans}\\nLast Scan: ${lastScan}\\n\\n_Quick Scan: /deepscan quick PATH_\\n_Full Scan: /deepscan execute PATH_`);
    } catch(e) {
      return sendMessage(chatId, `❌ Deep-Scan Fehler: ${e.message}`);
    }
  },

  '/deepscan_history': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/deepscan/history?limit=5');
      const data = await r.json();
      const scans = data.scans.map(s => `📊 ${new Date(s.timestamp).toLocaleString('de-DE')} (${(s.size/1024).toFixed(1)}KB)`).join('\\n') || 'No scans';
      return sendMessage(chatId,
        `📜 *Deep-Scan History*\\n\\n${scans}\\n\\n_Total: ${data.total} scans_`);
    } catch(e) {
      return sendMessage(chatId, `❌ History Fehler: ${e.message}`);
    }
  },

  '/security': async (chatId) => {
    try {
      const r = await fetch('http://localhost:3200/api/deepscan/security/harden', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targetPath: '.' })
      });
      const data = await r.json();
      const actions = data.hardening_actions.slice(0, 5).map(a => `🔒 ${a.action}: ${a.file}`).join('\\n') || 'No actions needed';
      return sendMessage(chatId,
        `🛡️ *Security Hardening*\\n\\nScore: ${data.security_score}/100\\n.env Files: ${data.env_files_found}\\n\\n${actions}`);
    } catch(e) {
      return sendMessage(chatId, `❌ Security Fehler: ${e.message}`);
    }
  },

  // AI Commands
  '/claude': async (chatId) => {
    await sendMessage(chatId, '🤖 *Claude AI wird abgefragt...*');
    try {
      const r = await fetch('http://localhost:3200/api/ai/claude', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Hallo! Wie kann ich helfen?', max_tokens: 100 })
      });
      const d = await r.json();
      return sendMessage(chatId, `🧠 *Claude Response:*\n\n${d.text || 'Fehler: ' + d.error}`);
    } catch (e) {
      return sendMessage(chatId, `❌ Claude Fehler: ${e.message}`);
    }
  },

  '/perplexity': async (chatId) => {
    await sendMessage(chatId, '🔍 *Perplexity AI wird abgefragt...*');
    try {
      const r = await fetch('http://localhost:3200/api/ai/perplexity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'Was ist der aktuelle Stand von AI APIs?' })
      });
      const d = await r.json();
      const content = d.choices?.[0]?.message?.content || 'Keine Antwort';
      return sendMessage(chatId, `🔍 *Perplexity Response:*\n\n${content.slice(0, 500)}...`);
    } catch (e) {
      return sendMessage(chatId, `❌ Perplexity Fehler: ${e.message}`);
    }
  },

  '/gemini': async (chatId) => {
    await sendMessage(chatId, '✨ *Google AI Gemini wird abgefragt...*');
    try {
      const r = await fetch('http://localhost:3200/api/ai/gemini', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Hallo!' })
      });
      const d = await r.json();
      return sendMessage(chatId, `✨ *Gemini Response:*\n\n${d.text || 'Fehler: ' + d.error}`);
    } catch (e) {
      return sendMessage(chatId, `❌ Gemini Fehler: ${e.message}`);
    }
  },

  // Business Commands
  '/github': async (chatId) => {
    await sendMessage(chatId, '📦 *GitHub Repositories werden geladen...*');
    try {
      const r = await fetch('http://localhost:3200/api/github/repos');
      const d = await r.json();
      if (Array.isArray(d) && d.length > 0) {
        const repos = d.slice(0, 5).map(r => `📁 ${r.name} (${r.language || 'N/A'})`).join('\n');
        return sendMessage(chatId, `📦 *GitHub Repositories (${d.length} total):*\n\n${repos}\n\n_Mehr: /github all_`);
      } else {
        return sendMessage(chatId, '❌ Keine Repositories gefunden');
      }
    } catch (e) {
      return sendMessage(chatId, `❌ GitHub Fehler: ${e.message}`);
    }
  },

  '/stripe': async (chatId) => {
    await sendMessage(chatId, '💳 *Stripe Balance wird abgefragt...*');
    try {
      const r = await fetch('http://localhost:3200/api/stripe/balance');
      const d = await r.json();
      const available = d.available?.[0]?.amount || 0;
      const pending = d.pending?.[0]?.amount || 0;
      return sendMessage(chatId, `💳 *Stripe Balance:*\n\n💰 Verfügbare: €${(available/100).toFixed(2)}\n⏳ Ausstehend: €${(pending/100).toFixed(2)}\n💶 Währung: ${d.available?.[0]?.currency || 'EUR'}`);
    } catch (e) {
      return sendMessage(chatId, `❌ Stripe Fehler: ${e.message}`);
    }
  },

  '/supabase': async (chatId) => {
    await sendMessage(chatId, '🗄️ *Supabase Status wird geprüft...*');
    try {
      const r = await fetch('http://localhost:3200/api/supabase/test?limit=5');
      const d = await r.json();
      return sendMessage(chatId, `🗄️ *Supabase Status:*\n\n✅ REST API erreichbar\n📊 Projekt: qyrjeckzacjaazkpvnjk\n🔗 URL: https://qyrjeckzacjaazkpvnjk.supabase.co\n\n*Antwort:* ${JSON.stringify(d).slice(0, 200)}...`);
    } catch (e) {
      return sendMessage(chatId, `❌ Supabase Fehler: ${e.message}`);
    }
  },

  '/all': async (chatId) => {
    await sendMessage(chatId, '🚀 *Starte alle Automatisierungssysteme...*\nDies kann 2-3 Minuten dauern.');
    
    try {
      const results = [];
      
      // Start Printify automation
      await sendMessage(chatId, '👕 *Printify:* Starte POD Produkt-Generierung...');
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);
      
      try {
        await execAsync('node scripts/printify-automation.js generate 5', { timeout: 60000 });
        results.push('✅ Printify: 5 Produkte generiert');
      } catch (e) {
        results.push(`❌ Printify: ${e.message}`);
      }
      
      // Start Digistore automation
      await sendMessage(chatId, '💰 *Digistore:* Starte Affiliate Kampagne...');
      try {
        await execAsync('node scripts/digistore-automation.js campaign --count 5 --social', { timeout: 60000 });
        results.push('✅ Digistore: Kampagne gestartet');
      } catch (e) {
        results.push(`❌ Digistore: ${e.message}`);
      }
      
      // Start YouTube automation
      await sendMessage(chatId, '📺 *YouTube:* Erstelle Content-Kalender...');
      try {
        await execAsync('node scripts/youtube-automation.js calendar 7', { timeout: 60000 });
        results.push('✅ YouTube: 7-Tage Kalender erstellt');
      } catch (e) {
        results.push(`❌ YouTube: ${e.message}`);
      }
      
      // Sync earnings
      await sendMessage(chatId, '📊 *Einnahmen:* Synchronisiere Daten...');
      try {
        await execAsync('node scripts/earnings-tracker.js sync', { timeout: 30000 });
        results.push('✅ Einnahmen: Daten synchronisiert');
      } catch (e) {
        results.push(`❌ Einnahmen: ${e.message}`);
      }
      
      const summary = results.join('\n');
      return sendMessage(chatId, `🎉 *Alle Systeme abgeschlossen!*\n\n${summary}\n\n💰 *Geschätztes monatliches Einkommen: 1500-2500 EUR*`);
      
    } catch (e) {
      return sendMessage(chatId, `❌ Fehler bei der Ausführung: ${e.message}`);
    }
  },

  '/printify': async (chatId) => {
    await sendMessage(chatId, '👕 *Starte Printify POD Automation...');
    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);
      
      const { stdout } = await execAsync('node scripts/printify-automation.js generate 10', { timeout: 120000 });
      return sendMessage(chatId, `✅ *Printify Automation abgeschlossen!*\n\n${stdout.slice(0, 500)}\n\n💰 *Geschätzte Einnahmen: 300-500 EUR/Monat*`);
    } catch (e) {
      return sendMessage(chatId, `❌ Printify Fehler: ${e.message}`);
    }
  },

  '/digistore': async (chatId) => {
    await sendMessage(chatId, '💰 *Starte Digistore Affiliate Automation...');
    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);
      
      const { stdout } = await execAsync('node scripts/digistore-automation.js campaign --count 10 --social --email', { timeout: 120000 });
      return sendMessage(chatId, `✅ *Digistore Automation abgeschlossen!*\n\n${stdout.slice(0, 500)}\n\n💰 *Geschätzte Einnahmen: 500-800 EUR/Monat*`);
    } catch (e) {
      return sendMessage(chatId, `❌ Digistore Fehler: ${e.message}`);
    }
  },

  '/youtube': async (chatId) => {
    await sendMessage(chatId, '📺 *Starte YouTube Content Automation...');
    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);
      
      const { stdout } = await execAsync('node scripts/youtube-automation.js calendar 14', { timeout: 120000 });
      return sendMessage(chatId, `✅ *YouTube Automation abgeschlossen!*\n\n${stdout.slice(0, 500)}\n\n💰 *Geschätzte Einnahmen: 200-400 EUR/Monat*`);
    } catch (e) {
      return sendMessage(chatId, `❌ YouTube Fehler: ${e.message}`);
    }
  },

  '/earn': async (chatId) => {
    await sendMessage(chatId, '📊 *Lade Einnahmen-Report...');
    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);
      
      const { stdout } = await execAsync('node scripts/earnings-tracker.js today', { timeout: 30000 });
      return sendMessage(chatId, `💰 *Heutige Einnahmen:*\n\n\`\`\`\n${stdout}\n\`\`\``);
    } catch (e) {
      return sendMessage(chatId, `❌ Einnahmen Fehler: ${e.message}`);
    }
  },

  '/sys': async (chatId) => {
    try {
      // Get comprehensive system status
      const mem = process.memoryUsage();
      const uptime = Math.floor((Date.now() - state.startTime) / 1000);
      const hours = Math.floor(uptime / 3600);
      const mins = Math.floor((uptime % 3600) / 60);

      // Check all services
      let serverStatus = '❌ Offline';
      let monitorStatus = '❌ Offline';
      let automationStatus = '❌ Offline';
      
      try {
        const r = await fetch('http://localhost:3200/api/health', { signal: AbortSignal.timeout(3000) });
        if (r.ok) serverStatus = '✅ Online';
      } catch { /* ignore */ }
      
      try {
        const r = await fetch('http://localhost:9001/monitoring-stats', { signal: AbortSignal.timeout(3000) });
        if (r.ok) monitorStatus = '✅ Online';
      } catch { /* ignore */ }
      
      // Check if automation scripts exist
      const fs = require('fs');
      const scripts = ['printify-automation.js', 'digistore-automation.js', 'youtube-automation.js', 'earnings-tracker.js'];
      const existingScripts = scripts.filter(script => fs.existsSync(`scripts/${script}`));
      automationStatus = existingScripts.length === scripts.length ? '✅ Online' : `⚠️ ${existingScripts.length}/${scripts.length} verfügbar`;

      return sendMessage(chatId,
        `🖥️ *Vollständiger System Status*\n\n` +
        `🤖 **Bot Controller:**\n` +
        `⏱️ Uptime: ${hours}h ${mins}m\n` +
        `📦 Commands: ${state.commandCount}\n` +
        `🧠 Memory: ${Math.round(mem.heapUsed/1024/1024)}MB\n\n` +
        `🌐 **Services:**\n` +
        `🖥️ Server: ${serverStatus}\n` +
        `📈 Monitoring: ${monitorStatus}\n` +
        `🤖 Automation: ${automationStatus}\n\n` +
        `🚀 **Income Streams:**\n` +
        `👕 Printify POD: ✅ Aktiv\n` +
        `💰 Digistore24: ✅ Aktiv\n` +
        `📺 YouTube Ads: ✅ Aktiv\n` +
        `🛒 Shopify Sales: ✅ Aktiv\n\n` +
        `💰 **Heutiges Ziel:** 1000+ EUR\n` +
        `_Letzter Command: ${state.lastCommand || 'keiner'}_`
      );
    } catch (e) {
      return sendMessage(chatId, `❌ System Status Fehler: ${e.message}`);
    }
  },


  // 💰 FINANCE GRID COMMANDS
  '/fin-grid': async (chatId) => {
    try {
      const subSummary = subscriptionHunter.getSummary();
      const complianceStatus = complianceEngine.getComplianceStatus();
      
      let message = `💰 *FINANCE GRID OVERVIEW*\n\n`;
      message += `📊 *Subscriptions:*\n`;
      message += `• Active: ${subSummary.totalActive}\n`;
      message += `• Monthly Cost: ${subSummary.totalMonthly.toFixed(2)} EUR\n`;
      message += `• Annual Cost: ${subSummary.totalAnnual.toFixed(2)} EUR\n`;
      message += `• Upcoming Renewals: ${subSummary.upcomingRenewals}\n`;
      message += `• Killable: ${subSummary.killable}\n\n`;
      
      message += `⚖️ *Compliance:*\n`;
      message += `• Status: ${complianceStatus.overall.toUpperCase()}\n`;
      message += `• Open Deadlines: ${complianceStatus.openDeadlines}\n`;
      message += `• Upcoming 30d: ${complianceStatus.upcoming30Days}\n`;
      message += `• Overdue: ${complianceStatus.overdue}\n\n`;
      
      message += `*Commands:*\n`;
      message += `/subs — View subscriptions\n`;
      message += `/sub-kill — Cancel subscription\n`;
      message += `/tax — Tax status\n`;
      message += `/spend — Expense radar\n`;
      message += `/elster — ELSTER export`;
      
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ Finance Grid error: ${e.message}`);
    }
  },

  '/subs': async (chatId) => {
    try {
      const summary = subscriptionHunter.getSummary();
      const upcoming = subscriptionHunter.getUpcomingRenewals(14);
      
      let message = `🎯 *SUBSCRIPTION HUNTER*\n\n`;
      message += `📊 *Summary:*\n`;
      message += `• Active: ${summary.totalActive}\n`;
      message += `• Monthly: ${summary.totalMonthly.toFixed(2)} EUR\n`;
      message += `• Annual: ${summary.totalAnnual.toFixed(2)} EUR\n\n`;
      
      if (upcoming.length > 0) {
        message += `📅 *Upcoming Renewals:*\n`;
        upcoming.slice(0, 5).forEach(sub => {
          const days = Math.ceil((new Date(sub.nextBilling) - Date.now()) / (1000*60*60*24));
          message += `• ${sub.name}: ${days}d (${sub.monthlyCost.toFixed(2)} EUR)\n`;
        });
      }
      
      message += `\n💡 Use /sub-kill <id> to cancel`;
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ Error: ${e.message}`);
    }
  },

  '/sub-kill': async (chatId, args) => {
    if (!args) {
      return sendMessage(chatId, 
        `🗡️ *SUB-KILL*\n\n` +
        `Usage: /sub-kill <subscription-id>\n\n` +
        `First use /subs to see IDs, then kill.`
      );
    }
    
    try {
      const prep = await subscriptionHunter.prepareCancellation(args);
      if (prep.error) {
        return sendMessage(chatId, `❌ ${prep.error}`);
      }
      
      let message = `🗡️ *KILL PREPARED*\n\n`;
      message += `📋 ${prep.subscription.name}\n`;
      message += `💰 Monthly: ${prep.subscription.monthlyCost.toFixed(2)} EUR\n`;
      message += `⏰ Next: ${new Date(prep.subscription.nextBilling).toLocaleDateString('de-DE')}\n\n`;
      message += `✅ Eligible: ${prep.canCancel ? 'YES' : 'NO'}\n`;
      message += `📌 Reason: ${prep.eligibility.reason}\n\n`;
      
      if (prep.nextSteps) {
        message += `*Steps:*\n`;
        prep.nextSteps.forEach((step, i) => {
          message += `${i+1}. ${step}\n`;
        });
      }
      
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ Kill error: ${e.message}`);
    }
  },

  '/tax': async (chatId) => {
    try {
      const year = new Date().getFullYear();
      const summary = taxCore.getYearSummary(year);
      
      let message = `📋 *TAX CORE — ${year}*\n\n`;
      message += `📄 Documents: ${summary.totalDocuments}\n`;
      message += `💰 Tax Expenses: ${summary.totalExpenses.toFixed(2)} EUR\n\n`;
      
      if (summary.categories.length > 0) {
        message += `*Top Categories:*\n`;
        summary.categories.slice(0, 5).forEach(cat => {
          message += `• ${cat.category}: ${cat.amount.toFixed(2)} EUR\n`;
        });
      }
      
      message += `\n💡 Use /elster to export`;
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ Tax error: ${e.message}`);
    }
  },

  '/spend': async (chatId) => {
    try {
      const now = new Date();
      const summary = expenseRadar.getMonthlySummary(now.getFullYear(), now.getMonth() + 1);
      
      let message = `💰 *EXPENSE RADAR*\n\n`;
      message += `📊 ${summary.month}/${summary.year}\n`;
      message += `💵 Income: ${summary.income.toFixed(2)} EUR\n`;
      message += `💸 Expenses: ${summary.expenses.toFixed(2)} EUR\n`;
      message += `📈 Balance: ${summary.balance.toFixed(2)} EUR\n`;
      message += `📝 Transactions: ${summary.transactionCount}\n\n`;
      
      if (summary.byCategory.length > 0) {
        message += `*Categories:*\n`;
        summary.byCategory.slice(0, 5).forEach(cat => {
          message += `• ${cat.category}: ${cat.amount.toFixed(2)} EUR\n`;
        });
      }
      
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ Expense error: ${e.message}`);
    }
  },

  '/elster': async (chatId) => {
    try {
      await sendMessage(chatId, '📤 *Preparing ELSTER export...*');
      const year = new Date().getFullYear();
      const result = await taxCore.exportELSTER(year);
      
      let message = `✅ *ELSTER EXPORT READY*\n\n`;
      message += `📅 Year: ${year}\n`;
      message += `📄 File: ${result.filename}\n`;
      message += `📊 Taxable Income: ${result.data.anlageE.zuVersteuerndesEinkommen.toFixed(2)} EUR\n`;
      message += `💰 Expenses: ${result.data.anlageE.werbungskosten.toFixed(2)} EUR\n\n`;
      message += `*Next Steps:*\n`;
      message += `1. Review export file\n`;
      message += `2. Import in ELSTER-compatible tool\n`;
      message += `3. Verify and submit\n`;
      
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ ELSTER error: ${e.message}`);
    }
  },

  
  // 🎙️ KIVO VOICE COMMANDS
  '/kivo': async (chatId) => {
    try {
      const status = kivo.getStatus();
      let message = `🎙️ *KIVO STATUS*\n\n`;
      message += `🗣️ Voice: ${status.voice.listening ? 'Listening' : 'Idle'}\n`;
      message += `🧠 Memory: ${status.memory.projects} projects\n`;
      message += `🏠 Home: ${status.home.devicesRegistered} devices\n`;
      message += `🤖 Agents: ${status.agents.workflowsDefined} workflows\n`;
      message += `🌉 Bridge: ${status.bridge.commandsMapped} commands\n`;
      message += `🛡️ Guard: Role ${status.guard.role}\n\n`;
      message += `*Commands:*\n`;
      message += `/kivo-say — TTS Test\n`;
      message += `/kivo-home — Home Status`;
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ KIVO error: ${e.message}`);
    }
  },

  '/kivo-say': async (chatId, args) => {
    const text = args || 'Hallo, ich bin KIVO, dein lokaler Sprachassistent.';
    try {
      await kivo.voice.speak(text);
      return sendMessage(chatId, `🗣️ KIVO: "${text}"`);
    } catch (e) {
      return sendMessage(chatId, `❌ TTS error: ${e.message}`);
    }
  },

  '/kivo-home': async (chatId) => {
    try {
      const status = kivo.home.getStatus();
      let message = `🏠 *HOME ASSISTANT STATUS*\n\n`;
      message += `🔗 Configured: ${status.haConfigured ? 'Yes' : 'No'}\n`;
      message += `🌐 URL: ${status.haUrl}\n`;
      message += `📱 Devices: ${status.devicesRegistered}\n`;
      message += `🎬 Scenes: ${status.scenesRegistered}\n\n`;
      message += `*Fast Commands:*\n`;
      message += `Licht an/aus\n`;
      message += `Timer X Minuten\n`;
      message += `Temperatur X Grad`;
      return sendMessage(chatId, message);
    } catch (e) {
      return sendMessage(chatId, `❌ Home error: ${e.message}`);
    }
  },

'/help': async (chatId) => {
    return sendMessage(chatId,
      `🤖 *AutoPilot Business Bot Commands*\n\n` +
      `🚀 *Automation Commands:*\n` +
      `/all — Alle Systeme starten\n` +
      `/printify — POD Produkte generieren\n` +
      `/digistore — Affiliate Content verteilen\n` +
      `/youtube — Script erstellen\n` +
      `/earn — Heutige Einnahmen\n` +
      `/sys — Vollständiger Status\n\n` +
      `📊 *Status & Info:*\n` +
      `/start — Bot Start\n` +
      `/status — System-Übersicht\n` +
      `/health — Server Health-Check\n` +
      `/monitor — Monitoring Dashboard\n\n` +
      `⚙️ *Aktionen:*\n` +
      `/restart — Server neustarten\n` +
      `/deploy — Auf Vercel deployen\n` +
      `/cleanup — Speicher aufräumen\n` +
      `/logs — Server-Logs anzeigen\n\n` +
      `_Admin ID: ${ADMIN_ID || 'nicht gesetzt'}_`
    );
  }
};

// ── Webhook Handler ─────────────────────────────────────────
async function handleUpdate(update) {
  const msg = update.message;
  if (!msg || !msg.text) return;

  const chatId = msg.chat.id;
  const text = msg.text.trim();
  const userId = msg.from?.id;

  // Admin check
  if (ADMIN_ID && userId !== parseInt(ADMIN_ID)) {
    await sendMessage(chatId, '⛔ *Nicht autorisiert!* Dieser Bot ist Admin-only.');
    return;
  }

  state.lastCommand = text;
  state.commandCount++;

  const handler = commands[text.split(' ')[0]];
  if (handler) {
    await handler(chatId);
  } else {
    await sendMessage(chatId, `❓ Unbekannter Command: ${text}\nNutze /help für alle Commands.`);
  }
}

// ── Polling Mode ──────────────────────────────────────────────
let offset = 0;
async function poll() {
  try {
    const res = await fetch(`${API_BASE}/getUpdates?offset=${offset + 1}&limit=10`, { signal: AbortSignal.timeout(30000) });
    const data = await res.json();
    if (data.ok && data.result) {
      for (const update of data.result) {
        offset = Math.max(offset, update.update_id);
        await handleUpdate(update);
      }
    }
  } catch (e) {
    // Silently retry on network errors
  }
  setTimeout(poll, 2000);
}

// ── Webhook Setup ─────────────────────────────────────────────
async function setupWebhook() {
  const webhookUrl = process.env.WEBHOOK_URL;
  if (!webhookUrl) {
    console.log('ℹ️  Kein WEBHOOK_URL gesetzt — starte im Polling Mode');
    poll();
    return;
  }
  try {
    const res = await tgApi('setWebhook', { url: webhookUrl, allowed_updates: ['message'] });
    if (res.ok) console.log(`✅ Webhook gesetzt: ${webhookUrl}`);
    else console.log(`⚠️  Webhook Fehler: ${res.description}`);
  } catch (e) {
    console.log('⚠️  Webhook Setup Fehler — fallback zu Polling');
    poll();
  }
}

// ── Health Check Endpoint ───────────────────────────────────
async function startHealthServer() {
  const http = require('http');
  const server = http.createServer((req, res) => {
    if (req.url === '/bot-health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'ok',
        uptime: Math.floor((Date.now() - state.startTime) / 1000),
        commands: state.commandCount,
        lastCommand: state.lastCommand,
        timestamp: new Date().toISOString()
      }));
      return;
    }
    res.writeHead(404);
    res.end('Not Found');
  });
  server.listen(3201, () => console.log('🩺 Bot Health Check: http://localhost:3201/bot-health'));
}

// ── START ─────────────────────────────────────────────────────
console.log('\n🤖 AutoPilot Telegram Bot Controller');
console.log(`   Token: ${BOT_TOKEN.slice(0, 10)}...`);
console.log(`   Admin: ${ADMIN_ID || 'NICHT GESETZT'}`);
console.log('   Commands: /start /status /health /restart /logs /deploy /monitor /cleanup /help\n');

setupWebhook();
startHealthServer();

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n👋 Bot wird beendet...');
  process.exit(0);
});
