/**
 * Telegram Notification Client
 * 
 * Dieses Modul erlaubt jedem Service in der Windsurf Platform,
 * Notifications an den zentralen Telegram Bot zu senden.
 * 
 * Verwendung:
 *   import NotificationClient from './services/telegram-notification-client.js';
 *   const notifier = new NotificationClient({ serviceName: 'shopify' });
 *   await notifier.info('Neue Bestellung', '€45,90 von Max Mustermann');
 */

import axios from 'axios';

class TelegramNotificationClient {
  constructor(options = {}) {
    this.botUrl = options.botUrl || process.env.TELEGRAM_BOT_URL || 'http://localhost:8000';
    this.serviceName = options.serviceName || 'unknown-service';
    this.timeout = options.timeout || 5000;
    this.retries = options.retries || 3;
    
    this.levelEmojis = {
      info: 'ℹ️',
      warning: '⚠️',
      error: '❌',
      critical: '🚨',
      success: '✅'
    };
  }

  async _send(level, title, message, metadata = {}) {
    const payload = {
      service: this.serviceName,
      type: level, // Bot API erwartet 'type' nicht 'level'
      title,
      message,
      metadata: {
        ...metadata,
        timestamp: new Date().toISOString(),
        client_version: '1.0.0'
      }
    };

    for (let attempt = 1; attempt <= this.retries; attempt++) {
      try {
        const response = await axios.post(
          `${this.botUrl}/api/send-notification`,
          payload,
          { timeout: this.timeout }
        );
        return { success: true, data: response.data };
      } catch (error) {
        if (attempt === this.retries) {
          console.error(`[${this.serviceName}] Notification failed after ${this.retries} attempts:`, error.message);
          return { success: false, error: error.message };
        }
        await new Promise(r => setTimeout(r, 1000 * attempt));
      }
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

  async sendRaw(payload) {
    return this._send(
      payload.level || 'info',
      payload.title,
      payload.message,
      payload.metadata
    );
  }

  async broadcast(title, message, metadata) {
    const payload = {
      service: this.serviceName,
      level: 'broadcast',
      title,
      message,
      metadata: {
        ...metadata,
        timestamp: new Date().toISOString()
      }
    };

    try {
      const response = await axios.post(
        `${this.botUrl}/api/broadcast`,
        payload,
        { timeout: this.timeout }
      );
      return { success: true, data: response.data };
    } catch (error) {
      console.error(`[${this.serviceName}] Broadcast failed:`, error.message);
      return { success: false, error: error.message };
    }
  }

  async healthCheck() {
    try {
      const response = await axios.get(`${this.botUrl}/health`, { timeout: 3000 });
      return { healthy: true, data: response.data };
    } catch (error) {
      return { healthy: false, error: error.message };
    }
  }
}

export default TelegramNotificationClient;
