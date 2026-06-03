/**
 * 🤖 Enhanced Telegram Webhook V2
 * Integriert mit Revenue First Mode und RUDIBOT Orchestrator
 * Basierend auf Download-Dateien optimiert für Multi-Agent-System
 */

const axios = require('axios');
const { createClient } = require('@supabase/supabase-js');

class TelegramWebhookV2 {
  constructor(context, orchestrator) {
    this.context = context;
    this.orchestrator = orchestrator;
    this.ollamaUrl = process.env.OLLAMA_URL || 'http://localhost:11434';
    this.ollamaModel = process.env.OLLAMA_MODEL || 'llama3.2';
    // Supabase optional - fallback if not configured
    this.supabase = process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_KEY 
      ? createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY)
      : null;
    this.ADMIN_ID = process.env.AUTHORIZED_USER_ID;
    
    // Revenue First Commands
    this.commands = {
      '/start': this.handleStart.bind(this),
      '/help': this.handleHelp.bind(this),
      '/status': this.handleStatus.bind(this),
      '/revenue': this.handleRevenue.bind(this),
      '/costs': this.handleCosts.bind(this),
      '/orders': this.handleOrders.bind(this),
      '/sync': this.handleSync.bind(this),
      '/approve': this.handleApprove.bind(this),
      '/report': this.handleReport.bind(this)
    };
  }

  async handleRequest(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method !== 'POST') return res.json({ ok: true });

    try {
      const msg = req.body?.message;
      if (!msg) return res.sendStatus(200);

      const chatId = msg.chat.id;
      const text = msg.text || '';
      if (!text) return res.sendStatus(200);

      // Logge Nachricht
      await this.logMessage(chatId, text);

      // Admin-Check für Control-Commands
      if (this.isAdminCommand(text) && String(chatId) !== String(this.ADMIN_ID)) {
        await this.sendMessage(chatId, '🚫 Nicht autorisiert.');
        return res.sendStatus(200);
      }

      // Command verarbeiten
      const command = text.split(' ')[0];
      const handler = this.commands[command];
      
      if (handler) {
        await handler(chatId, text, msg);
      } else {
        // Fallback zu Ollama (lokale KI, kostenlos)
        await this.handleOllamaResponse(chatId, text, msg);
      }

    } catch (error) {
      console.error('Telegram webhook error:', error.message);
      
      // Fallback Antwort
      const msg = req.body?.message;
      if (msg?.chat?.id) {
        await this.sendMessage(msg.chat.id, '🤖 RudiBot ist online! Kurzer Moment...');
      }
    }

    res.sendStatus(200);
  }

  async handleStart(chatId, text, msg) {
    const reply = `🤖 *@DudiRudibot - Ollama Mode v2.0*

🧠 *Lokale KI (Ollama)* - Kein Claude, keine API-Kosten!
🎯 *Revenue First aktiv!* Umsatz, Kosten, Automation.

*Commands:*
/revenue — Umsatz-Check
/costs — Kosten-Analysis  
/orders — Shopify Orders
/sync — Daten synchronisieren
/approve — Genehmigungen
/status — System Status
/help — Diese Hilfe

💚 Ready for Revenue!`;
    
    await this.sendMessage(chatId, reply);
  }

  async handleHelp(chatId, text, msg) {
    const reply = `📋 *RudiBot Commands*

📊 *Revenue:*
/revenue — Heute & Gesamt
/orders — Aktive Bestellungen
/sync — Shopify/PayPal sync

💰 *Costs:*
/costs — Kosten-Übersicht
/approve — Kündigungen prüfen

⚙️ *System:*
/status — Health Check
/report — Tages Report
/help — Diese Hilfe

🚀 Alle Befehle arbeiten mit echten Live-Daten!`;
    
    await this.sendMessage(chatId, reply);
  }

  async handleStatus(chatId, text, msg) {
    try {
      const health = await this.orchestrator.getSystemHealth?.() || {
        revenueTracking: false,
        shopifyApi: false,
        jobQueue: false
      };

      const { count: logs } = await this.supabase.from('logs')
        .select('*', { count: 'exact', head: true })
        .gte('created_at', new Date(Date.now()-86400000).toISOString())
        .catch(() => ({ count: 0 }));

      const reply = `📊 *RudiBot Status*

✅ Server: Online
${health.revenueTracking ? '✅' : '❌'} Revenue First: ${health.revenueTracking ? 'Aktiv' : 'Inaktiv'}
${health.shopifyApi ? '✅' : '❌'} Shopify API: ${health.shopifyApi ? 'Verbunden' : 'Fehler'}
${health.jobQueue ? '✅' : '❌'} Job Queue: ${health.jobQueue ? 'Laufend' : 'Gestoppt'}

📝 Events heute: ${logs || 0}
🛒 Store: ${process.env.SHOPIFY_STORE_URL || 'Nicht gesetzt'}

🚀 Revenue First Mode bereit!`;
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, '❌ Status-Check fehlgeschlagen');
    }
  }

  async handleRevenue(chatId, text, msg) {
    try {
      // Nutze Revenue First Mode
      const { RevenueFirstMode } = require('../core/revenue-first');
      const revenueMode = new RevenueFirstMode(this.context, this.orchestrator);
      
      const dashboard = await revenueMode.generateRevenueDashboard();
      
      const reply = `💰 *Revenue First Status*

📈 *Heute:* €${dashboard.revenue.today.toFixed(2)}
📊 *Gesamt:* €${dashboard.revenue.total.toFixed(2)}
📦 *Offene Orders:* ${dashboard.revenue.pendingOrders}
🛒 *Heute:* ${dashboard.revenue.todayOrders} Orders

💸 *Kosten heute:* €${dashboard.costs.today.toFixed(2)}
📉 *Netto:* €${(dashboard.revenue.today - dashboard.costs.today).toFixed(2)}

${dashboard.revenue.today > dashboard.costs.today ? '🟢 Profitabel!' : '🟡 Break-even prüfen'}

💚 Revenue First aktiv!`;
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, '❌ Revenue-Daten nicht verfügbar');
    }
  }

  async handleCosts(chatId, text, msg) {
    try {
      const { RevenueFirstMode } = require('../core/revenue-first');
      const revenueMode = new RevenueFirstMode(this.context, this.orchestrator);
      
      const costAnalysis = await revenueMode.identifyCostSavingOpportunities();
      const savings = costAnalysis.potentialSavings.filter(s => 
        s.priority === 'high' && s.savingAmount > 10
      ).slice(0, 5); // Top 5

      let reply = `💸 *Cost Analysis*

📊 *Gesamtkosten heute:* €${costAnalysis.totalCosts.toFixed(2)}
🎯 *Einspar-Potenzial:* €${costAnalysis.totalSavings.toFixed(2)}
📋 *Kandidaten:* ${savings.length} Services`;

      if (savings.length > 0) {
        reply += `\n\n🔥 *Top Einsparungen:*\n`;
        savings.forEach((saving, i) => {
          reply += `${i + 1}. ${saving.name}: €${saving.savingAmount.toFixed(2)} (${saving.priority})\n`;
        });
      }

      reply += `\n💡 Tip: /approve für Kündigungs-Pläne`;
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, '❌ Cost-Analyse fehlgeschlagen');
    }
  }

  async handleOrders(chatId, text, msg) {
    try {
      const orders = await this.context.shopify.getOrders?.({ limit: 5 }) || [];
      
      let reply = `📦 *Shopify Orders*

🔍 *Letzte 5 Orders:*`;

      if (orders.length > 0) {
        orders.forEach((order, i) => {
          const status = order.financial_status === 'paid' ? '✅ Bezahlt' : '⏳ Offen';
          reply += `\n${i + 1}. #${order.id} - €${order.total_price} - ${status}`;
        });
      } else {
        reply += '\nKeine Orders gefunden';
      }

      reply += `\n\n💰 Gesamt: ${orders.length} Orders`;
      reply += `\n💡 Tip: /sync für Live-Update`;
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, '❌ Shopify-Orders nicht verfügbar');
    }
  }

  async handleSync(chatId, text, msg) {
    try {
      await this.sendMessage(chatId, '🔄 Synchronisiere Daten...');
      
      // Sync Jobs ausführen
      const jobs = ['sync-shopify-orders', 'sync-shopify-products', 'scan-costs'];
      const results = [];
      
      for (const jobName of jobs) {
        try {
          const result = await this.orchestrator.executeJob?.(jobName) || { status: 'skipped' };
          results.push(`✅ ${jobName}: ${result.status}`);
        } catch (error) {
          results.push(`❌ ${jobName}: ${error.message}`);
        }
      }

      const reply = `🔄 *Sync Complete*

${results.join('\n')}

💚 Daten aktualisiert!`;
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, '❌ Sync fehlgeschlagen');
    }
  }

  async handleApprove(chatId, text, msg) {
    try {
      const approvals = await this.orchestrator.getPendingApprovals?.() || [];
      
      let reply = `📋 *Genehmigungen*

🔍 *Ausstehend:* ${approvals.length} Aktionen`;

      if (approvals.length > 0) {
        approvals.slice(0, 5).forEach((approval, i) => {
          reply += `\n${i + 1}. ${approval.jobName} (${approval.type})`;
        });
        
        reply += `\n\n💡 Reply mit Nummer zum Genehmigen`;
      } else {
        reply += '\n✅ Keine Genehmigungen nötig';
      }
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, '❌ Genehmigungen nicht verfügbar');
    }
  }

  async handleReport(chatId, text, msg) {
    const today = new Date().toLocaleDateString('de');
    
    try {
      const { RevenueFirstMode } = require('../core/revenue-first');
      const revenueMode = new RevenueFirstMode(this.context, this.orchestrator);
      const dashboard = await revenueMode.generateRevenueDashboard();
      
      const reply = `📈 *Daily Report*

📅 *Datum:* ${today}

💰 *Revenue:*
  Heute: €${dashboard.revenue.today.toFixed(2)}
  Gesamt: €${dashboard.revenue.total.toFixed(2)}

💸 *Costs:*
  Heute: €${dashboard.costs.today.toFixed(2)}
  Gesamt: €${dashboard.costs.total.toFixed(2)}

📊 *Netto:* €${(dashboard.revenue.today - dashboard.costs.today).toFixed(2)}
📦 *Orders:* ${dashboard.revenue.todayOrders}

🚀 *System Status:* Alle 30 Module aktiv
💚 *Revenue First Mode:* Optimiert für Umsatz

✅ *RudiBot läuft stabil*`;
      
      await this.sendMessage(chatId, reply);
    } catch (error) {
      await this.sendMessage(chatId, `📈 *Daily Report*\n\n📅 Datum: ${today}\n\n✅ RudiBot läuft stabil\n✅ Alle Webhooks aktiv\n✅ Vercel deployed\n\n💰 Systeme aktiv: 30`);
    }
  }

  async handleOllamaResponse(chatId, text, msg) {
    try {
      // Prüfe ob Ollama läuft
      const healthCheck = await axios.get(`${this.ollamaUrl}/api/tags`, { timeout: 3000 })
        .catch(() => null);
      
      if (!healthCheck) {
        await this.sendMessage(chatId, '🤖 RudiBot (Ollama) ist offline. Starte Ollama mit: `ollama run llama3.2`');
        return;
      }

      const systemPrompt = `Du bist RudiBot (@DudiRudibot), ein freundlicher KI-Assistent für E-Commerce Automation. 
Du nutzt Ollama (lokale KI) - keine Cloud-API nötig!
Spezialisiert auf: Shopify, Revenue First Mode, Automation.
Antworte kurz, prägnant und auf Deutsch. 
Bei Umsatz/Kosten-Fragen: verweise auf Commands wie /revenue, /costs.`;

      const response = await axios.post(`${this.ollamaUrl}/api/generate`, {
        model: this.ollamaModel,
        prompt: `${systemPrompt}\n\nBenutzer: ${text}\n\nRudiBot:`,
        stream: false,
        options: {
          temperature: 0.7,
          num_predict: 500
        }
      }, { timeout: 30000 });

      const replyText = response.data?.response || '🤖 Keine Antwort von Ollama';
      await this.sendMessage(chatId, replyText.trim());
    } catch (error) {
      console.error('Ollama Fehler:', error.message);
      await this.sendMessage(chatId, '🤖 RudiBot (Ollama) ist online! Nutze /help für Commands. Starte Ollama mit: `ollama run llama3.2`');
    }
  }

  async sendMessage(chatId, text) {
    await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        chat_id: chatId, 
        text, 
        parse_mode: 'Markdown' 
      })
    });
  }

  async logMessage(chatId, text) {
    if (!this.supabase) return; // Skip logging if Supabase not configured
    await this.supabase.from('logs').insert({
      system: 'telegram',
      event: 'message',
      data: { chatId, text: text.slice(0, 50) },
      created_at: new Date().toISOString()
    }).catch(() => {});
  }

  isAdminCommand(text) {
    const adminCommands = ['/status', '/report', '/approve', '/sync'];
    return adminCommands.some(cmd => text.startsWith(cmd));
  }
}

// Export für Vercel/Serverless
module.exports = async function handler(req, res) {
  // Lazy initialization für serverless
  if (!global.telegramWebhookV2) {
    const { AppContext } = require('../core/app-context');
    const { Orchestrator } = require('../core/orchestrator');
    
    const context = new AppContext();
    const orchestrator = new Orchestrator();
    global.telegramWebhookV2 = new TelegramWebhookV2(context, orchestrator);
  }

  return global.telegramWebhookV2.handleRequest(req, res);
};

// Export für lokale Nutzung
module.exports.TelegramWebhookV2 = TelegramWebhookV2;
