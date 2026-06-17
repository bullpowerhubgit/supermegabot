import { EventEmitter } from 'events';
import { Logger } from '../utils/Logger';

export interface Agent {
  id: string;
  name: string;
  type: 'shopify' | 'telegram' | 'ai' | 'monitoring';
  status: 'idle' | 'running' | 'error';
  capabilities: string[];
}

export interface AgentStatus {
  total: number;
  active: number;
  idle: number;
  error: number;
  agents: Agent[];
}

export class AgentOrchestrator extends EventEmitter {
  private logger: Logger;
  private agents: Map<string, Agent> = new Map();
  private initialized: boolean = false;

  constructor() {
    super();
    this.logger = new Logger('AgentOrchestrator');
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Agent Orchestrator...');
    
    // Register default agents
    this.registerAgent({
      id: 'shopify-automator',
      name: 'Shopify Automator',
      type: 'shopify',
      status: 'idle',
      capabilities: ['product_management', 'order_processing', 'inventory_sync']
    });
    
    this.registerAgent({
      id: 'telegram-bot',
      name: 'Telegram Bot',
      type: 'telegram',
      status: 'idle',
      capabilities: ['message_handling', 'command_processing', 'notifications']
    });
    
    this.registerAgent({
      id: 'ai-advisor',
      name: 'AI Advisor',
      type: 'ai',
      status: 'idle',
      capabilities: ['price_optimization', 'demand_forecasting', 'recommendations']
    });
    
    this.registerAgent({
      id: 'system-monitor',
      name: 'System Monitor',
      type: 'monitoring',
      status: 'idle',
      capabilities: ['performance_tracking', 'health_checks', 'alerting']
    });
    
    this.initialized = true;
    this.logger.info('Agent Orchestrator initialized successfully');
    this.emit('initialized');
  }

  async shutdown(): Promise<void> {
    this.logger.info('Shutting down Agent Orchestrator...');
    
    // Stop all active agents
    for (const agent of this.agents.values()) {
      if (agent.status === 'running') {
        await this.stopAgent(agent.id);
      }
    }
    
    this.initialized = false;
    this.logger.info('Agent Orchestrator shut down successfully');
    this.emit('shutdown');
  }

  registerAgent(agent: Agent): void {
    this.agents.set(agent.id, agent);
    this.logger.info(`Agent registered: ${agent.name} (${agent.id})`);
    this.emit('agent:registered', agent);
  }

  async startAgent(agentId: string): Promise<void> {
    const agent = this.agents.get(agentId);
    if (!agent) {
      throw new Error(`Agent not found: ${agentId}`);
    }
    
    if (agent.status === 'running') {
      this.logger.warn(`Agent already running: ${agentId}`);
      return;
    }
    
    agent.status = 'running';
    this.logger.info(`Agent started: ${agent.name}`);
    this.emit('agent:started', agent);
  }

  async stopAgent(agentId: string): Promise<void> {
    const agent = this.agents.get(agentId);
    if (!agent) {
      throw new Error(`Agent not found: ${agentId}`);
    }
    
    agent.status = 'idle';
    this.logger.info(`Agent stopped: ${agent.name}`);
    this.emit('agent:stopped', agent);
  }

  async executeAgent(agentId: string, command: string, parameters: any = {}): Promise<any> {
    const agent = this.agents.get(agentId);
    if (!agent) {
      throw new Error(`Agent not found: ${agentId}`);
    }
    
    if (agent.status !== 'running') {
      await this.startAgent(agentId);
    }
    
    this.logger.info(`Executing command on agent ${agent.name}: ${command}`);
    
    // Simulate agent execution
    const result = {
      agentId,
      command,
      parameters,
      result: `Executed ${command} successfully`,
      timestamp: new Date().toISOString()
    };
    
    this.emit('agent:executed', { agent, command, result });
    return result;
  }

  getStatus(): AgentStatus {
    const agents = Array.from(this.agents.values());
    
    return {
      total: agents.length,
      active: agents.filter(a => a.status === 'running').length,
      idle: agents.filter(a => a.status === 'idle').length,
      error: agents.filter(a => a.status === 'error').length,
      agents: [...agents]
    };
  }

  getAgentStatus(): AgentStatus {
    return this.getStatus();
  }

  getAgent(agentId: string): Agent | undefined {
    return this.agents.get(agentId);
  }

  getAllAgents(): Agent[] {
    return Array.from(this.agents.values());
  }
}
