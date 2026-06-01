#!/usr/bin/env node
/**
 * RudiBot Externe Agenten Integration
 * Verbindet mit externen AI-Agenten und APIs
 */

import https from 'https';
import http from 'http';
import { EventEmitter } from 'events';
import fs from 'fs';
import path from 'path';
import { APIHelper } from './config/api-helper.js';

class ExterneAgenten extends EventEmitter {
  constructor() {
    super();
    this.agenten = new Map();
    this.connections = new Map();
    this.responses = new Map();
    this.apiHelper = new APIHelper();
    this.config = this.loadConfig();
    this.setupAgenten();
  }

  loadConfig() {
    try {
      const configPath = path.join(process.cwd(), 'RudiBot-Secure-API', 'api-keys.txt');
      const content = fs.readFileSync(configPath, 'utf8');
      
      const keys = {};
      content.split('\n').forEach(line => {
        if (line.includes('ANTHROPIC_API_KEY=')) {
          keys.anthropic = line.split('=')[1];
        }
        if (line.includes('PERPLEXITY_API_KEY=')) {
          keys.perplexity = line.split('=')[1];
        }
        if (line.includes('TELEGRAM_BOT_TOKEN=')) {
          keys.telegram = line.split('=')[1];
        }
        if (line.includes('GOOGLE_CLIENT_ID=')) {
          keys.google = line.split('=')[1];
        }
      });
      
      return keys;
    } catch (e) {
      // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('⚠️ API-Keys nicht gefunden');
      return {};
    }
  }

  setupAgenten() {
    // Anthropic Claude
    this.agenten.set('claude', {
      name: 'Claude (Anthropic)',
      type: 'ai',
      endpoint: 'https://api.anthropic.com/v1/messages',
      key: this.config.anthropic,
      model: 'claude-sonnet-4-20250514',
      status: 'configured',
      description: 'Advanced AI Agent for complex tasks'
    });

    // Perplexity
    this.agenten.set('perplexity', {
      name: 'Perplexity AI',
      type: 'search',
      endpoint: 'https://api.perplexity.ai/chat/completions',
      key: this.config.perplexity,
      model: 'llama-3-sonar-large-32k-online',
      status: 'configured',
      description: 'Real-time search and web access'
    });

    // Telegram Bot
    this.agenten.set('telegram', {
      name: 'Telegram Bot',
      type: 'notification',
      endpoint: 'https://api.telegram.org/bot' + this.config.telegram,
      key: this.config.telegram,
      status: 'configured',
      description: 'Mobile notifications and chat interface'
    });

    // Google APIs
    this.agenten.set('google', {
      name: 'Google APIs',
      type: 'integration',
      endpoint: 'https://www.googleapis.com',
      key: this.config.google,
      status: 'configured',
      description: 'Google Drive, Ads, Merchant Center'
    });

    // Cascade (aktueller Agent)
    this.agenten.set('cascade', {
      name: 'Cascade (Current)',
      type: 'ai',
      endpoint: 'local',
      status: 'active',
      description: 'Current AI Assistant - System Integration'
    });

    // Ollama (Local)
    this.agenten.set('ollama', {
      name: 'Ollama Local',
      type: 'ai',
      endpoint: 'http://localhost:11434',
      status: 'active',
      description: 'Local AI Models - llama3.2, gemma4'
    });
  }

  async callAgent(agentName, message, options = {}) {
    const agent = this.agenten.get(agentName);
    if (!agent) {
      throw new Error(`Agent ${agentName} nicht gefunden`);
    }

    try {
      if (agentName === 'claude') {
        return await this.callClaude(message, options);
      } else if (agentName === 'perplexity') {
        return await this.callPerplexity(message, options);
      } else if (agentName === 'telegram') {
        return await this.callTelegram(message, options);
      } else if (agentName === 'ollama') {
        return await this.callOllama(message, options);
      }
    } catch (e) {
      console.error(`Fehler bei ${agentName}:`, e.message);
      return { error: e.message, agent: agentName };
    }
  }

  async callClaude(message, options = {}) {
    const agent = this.agenten.get('claude');
    
    const data = JSON.stringify({
      model: agent.model,
      max_tokens: options.maxTokens || 1000,
      messages: [{
        role: 'user',
        content: message
      }]
    });

    return new Promise((resolve, reject) => {
      const req = https.request({
        hostname: 'api.anthropic.com',
        port: 443,
        path: '/v1/messages',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': agent.key,
          'anthropic-version': '2023-06-01',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let response = '';
        res.on('data', chunk => response += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(response);
            
            if (result.error) {
              reject(new Error(result.error.message || JSON.stringify(result.error)));
              return;
            }
            
            if (!result.content || !result.content[0]) {
              reject(new Error('Invalid API response structure'));
              return;
            }
            
            resolve({
              agent: 'claude',
              response: result.content[0].text,
              usage: result.usage
            });
          } catch (e) {
            reject(e);
          }
        });
      });

      req.on('error', reject);
      req.write(data);
      req.end();
    });
  }

  async callPerplexity(message, options = {}) {
    const agent = this.agenten.get('perplexity');
    
    const data = JSON.stringify({
      model: agent.model,
      messages: [{
        role: 'user',
        content: message
      }]
    });

    return new Promise((resolve, reject) => {
      const req = https.request({
        hostname: 'api.perplexity.ai',
        port: 443,
        path: '/chat/completions',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${agent.key}`,
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let response = '';
        res.on('data', chunk => response += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(response);
            resolve({
              agent: 'perplexity',
              response: result.choices[0].message.content,
              usage: result.usage
            });
          } catch (e) {
            reject(e);
          }
        });
      });

      req.on('error', reject);
      req.write(data);
      req.end();
    });
  }

  async callTelegram(message, options = {}) {
    const agent = this.agenten.get('telegram');
    
    const data = JSON.stringify({
      chat_id: options.chatId || 'YOUR_CHAT_ID',
      text: message,
      parse_mode: 'HTML'
    });

    return new Promise((resolve, reject) => {
      const req = https.request({
        hostname: 'api.telegram.org',
        port: 443,
        path: `/bot${agent.key}/sendMessage`,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let response = '';
        res.on('data', chunk => response += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(response);
            resolve({
              agent: 'telegram',
              response: 'Message sent',
              result: result
            });
          } catch (e) {
            reject(e);
          }
        });
      });

      req.on('error', reject);
      req.write(data);
      req.end();
    });
  }

  async callOllama(message, options = {}) {
    const agent = this.agenten.get('ollama');
    const model = options.model || 'llama3.2';
    
    const data = JSON.stringify({
      model: model,
      prompt: message,
      stream: false
    });

    return new Promise((resolve, reject) => {
      const req = http.request({
        hostname: 'localhost',
        port: 11434,
        path: '/api/generate',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let response = '';
        res.on('data', chunk => response += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(response);
            resolve({
              agent: 'ollama',
              model: model,
              response: result.response,
              usage: {
                prompt_tokens: result.prompt_eval_count || 0,
                completion_tokens: result.eval_count || 0
              }
            });
          } catch (e) {
            reject(e);
          }
        });
      });

      req.on('error', reject);
      req.write(data);
      req.end();
    });
  }

  async multiAgentQuery(prompt, agents = ['claude', 'ollama', 'perplexity']) {
    const results = [];
    
    for (const agentName of agents) {
      try {
        const result = await this.callAgent(agentName, prompt);
        results.push(result);
      } catch (e) {
        results.push({
          agent: agentName,
          error: e.message
        });
      }
    }
    
    return {
      prompt,
      timestamp: new Date().toISOString(),
      agents: results,
      consensus: this.findConsensus(results)
    };
  }

  findConsensus(results) {
    const validResults = results.filter(r => !r.error && r.response);
    if (validResults.length === 0) return null;
    
    // Einfache Konsens-Findung: längste gemeinsame Antwort
    const responses = validResults.map(r => r.response);
    return responses[0]; // Placeholder für bessere Konsens-Logik
  }

  getStatus() {
    const status = {};
    for (const [name, agent] of this.agenten) {
      status[name] = {
        name: agent.name,
        type: agent.type,
        status: agent.status,
        endpoint: agent.endpoint,
        description: agent.description
      };
    }
    return status;
  }
}

export default ExterneAgenten;
