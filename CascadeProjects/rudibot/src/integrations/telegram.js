/**
 * Telegram Integration — Core Telegram bot functionality
 * Handles message routing, voice processing, and inline keyboards
 */

const TelegramBot = require('node-telegram-bot-api');

class TelegramIntegration {
  constructor(token, options = {}) {
    this.bot = new TelegramBot(token, options);
    this.messageHandlers = new Map();
    this.callbackHandlers = new Map();
    this.voiceHandler = null;
    this.setupBot();
  }

  setupBot() {
    // Message handler
    this.bot.on('message', async (msg) => {
      await this.handleMessage(msg);
    });

    // Callback handler
    this.bot.on('callback_query', async (callback) => {
      await this.handleCallback(callback);
    });

    // Voice handler
    this.bot.on('voice', async (msg) => {
      await this.handleVoice(msg);
    });
  }

  // ── Message Handling ───────────────────────────────────────
  async handleMessage(msg) {
    const chatId = msg.chat.id;
    const text = msg.text || '';
    
    try {
      // Check for registered handlers
      for (const [pattern, handler] of this.messageHandlers) {
        if (this.matchesPattern(text, pattern)) {
          const result = await handler(msg, chatId);
          if (result && result.message) {
            await this.sendMessage(chatId, result.message, result.options);
          }
          return;
        }
      }

      // No handler found, pass to default handler
      if (this.defaultHandler) {
        const result = await this.defaultHandler(msg, chatId);
        if (result && result.message) {
          await this.sendMessage(chatId, result.message, result.options);
        }
      }
    } catch (e) {
      console.error('Message handling error:', e);
      await this.sendMessage(chatId, '❌ An error occurred while processing your message.');
    }
  }

  async handleVoice(msg) {
    const chatId = msg.chat.id;
    
    try {
      if (this.voiceHandler) {
        const result = await this.voiceHandler(msg, chatId);
        if (result && result.message) {
          await this.sendMessage(chatId, result.message, result.options);
        }
      } else {
        await this.sendMessage(chatId, '🎤 Voice message received, but voice processing is not configured.');
      }
    } catch (e) {
      console.error('Voice handling error:', e);
      await this.sendMessage(chatId, '❌ An error occurred while processing your voice message.');
    }
  }

  async handleCallback(callback) {
    const chatId = callback.message.chat.id;
    const data = callback.data;
    
    try {
      // Acknowledge callback
      await this.bot.answerCallbackQuery(callback.id);

      // Find handler
      for (const [pattern, handler] of this.callbackHandlers) {
        if (this.matchesPattern(data, pattern)) {
          const result = await handler(callback, chatId);
          if (result && result.message) {
            if (result.editMessage) {
              await this.editMessage(chatId, callback.message.message_id, result.message, result.options);
            } else {
              await this.sendMessage(chatId, result.message, result.options);
            }
          }
          return;
        }
      }

      // No handler found
      await this.sendMessage(chatId, '❌ Unknown action');
    } catch (e) {
      console.error('Callback handling error:', e);
      await this.sendMessage(chatId, '❌ An error occurred while processing your action.');
    }
  }

  // ── Message Sending ───────────────────────────────────────
  async sendMessage(chatId, text, options = {}) {
    const defaultOptions = {
      parse_mode: 'Markdown',
      disable_web_page_preview: true
    };

    const finalOptions = { ...defaultOptions, ...options };
    return await this.bot.sendMessage(chatId, text, finalOptions);
  }

  async editMessage(chatId, messageId, text, options = {}) {
    const defaultOptions = {
      parse_mode: 'Markdown',
      disable_web_page_preview: true
    };

    const finalOptions = { ...defaultOptions, ...options };
    return await this.bot.editMessageText(text, {
      chat_id: chatId,
      message_id: messageId,
      ...finalOptions
    });
  }

  async sendPhoto(chatId, photo, caption, options = {}) {
    const defaultOptions = {
      parse_mode: 'Markdown'
    };

    const finalOptions = { ...defaultOptions, ...options };
    return await this.bot.sendPhoto(chatId, photo, caption, finalOptions);
  }

  async sendAudio(chatId, audio, caption, options = {}) {
    const defaultOptions = {
      parse_mode: 'Markdown'
    };

    const finalOptions = { ...defaultOptions, ...options };
    return await this.bot.sendAudio(chatId, audio, caption, finalOptions);
  }

  // ── Handler Registration ─────────────────────────────────
  registerMessageHandler(pattern, handler) {
    this.messageHandlers.set(pattern, handler);
  }

  registerCallbackHandler(pattern, handler) {
    this.callbackHandlers.set(pattern, handler);
  }

  setVoiceHandler(handler) {
    this.voiceHandler = handler;
  }

  setDefaultHandler(handler) {
    this.defaultHandler = handler;
  }

  // ── Pattern Matching ─────────────────────────────────────
  matchesPattern(text, pattern) {
    if (pattern instanceof RegExp) {
      return pattern.test(text);
    }
    
    if (pattern.startsWith('/')) {
      return text.startsWith(pattern);
    }
    
    if (pattern.includes('*')) {
      const regex = new RegExp(pattern.replace(/\*/g, '.*'));
      return regex.test(text);
    }
    
    return text === pattern;
  }

  // ── Utility Methods ───────────────────────────────────────
  async getFileLink(fileId) {
    return await this.bot.getFileLink(fileId);
  }

  async getFile(fileId) {
    return await this.bot.getFile(fileId);
  }

  async getUserProfilePhotos(userId, offset = 0, limit = 1) {
    return await this.bot.getUserProfilePhotos(userId, { offset, limit });
  }

  async getChat(chatId) {
    return await this.bot.getChat(chatId);
  }

  async getChatAdministrators(chatId) {
    return await this.bot.getChatAdministrators(chatId);
  }

  async getChatMemberCount(chatId) {
    return await this.bot.getChatMemberCount(chatId);
  }

  async getChatMember(chatId, userId) {
    return await this.bot.getChatMember(chatId, userId);
  }

  // ── Webhook Support ───────────────────────────────────────
  async setWebHook(webHookUrl, options = {}) {
    return await this.bot.setWebHook(webHookUrl, options);
  }

  async deleteWebHook() {
    return await this.bot.deleteWebHook();
  }

  async getWebHookInfo() {
    return await this.bot.getWebHookInfo();
  }

  // ── Polling Support ───────────────────────────────────────
  startPolling(options = {}) {
    this.bot.startPolling(options);
  }

  stopPolling() {
    this.bot.stopPolling();
  }

  isPolling() {
    return this.bot.isPolling();
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      connected: true,
      messageHandlers: this.messageHandlers.size,
      callbackHandlers: this.callbackHandlers.size,
      hasVoiceHandler: !!this.voiceHandler,
      hasDefaultHandler: !!this.defaultHandler
    };
  }

  // ── Error Handling ───────────────────────────────────────
  onError(handler) {
    this.bot.on('error', handler);
  }

  onPollingError(handler) {
    this.bot.on('polling_error', handler);
  }

  // ── Rate Limiting ───────────────────────────────────────
  async sendMessageWithRetry(chatId, text, options = {}, maxRetries = 3) {
    for (let i = 0; i < maxRetries; i++) {
      try {
        return await this.sendMessage(chatId, text, options);
      } catch (e) {
        if (e.response && e.response.body && e.response.body.error_code === 429) {
          // Rate limited, wait and retry
          const retryAfter = e.response.body.parameters?.retry_after || 5;
          await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
          continue;
        }
        throw e;
      }
    }
    throw new Error('Max retries exceeded');
  }

  // ── Cleanup ─────────────────────────────────────────────
  close() {
    if (this.isPolling()) {
      this.stopPolling();
    }
  }
}

module.exports = { TelegramIntegration };
