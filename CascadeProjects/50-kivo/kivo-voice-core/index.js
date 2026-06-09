/**
 * KIVO VOICE CORE — Wake Word, STT, TTS, Session Handling
 * Local-first voice processing pipeline
 */

const EventEmitter = require('events');
const fs = require('fs');
const path = require('path');

const CONFIG = {
  wakeWord: 'Hey Kivo',
  wakeWordVariants: ['hey kivo', 'kivo', 'okay kivo'],
  sttProvider: process.env.KIVO_STT_PROVIDER || 'whisper-local', // whisper-local, openai-whisper
  ttsProvider: process.env.KIVO_TTS_PROVIDER || 'piper', // piper, coqui
  language: process.env.KIVO_LANGUAGE || 'de-DE',
  sessionTimeoutMs: 30000, // 30s session timeout
  maxRecordingSec: 30,
};

class KivoVoiceCore extends EventEmitter {
  constructor(options = {}) {
    super();
    this.config = { ...CONFIG, ...options };
    this.session = null;
    this.isListening = false;
    this.audioBuffer = [];
    this.sessionTimer = null;
  }

  // ── Wake Word Detection ────────────────────────────────────
  detectWakeWord(transcript) {
    const lower = transcript.toLowerCase().trim();
    const detected = this.config.wakeWordVariants.some(v => lower.includes(v));
    if (detected) {
      this.emit('wake', { transcript, timestamp: new Date().toISOString() });
      this.startSession();
    }
    return detected;
  }

  // ── Session Management ─────────────────────────────────────
  startSession() {
    if (this.session) this.endSession();
    this.session = {
      id: `sess-${Date.now()}`,
      startedAt: Date.now(),
      utterances: [],
      context: {},
    };
    this.isListening = true;
    this.emit('session:start', this.session);

    this.sessionTimer = setTimeout(() => {
      this.emit('session:timeout', this.session);
      this.endSession();
    }, this.config.sessionTimeoutMs);
  }

  endSession() {
    if (this.sessionTimer) clearTimeout(this.sessionTimer);
    if (this.session) {
      this.session.endedAt = Date.now();
      this.emit('session:end', this.session);
    }
    this.session = null;
    this.isListening = false;
    this.audioBuffer = [];
  }

  // ── STT (Speech-to-Text) ───────────────────────────────────
  async transcribe(audioBuffer) {
    // Placeholder: integrate with Whisper or local STT
    // For now, simulate or delegate to external service
    if (this.config.sttProvider === 'whisper-local') {
      // TODO: spawn whisper.cpp or faster-whisper locally
      throw new Error('Local Whisper STT requires whisper.cpp or faster-whisper setup. Install and configure KIVO_WHISPER_PATH.');
    }
    // Fallback: simulate for testing
    return { text: '', confidence: 0 };
  }

  // ── TTS (Text-to-Speech) ─────────────────────────────────
  async speak(text, options = {}) {
    const utterance = {
      text,
      language: options.language || this.config.language,
      voice: options.voice || 'default',
      speed: options.speed || 1.0,
      timestamp: new Date().toISOString(),
    };

    if (this.config.ttsProvider === 'piper') {
      // TODO: spawn piper process for local TTS
      // piper --model de_DE-thorsten_medium.onnx --output_file /tmp/kivo_out.wav
      console.log(`[KIVO TTS] ${text}`);
      this.emit('tts', utterance);
      return utterance;
    }

    // Fallback: log only (for headless / debug mode)
    console.log(`[KIVO TTS] ${text}`);
    this.emit('tts', utterance);
    return utterance;
  }

  // ── Intent Routing ─────────────────────────────────────────
  async processUtterance(text, options = {}) {
    if (!this.session) this.startSession();

    const utterance = {
      text,
      timestamp: Date.now(),
      intent: null,
      entities: {},
    };

    // Simple intent classification
    const intent = this.classifyIntent(text);
    utterance.intent = intent;
    this.session.utterances.push(utterance);

    if (options.emit !== false) {
      this.emit('utterance', utterance);
    }
    return utterance;
  }

  classifyIntent(text) {
    const lower = text.toLowerCase();
    // Fast path — home control
    if (/licht|lampe|light|steckdose|schalter/i.test(lower)) return { type: 'home', action: 'control', confidence: 0.9 };
    if (/temperatur|heizung|thermostat/i.test(lower)) return { type: 'home', action: 'climate', confidence: 0.9 };
    if (/timer|wecker|alarm|countdown/i.test(lower)) return { type: 'home', action: 'timer', confidence: 0.95 };
    if (/tor|garage|tür|schloss/i.test(lower)) return { type: 'home', action: 'access', confidence: 0.9 };

    // Agent path — complex tasks
    if (/abo|vertrag|kündig|subscription|cancel/i.test(lower)) return { type: 'agent', action: 'subscription', confidence: 0.85 };
    if (/steuer|tax|elster|finanz/i.test(lower)) return { type: 'agent', action: 'finance', confidence: 0.85 };
    if (/scan|audit|security|sicherheit/i.test(lower)) return { type: 'agent', action: 'security', confidence: 0.85 };
    if (/report|status|übersicht|tagesbericht/i.test(lower)) return { type: 'agent', action: 'report', confidence: 0.8 };
    if (/deepscan|deep scan|härten|hardening/i.test(lower)) return { type: 'agent', action: 'deepscan', confidence: 0.9 };

    // Rudibot bridge
    if (/rudibot|bot|telegram|befehl/i.test(lower)) return { type: 'rudibot', action: 'command', confidence: 0.8 };

    // Memory / context
    if (/projekt|project|merk|erinner|notiz/i.test(lower)) return { type: 'memory', action: 'store', confidence: 0.75 };

    return { type: 'unknown', action: 'fallback', confidence: 0.5 };
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      listening: this.isListening,
      sessionActive: !!this.session,
      sessionId: this.session?.id || null,
      config: this.config,
    };
  }
}

module.exports = { KivoVoiceCore };
