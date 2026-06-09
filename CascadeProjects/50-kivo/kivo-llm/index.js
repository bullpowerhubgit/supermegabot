/**
 * KIVO LLM — OpenAI-Compatible Provider Client
 * Supports custom baseURL, apiKey, and model selection
 */

class KivoLLM {
  constructor(options = {}) {
    this.provider = options.provider || process.env.KIVO_LLM_PROVIDER || 'openai';
    this.apiKey = options.apiKey || process.env.KIVO_LLM_API_KEY || '';
    this.baseURL = options.baseURL || process.env.KIVO_LLM_BASE_URL || 'https://api.openai.com/v1';
    this.model = options.model || process.env.KIVO_LLM_MODEL || 'gpt-4o-mini';
    this.timeout = options.timeout || 30000;
  }

  get headers() {
    const h = { 'Content-Type': 'application/json' };
    if (this.apiKey && this.apiKey.length > 10) {
      h['Authorization'] = `Bearer ${this.apiKey}`;
    }
    return h;
  }

  async chat(messages, options = {}) {
    const url = `${this.baseURL}/chat/completions`;
    const body = {
      model: this.model,
      messages,
      temperature: options.temperature ?? 0.7,
      max_tokens: options.max_tokens ?? 512,
      ...(options.tools ? { tools: options.tools, tool_choice: options.tool_choice || 'auto' } : {}),
    };

    const res = await fetch(url, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout),
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`LLM request failed (${res.status}): ${err}`);
    }

    const data = await res.json();
    return {
      content: data.choices?.[0]?.message?.content || '',
      toolCalls: data.choices?.[0]?.message?.tool_calls || null,
      usage: data.usage || null,
      model: data.model || this.model,
    };
  }

  sanitizeInput(text) {
    // Basic sanitization to prevent prompt injection
    return String(text).replace(/["\\]/g, '').slice(0, 500);
  }

  async classifyIntent(text, categories = []) {
    const defaultCategories = [
      { type: 'home', actions: ['control', 'climate', 'timer', 'access'] },
      { type: 'agent', actions: ['subscription', 'finance', 'security', 'report', 'deepscan'] },
      { type: 'rudibot', actions: ['command'] },
      { type: 'memory', actions: ['store'] },
    ];
    const cats = categories.length ? categories : defaultCategories;

    const safeText = this.sanitizeInput(text);

    const prompt = `Classify the user utterance into one intent type and action.
Available categories: ${JSON.stringify(cats)}
Respond ONLY with valid JSON: {"type": "...", "action": "...", "confidence": 0.0-1.0}
Utterance: "${safeText}"`;

    const result = await this.chat(
      [{ role: 'user', content: prompt }],
      { temperature: 0.2, max_tokens: 128 }
    );

    try {
      const parsed = JSON.parse(result.content);
      // Validate response structure
      if (
        parsed &&
        typeof parsed.type === 'string' &&
        typeof parsed.action === 'string' &&
        typeof parsed.confidence === 'number' &&
        parsed.confidence >= 0 &&
        parsed.confidence <= 1
      ) {
        return parsed;
      }
    } catch {
      // Fall through to fallback
    }
    return { type: 'unknown', action: 'fallback', confidence: 0.5 };
  }

  getStatus() {
    const hasKey = typeof this.apiKey === 'string' && this.apiKey.length > 10;
    return {
      provider: this.provider,
      model: this.model,
      baseURL: this.baseURL,
      configured: hasKey && !!this.baseURL,
    };
  }
}

module.exports = { KivoLLM };
