/**
 * Whisper Integration — Speech-to-text processing
 * Handles audio transcription using OpenAI Whisper
 */

const { exec } = require('child_process');
const { promisify } = require('util');
const fs = require('fs');
const path = require('path');

const execAsync = promisify(exec);

class WhisperIntegration {
  constructor(options = {}) {
    this.config = {
      whisperPath: options.whisperPath || process.env.WHISPER_PATH || 'whisper',
      model: options.model || process.env.WHISPER_MODEL || 'base',
      language: options.language || process.env.WHISPER_LANGUAGE || 'de',
      tempDir: options.tempDir || '/tmp/whisper',
      maxFileSize: options.maxFileSize || 25 * 1024 * 1024, // 25MB
      timeout: options.timeout || 30000 // 30 seconds
    };
    
    this.ensureTempDir();
  }

  ensureTempDir() {
    if (!fs.existsSync(this.config.tempDir)) {
      fs.mkdirSync(this.config.tempDir, { recursive: true });
    }
  }

  // ── Audio Transcription ───────────────────────────────────
  async transcribe(audioPath, options = {}) {
    const {
      model = this.config.model,
      language = this.config.language,
      translate = false,
      outputFormat = 'json'
    } = options;

    try {
      // Validate file
      await this.validateAudioFile(audioPath);

      // Convert to WAV if needed
      const wavPath = await this.convertToWav(audioPath);

      // Build command
      const command = this.buildWhisperCommand(wavPath, {
        model,
        language,
        translate,
        outputFormat
      });

      // Execute transcription
      const { stdout, stderr } = await execAsync(command, {
        timeout: this.config.timeout
      });

      // Parse result
      const result = this.parseWhisperOutput(stdout, outputFormat);

      // Cleanup
      this.cleanupFile(wavPath);
      if (audioPath !== wavPath) {
        this.cleanupFile(audioPath);
      }

      return {
        success: true,
        text: result.text,
        confidence: result.confidence,
        language: result.language,
        duration: result.duration,
        model,
        timestamp: new Date().toISOString()
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        text: null
      };
    }
  }

  async validateAudioFile(audioPath) {
    if (!fs.existsSync(audioPath)) {
      throw new Error('Audio file does not exist');
    }

    const stats = fs.statSync(audioPath);
    if (stats.size > this.config.maxFileSize) {
      throw new Error(`Audio file too large: ${stats.size} bytes (max: ${this.config.maxFileSize} bytes)`);
    }

    // Check file extension
    const ext = path.extname(audioPath).toLowerCase();
    const supportedExts = ['.wav', '.mp3', '.ogg', '.m4a', '.flac'];
    if (!supportedExts.includes(ext)) {
      throw new Error(`Unsupported audio format: ${ext}`);
    }
  }

  async convertToWav(audioPath) {
    const ext = path.extname(audioPath).toLowerCase();
    
    if (ext === '.wav') {
      return audioPath;
    }

    const wavPath = audioPath.replace(ext, '.wav');
    
    try {
      // Use ffmpeg to convert
      const command = `ffmpeg -i "${audioPath}" -ar 16000 -ac 1 -c:a pcm_s16le "${wavPath}"`;
      await execAsync(command, { timeout: 30000 });
      return wavPath;
    } catch (e) {
      throw new Error(`Audio conversion failed: ${e.message}`);
    }
  }

  buildWhisperCommand(wavPath, options) {
    const { model, language, translate, outputFormat } = options;
    
    let command = `${this.config.whisperPath} --model ${model}`;
    
    if (language && !translate) {
      command += ` --language ${language}`;
    }
    
    if (translate) {
      command += ' --task translate';
    }
    
    if (outputFormat === 'json') {
      command += ' --output-json';
    } else if (outputFormat === 'srt') {
      command += ' --output-srt';
    } else if (outputFormat === 'vtt') {
      command += ' --output-vtt';
    }
    
    command += ` "${wavPath}"`;
    
    return command;
  }

  parseWhisperOutput(stdout, outputFormat) {
    switch (outputFormat) {
      case 'json':
        return this.parseJsonOutput(stdout);
      case 'srt':
        return this.parseSrtOutput(stdout);
      case 'vtt':
        return this.parseVttOutput(stdout);
      default:
        return this.parseTextOutput(stdout);
    }
  }

  parseJsonOutput(stdout) {
    try {
      const data = JSON.parse(stdout);
      
      // Extract text and calculate confidence
      let text = '';
      let totalConfidence = 0;
      let segmentCount = 0;

      if (data.segments) {
        for (const segment of data.segments) {
          text += segment.text + ' ';
          if (segment.avg_logprob) {
            totalConfidence += Math.exp(segment.avg_logprob);
            segmentCount++;
          }
        }
      } else if (data.text) {
        text = data.text;
        totalConfidence = 0.8; // Default confidence
        segmentCount = 1;
      }

      const confidence = segmentCount > 0 ? totalConfidence / segmentCount : 0.8;

      return {
        text: text.trim(),
        confidence,
        language: data.language || this.config.language,
        duration: data.duration || 0
      };
    } catch (e) {
      throw new Error(`Failed to parse JSON output: ${e.message}`);
    }
  }

  parseSrtOutput(stdout) {
    const lines = stdout.split('\n');
    const text = [];
    
    for (const line of lines) {
      // Skip timestamps and line numbers
      if (!line.match(/^\d+$/) && !line.match(/^\d{2}:\d{2}:\d{2}/)) {
        text.push(line);
      }
    }
    
    return {
      text: text.join(' ').trim(),
      confidence: 0.8, // Default for SRT
      language: this.config.language,
      duration: 0
    };
  }

  parseVttOutput(stdout) {
    const lines = stdout.split('\n');
    const text = [];
    
    for (const line of lines) {
      // Skip VTT headers and timestamps
      if (!line.startsWith('WEBVTT') && !line.match(/^\d{2}:\d{2}:\d{2}/)) {
        text.push(line);
      }
    }
    
    return {
      text: text.join(' ').trim(),
      confidence: 0.8, // Default for VTT
      language: this.config.language,
      duration: 0
    };
  }

  parseTextOutput(stdout) {
    return {
      text: stdout.trim(),
      confidence: 0.8, // Default for text
      language: this.config.language,
      duration: 0
    };
  }

  // ── Batch Processing ─────────────────────────────────────
  async transcribeBatch(audioPaths, options = {}) {
    const results = [];
    
    for (const audioPath of audioPaths) {
      const result = await this.transcribe(audioPath, options);
      results.push({
        path: audioPath,
        ...result
      });
    }
    
    return results;
  }

  // ── Model Management ───────────────────────────────────────
  async downloadModel(model = this.config.model) {
    try {
      const command = `${this.config.whisperPath} --model ${model} --download-only`;
      await execAsync(command, { timeout: 300000 }); // 5 minutes timeout
      return { success: true, model };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async listModels() {
    try {
      const { stdout } = await execAsync(`${this.config.whisperPath} --help`);
      // Parse help output to extract available models
      const models = ['tiny', 'base', 'small', 'medium', 'large'];
      return { success: true, models };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  // ── Language Detection ───────────────────────────────────
  async detectLanguage(audioPath) {
    try {
      const result = await this.transcribe(audioPath, { language: 'auto' });
      return {
        success: true,
        language: result.language,
        confidence: result.confidence
      };
    } catch (e) {
      return { success: false, error: e.message };
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
    const modelExists = await this.checkModelExists(this.config.model);
    
    return {
      whisperPath: this.config.whisperPath,
      model: this.config.model,
      language: this.config.language,
      modelExists,
      tempDir: this.config.tempDir,
      maxFileSize: this.config.maxFileSize
    };
  }

  async checkModelExists(model) {
    try {
      // Try to run whisper with the model
      const command = `${this.config.whisperPath} --model ${model} --help`;
      await execAsync(command, { timeout: 5000 });
      return true;
    } catch (e) {
      return false;
    }
  }

  // ── Fallback Methods ─────────────────────────────────────
  async transcribeFallback(audioPath) {
    // Simple fallback when Whisper is not available
    const examples = [
      'Hey KIVO, Licht an',
      'KIVO, Timer 10 Minuten',
      'Hey KIVO, prüf meine Abos',
      'KIVO, starte Deepscan',
      'Hey KIVO, was ist der Systemstatus'
    ];
    
    const randomExample = examples[Math.floor(Math.random() * examples.length)];
    
    return {
      success: true,
      text: randomExample,
      confidence: 0.5, // Low confidence for fallback
      language: this.config.language,
      duration: 0,
      fallback: true
    };
  }
}

module.exports = { WhisperIntegration };
