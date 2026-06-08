import { TelegramConfig, TelegramAction } from './types.js';
import TelegramBot from 'node-telegram-bot-api';

export class TelegramController {
  private config: TelegramConfig;
  private bot: TelegramBot;

  constructor(config: TelegramConfig) {
    this.config = config;
    this.bot = new TelegramBot(config.token, { polling: false });
  }

  async execute(action: TelegramAction): Promise<any> {
    switch (action.action) {
      case 'sendMessage':
        return this.sendMessage(action.chatId || this.config.chatId!, action.text!);
      case 'getUpdates':
        return this.getUpdates();
      case 'getMe':
        return this.getMe();
      case 'sendPhoto':
        return this.sendPhoto(action.chatId || this.config.chatId!, action.file!);
      case 'sendDocument':
        return this.sendDocument(action.chatId || this.config.chatId!, action.file!);
      default:
        throw new Error(`Unknown Telegram action: ${action.action}`);
    }
  }

  private async sendMessage(chatId: string, text: string): Promise<any> {
    try {
      const message = await this.bot.sendMessage(chatId, text);
      return { success: true, message: { id: message.message_id, text: message.text } };
    } catch (error: any) {
      throw new Error(`Telegram message failed: ${error.message}`);
    }
  }

  private async getUpdates(): Promise<any> {
    try {
      const updates = await this.bot.getUpdates();
      return { success: true, updates };
    } catch (error: any) {
      throw new Error(`Telegram getUpdates failed: ${error.message}`);
    }
  }

  private async getMe(): Promise<any> {
    try {
      const botInfo = await this.bot.getMe();
      return { success: true, bot: botInfo };
    } catch (error: any) {
      throw new Error(`Telegram getMe failed: ${error.message}`);
    }
  }

  private async sendPhoto(chatId: string, file: string): Promise<any> {
    try {
      const message = await this.bot.sendPhoto(chatId, file);
      return { success: true, message: { id: message.message_id } };
    } catch (error: any) {
      throw new Error(`Telegram sendPhoto failed: ${error.message}`);
    }
  }

  private async sendDocument(chatId: string, file: string): Promise<any> {
    try {
      const message = await this.bot.sendDocument(chatId, file);
      return { success: true, message: { id: message.message_id } };
    } catch (error: any) {
      throw new Error(`Telegram sendDocument failed: ${error.message}`);
    }
  }
}
