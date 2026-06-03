/**
 * TTS Integration — Text-to-speech processing
 * Handles speech synthesis using Piper or other TTS engines
 */

const { exec } = require('child_process');
const { promisify } = require('util');
const fs = require('fs');
const path = require('path');

const execAsync = promisify(exec);

class TTSIntegration {
  constructor(options = {}) {
    this.config = {
      piperPath: options.piperPath || process.env.PIPER_PATH || 'piper',
      voice: options.voice || process.env.TTS_VOICE || 'de_DE-thorsten_medium',
      tempDir: options.tempDir || '/tmp/tts',
      sampleRate: options.sampleRate || 22050,
      maxTextLength: options.maxTextLength || 500,
      timeout: options.timeout || 10000
    };
    
    this.ensureTempDir();
  }

  ensureTempDir() {
    if (!fs.existsSync(this.config.tempDir)) {
      fs.mkdirSync(this.config.tempDir, { recursive: true });
    }
  }

  // ── Speech Synthesis ───────────────────────────────────────
  async synthesize(text, options = {}) {
    const {
      voice = this.config.voice,
      speed = 1.0,
      pitch = 1.0,
      volume = 1.0,
      outputFormat = 'wav'
    } = options;

    try {
      // Validate input
      this.validateText(text);

      // Generate audio
      const audioPath = await this.generateAudio(text, {
        voice,
        speed,
        pitch,
        volume,
        outputFormat
      });

      return {
        success: true,
        audioPath,
        text,
        voice,
        duration: await this.getAudioDuration(audioPath),
        timestamp: new Date().toISOString()
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        audioPath: null
      };
    }
  }

  validateText(text) {
    if (!text || typeof text !== 'string') {
      throw new Error('Text must be a non-empty string');
    }

    if (text.length > this.config.maxTextLength) {
      throw new Error(`Text too long: ${text.length} characters (max: ${this.config.maxTextLength})`);
    }

    // Remove or replace problematic characters
    const cleaned = text
      .replace(/[^\w\s\u00C0-\u024F\u0400-\u04FF.,!?;:()'"-]/g, '') // Keep letters, numbers, spaces, punctuation
      .replace(/\s+/g, ' ') // Normalize spaces
      .trim();

    if (cleaned.length === 0) {
      throw new Error('Text contains no speakable characters');
    }

    return cleaned;
  }

  async generateAudio(text, options) {
    const { voice, speed, pitch, volume, outputFormat } = options;
    
    const outputPath = path.join(this.config.tempDir, `tts_${Date.now()}.${outputFormat}`);
    
    try {
      // Build Piper command
      const command = this.buildPiperCommand(text, outputPath, {
        voice,
        speed,
        pitch,
        volume
      });

      // Execute synthesis
      await execAsync(command, {
        timeout: this.config.timeout
      });

      return outputPath;

    } catch (e) {
      // Cleanup on error
      this.cleanupFile(outputPath);
      throw new Error(`TTS synthesis failed: ${e.message}`);
    }
  }

  buildPiperCommand(text, outputPath, options) {
    const { voice, speed, pitch, volume } = options;
    
    let command = `${this.config.piperPath}`;
    
    if (voice) {
      command += ` --model ${voice}`;
    }
    
    if (speed !== 1.0) {
      command += ` --length_scale ${1.0 / speed}`;
    }
    
    if (pitch !== 1.0) {
      command += ` --pitch_scale ${pitch}`;
    }
    
    if (volume !== 1.0) {
      command += ` --noise_scale ${volume}`;
    }
    
    command += ` --output_file "${outputPath}"`;
    command += ` "${text}"`;
    
    return command;
  }

  async getAudioDuration(audioPath) {
    try {
      // Use ffprobe to get duration
      const command = `ffprobe -v quiet -show_entries format=duration -of csv=p=0 "${audioPath}"`;
      const { stdout } = await execAsync(command, { timeout: 5000 });
      return parseFloat(stdout.trim()) || 0;
    } catch (e) {
      // Fallback: estimate based on text length
      return 0;
    }
  }

  // ── Batch Synthesis ───────────────────────────────────────
  async synthesizeBatch(texts, options = {}) {
    const results = [];
    
    for (const text of texts) {
      const result = await this.synthesize(text, options);
      results.push({
        text,
        ...result
      });
    }
    
    return results;
  }

  // ── Voice Management ───────────────────────────────────────
  async listVoices() {
    const availableVoices = [
      'de_DE-thorsten_medium',
      'de_DE-thorsten_low',
      'de_DE-karlsson_low',
      'de_DE-eva_kob_medium',
      'en_US-lessac_medium',
      'en_US-lessac_low',
      'en_US-lessac_high',
      'en_GB-cori-medium',
      'fr_FR-siwis_medium',
      'fr_FR-gilles_low',
      'es_ES-dave_low',
      'es_ES-silvia_low',
      'it_IT-riccardo_low'
    ];

    return {
      success: true,
      voices: availableVoices.map(voice => ({
        id: voice,
        language: voice.split('_')[0],
        name: voice.split('-')[1]?.split('_')[0] || voice
      }))
    };
  }

  async downloadVoice(voice) {
    try {
      // Piper downloads voices automatically on first use
      // We can trigger a synthesis to ensure download
      await this.synthesize('test', { voice });
      return { success: true, voice };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  // ── Audio Processing ───────────────────────────────────────
  async convertFormat(inputPath, outputFormat) {
    const outputPath = inputPath.replace(/\.[^.]+$/, `.${outputFormat}`);
    
    try {
      const command = `ffmpeg -i "${inputPath}" "${outputPath}"`;
      await execAsync(command, { timeout: 30000 });
      return outputPath;
    } catch (e) {
      throw new Error(`Format conversion failed: ${e.message}`);
    }
  }

  async adjustVolume(audioPath, volumeMultiplier) {
    const outputPath = audioPath.replace(/(\.[^.]+)$/, '_adjusted$1');
    
    try {
      const command = `ffmpeg -i "${audioPath}" -filter:a "volume=${volumeMultiplier}" "${outputPath}"`;
      await execAsync(command, { timeout: 30000 });
      return outputPath;
    } catch (e) {
      throw new Error(`Volume adjustment failed: ${e.message}`);
    }
  }

  async concatAudio(audioPaths) {
    if (audioPaths.length === 0) {
      throw new Error('No audio files to concatenate');
    }

    const outputPath = path.join(this.config.tempDir, `tts_concat_${Date.now()}.wav`);
    
    try {
      // Create file list for ffmpeg
      const fileListPath = path.join(this.config.tempDir, 'filelist.txt');
      const fileList = audioPaths.map(path => `file '${path}'`).join('\n');
      fs.writeFileSync(fileListPath, fileList);

      // Concatenate
      const command = `ffmpeg -f concat -safe 0 -i "${fileListPath}" "${outputPath}"`;
      await execAsync(command, { timeout: 60000 });

      // Cleanup
      this.cleanupFile(fileListPath);

      return outputPath;
    } catch (e) {
      this.cleanupFile(outputPath);
      throw new Error(`Audio concatenation failed: ${e.message}`);
    }
  }

  // ── Utility Methods ───────────────────────────────────────
  cleanupFile(filePath) {
    try {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    } catch (e) {
      console.warn(`Failed to cleanup file: ${filePath}`, e.message);
    }
  }

  cleanupOldFiles(maxAge = 3600000) { // 1 hour
    try {
      const files = fs.readdirSync(this.config.tempDir);
      const now = Date.now();
      
      for (const file of files) {
        const filePath = path.join(this.config.tempDir, file);
        const stats = fs.statSync(filePath);
        
        if (now - stats.mtime.getTime() > maxAge) {
          this.cleanupFile(filePath);
        }
      }
    } catch (e) {
      console.warn('Failed to cleanup old files', e.message);
    }
  }

  // ── Status ─────────────────────────────────────────────────
  async getStatus() {
    const voiceAvailable = await this.checkVoiceAvailability(this.config.voice);
    
    return {
      piperPath: this.config.piperPath,
      voice: this.config.voice,
      voiceAvailable,
      tempDir: this.config.tempDir,
      sampleRate: this.config.sampleRate,
      maxTextLength: this.config.maxTextLength
    };
  }

  async checkVoiceAvailability(voice) {
    try {
      // Try to synthesize a short test
      await this.synthesize('test', { voice });
      return true;
    } catch (e) {
      return false;
    }
  }

  // ── Fallback Methods ─────────────────────────────────────
  async synthesizeFallback(text) {
    // Simple fallback when TTS is not available
    console.log(`[TTS FALLBACK] ${text}`);
    
    return {
      success: true,
      audioPath: null,
      text,
      voice: 'fallback',
      duration: this.estimateDuration(text),
      fallback: true
    };
  }

  estimateDuration(text) {
    // Rough estimate: 150 words per minute
    const words = text.split(/\s+/).length;
    return (words / 150) * 60; // seconds
  }

  // ── Streaming Support ─────────────────────────────────────
  async synthesizeStream(text, options = {}) {
    // For future implementation of streaming TTS
    const result = await this.synthesize(text, options);
    
    if (result.success && result.audioPath) {
      const audioBuffer = fs.readFileSync(result.audioPath);
      return {
        ...result,
        audioBuffer,
        stream: true
      };
    }
    
    return result;
  }
}

module.exports = { TTSIntegration };
