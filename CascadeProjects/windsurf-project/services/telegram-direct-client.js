/**
 * Direkter Telegram Client - Workaround für interne Bot API Fehler
 * Sendet Notifications direkt zur Telegram API
 */

import axios from 'axios';
import dotenv from 'dotenv';
dotenv.config();

class TelegramDirectClient {
  constructor(options = {}) {
    this.botToken = options.botToken || process.env.TELEGRAM_BOT_TOKEN;
    this.chatId = options.chatId || process.env.TELEGRAM_CHAT_ID;
    this.serviceName = options.serviceName || 'windsurf-platform';
    this.timeout = options.timeout || 5000;
    
    // Chat ID als String sicherstellen
    this.chatId = String(this.chatId);
    
    this.levelEmojis = {
      info: 'ℹ️',
      warning: '⚠️',
      error: '❌',
      critical: '🚨',
      success: '✅'
    };
    
    this.apiBase = `https://api.telegram.org/bot${this.botToken}`;
  }

  async _send(level, title, message, metadata = {}) {
    const emoji = this.levelEmojis[level] || 'ℹ️';
    const formattedMessage = `${emoji} ${this.serviceName.toUpperCase()}\n\n` +
                           `${title}\n\n` +
                           `${message}` +
                           (Object.keys(metadata).length > 0 ? `\n\nDetails: ${JSON.stringify(metadata, null, 2)}` : '');

    try {
      const response = await axios.post(
        `${this.apiBase}/sendMessage`,
        {
          chat_id: this.chatId,
          text: formattedMessage
        },
        { timeout: this.timeout }
      );
      
      return { success: true, data: response.data };
    } catch (error) {
      console.error(`[${this.serviceName}] Telegram API Error:`, error.message);
      return { success: false, error: error.message };
    }
  }

  async info(title, message, metadata) {
    return this._send('info', title, message, metadata);
  }

  async warning(title, message, metadata) {
    return this._send('warning', title, message, metadata);
  }

  async error(title, message, metadata) {
    return this._send('error', title, message, metadata);
  }

  async critical(title, message, metadata) {
    return this._send('critical', title, message, metadata);
  }

  async success(title, message, metadata) {
    return this._send('success', title, message, metadata);
  }

  async healthCheck() {
    try {
      const response = await axios.get(`${this.apiBase}/getMe`, { timeout: 10000 });
      return { healthy: true, data: response.data };
    } catch (error) {
      return { healthy: false, error: error.message };
    }
  }
}

export default TelegramDirectClient;
