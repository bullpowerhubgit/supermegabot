import { SlackConfig, SlackAction } from './types.js';
import { WebClient } from '@slack/web-api';

export class SlackController {
  private config: SlackConfig;
  private client: WebClient;

  constructor(config: SlackConfig) {
    this.config = config;
    this.client = new WebClient(config.token);
  }

  async execute(action: SlackAction): Promise<any> {
    switch (action.action) {
      case 'sendMessage':
        return this.sendMessage(action.channel || this.config.channel!, action.text!);
      case 'getChannels':
        return this.getChannels();
      case 'getUsers':
        return this.getUsers();
      case 'postMessage':
        return this.postMessage(action.channel!, action.text!, action.data);
      case 'uploadFile':
        return this.uploadFile(action.channel!, action.file!);
      default:
        throw new Error(`Unknown Slack action: ${action.action}`);
    }
  }

  private async sendMessage(channel: string, text: string): Promise<any> {
    try {
      const result = await this.client.chat.postMessage({ channel, text });
      return { success: true, message: result };
    } catch (error: any) {
      throw new Error(`Slack message failed: ${error.message}`);
    }
  }

  private async getChannels(): Promise<any> {
    try {
      const result = await this.client.conversations.list({ types: 'public_channel,private_channel' as any });
      return { success: true, channels: result.channels };
    } catch (error: any) {
      throw new Error(`Slack getChannels failed: ${error.message}`);
    }
  }

  private async getUsers(): Promise<any> {
    try {
      const result = await this.client.users.list({ limit: 100 });
      return { success: true, users: result.members };
    } catch (error: any) {
      throw new Error(`Slack getUsers failed: ${error.message}`);
    }
  }

  private async postMessage(channel: string, text: string, data?: any): Promise<any> {
    try {
      const result = await this.client.chat.postMessage({ channel, text, ...data });
      return { success: true, message: result };
    } catch (error: any) {
      throw new Error(`Slack postMessage failed: ${error.message}`);
    }
  }

  private async uploadFile(channel: string, file: string): Promise<any> {
    try {
      const result = await this.client.files.uploadV2({ channels: channel as any, file });
      return { success: true, file: result };
    } catch (error: any) {
      throw new Error(`Slack uploadFile failed: ${error.message}`);
    }
  }
}
