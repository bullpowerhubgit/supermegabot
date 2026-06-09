// ============================================
// RUDIBOT OPENCLAW NODE.JS CLIENT
// WebSocket Client für OpenClaw Gateway
// ============================================

import WebSocket from 'ws';

export interface OpenClawConfig {
  url?: string;
  token?: string;
  model?: string;
  timeout?: number;
}

export interface OpenClawMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface OpenClawResponse {
  content: string;
  model: string;
  tokens?: number;
  finish_reason?: string;
}

export class OpenClawClient {
  private ws: WebSocket | null = null;
  private config: Required<OpenClawConfig>;
  private messageQueue: OpenClawMessage[] = [];
  public isConnected = false;
  private messageId = 0;

  constructor(config: OpenClawConfig = {}) {
    this.config = {
      url: config.url || process.env.OPENCLAW_URL || 'ws://127.0.0.1:18789',
      token: config.token || process.env.OPENCLAW_TOKEN || '',
      model: config.model || process.env.OPENCLAW_MODEL || 'anthropic/claude-sonnet-4-20250514',
      timeout: config.timeout || 30000,
    };
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.config.url);

      this.ws.on('open', () => {
        this.isConnected = true;
        console.log('✅ OpenClaw connected to', this.config.url);
        resolve();
      });

      this.ws.on('error', (error) => {
        this.isConnected = false;
        reject(error);
      });

      this.ws.on('close', () => {
        this.isConnected = false;
        console.log('🔌 OpenClaw disconnected');
      });

      this.ws.on('message', (data) => {
        this.handleMessage(data.toString());
      });
    });
  }

  async chat(messages: OpenClawMessage[]): Promise<OpenClawResponse> {
    if (!this.isConnected) {
      await this.connect();
    }

    const id = ++this.messageId;
    const payload = {
      id,
      model: this.config.model,
      messages,
      stream: false,
    };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('OpenClaw request timeout'));
      }, this.config.timeout);

      const handler = (data: string) => {
        try {
          const response = JSON.parse(data);
          if (response.id === id) {
            clearTimeout(timeout);
            this.ws?.off('message', handler);
            resolve({
              content: response.content || response.text || response.response,
              model: response.model,
              tokens: response.tokens,
              finish_reason: response.finish_reason,
            });
          }
        } catch (e) {
          // Ignore parse errors for other messages
        }
      };

      this.ws?.on('message', handler);
      this.ws?.send(JSON.stringify(payload));
    });
  }

  async complete(prompt: string, systemPrompt?: string): Promise<string> {
    const messages: OpenClawMessage[] = [];
    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }
    messages.push({ role: 'user', content: prompt });

    const response = await this.chat(messages);
    return response.content;
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.isConnected = false;
    }
  }

  private handleMessage(data: string): void {
    // Base handler - extended in subclasses
  }
}

// Singleton instance
let openClawInstance: OpenClawClient | null = null;

export function getOpenClawClient(config?: OpenClawConfig): OpenClawClient {
  if (!openClawInstance) {
    openClawInstance = new OpenClawClient(config);
  }
  return openClawInstance;
}

export default OpenClawClient;
