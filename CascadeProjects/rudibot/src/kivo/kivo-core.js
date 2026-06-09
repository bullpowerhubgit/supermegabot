/**
 * KIVO Core (Embedded) — Thinking, Memory, Intent Detection, Response Logic
 * Embedded version for tight Rudibot integration
 */

const { KivoMemory } = require('../50-kivo/kivo-memory');
const { KivoRudibotBridge } = require('../50-kivo/kivo-rudibot-bridge');
const { KivoGuard } = require('../50-kivo/kivo-guard');

class EmbeddedKivoCore {
  constructor(options = {}) {
    this.memory = new KivoMemory();
    this.bridge = new KivoRudibotBridge(options.rudibot);
    this.guard = new KivoGuard(options.guard);
    this.session = null;
  }

  // ── Intent Classification ───────────────────────────────────
  classifyIntent(text) {
    const lower = text.toLowerCase();
    
    // Fast path — home control
    if (/licht|lampe|light|steckdose|schalter/i.test(lower)) 
      return { type: 'home', action: 'control', confidence: 0.9 };
    if (/temperatur|heizung|thermostat/i.test(lower)) 
      return { type: 'home', action: 'climate', confidence: 0.9 };
    if (/timer|wecker|alarm|countdown/i.test(lower)) 
      return { type: 'home', action: 'timer', confidence: 0.95 };
    if (/tor|garage|tür|schloss/i.test(lower)) 
      return { type: 'home', action: 'access', confidence: 0.9 };

    // Agent path — complex tasks
    if (/abo|vertrag|kündig|subscription|cancel/i.test(lower)) 
      return { type: 'agent', action: 'subscription', confidence: 0.85 };
    if (/steuer|tax|elster|finanz/i.test(lower)) 
      return { type: 'agent', action: 'finance', confidence: 0.85 };
    if (/scan|audit|security|sicherheit/i.test(lower)) 
      return { type: 'agent', action: 'security', confidence: 0.85 };
    if (/report|status|übersicht|tagesbericht/i.test(lower)) 
      return { type: 'agent', action: 'report', confidence: 0.8 };
    if (/deepscan|deep scan|härten|hardening/i.test(lower)) 
      return { type: 'agent', action: 'deepscan', confidence: 0.9 };

    // Rudibot bridge
    if (/rudibot|bot|telegram|befehl/i.test(lower)) 
      return { type: 'rudibot', action: 'command', confidence: 0.8 };

    return { type: 'unknown', action: 'fallback', confidence: 0.5 };
  }

  // ── Process Text ───────────────────────────────────────────
  async processText(text, chatId) {
    if (!this.session) {
      this.session = { id: Date.now(), startedAt: Date.now(), chatId };
    }

    const intent = this.classifyIntent(text);
    const utterance = { text, intent, timestamp: Date.now() };
    
    // Store in memory
    this.memory.addConversationEntry({ 
      text, 
      intent, 
      source: 'telegram', 
      chatId 
    });

    // Guard check
    const intentStr = `${intent.type}.${intent.action}`;
    const guardCheck = this.guard.checkApproval(intentStr);

    if (!guardCheck.allowed && guardCheck.requiresApproval) {
      return {
        blocked: true,
        requiresApproval: true,
        reason: guardCheck.reason,
        action: intentStr,
        intent
      };
    }

    // Route by intent type
    switch (intent.type) {
      case 'home':
        return this.handleHomeIntent(intent, text);
      case 'agent':
        return this.handleAgentIntent(intent, text);
      case 'rudibot':
        return this.handleRudibotIntent(intent, text);
      default:
        return this.handleFallback(intent, text);
    }
  }

  async handleHomeIntent(intent, text) {
    const responses = {
      control: () => ({ message: '🏠 Home Control: Licht wird geschaltet...', device: 'light', action: 'toggle' }),
      climate: () => ({ message: '🌡️ Klimasteuerung wird angepasst...', device: 'climate', action: 'adjust' }),
      timer: () => {
        const match = text.match(/(\d+)\s*(min|minute|stunde|hour|sek|sec)/i);
        const minutes = match ? parseInt(match[1]) : 10;
        return { message: `⏰ Timer für ${minutes} Minuten gestellt`, timer: { minutes } };
      },
      access: () => ({ message: '🔓 Zugang wird geprüft...', device: 'garage', action: 'toggle' })
    };

    const handler = responses[intent.action] || responses.control;
    return handler();
  }

  async handleAgentIntent(intent, text) {
    const result = await this.bridge.handleComplexQuery(text);
    if (result.success && result.message) {
      return { message: result.message, agent: true };
    }
    return { message: '🤖 Agent-Aktion ausgeführt...', agent: true };
  }

  async handleRudibotIntent(intent, text) {
    const result = await this.bridge.handleComplexQuery(text);
    if (result.success && result.message) {
      return { message: result.message, rudibot: true };
    }
    return { message: '🤖 Rudibot-Aktion ausgeführt...', rudibot: true };
  }

  async handleFallback(intent, text) {
    return { 
      message: `🤔 Das habe ich nicht verstanden: "${text}"\n\nVersuche es mit "Licht an", "Timer 10 Minuten" oder "prüf meine Abos".`,
      fallback: true 
    };
  }

  // ── Approval Management ─────────────────────────────────────
  approve(intentStr) {
    const approval = this.guard.approve(intentStr);
    return approval;
  }

  // ── Session Management ─────────────────────────────────────
  endSession() {
    if (this.session) {
      this.session.endedAt = Date.now();
      const duration = this.session.endedAt - this.session.startedAt;
      this.memory.addConversationEntry({ 
        event: 'session_end', 
        duration,
        chatId: this.session.chatId 
      });
    }
    this.session = null;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      session: !!this.session,
      sessionId: this.session?.id || null,
      memory: this.memory.getStatus(),
      bridge: this.bridge.getStatus(),
      guard: this.guard.getStatus()
    };
  }
}

module.exports = { EmbeddedKivoCore };
