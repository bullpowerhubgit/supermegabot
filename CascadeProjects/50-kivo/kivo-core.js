/**
 * KIVO CORE — Main Orchestrator
 * Local-first voice agent integrating all KIVO modules
 */

const { KivoVoiceCore } = require('./kivo-voice-core');
const { KivoMemory } = require('./kivo-memory');
const { KivoHome } = require('./kivo-home');
const { KivoAgents } = require('./kivo-agents');
const { KivoRudibotBridge } = require('./kivo-rudibot-bridge');
const { KivoGuard } = require('./kivo-guard');

let KivoLLM;
try {
  KivoLLM = require('./kivo-llm').KivoLLM;
} catch {
  KivoLLM = null;
}

// Allowed intent types for LLM re-classification
const ALLOWED_INTENT_TYPES = new Set(['home', 'agent', 'rudibot', 'memory']);

function isValidIntent(candidate) {
  if (!candidate || typeof candidate !== 'object') return false;

  const { type, action, confidence } = candidate;

  if (typeof type !== 'string' || !ALLOWED_INTENT_TYPES.has(type)) return false;
  if (typeof action !== 'string' || !action.trim()) return false;
  if (typeof confidence !== 'number') return false;
  if (confidence < 0 || confidence > 1) return false;

  return true;
}

class KivoCore {
  constructor(options = {}) {
    this.voice = new KivoVoiceCore(options.voice);
    this.memory = new KivoMemory();
    this.home = new KivoHome(options.home);
    this.agents = new KivoAgents();
    this.bridge = new KivoRudibotBridge(options.rudibot);
    this.guard = new KivoGuard(options.guard);
    this.llm =
      KivoLLM && options.llm !== false
        ? new KivoLLM(options.llm || {})
        : null;

    this.agents.setupDefaultWorkflows();
    this.setupEventHandlers();
  }

  setupEventHandlers() {
    // Voice -> Intent -> Router
    if (typeof this.voice.on === 'function') {
      this.voice.on('utterance', async (utterance) => {
        try {
          await this.handleIntent(utterance);
        } catch (err) {
          console.error('[KIVO] Error handling utterance:', err);
        }
      });
    }

    // Approval requests
    if (typeof this.agents.on === 'function') {
      this.agents.on('workflow:approval_required', (event) => {
        console.log('[KIVO] Approval required:', event.reason);
      });
    }
  }

  async handleIntent(utterance) {
    if (!utterance || typeof utterance !== 'object') {
      console.warn('[KIVO] Invalid utterance payload:', utterance);
      await this.voice.speak('Das habe ich nicht verstanden.');
      return { unknown: true };
    }

    let { intent, text } = utterance;
    text = typeof text === 'string' ? text : '';

    if (!intent || typeof intent !== 'object') {
      intent = { type: 'memory', action: 'note', confidence: 0 };
    }

    const baseConfidence =
      typeof intent.confidence === 'number' ? intent.confidence : 0;

    // Optional: LLM-based re-classification for low-confidence intents
    if (this.llm && baseConfidence < 0.7 && text.trim()) {
      try {
        const llmIntent = await this.llm.classifyIntent(text);

        if (isValidIntent(llmIntent) && llmIntent.confidence > baseConfidence) {
          intent = llmIntent;
        }
      } catch (e) {
        console.error('[KIVO] LLM classifyIntent failed, using original intent:', e);
      }
    }

    // Store in memory
    this.memory.addConversationEntry({ text, intent, source: 'voice' });

    // Guard check
    const intentStr = `${intent.type}.${intent.action}`;
    const guardCheck = this.guard.checkApproval(intentStr);

    if (!guardCheck.allowed && guardCheck.requiresApproval) {
      await this.voice.speak(`Diese Aktion erfordert eine Freigabe: ${guardCheck.reason}. Sage "Freigabe" um fortzufahren.`);
      return { blocked: true, reason: guardCheck.reason, intent: intentStr };
    }

    // Route by intent type
    switch (intent.type) {
      case 'home':
        return this.handleHomeIntent(intent, text);
      case 'agent':
        return this.handleAgentIntent(intent, text);
      case 'rudibot':
        return this.handleRudibotIntent(intent, text);
      case 'memory':
        return this.handleMemoryIntent(intent, text);
      default:
        await this.voice.speak('Das habe ich nicht verstanden. Bitte wiederhole deine Anfrage.');
        return { unknown: true, intent };
    }
  }

  async handleHomeIntent(intent, text) {
    const responses = {
      control: async () => {
        await this.voice.speak('Home Control aktiviert.');
        return { device: 'unknown', action: 'control' };
      },
      climate: async () => {
        await this.voice.speak('Klima-Einstellung wird angepasst.');
        return { action: 'climate' };
      },
      timer: async () => {
        const match = text.match(
          /(\d+)\s*(min|minute|minuten|stunden|stunde|hour|hours|sek|sec|sekunde|sekunden)/i
        );
        let minutes = 10;

        if (match) {
          const value = parseInt(match[1], 10);
          const unit = match[2].toLowerCase();

          if (['stunde', 'stunden', 'hour', 'hours'].includes(unit)) {
            minutes = value * 60;
          } else if (['sek', 'sec', 'sekunde', 'sekunden'].includes(unit)) {
            minutes = Math.max(1, Math.ceil(value / 60));
          } else {
            minutes = value;
          }
        }

        const result = await this.home.setTimer(minutes, 'Kivo Timer');
        await this.voice.speak(`Timer für ${minutes} Minuten gestellt.`);
        return result;
      },
      access: async () => {
        await this.voice.speak('Zugang wird geprüft.');
        return { action: 'access' };
      },
    };

    const handler = responses[intent.action] || responses.control;
    return handler();
  }

  async handleAgentIntent(intent, text) {
    const workflows = {
      subscription: 'saas_cost_analysis',
      finance: 'tax_preparation',
      security: 'security_audit',
      report: 'morning_briefing',
      deepscan: 'security_audit',
    };

    const workflowId = workflows[intent.action];
    if (workflowId) {
      const run = await this.agents.runWorkflow(workflowId, { query: text });

      if (run.status === 'awaiting_approval') {
        await this.voice.speak('Ich habe eine Aktion vorbereitet, die eine Freigabe benötigt. Prüfe die Details und bestätige.');
      } else if (run.status === 'completed') {
        await this.voice.speak('Aufgabe abgeschlossen.');
      }

      return run;
    }

    // Fallback: direct bridge call
    const result = await this.bridge.handleComplexQuery(text);
    if (result.success && result.message) {
      await this.voice.speak(result.message);
    }
    return result;
  }

  async handleRudibotIntent(intent, text) {
    const result = await this.bridge.handleComplexQuery(text);
    if (result.success && result.message) {
      await this.voice.speak(result.message);
    }
    return result;
  }

  async handleMemoryIntent(intent, text) {
    await this.voice.speak('Ich habe mir das gemerkt.');
    return { stored: true };
  }

  // ── Main Entry ─────────────────────────────────────────────
  async processText(text) {
    const utterance = await this.voice.processUtterance(text, { emit: false });
    return this.handleIntent(utterance);
  }

  // ── Approval ─────────────────────────────────────────────
  async approve(intentStr) {
    const approval = this.guard.approve(intentStr);
    await this.voice.speak('Freigabe erteilt.');
    return approval;
  }

  // ── Status ───────────────────────────────────────────────
  getStatus() {
    return {
      voice: this.voice.getStatus(),
      memory: this.memory.getStatus(),
      home: this.home.getStatus(),
      agents: this.agents.getStatus(),
      bridge: this.bridge.getStatus(),
      guard: this.guard.getStatus(),
      llm: this.llm ? this.llm.getStatus() : null,
    };
  }
}

module.exports = { KivoCore };

// ── CLI / Direct Test ──────────────────────────────────────
if (require.main === module) {
  const kivo = new KivoCore();

  async function demo() {
    console.log('🎙️  KIVO CORE DEMO\n');

    const commands = [
      'Hey Kivo, Licht an',
      'Hey Kivo, Timer 10 Minuten',
      'Hey Kivo, Timer 1 Stunde',
      'Hey Kivo, prüf meine Abos',
      'Hey Kivo, starte Deepscan',
      'Hey Kivo, was kostet mich gerade unnötig Geld?',
      'Hey Kivo, zeig mir den Tagesbericht',
    ];

    for (const cmd of commands) {
      console.log(`\n🗣️  User: "${cmd}"`);
      const result = await kivo.processText(cmd);
      console.log('🤖 KIVO:', result);
    }

    console.log('\n📊 KIVO Status:', JSON.stringify(kivo.getStatus(), null, 2));
  }

  demo().catch(console.error);
}
