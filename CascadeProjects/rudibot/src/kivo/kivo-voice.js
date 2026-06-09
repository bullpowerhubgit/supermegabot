/**
 * KIVO Voice — Voice message handling, transcription, TTS
 * Delegates to WhisperService for actual processing
 */

const { WhisperService } = require('../integrations/whisper/whisper-service');
const fs = require('fs');
const path = require('path');

class KivoVoice {
  constructor(options = {}) {
    this.whisper = new WhisperService({
      provider: options.provider || 'auto',
      language: options.language || 'de',
      ...options
    });
    
    this.config = {
      piperPath: options.piperPath || process.env.PIPER_PATH,
      tempDir: options.tempDir || '/tmp/kivo-voice',
      language: options.language || 'de'
    };
  }

  setBot(bot) {
    this.whisper.setBot(bot);
  }

  // ── Voice Message Processing ───────────────────────────────
  async processVoiceMessage(voiceMessage, bot) {
    if (bot) this.setBot(bot);
    
    // Delegate to WhisperService:
    // Telegram Voice → Download → FFmpeg → Whisper → Text
    return await this.whisper.processVoiceMessage(voiceMessage);
  }

  // ── Direct Audio Processing ────────────────────────────────
  async processLocalFile(audioPath, options = {}) {
    return await this.whisper.processLocalFile(audioPath, options);
  }

  // ── Batch Processing ───────────────────────────────────────
  async processBatch(voiceMessages) {
    return await this.whisper.processBatch(voiceMessages);
  }

  // ── Text-to-Speech ───────────────────────────────────────
  async speak(text, options = {}) {
    if (!this.config.piperPath) {
      // Fallback: just log
      console.log(`[KIVO TTS] ${text}`);
      return { success: true, audioPath: null, text };
    }

    try {
      const audioPath = await this.generateTTS(text, options);
      return { success: true, audioPath, text };
    } catch (e) {
      console.log(`[KIVO TTS] ${text}`);
      return { success: true, audioPath: null, text };
    }
  }

  async generateTTS(text, options = {}) {
    const voice = options.voice || 'de_DE-thorsten_medium';
    const outputPath = path.join(this.config.tempDir, `tts_${Date.now()}.wav`);
    
    const command = `${this.config.piperPath} --model ${voice} --output_file ${outputPath} "${text}"`;
    const { exec } = require('child_process');
    const { promisify } = require('util');
    const execAsync = promisify(exec);
    
    await execAsync(command);
    return outputPath;
  }

  // ── Cleanup ─────────────────────────────────────────────
  cleanup() {
    this.whisper.cleanupAll();
  }

  cleanupOldFiles(maxAge = 3600000) { // 1 hour
    this.whisper.cleanup(); // delegated to WhisperService
  }

  // ── Status ───────────────────────────────────────────────
  async getStatus() {
    const whisperStatus = await this.whisper.getStatus();
    
    return {
      whisperService: whisperStatus,
      piperAvailable: !!this.config.piperPath,
      tempDir: this.config.tempDir,
      language: this.config.language
    };
  }
}

module.exports = { KivoVoice };
