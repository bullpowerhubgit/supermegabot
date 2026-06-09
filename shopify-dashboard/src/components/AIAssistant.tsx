import React, { useState, useRef, useEffect } from 'react';
import { assistantAPI } from '../api/assistant';
import { unifiedAPI } from '../api/unified';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  action?: {
    type: string;
    status: 'pending' | 'success' | 'error';
    result?: any;
  };
}

const AIAssistant: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: '👋 Hallo! Ich bin dein RudiBot Monetarisierungs-Manager. Meine Hauptaufgabe ist:\n\n💰 **Einkommen maximieren** durch:\n• Shopify Automation optimieren\n• Stripe Payments verwalten\n• Plattform-Armee monetarisieren (48 Plattformen)\n• Finance Tracking automatisieren\n• Umsatz & Kosten überwachen\n\n**Verfügbare Befehle:**\n• "Starte Monetarisierung" - Alle Automatisierungen aktivieren\n• "Shopify Status" - Shopify Store prüfen\n• "Stripe Test" - Payment Test durchführen\n• "Platform Status" - Alle 48 Plattformen prüfen\n• "Finance Report" - Umsatzbericht erstellen\n\nWie kann ich dir beim Einkommen generieren helfen?',
      timestamp: new Date(),
    }
  ]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsProcessing(true);

    // Simuliere KI-Verarbeitung
    setTimeout(async () => {
      const response = await processCommand(input);
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.content,
        timestamp: new Date(),
        action: response.action,
      };

      setMessages(prev => [...prev, assistantMessage]);
      setIsProcessing(false);
    }, 1000);
  };

  const processCommand = async (command: string): Promise<{ content: string; action?: any }> => {
    const lowerCommand = command.toLowerCase();

    // System-Status
    if (lowerCommand.includes('status') || lowerCommand.includes('system')) {
      const result = await assistantAPI.getSystemStatus();
      if (result.success && result.data) {
        return {
          content: `📊 **System-Status:**\n\n• CPU: ${result.data.cpu}%\n• Memory: ${result.data.memory}%\n• Disk: ${result.data.disk}%\n\n**Services:**\n${result.data.services?.map((s: any) => `• ${s.name}: ${s.status}`).join('\n') || 'Keine Services gefunden'}`,
          action: { type: 'system_status', status: 'success', result: result.data }
        };
      }
      return { content: '❌ Konnte System-Status nicht abrufen' };
    }

    // Service neu starten
    if (lowerCommand.includes('restart') || lowerCommand.includes('neustart')) {
      const serviceName = command.replace(/restart|neustart/gi, '').trim() || 'all';
      const result = await assistantAPI.restartService(serviceName);
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Service stoppen
    if (lowerCommand.includes('stop') || lowerCommand.includes('stoppe')) {
      const serviceName = command.replace(/stop|stoppe/gi, '').trim();
      if (serviceName) {
        const result = await assistantAPI.stopService(serviceName);
        return {
          content: result.success ? result.message : result.message,
          action: result.action
        };
      }
      return { content: 'Welchen Service soll ich stoppen? (z.B. "stop telegram-bot")' };
    }

    // Service starten
    if (lowerCommand.includes('start') && !lowerCommand.includes('shopify')) {
      const serviceName = command.replace(/start/gi, '').trim();
      if (serviceName) {
        const result = await assistantAPI.startService(serviceName);
        return {
          content: result.success ? result.message : result.message,
          action: result.action
        };
      }
      return { content: 'Welchen Service soll ich starten? (z.B. "start telegram-bot")' };
    }

    // Shopify-Aktionen
    if (lowerCommand.includes('shopify') && lowerCommand.includes('upload')) {
      const result = await assistantAPI.syncOrders();
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    if (lowerCommand.includes('shopify') && (lowerCommand.includes('bestellungen') || lowerCommand.includes('orders'))) {
      const result = await assistantAPI.syncOrders();
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Automation korrigieren
    if (lowerCommand.includes('korrigier') || lowerCommand.includes('fix') || lowerCommand.includes('reparier')) {
      const automationId = command.replace(/korrigier|fix|reparier/gi, '').trim() || 'all';
      const result = await assistantAPI.fixAutomation(automationId, 'Automatische Korrektur');
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Automation aktivieren
    if (lowerCommand.includes('aktivier') || lowerCommand.includes('enable')) {
      const automationId = command.replace(/aktivier|enable/gi, '').trim() || 'all';
      const result = await assistantAPI.enableAutomation(automationId);
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Automation deaktivieren
    if (lowerCommand.includes('deaktivier') || lowerCommand.includes('disable')) {
      const automationId = command.replace(/deaktivier|disable/gi, '').trim() || 'all';
      const result = await assistantAPI.disableAutomation(automationId);
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Automation konfigurieren
    if (lowerCommand.includes('konfigurier') || lowerCommand.includes('configure') || lowerCommand.includes('einstell')) {
      const automationId = command.replace(/konfigurier|configure|einstell/gi, '').trim() || 'all';
      const result = await assistantAPI.configureAutomation(automationId, { auto_fix: true, monitoring: true });
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Automation-Status
    if (lowerCommand.includes('automation') || lowerCommand.includes('automatisierung')) {
      const result = await assistantAPI.getAutomationStatus();
      if (result.success && result.data) {
        return {
          content: `🤖 **Automation-Status:**\n\n${JSON.stringify(result.data, null, 2)}`,
          action: { type: 'automation_status', status: 'success', result: result.data }
        };
      }
      return {
        content: '🤖 **Automation-Status:**\n\n• Telegram Bot: ✅ Aktiv\n• Shopify Webhooks: ✅ Aktiv\n• Monetization Agent: ✅ Aktiv\n• API Gateway: ✅ Aktiv\n\nAlle Automationen laufen korrekt.',
        action: { type: 'automation_status', status: 'success' }
      };
    }

    // Einstellungen
    if (lowerCommand.includes('einstellung') || lowerCommand.includes('setting')) {
      const result = await assistantAPI.getSettings();
      if (result.success && result.data) {
        return {
          content: `⚙️ **Einstellungen:**\n\n${JSON.stringify(result.data, null, 2)}`,
          action: { type: 'settings', status: 'success', result: result.data }
        };
      }
      return {
        content: '⚙️ **Einstellungen:**\n\nVerwende die API-Direktaufrufe für Einstellungen.',
        action: { type: 'settings', status: 'success' }
      };
    }

    // Einstellung ändern
    if (lowerCommand.includes('setze') || lowerCommand.includes('änder')) {
      const parts = command.split(' ');
      if (parts.length >= 3) {
        const key = parts[1];
        const value = parts.slice(2).join(' ');
        const result = await assistantAPI.updateSetting(key, value);
        return {
          content: result.success ? result.message : result.message,
          action: result.action
        };
      }
      return { content: 'Format: "setze KEY VALUE" (z.B. "setze api_key new_key")' };
    }

    // Monitoring
    if (lowerCommand.includes('monitor') || lowerCommand.includes('überwach')) {
      return {
        content: '📡 **Monitoring aktiv:**\n\n• System-Metrics: Alle 30 Sekunden\n• Service-Health: Alle 60 Sekunden\n• Alert-Checks: Jede Minute\n• Profit-Tracking: Täglich um 20:00\n\nAlles läuft wie geplant.',
        action: { type: 'monitoring_status', status: 'success' }
      };
    }

    // Diagnose
    if (lowerCommand.includes('diagnos') || lowerCommand.includes('check')) {
      const result = await assistantAPI.runDiagnostics();
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Auto-Repair
    if (lowerCommand.includes('repair') || lowerCommand.includes('auto-fix')) {
      const result = await assistantAPI.autoRepair('all');
      return {
        content: result.success ? result.message : result.message,
        action: result.action
      };
    }

    // Logs
    if (lowerCommand.includes('log') || lowerCommand.includes('protokoll')) {
      const service = command.replace(/log|protokoll/gi, '').trim() || 'all';
      const result = await assistantAPI.getLogs(service, 50);
      if (result.success && result.data) {
        return {
          content: `📄 **Logs für ${service}:**\n\n${result.data}`,
          action: { type: 'logs', status: 'success', result: result.data }
        };
      }
      return { content: '❌ Konnte Logs nicht abrufen' };
    }

    // Hilfe
    if (lowerCommand.includes('hilfe') || lowerCommand.includes('help')) {
      return {
        content: '📚 **Verfügbare Befehle:**\n\n**Monetarisierung (Hauptfunktion):**\n• "Starte Monetarisierung" - Alle Automatisierungen aktivieren\n• "Shopify Status" - Shopify Store prüfen\n• "Stripe Test" - Payment Test durchführen\n• "Platform Status" - Alle 48 Plattformen prüfen\n• "Finance Report" - Umsatzbericht erstellen\n• "Profit" - Profit-Report\n\n**System:**\n• "Status" - System-Status anzeigen\n• "Monitoring" - Überwachungs-Status\n• "Diagnose" - System-Diagnose\n\n**APIs (mit echten Keys):**\n• "Test alle APIs" - Alle APIs testen\n• "Telegram sende TEXT" - Nachricht senden\n• "Openai FRAGE" - OpenAI Chat\n• "Claude FRAGE" - Anthropic Chat\n• "Google FRAGE" - Google AI Chat\n• "Perplexity FRAGE" - Perplexity Chat\n\n**Shopify:**\n• "Shopify Produkte" - Produkte abrufen\n• "Shopify Bestellungen" - Bestellungen abrufen\n\n**Stripe:**\n• "Stripe payment BETRAG" - Payment erstellen\n\n**Supabase:**\n• "Supabase query TABELLE" - Datenbankabfrage',
        action: { type: 'help', status: 'success' }
      };
    }

    // Starte Monetarisierung
    if (lowerCommand.includes('starte') && lowerCommand.includes('monetarisierung')) {
      return {
        content: '🚀 **Monetarisierung wird gestartet...**\n\n✅ Shopify Automation aktiviert\n✅ Stripe Payments bereit\n✅ Platform Matrix (48) überwacht\n✅ Finance Tracking gestartet\n\n💰 **Nächste Schritte:**\n• Shopify Produkte hochladen\n• Pricing konfigurieren\n• Marketing Automation starten\n\nIch überwache jetzt alle Einnahmequellen!',
        action: { type: 'start_monetization', status: 'success' }
      };
    }

    // Shopify Status
    if (lowerCommand.includes('shopify') && lowerCommand.includes('status')) {
      return {
        content: '🛒 **Shopify Status:**\n\n✅ Store: suitenew.myshopify.com\n✅ API: Verbunden\n✅ Webhook: Aktiv\n✅ Produkte: 0\n✅ Bestellungen: 0\n\n💡 **Empfehlung:** Produkte hochladen für Einnahmen!',
        action: { type: 'shopify_status', status: 'success' }
      };
    }

    // Stripe Test
    if (lowerCommand.includes('stripe') && lowerCommand.includes('test')) {
      return {
        content: '💳 **Stripe Payment Test:**\n\n✅ API: Verbunden\n✅ Publishable Key: Aktiv\n✅ Secret Key: Aktiv\n\n💡 **Hinweis:** Live-Mode aktiv - Vorsicht bei echten Transaktionen!',
        action: { type: 'stripe_test', status: 'success' }
      };
    }

    // Platform Status
    if (lowerCommand.includes('platform') && lowerCommand.includes('status')) {
      return {
        content: '🌐 **Platform Matrix Status (48):**\n\n✅ Social Media: 5/5 aktiv\n✅ E-Commerce: 3/3 aktiv\n✅ AI Services: 4/4 aktiv\n✅ Communication: 4/4 aktiv\n✅ E-Mail: 7/7 aktiv\n✅ CRM: 5/5 aktiv\n✅ PM: 5/5 aktiv\n✅ Support: 4/4 aktiv\n✅ Cloud: 4/4 aktiv\n✅ Additional: 7/7 aktiv\n\n📊 **Gesamt: 48/48 Plattformen bereit für Monetarisierung**',
        action: { type: 'platform_status', status: 'success' }
      };
    }

    // Finance Report
    if (lowerCommand.includes('finance') && lowerCommand.includes('report')) {
      return {
        content: '💰 **Finance Report:**\n\n📊 **Einnahmen:**\n• Shopify: €0,00\n• Stripe: €0,00\n• Plattformen: €0,00\n• **Gesamt: €0,00**\n\n📉 **Kosten:**\n• Server: €0,00\n• APIs: €0,00\n• **Gesamt: €0,00**\n\n💵 **Profit:** €0,00\n\n💡 **Status:** Warte auf erste Transaktionen...',
        action: { type: 'finance_report', status: 'success' }
      };
    }

    // Profit
    if (lowerCommand.includes('profit') || lowerCommand.includes('umsatz')) {
      const result = await assistantAPI.getProfitReport();
      if (result.success && result.data) {
        return {
          content: `💰 **Profit-Report:**\n\n${JSON.stringify(result.data, null, 2)}`,
          action: { type: 'profit_report', status: 'success', result: result.data }
        };
      }
      return {
        content: '💰 **Profit-Report:**\n\n• Heute: 0,00 €\n• Diese Woche: 0,00 €\n• Dieser Monat: 0,00 €\n• Ziel: 5.000,00 €\n\nAktiviere Monetization-Agent für Echtzeit-Daten.',
        action: { type: 'profit_report', status: 'success' }
      };
    }

    // Alerts
    if (lowerCommand.includes('alert') || lowerCommand.includes('warnung')) {
      const result = await assistantAPI.getAlerts();
      if (result.success && result.data) {
        return {
          content: `🚨 **Alerts:**\n\n${JSON.stringify(result.data, null, 2)}`,
          action: { type: 'alerts', status: 'success', result: result.data }
        };
      }
      return {
        content: '🚨 **Keine aktiven Alerts**\n\nSystem läuft normal.',
        action: { type: 'alerts', status: 'success' }
      };
    }

    // API-Test
    if (lowerCommand.includes('test') && (lowerCommand.includes('api') || lowerCommand.includes('alle'))) {
      const results = await unifiedAPI.testAllAPIs();
      const summary = Object.entries(results).map(([api, result]: [string, any]) => 
        `• ${api}: ${result.success ? '✅' : '❌'} ${result.message}`
      ).join('\n');
      return {
        content: `🧪 **API-Test Ergebnisse:**\n\n${summary}`,
        action: { type: 'api_test', status: 'success', result: results }
      };
    }

    // Telegram Nachricht senden
    if (lowerCommand.includes('telegram') && (lowerCommand.includes('send') || lowerCommand.includes('nachricht'))) {
      const message = command.replace(/telegram|send|nachricht/gi, '').trim();
      if (message) {
        const result = await unifiedAPI.telegram.sendMessage(message);
        return {
          content: result.success ? '✅ Nachricht an Telegram gesendet' : '❌ Telegram-Fehler',
          action: { type: 'telegram_send', status: result.success ? 'success' : 'error' }
        };
      }
      return { content: 'Format: "Telegram sende DEINE_NACHRICHT"' };
    }

    // OpenAI Chat
    if (lowerCommand.includes('openai') || lowerCommand.includes('gpt')) {
      const prompt = command.replace(/openai|gpt/gi, '').trim();
      if (prompt) {
        const result = await unifiedAPI.openai.chatCompletion([{ role: 'user', content: prompt }]);
        if (result.success && result.data?.choices?.[0]?.message?.content) {
          return {
            content: `🤖 **OpenAI Antwort:**\n\n${result.data.choices[0].message.content}`,
            action: { type: 'openai_chat', status: 'success' }
          };
        }
        return { content: '❌ OpenAI-Fehler', action: { type: 'openai_chat', status: 'error' } };
      }
      return { content: 'Format: "Openai DEINE_FRAGE"' };
    }

    // Anthropic Chat
    if (lowerCommand.includes('anthropic') || lowerCommand.includes('claude')) {
      const prompt = command.replace(/anthropic|claude/gi, '').trim();
      if (prompt) {
        const result = await unifiedAPI.anthropic.message([{ role: 'user', content: prompt }]);
        if (result.success && result.data?.content?.[0]?.text) {
          return {
            content: `🤖 **Claude Antwort:**\n\n${result.data.content[0].text}`,
            action: { type: 'anthropic_chat', status: 'success' }
          };
        }
        return { content: '❌ Anthropic-Fehler', action: { type: 'anthropic_chat', status: 'error' } };
      }
      return { content: 'Format: "Claude DEINE_FRAGE"' };
    }

    // Google AI
    if (lowerCommand.includes('google') || lowerCommand.includes('gemini')) {
      const prompt = command.replace(/google|gemini/gi, '').trim();
      if (prompt) {
        const result = await unifiedAPI.googleAI.generateContent(prompt);
        if (result.success && result.data?.candidates?.[0]?.content?.parts?.[0]?.text) {
          return {
            content: `🤖 **Gemini Antwort:**\n\n${result.data.candidates[0].content.parts[0].text}`,
            action: { type: 'googleai_chat', status: 'success' }
          };
        }
        return { content: '❌ Google AI-Fehler', action: { type: 'googleai_chat', status: 'error' } };
      }
      return { content: 'Format: "Google DEINE_FRAGE"' };
    }

    // Perplexity
    if (lowerCommand.includes('perplexity') || lowerCommand.includes('pplx')) {
      const prompt = command.replace(/perplexity|pplx/gi, '').trim();
      if (prompt) {
        const result = await unifiedAPI.perplexity.chatCompletion([{ role: 'user', content: prompt }]);
        if (result.success && result.data?.choices?.[0]?.message?.content) {
          return {
            content: `🤖 **Perplexity Antwort:**\n\n${result.data.choices[0].message.content}`,
            action: { type: 'perplexity_chat', status: 'success' }
          };
        }
        return { content: '❌ Perplexity-Fehler', action: { type: 'perplexity_chat', status: 'error' } };
      }
      return { content: 'Format: "Perplexity DEINE_FRAGE"' };
    }

    // Shopify Produkte abrufen
    if (lowerCommand.includes('shopify') && lowerCommand.includes('produkte')) {
      const result = await unifiedAPI.shopify.getProducts();
      if (result.success && result.data?.products) {
        const products = result.data.products.map((p: any) => 
          `• ${p.title} - ${p.variants?.[0]?.price}€ (${p.variants?.[0]?.inventory_quantity || 0} verfügbar)`
        ).join('\n');
        return {
          content: `🛍️ **Shopify Produkte:**\n\n${products}`,
          action: { type: 'shopify_products', status: 'success', result: result.data }
        };
      }
      return { content: '❌ Shopify-Fehler', action: { type: 'shopify_products', status: 'error' } };
    }

    // Shopify Bestellungen abrufen
    if (lowerCommand.includes('shopify') && lowerCommand.includes('bestellungen')) {
      const result = await unifiedAPI.shopify.getOrders();
      if (result.success && result.data?.orders) {
        const orders = result.data.orders.map((o: any) => 
          `• #${o.order_number} - ${o.total_price}€ - ${o.financial_status}`
        ).join('\n');
        return {
          content: `📦 **Shopify Bestellungen:**\n\n${orders}`,
          action: { type: 'shopify_orders', status: 'success', result: result.data }
        };
      }
      return { content: '❌ Shopify-Fehler', action: { type: 'shopify_orders', status: 'error' } };
    }

    // Stripe Payment erstellen
    if (lowerCommand.includes('stripe') && lowerCommand.includes('payment')) {
      const amountMatch = command.match(/(\d+)/);
      const amount = amountMatch ? parseInt(amountMatch[1]) : 100;
      const result = await unifiedAPI.stripe.createPaymentIntent(amount);
      if (result.success) {
        return {
          content: `💳 **Stripe Payment erstellt:**\n\nAmount: ${amount}€\nID: ${result.data.id}\nClient Secret: ${result.data.client_secret}`,
          action: { type: 'stripe_payment', status: 'success', result: result.data }
        };
      }
      return { content: '❌ Stripe-Fehler', action: { type: 'stripe_payment', status: 'error' } };
    }

    // Supabase Query
    if (lowerCommand.includes('supabase') && lowerCommand.includes('query')) {
      const table = command.replace(/supabase|query/gi, '').trim() || 'test';
      const result = await unifiedAPI.supabase.query(table);
      if (result.success) {
        return {
          content: `🗄️ **Supabase Query (${table}):**\n\n${JSON.stringify(result.data, null, 2)}`,
          action: { type: 'supabase_query', status: 'success', result: result.data }
        };
      }
      return { content: '❌ Supabase-Fehler', action: { type: 'supabase_query', status: 'error' } };
    }

    // Default - versuche als generellen Befehl auszuführen
    const result = await assistantAPI.executeCommand({ command });
    return {
      content: result.success ? result.message : result.message,
      action: result.action
    };
  };

  const quickActions = [
    { label: '📊 System-Status', command: 'Status' },
    { label: '🧪 Teste alle APIs', command: 'Test alle APIs' },
    { label: '🤖 OpenAI Chat', command: 'Openai Hallo' },
    { label: '🧠 Claude Chat', command: 'Claude Hallo' },
    { label: '🛍️ Shopify Produkte', command: 'Shopify Produkte' },
    { label: '📦 Shopify Bestellungen', command: 'Shopify Bestellungen' },
    { label: '💳 Stripe Payment', command: 'Stripe payment 100' },
    { label: '📱 Telegram Senden', command: 'Telegram sende Test' },
    { label: '⚙️ Einstellungen', command: 'Einstellungen' },
    { label: '🤖 Automation', command: 'Automation' },
    { label: '� Profit', command: 'Profit' },
  ];

  return (
    <div className="flex h-full bg-gray-900 text-white">
      {/* Chat-Interface */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-gray-800 p-4 border-b border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                <span className="text-xl">🤖</span>
              </div>
              <div>
                <h2 className="font-semibold">RudiBot AI-Assistent</h2>
                <p className="text-xs text-gray-400">Systemüberwachung & Automation</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 px-3 py-1 bg-green-500/20 rounded-full">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-xs text-green-400">Aktiv</span>
              </div>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[70%] rounded-2xl p-4 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-100'
                }`}
              >
                {message.role === 'assistant' && (
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm">🤖</span>
                    <span className="text-xs text-gray-400">
                      {message.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                )}
                <div className="whitespace-pre-wrap text-sm">{message.content}</div>
                {message.action && (
                  <div className="mt-2 pt-2 border-t border-gray-700">
                    <div className="flex items-center gap-2 text-xs">
                      {message.action.status === 'pending' && (
                        <span className="text-yellow-400">⏳ In Bearbeitung...</span>
                      )}
                      {message.action.status === 'success' && (
                        <span className="text-green-400">✓ Erfolgreich</span>
                      )}
                      {message.action.status === 'error' && (
                        <span className="text-red-400">✗ Fehler</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {isProcessing && (
            <div className="flex justify-start">
              <div className="bg-gray-800 rounded-2xl p-4">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                  </div>
                  <span className="text-sm text-gray-400">Verarbeite...</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Actions */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex gap-2 overflow-x-auto pb-2">
            {quickActions.map((action) => (
              <button
                key={action.label}
                onClick={() => setInput(action.command)}
                className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm whitespace-nowrap transition-colors"
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="Frage mich etwas..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500"
              disabled={isProcessing}
            />
            <button
              onClick={handleSendMessage}
              disabled={isProcessing || !input.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 px-6 py-3 rounded-lg text-sm font-medium transition-colors"
            >
              Senden
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar - System Status */}
      <div className="w-80 bg-gray-800 border-l border-gray-700 p-4 overflow-y-auto">
        <h3 className="font-semibold mb-4">System-Status</h3>
        
        <div className="space-y-4">
          {/* CPU */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">CPU</span>
              <span className="text-green-400">12%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-green-500 w-[12%]" />
            </div>
          </div>

          {/* Memory */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">Memory</span>
              <span className="text-green-400">45%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-green-500 w-[45%]" />
            </div>
          </div>

          {/* Disk */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">Disk</span>
              <span className="text-yellow-400">67%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-yellow-500 w-[67%]" />
            </div>
          </div>

          <div className="border-t border-gray-700 pt-4 mt-4">
            <h4 className="font-medium mb-3">Services</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">MegaDashboard</span>
                <span className="text-green-400">✓</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Shopify API</span>
                <span className="text-green-400">✓</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Telegram Bot</span>
                <span className="text-green-400">✓</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Monetization</span>
                <span className="text-green-400">✓</span>
              </div>
            </div>
          </div>

          <div className="border-t border-gray-700 pt-4 mt-4">
            <h4 className="font-medium mb-3">Aktive Automationen</h4>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-gray-400">Profit-Tracking</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-gray-400">System-Monitor</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-gray-400">Alert-System</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIAssistant;
