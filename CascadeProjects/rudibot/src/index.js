/**
 * Rudibot + KIVO Integration Main Entry Point
 * Orchestrates all modules for voice-enabled autonomous bot
 */

const TelegramBot = require('node-telegram-bot-api');
const { TelegramIntegration } = require('./integrations/telegram');
const { WhisperService } = require('./integrations/whisper/whisper-service');
const { TTSIntegration } = require('./integrations/tts');
const { HomeAssistantIntegration } = require('./integrations/homeassistant');

const { TelegramRouter } = require('./bot/telegram-router');
const { CommandHandler } = require('./bot/command-handler');
const { CallbackHandler } = require('./bot/callback-handler');

const { EmbeddedKivoCore } = require('./kivo/kivo-core');
const { KivoIntents } = require('./kivo/kivo-intents');
const { KivoVoice } = require('./kivo/kivo-voice');
const { EmbeddedKivoGuard } = require('./kivo/kivo-guard');
const { KivoReply } = require('./kivo/kivo-reply');

const { DeepscanAction } = require('./actions/deepscan-action');
const { CancelSubscriptionAction } = require('./actions/cancel-subscription-action');
const { HomeAssistantAction } = require('./actions/homeassistant-action');
const { DashboardAction } = require('./actions/dashboard-action');

class RudibotKivo {
  constructor(token, options = {}) {
    this.token = token;
    this.options = {
      polling: true,
      allowedUserIds: options.allowedUserIds || [],
      kivoRole: options.kivoRole || 'user',
      homeAssistant: options.homeAssistant || {},
      ...options
    };

    this.setupIntegrations();
    this.setupKivo();
    this.setupActions();
    this.setupBot();
  }

  setupIntegrations() {
    // Telegram integration
    this.telegram = new TelegramIntegration(this.token, {
      polling: this.options.polling
    });

    // Voice integrations
    this.whisper = new WhisperService({
      provider: this.options.whisperProvider || 'auto',
      language: this.options.language || 'de',
      openai: {
        apiKey: process.env.OPENAI_API_KEY
      },
      local: {
        serverUrl: process.env.WHISPER_SERVER_URL || 'http://localhost:8080'
      }
    });

    this.tts = new TTSIntegration({
      piperPath: this.options.piperPath,
      voice: this.options.ttsVoice || 'de_DE-thorsten_medium'
    });

    // Home Assistant
    this.homeAssistant = new HomeAssistantIntegration(this.options.homeAssistant);
  }

  setupKivo() {
    // Core KIVO components
    this.kivoCore = new EmbeddedKivoCore({
      guard: { role: this.options.kivoRole },
      rudibot: { baseUrl: 'http://localhost:3201' }
    });

    this.kivoIntents = new KivoIntents();
    this.kivoVoice = new KivoVoice({
      whisperPath: this.options.whisperPath,
      piperPath: this.options.piperPath
    });

    this.kivoGuard = new EmbeddedKivoGuard({
      role: this.options.kivoRole,
      allowedUserIds: this.options.allowedUserIds
    });

    this.kivoReply = new KivoReply();
  }

  setupActions() {
    // Action handlers
    this.deepscanAction = new DeepscanAction(null); // TODO: pass validator scanner
    this.cancelAction = new CancelSubscriptionAction(null, null); // TODO: pass hunter and engine
    this.homeAction = new HomeAssistantAction(this.options.homeAssistant);
    this.dashboardAction = new DashboardAction({ baseUrl: 'http://localhost:3000' });
  }

  setupBot() {
    // Connect Whisper to Telegram bot
    this.whisper.setBot(this.telegram.bot);

    // Bot components
    this.commandHandler = new CommandHandler(this.kivoCore, {
      telegram: this.telegram,
      integrations: {
        homeAssistant: this.homeAssistant
      }
    });

    this.callbackHandler = new CallbackHandler(this.kivoCore, this.commandHandler);
    this.router = new TelegramRouter(this.kivoCore, this.commandHandler.commands);

    // Register handlers
    this.registerHandlers();
  }

  registerHandlers() {
    // Message handlers
    this.telegram.registerMessageHandler(/^\/.*/, async (msg, chatId) => {
      return this.handleCommand(msg, chatId);
    });

    this.telegram.registerMessageHandler(/./, async (msg, chatId) => {
      return this.handleText(msg, chatId);
    });

    // Voice handler - uses WhisperService pipeline
    this.telegram.setVoiceHandler(async (msg, chatId) => {
      return this.handleVoice(msg, chatId);
    });

    // Callback handlers
    this.telegram.registerCallbackHandler(/^approve_/, async (callback, chatId) => {
      return this.handleApproval(callback, chatId);
    });

    this.telegram.registerCallbackHandler(/^cancel_/, async (callback, chatId) => {
      return this.handleCancellation(callback, chatId);
    });

    this.telegram.registerCallbackHandler(/^home_/, async (callback, chatId) => {
      return this.handleHomeAction(callback, chatId);
    });

    this.telegram.registerCallbackHandler(/^action_/, async (callback, chatId) => {
      return this.handleGenericAction(callback, chatId);
    });

    // Default handler for KIVO
    this.telegram.setDefaultHandler(async (msg, chatId) => {
      return this.handleKivoRequest(msg, chatId);
    });
  }

  // ── Message Handlers ───────────────────────────────────────
  async handleCommand(msg, chatId) {
    const text = msg.text || '';
    const command = text.split(' ')[0];
    const args = text.slice(command.length).trim();

    // Check authorization
    if (!this.kivoGuard.isUserAuthorized(chatId)) {
      return {
        message: '🚫 Unauthorized access',
        options: { parse_mode: 'Markdown' }
      };
    }

    // Handle command
    const handler = this.commandHandler.getHandler(command);
    if (handler) {
      return await handler(chatId, args);
    }

    return { message: '❌ Unknown command' };
  }

  async handleText(msg, chatId) {
    const text = msg.text || '';

    // Check authorization
    if (!this.kivoGuard.isUserAuthorized(chatId)) {
      return {
        message: '🚫 Unauthorized access',
        options: { parse_mode: 'Markdown' }
      };
    }

    // Route to KIVO if it looks like a KIVO request
    if (this.router.isKivoRequest(text)) {
      return await this.handleKivoRequest(msg, chatId);
    }

    return { message: '❌ I did not understand that. Type /help for available commands.' };
  }

  async handleVoice(msg, chatId) {
    // Check authorization
    if (!this.kivoGuard.isUserAuthorized(chatId)) {
      return {
        message: '🚫 Unauthorized access',
        options: { parse_mode: 'Markdown' }
      };
    }

    try {
      // Process voice message using WhisperService pipeline:
      // Telegram Voice → Download → FFmpeg → Whisper → Text
      const voiceResult = await this.whisper.processVoiceMessage(msg.voice);
      
      if (voiceResult.success) {
        // Log transcription
        this.auditLog?.logVoice(chatId, msg.voice.duration, voiceResult.text, voiceResult.confidence);
        
        // Process transcribed text through KIVO
        const textResult = await this.handleKivoText(voiceResult.text, chatId);
        
        // Add source info to response
        textResult.message = `🎙️ *Voice Transcription* (${voiceResult.source})\n\n_${voiceResult.text}_\n\n${textResult.message}`;
        
        // Optional: TTS response
        if (textResult.message && this.tts) {
          try {
            const ttsResult = await this.tts.synthesize(textResult.message);
            if (ttsResult.success && ttsResult.audioPath) {
              await this.telegram.sendAudio(chatId, ttsResult.audioPath, textResult.message);
              return { handled: true };
            }
          } catch (e) {
            console.warn('TTS failed:', e.message);
          }
        }
        
        return textResult;
      } else {
        return {
          message: `❌ Voice processing failed: ${voiceResult.error}`,
          options: { parse_mode: 'Markdown' }
        };
      }
    } catch (e) {
      console.error('Voice handling error:', e);
      return {
        message: '❌ An error occurred while processing your voice message.',
        options: { parse_mode: 'Markdown' }
      };
    }
  }

  async handleKivoRequest(msg, chatId) {
    const text = msg.text || '';
    return await this.handleKivoText(text, chatId);
  }

  async handleKivoText(text, chatId) {
    try {
      // Process through KIVO core
      const result = await this.kivoCore.processText(text, chatId);
      
      // Format response
      const response = this.kivoReply.formatResponse(result, {
        showContext: true,
        showConfidence: true
      });

      // Handle approval requirement
      if (result.blocked && result.requiresApproval) {
        const approvalId = this.callbackHandler.createPendingApproval(
          result.action,
          result.reason,
          {},
          chatId
        );

        const keyboard = this.callbackHandler.getApprovalButtons(approvalId);
        
        return {
          message: this.kivoReply.formatApprovalRequired(result.reason, result.action),
          options: {
            parse_mode: 'Markdown',
            reply_markup: { inline_keyboard: keyboard }
          }
        };
      }

      // Handle home control
      if (result.type === 'home' && result.device) {
        const keyboard = this.kivoReply.getHomeKeyboard();
        return {
          message: response.text,
          options: {
            parse_mode: 'Markdown',
            reply_markup: keyboard
          }
        };
      }

      return {
        message: response.text,
        options: {
          parse_mode: 'Markdown',
          reply_markup: response.keyboard
        }
      };

    } catch (e) {
      console.error('KIVO processing error:', e);
      return {
        message: '❌ KIVO processing failed.',
        options: { parse_mode: 'Markdown' }
      };
    }
  }

  // ── Callback Handlers ─────────────────────────────────────
  async handleApproval(callback, chatId) {
    const actionId = callback.data.replace('approve_', '');
    const approval = this.callbackHandler.pendingApprovals.get(actionId);
    
    if (!approval) {
      return {
        message: '❌ Approval expired or not found',
        editMessage: callback.message.message_id
      };
    }

    try {
      // Execute approved action
      const result = await this.executeApprovedAction(approval);
      
      // Remove from pending
      this.callbackHandler.pendingApprovals.delete(actionId);
      
      return {
        message: `✅ *APPROVED*\n\n${approval.description}\n\nResult: ${result.message || 'Success'}`,
        editMessage: callback.message.message_id,
        options: { parse_mode: 'Markdown' }
      };
    } catch (e) {
      return {
        message: `❌ Approval failed: ${e.message}`,
        editMessage: callback.message.message_id,
        options: { parse_mode: 'Markdown' }
      };
    }
  }

  async handleCancellation(callback, chatId) {
    const actionId = callback.data.replace('cancel_', '');
    const approval = this.callbackHandler.pendingApprovals.get(actionId);
    
    if (approval) {
      this.callbackHandler.pendingApprovals.delete(actionId);
    }
    
    return {
      message: `❌ *CANCELLED*\n\n${approval?.description || 'Action'}\n\nAction aborted.`,
      editMessage: callback.message.message_id,
      options: { parse_mode: 'Markdown' }
    };
  }

  async handleHomeAction(callback, chatId) {
    const action = callback.data.replace('home_', '');
    
    try {
      const result = await this.homeAction.execute(action, { chatId });
      
      return {
        message: result.message,
        options: { parse_mode: 'Markdown' }
      };
    } catch (e) {
      return {
        message: `❌ Home action failed: ${e.message}`,
        options: { parse_mode: 'Markdown' }
      };
    }
  }

  async handleGenericAction(callback, chatId) {
    const action = callback.data.replace('action_', '');
    
    // Handle generic actions based on prefix
    if (action.startsWith('deepscan_')) {
      const scope = action.replace('deepscan_', '');
      const result = await this.deepscanAction.execute({ scope, chatId });
      return { message: result.message, options: { parse_mode: 'Markdown' } };
    }
    
    if (action.startsWith('dashboard_')) {
      const scope = action.replace('dashboard_', '');
      const result = await this.dashboardAction.execute('status', { scope, chatId });
      return { message: result.message, options: { parse_mode: 'Markdown' } };
    }
    
    return {
      message: '❌ Unknown action',
      options: { parse_mode: 'Markdown' }
    };
  }

  async executeApprovedAction(approval) {
    switch (approval.type) {
      case 'subscription_kill':
        return await this.cancelAction.execute(approval.args);
      case 'elster_export':
        return { message: 'ELSTER export executed (simulated)' };
      case 'deepscan':
        return await this.deepscanAction.execute({ scope: 'full', chatId: approval.chatId });
      default:
        throw new Error(`Unknown approval type: ${approval.type}`);
    }
  }

  // ── Bot Lifecycle ─────────────────────────────────────────
  start() {
    console.log('🤖 Starting Rudibot + KIVO integration...');
    
    // Start polling
    if (this.options.polling) {
      this.telegram.startPolling();
      console.log('✅ Bot started with polling');
    }
    
    // Cleanup old files periodically
    setInterval(() => {
      this.kivoVoice.cleanupOldFiles();
      this.whisper.cleanupOldFiles();
      this.tts.cleanupOldFiles();
    }, 60 * 60 * 1000); // Every hour
    
    console.log('🎙️ KIVO voice integration ready');
    console.log('🏠 Home Assistant integration configured');
    console.log('📊 Dashboard integration ready');
  }

  stop() {
    console.log('🛑 Stopping Rudibot + KIVO...');
    
    this.telegram.stopPolling();
    this.telegram.close();
    
    console.log('✅ Bot stopped');
  }

  // ── Status ─────────────────────────────────────────────────
  async getStatus() {
    const kivoStatus = this.kivoCore.getStatus();
    const telegramStatus = this.telegram.getStatus();
    const haStatus = await this.homeAssistant.getStatus();
    const whisperStatus = await this.whisper.getStatus();
    
    return {
      bot: {
        running: telegramStatus.connected,
        messageHandlers: telegramStatus.messageHandlers,
        callbackHandlers: telegramStatus.callbackHandlers
      },
      kivo: kivoStatus,
      voice: {
        whisper: whisperStatus,
        tts: await this.tts.getStatus()
      },
      integrations: {
        telegram: telegramStatus,
        homeAssistant: haStatus
      },
      actions: {
        deepscan: this.deepscanAction.getStatus(),
        cancel: this.cancelAction.getStatus(),
        home: this.homeAction.getStatus(),
        dashboard: this.dashboardAction.getStatus()
      }
    };
  }
}

module.exports = { RudibotKivo };

// ── CLI Entry Point ────────────────────────────────────────
if (require.main === module) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) {
    console.error('❌ TELEGRAM_BOT_TOKEN environment variable required');
    process.exit(1);
  }

  const bot = new RudibotKivo(token, {
    allowedUserIds: process.env.ALLOWED_USER_IDS?.split(',') || [],
    kivoRole: process.env.KIVO_ROLE || 'user',
    homeAssistant: {
      baseUrl: process.env.HOME_ASSISTANT_URL,
      token: process.env.HOME_ASSISTANT_TOKEN
    }
  });

  bot.start();

  // Graceful shutdown
  process.on('SIGINT', () => {
    console.log('\n🛑 Received SIGINT, shutting down gracefully...');
    bot.stop();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    console.log('\n🛑 Received SIGTERM, shutting down gracefully...');
    bot.stop();
    process.exit(0);
  });
}
