import { EventEmitter } from 'events';
import { Logger } from '../utils/Logger';

export interface TelegramConfig {
  token: string;
  allowedUsers: string[];
}

export interface TelegramMessage {
  messageId: number;
  from: {
    id: number;
    username?: string;
    firstName: string;
    lastName?: string;
  };
  chat: {
    id: number;
    type: 'private' | 'group' | 'supergroup' | 'channel';
  };
  text: string;
  date: number;
}

export class TelegramBot extends EventEmitter {
  private logger: Logger;
  private config: TelegramConfig | null = null;
  private connected: boolean = false;
  private initialized: boolean = false;
  private polling: boolean = false;

  constructor() {
    super();
    this.logger = new Logger('TelegramBot');
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Telegram Bot...');
    
    // Load configuration from environment
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const allowedUsers = process.env.TELEGRAM_ALLOWED_USERS?.split(',').map(u => u.trim()) || [];
    
    if (!token) {
      this.logger.warn('Telegram bot token not configured, running in demo mode');
    } else {
      this.config = {
        token,
        allowedUsers
      };
      this.connected = true;
      this.logger.info('Telegram bot initialized successfully');
    }
    
    this.initialized = true;
    
    // Start polling if connected
    if (this.connected) {
      this.startPolling();
    }
    
    this.emit('initialized');
  }

  async shutdown(): Promise<void> {
    this.logger.info('Shutting down Telegram Bot...');
    
    this.stopPolling();
    this.connected = false;
    this.initialized = false;
    
    this.emit('shutdown');
  }

  isConnected(): boolean {
    return this.connected;
  }

  private startPolling(): void {
    if (this.polling || !this.config) return;
    
    this.polling = true;
    this.logger.info('Starting Telegram bot polling...');
    
    // Simulate polling (in real implementation, use node-telegram-bot-api)
    this.simulatePolling();
  }

  private stopPolling(): void {
    this.polling = false;
    this.logger.info('Stopped Telegram bot polling');
  }

  private simulatePolling(): void {
    if (!this.polling) return;
    
    // Simulate receiving messages every 10 seconds
    setTimeout(() => {
      if (this.polling && this.config) {
        // Generate demo message
        const demoMessage: TelegramMessage = {
          messageId: Math.floor(Math.random() * 10000),
          from: {
            id: parseInt(this.config.allowedUsers[0] || '123456789'),
            username: 'demo_user',
            firstName: 'Demo',
            lastName: 'User'
          },
          chat: {
            id: parseInt(this.config.allowedUsers[0] || '123456789'),
            type: 'private'
          },
          text: this.getRandomCommand(),
          date: Math.floor(Date.now() / 1000)
        };
        
        this.handleMessage(demoMessage);
        this.simulatePolling(); // Continue polling
      }
    }, 10000);
  }

  private handleMessage(message: TelegramMessage): void {
    this.logger.info(`Received message: ${message.text} from ${message.from.firstName}`);
    
    // Check if user is allowed
    if (this.config && !this.config.allowedUsers.includes(message.from.id.toString())) {
      this.logger.warn(`Unauthorized user attempted to use bot: ${message.from.id}`);
      return;
    }
    
    // Process command
    const response = this.processCommand(message.text);
    
    // Send response (simulated)
    this.sendMessage(message.chat.id, response);
    
    this.emit('message:received', message);
    this.emit('message:processed', { message, response });
  }

  private processCommand(text: string): string {
    const command = text.toLowerCase().trim();
    
    switch (command) {
      case '/start':
        return '🤖 Super Mega Bot is online! Use /help to see available commands.';
        
      case '/help':
        return `📋 Available commands:
/start - Start the bot
/status - Check bot status
/shopify - Shopify status
/orders - Recent orders
/products - Product list
/revenue - Revenue overview
/health - System health`;
        
      case '/status':
        return `🟢 Bot Status: Online
📊 Uptime: ${Math.floor(process.uptime())}s
🔌 Connected: ${this.connected ? 'Yes' : 'No'}
⚡ Active Users: ${this.config?.allowedUsers.length || 0}`;
        
      case '/shopify':
        return '🛒 Shopify Integration: Connected\n📦 Products: 0\n📋 Orders: 0\n💰 Revenue: CHF 0.00';
        
      case '/orders':
        return '📋 Recent Orders:\n#1001 - Demo Order 1 - CHF 99.99\n#1002 - Demo Order 2 - CHF 149.99';
        
      case '/products':
        return '📦 Products (5):\n• Demo Product 1 - CHF 99.99\n• Demo Product 2 - CHF 149.99\n• Demo Product 3 - CHF 199.99';
        
      case '/revenue':
        return '💰 Revenue Overview:\n📅 Today: CHF 0.00\n📈 This Week: CHF 0.00\n📊 This Month: CHF 0.00';
        
      case '/health':
        return '🏥 System Health:\n🟢 Bot: Healthy\n🟢 Agents: 4 Active\n🟢 Memory: 45%\n🟢 CPU: 12%';
        
      default:
        return '❓ Unknown command. Use /help to see available commands.';
    }
  }

  private getRandomCommand(): string {
    const commands = ['/status', '/shopify', '/orders', '/products', '/revenue', '/health'];
    return commands[Math.floor(Math.random() * commands.length)];
  }

  private async sendMessage(chatId: number, text: string): Promise<void> {
    this.logger.info(`Sending message to chat ${chatId}: ${text.substring(0, 50)}...`);
    
    // In real implementation, this would use the Telegram Bot API
    // For demo, we just log the message
    this.emit('message:sent', { chatId, text });
  }

  async sendNotification(userId: string, message: string): Promise<void> {
    if (!this.connected || !this.config) {
      this.logger.warn('Cannot send notification: bot not connected');
      return;
    }
    
    await this.sendMessage(parseInt(userId), message);
  }

  async broadcast(message: string): Promise<void> {
    if (!this.connected || !this.config) {
      this.logger.warn('Cannot broadcast: bot not connected');
      return;
    }
    
    for (const userId of this.config.allowedUsers) {
      await this.sendMessage(parseInt(userId), message);
    }
    
    this.logger.info(`Broadcast message sent to ${this.config.allowedUsers.length} users`);
  }
}
