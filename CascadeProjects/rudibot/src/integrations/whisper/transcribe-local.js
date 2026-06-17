/**
 * Transcribe Local — Local Whisper/faster-whisper server
 * Connects to locally hosted HTTP service for privacy
 */

const fs = require('fs');
const FormData = require('form-data');

class LocalTranscriber {
  constructor(options = {}) {
    this.config = {
      serverUrl: options.serverUrl || process.env.WHISPER_SERVER_URL || 'http://localhost:8080',
      model: options.model || 'base',
      language: options.language || 'de',
      timeout: options.timeout || 60000,
      ...options
    };
  }

  async transcribe(audioPath, options = {}) {
    const {
      language = this.config.language,
      model = this.config.model,
      task = 'transcribe',
      outputFormat = 'json'
    } = options;

    try {
      const formData = new FormData();
      formData.append('audio', fs.createReadStream(audioPath));
      formData.append('language', language);
      formData.append('model', model);
      formData.append('task', task);

      const response = await fetch(`${this.config.serverUrl}/transcribe`, {
        method: 'POST',
        headers: formData.getHeaders(),
        body: formData,
        signal: AbortSignal.timeout(this.config.timeout)
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Local Whisper server error: ${response.status} ${error}`);
      }

      const result = await response.json();

      return {
        success: true,
        text: result.text,
        language: result.language || language,
        model: result.model || model,
        duration: result.duration || null,
        segments: result.segments || [],
        confidence: this.estimateConfidence(result),
        source: 'local-whisper',
        timestamp: new Date().toISOString()
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        text: null,
        source: 'local-whisper'
      };
    }
  }

  // ── Health Check ────────────────────────────────────────────
  async healthCheck() {
    try {
      const response = await fetch(`${this.config.serverUrl}/health`, {
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        return {
          healthy: false,
          error: `HTTP ${response.status}`
        };
      }

      const data = await response.json();
      return {
        healthy: true,
        ...data
      };
    } catch (e) {
      return {
        healthy: false,
        error: e.message
      };
    }
  }

  // ── Server Management ─────────────────────────────────────
  async getModels() {
    try {
      const response = await fetch(`${this.config.serverUrl}/models`, {
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        return { success: false, error: `HTTP ${response.status}` };
      }

      const data = await response.json();
      return {
        success: true,
        models: data.models || []
      };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async getLanguages() {
    try {
      const response = await fetch(`${this.config.serverUrl}/languages`, {
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        return { success: false, error: `HTTP ${response.status}` };
      }

      const data = await response.json();
      return {
        success: true,
        languages: data.languages || []
      };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  // ── Batch Processing ────────────────────────────────────────
  async transcribeBatch(audioPaths, options = {}) {
    const results = [];
    for (const path of audioPaths) {
      const result = await this.transcribe(path, options);
      results.push({ path, ...result });
    }
    return results;
  }

  // ── Confidence Estimation ───────────────────────────────────
  estimateConfidence(result) {
    const text = result.text || '';
    if (text.length < 3) return 0.5;

    // If segments with avg_logprob are available, use them
    if (result.segments && result.segments.length > 0) {
      const avgLogprob = result.segments.reduce((sum, s) => sum + (s.avg_logprob || -1), 0) / result.segments.length;
      if (avgLogprob > -0.3) return 0.95;
      if (avgLogprob > -0.5) return 0.85;
      if (avgLogprob > -0.7) return 0.75;
      return 0.65;
    }

    // Fallback: heuristic based on text patterns
    if (text.includes('...') || text.includes('[unintelligible]')) return 0.6;
    if (/[^\w\s\u00C0-\u024F.,!?;:'"-]/.test(text)) return 0.7;
    return 0.9;
  }

  // ── Status ──────────────────────────────────────────────────
  getStatus() {
    return {
      configured: true,
      serverUrl: this.config.serverUrl,
      model: this.config.model,
      language: this.config.language,
      timeout: this.config.timeout
    };
  }
}

module.exports = { LocalTranscriber };
