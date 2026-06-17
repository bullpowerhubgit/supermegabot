import { DiscordConfig, DiscordAction } from './types.js';
import { Client, GatewayIntentBits } from 'discord.js';

export class DiscordController {
  private config: DiscordConfig;
  private client: Client;

  constructor(config: DiscordConfig) {
    this.config = config;
    this.client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent] });
  }

  async execute(action: DiscordAction): Promise<any> {
    if (!this.client.isReady()) {
      await this.client.login(this.config.token);
    }

    switch (action.action) {
      case 'sendMessage':
        return this.sendMessage(action.channelId!, action.text!);
      case 'getChannels':
        return this.getChannels();
      case 'getMessages':
        return this.getMessages(action.channelId!);
      case 'createChannel':
        return this.createChannel(action.data);
      case 'deleteChannel':
        return this.deleteChannel(action.channelId!);
      default:
        throw new Error(`Unknown Discord action: ${action.action}`);
    }
  }

  private async sendMessage(channelId: string, text: string): Promise<any> {
    try {
      const channel = await this.client.channels.fetch(channelId);
      if (!channel || !('send' in channel)) {
        throw new Error('Channel not found or cannot send messages');
      }
      const message = await channel.send(text);
      return { success: true, message: { id: message.id, content: message.content } };
    } catch (error: any) {
      throw new Error(`Discord message failed: ${error.message}`);
    }
  }

  private async getChannels(): Promise<any> {
    try {
      const guild = this.config.guildId ? await this.client.guilds.fetch(this.config.guildId) : this.client.guilds.cache.first();
      if (!guild) {
        throw new Error('Guild not found');
      }
      const channels = await guild.channels.fetch();
      return { success: true, channels: channels.filter(c => c !== null).map(c => ({ id: c.id, name: c.name, type: c.type })) };
    } catch (error: any) {
      throw new Error(`Discord getChannels failed: ${error.message}`);
    }
  }

  private async getMessages(channelId: string): Promise<any> {
    try {
      const channel = await this.client.channels.fetch(channelId);
      if (!channel || !('messages' in channel)) {
        throw new Error('Channel not found or cannot fetch messages');
      }
      const messages = await channel.messages.fetch({ limit: 50 });
      return { success: true, messages: messages.map(m => ({ id: m.id, content: m.content, author: m.author.username })) };
    } catch (error: any) {
      throw new Error(`Discord getMessages failed: ${error.message}`);
    }
  }

  private async createChannel(data: any): Promise<any> {
    try {
      const guild = this.config.guildId ? await this.client.guilds.fetch(this.config.guildId) : this.client.guilds.cache.first();
      if (!guild) {
        throw new Error('Guild not found');
      }
      const channel = await guild.channels.create({ name: data.name, type: data.type });
      return { success: true, channel: { id: channel.id, name: channel.name } };
    } catch (error: any) {
      throw new Error(`Discord createChannel failed: ${error.message}`);
    }
  }

  private async deleteChannel(channelId: string): Promise<any> {
    try {
      const channel = await this.client.channels.fetch(channelId);
      if (!channel) {
        throw new Error('Channel not found');
      }
      await channel.delete();
      return { success: true, message: 'Channel deleted' };
    } catch (error: any) {
      throw new Error(`Discord deleteChannel failed: ${error.message}`);
    }
  }

  async close(): Promise<void> {
    if (this.client.isReady()) {
      await this.client.destroy();
    }
  }
}
