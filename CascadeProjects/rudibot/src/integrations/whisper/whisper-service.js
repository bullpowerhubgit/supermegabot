/**
 * Whisper Service — Central voice processing orchestrator
 * Coordinates download → convert → transcribe → cleanup
 */

const { TelegramVoiceDownloader } = require('./download-telegram-voice');
const { AudioConverter } = require('./convert-audio');
const { OpenAITranscriber } = require('./transcribe-openai');
const { LocalTranscriber } = require('./transcribe-local');
const fs = require('fs');

const TEMP_DIR = process.env.TEMP_DIR || '/tmp/kivo-voice';

class WhisperService {
  constructor(options = {}) {
    this.config = {
      provider: options.provider || process.env.WHISPER_PROVIDER || 'auto', // auto, openai, local
      language: options.language || 'de',
      autoCleanup: options.autoCleanup !== false,
      ...options
    };

    this.downloader = null;
    this.converter = new AudioConverter(options.converter);
    this.openai = new OpenAITranscriber(options.openai);
    this.local = new LocalTranscriber(options.local);
  }

  setBot(bot) {
    this.downloader = new TelegramVoiceDownloader(bot);
  }

  // ── Main Entry: Telegram Voice → Text ────────────────────
  async processVoiceMessage(voiceMessage, options = {}) {
    let localPath = null;
    let wavPath = null;

    try {
      // Step 1: Download from Telegram
      if (!this.downloader) {
        throw new Error('Telegram bot not configured. Call setBot() first.');
      }

      const download = await this.downloader.download(voiceMessage);
      if (!download.success) {
        throw new Error(`Download failed: ${download.error}`);
      }

      localPath = download.path;

      // Step 2: Convert to WAV
      const conversion = await this.converter.oggToWav(localPath);
      if (!conversion.success) {
        throw new Error(`Conversion failed: ${conversion.error}`);
      }

      wavPath = conversion.outputPath;

      // Step 3: Transcribe
      const transcription = await this.transcribe(wavPath, options);
      if (!transcription.success) {
        throw new Error(`Transcription failed: ${transcription.error}`);
      }

      return {
        success: true,
        text: transcription.text,
        confidence: transcription.confidence,
        source: transcription.source,
        duration: download.duration,
        language: transcription.language,
        originalSize: download.size,
        processingTime: Date.now() - download.timestamp || Date.now()
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        text: null,
        fallback: true
      };
    } finally {
      // Step 4: Cleanup
      if (this.config.autoCleanup) {
        this.cleanup(localPath, wavPath);
      }
    }
  }

  // ── Transcribe (Auto-Select Provider) ────────────────────
  async transcribe(audioPath, options = {}) {
    const provider = options.provider || this.config.provider;

    switch (provider) {
      case 'openai':
        return await this.openai.transcribe(audioPath, options);
      case 'local':
        return await this.local.transcribe(audioPath, options);
      case 'auto':
      default:
        return await this.autoTranscribe(audioPath, options);
    }
  }

  async autoTranscribe(audioPath, options = {}) {
    // Try local first (privacy, no API costs)
    if (this.local) {
      const health = await this.local.healthCheck();
      if (health.healthy) {
        const result = await this.local.transcribe(audioPath, options);
        if (result.success) {
          return { ...result, source: 'local-whisper' };
        }
      }
    }

    // Fallback to OpenAI
    if (this.openai && this.openai.getStatus().configured) {
      const result = await this.openai.transcribe(audioPath, options);
      if (result.success) {
        return { ...result, source: 'openai' };
      }
    }

    return {
      success: false,
      error: 'No transcription provider available',
      text: null
    };
  }

  // ── Process Local Audio File ─────────────────────────────
  async processLocalFile(audioPath, options = {}) {
    let wavPath = null;

    try {
      // Convert if needed
      const ext = audioPath.split('.').pop().toLowerCase();
      if (ext !== 'wav') {
        const conversion = await this.converter.oggToWav(audioPath);
        wavPath = conversion.outputPath;
      } else {
        wavPath = audioPath;
      }

      // Transcribe
      const result = await this.transcribe(wavPath, options);
      return result;

    } catch (e) {
      return {
        success: false,
        error: e.message,
        text: null
      };
    } finally {
      if (this.config.autoCleanup && wavPath && wavPath !== audioPath) {
        this.cleanup(null, wavPath);
      }
    }
  }

  // ── Batch Processing ───────────────────────────────────────
  async processBatch(voiceMessages, options = {}) {
    const results = [];
    for (const msg of voiceMessages) {
      const result = await this.processVoiceMessage(msg, options);
      results.push(result);
    }
    return results;
  }

  // ── Cleanup ────────────────────────────────────────────────
  cleanup(oggPath, wavPath) {
    if (oggPath && oggPath !== wavPath) {
      try {
        if (fs.existsSync(oggPath)) fs.unlinkSync(oggPath);
      } catch (e) {
        console.warn(`[WhisperService] Failed to cleanup OGG: ${oggPath}`);
      }
    }

    if (wavPath) {
      try {
        if (fs.existsSync(wavPath)) fs.unlinkSync(wavPath);
      } catch (e) {
        console.warn(`[WhisperService] Failed to cleanup WAV: ${wavPath}`);
      }
    }
  }

  cleanupAll() {
    try {
      if (fs.existsSync(TEMP_DIR)) {
        const files = fs.readdirSync(TEMP_DIR);
        for (const file of files) {
          const filePath = `${TEMP_DIR}/${file}`;
          try {
            fs.unlinkSync(filePath);
          } catch (e) {
            // Ignore
          }
        }
      }
    } catch (e) {
      console.warn('[WhisperService] Cleanup error:', e.message);
    }
  }

  // ── Status ───────────────────────────────────────────────────
  async getStatus() {
    const localHealth = this.local ? await this.local.healthCheck() : { healthy: false };

    return {
      provider: this.config.provider,
      language: this.config.language,
      autoCleanup: this.config.autoCleanup,
      downloader: this.downloader ? this.downloader.getStatus() : null,
      converter: this.converter.getStatus(),
      openai: this.openai.getStatus(),
      local: {
        ...this.local.getStatus(),
        healthy: localHealth.healthy
      }
    };
  }

  // ── Configuration ────────────────────────────────────────────
  setProvider(provider) {
    this.config.provider = provider;
  }

  setLanguage(language) {
    this.config.language = language;
  }
}

module.exports = { WhisperService };
