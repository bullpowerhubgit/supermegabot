/**
 * Transcribe OpenAI — API-based speech-to-text
 * Uses OpenAI Whisper API for high-quality transcription
 */

const fs = require('fs');
const FormData = require('form-data');

class OpenAITranscriber {
  constructor(options = {}) {
    this.config = {
      apiKey: options.apiKey || process.env.OPENAI_API_KEY,
      baseUrl: options.baseUrl || 'https://api.openai.com/v1',
      model: options.model || 'whisper-1',
      language: options.language || 'de',
      ...options
    };
  }

  async transcribe(audioPath, options = {}) {
    if (!this.config.apiKey) {
      throw new Error('OPENAI_API_KEY not configured');
    }

    const {
      model = this.config.model,
      language = this.config.language,
      prompt = '',
      responseFormat = 'json',
      temperature = 0
    } = options;

    try {
      const formData = new FormData();
      formData.append('file', fs.createReadStream(audioPath));
      formData.append('model', model);
      formData.append('language', language);
      formData.append('response_format', responseFormat);
      formData.append('temperature', String(temperature));

      if (prompt) {
        formData.append('prompt', prompt);
      }

      const response = await fetch(`${this.config.baseUrl}/audio/transcriptions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.config.apiKey}`,
          ...formData.getHeaders()
        },
        body: formData,
        signal: AbortSignal.timeout(60000) // 60s timeout
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`OpenAI API error: ${response.status} ${error}`);
      }

      const result = await response.json();

      return {
        success: true,
        text: result.text,
        model,
        language,
        duration: result.duration || null,
        confidence: this.estimateConfidence(result),
        source: 'openai',
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

  // ── Translation ─────────────────────────────────────────────
  async translate(audioPath, options = {}) {
    if (!this.config.apiKey) {
      throw new Error('OPENAI_API_KEY not configured');
    }

    try {
      const formData = new FormData();
      formData.append('file', fs.createReadStream(audioPath));
      formData.append('model', options.model || this.config.model);

      const response = await fetch(`${this.config.baseUrl}/audio/translations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.config.apiKey}`,
          ...formData.getHeaders()
        },
        body: formData,
        signal: AbortSignal.timeout(60000)
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`OpenAI API error: ${response.status} ${error}`);
      }

      const result = await response.json();

      return {
        success: true,
        text: result.text,
        source: 'openai-translation',
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

  // ── Batch Processing ────────────────────────────────────────
  async transcribeBatch(audioPaths, options = {}) {
    const results = [];
    for (const path of audioPaths) {
      const result = await this.transcribe(path, options);
      results.push({
        path,
        ...result
      });
    }
    return results;
  }

  // ── Confidence Estimation ───────────────────────────────────
  estimateConfidence(result) {
    // OpenAI doesn't provide confidence scores directly
    // We estimate based on text length and absence of error patterns
    const text = result.text || '';
    if (text.length < 3) return 0.5;
    if (text.includes('...') || text.includes('[unintelligible]')) return 0.7;
    return 0.9;
  }

  // ── Status ────────────────────────────────────────────────────
  getStatus() {
    return {
      configured: !!this.config.apiKey,
      model: this.config.model,
      language: this.config.language,
      baseUrl: this.config.baseUrl
    };
  }
}

module.exports = { OpenAITranscriber };
