// ============================================
// RUDIBOT OPENCLAW PYTHON-NODE.JS BRIDGE
// Connects Python OpenClaw Gateway to Node.js
// ============================================

import { OpenClawClient } from './openclaw-client.js';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

export interface BridgeConfig {
  pythonPath?: string;
  gatewayPath?: string;
  gatewayPort?: number;
}

export class OpenClawBridge {
  private pythonProcess: ChildProcess | null = null;
  private client: OpenClawClient;
  private config: Required<BridgeConfig>;

  constructor(config: BridgeConfig = {}) {
    this.config = {
      pythonPath: config.pythonPath || process.env.PYTHON_PATH || 'python3',
      gatewayPath: config.gatewayPath || process.env.OPENCLAW_GATEWAY_PATH || path.join(process.cwd(), '../rudibot-eternal'),
      gatewayPort: config.gatewayPort || 18789,
    };

    this.client = new OpenClawClient({
      url: `ws://127.0.0.1:${this.config.gatewayPort}`,
    });
  }

  async start(): Promise<void> {
    console.log('🐍 Starting Python OpenClaw Gateway...');

    this.pythonProcess = spawn(this.config.pythonPath, [
      path.join(this.config.gatewayPath, 'openclaw_gateway.py'),
      '--port', this.config.gatewayPort.toString(),
    ]);

    this.pythonProcess.stdout?.on('data', (data) => {
      console.log(`[OpenClaw] ${data.toString().trim()}`);
    });

    this.pythonProcess.stderr?.on('data', (data) => {
      console.error(`[OpenClaw Error] ${data.toString().trim()}`);
    });

    this.pythonProcess.on('close', (code) => {
      console.log(`[OpenClaw] Gateway exited with code ${code}`);
      this.pythonProcess = null;
    });

    // Wait for gateway to start
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Connect WebSocket client
    await this.client.connect();
  }

  async stop(): Promise<void> {
    console.log('🛑 Stopping OpenClaw Bridge...');

    this.client.disconnect();

    if (this.pythonProcess) {
      this.pythonProcess.kill('SIGTERM');
      this.pythonProcess = null;
    }
  }

  async chat(message: string, systemPrompt?: string): Promise<string> {
    return await this.client.complete(message, systemPrompt);
  }

  getClient(): OpenClawClient {
    return this.client;
  }

  isRunning(): boolean {
    return this.pythonProcess !== null && this.client.isConnected;
  }
}

// Singleton instance
let bridgeInstance: OpenClawBridge | null = null;

export function getOpenClawBridge(config?: BridgeConfig): OpenClawBridge {
  if (!bridgeInstance) {
    bridgeInstance = new OpenClawBridge(config);
  }
  return bridgeInstance;
}

export default OpenClawBridge;
