/**
 * RUDIBOT Multi-Agent Coordinator
 * Zentrale Koordination mehrerer Agenten mit Kommunikation, Task-Verteilung und Konfliktlösung
 */

const EventEmitter = require('events');
const crypto = require('crypto');

class AgentCoordinator extends EventEmitter {
  constructor(options = {}) {
    super();
    this.logger = options.logger || console;
    
    // Agent Registry
    this.agents = new Map();
    this.agentGroups = new Map();
    this.agentCapabilities = new Map();
    
    // Task Management
    this.taskQueue = [];
    this.activeTasks = new Map();
    this.completedTasks = [];
    this.failedTasks = [];
    
    // Communication
    this.messageBus = new Map();
    this.agentChannels = new Map();
    this.broadcastHistory = [];
    
    // Coordination
    this.activeCollaborations = new Map();
    this.resourceLocks = new Map();
    this.conflictResolution = new Map();
    
    // Performance Tracking
    this.agentMetrics = new Map();
    this.collaborationHistory = [];
    
    this.initializeCoordinator();
  }

  // Agent Registration
  registerAgent(agentConfig) {
    const {
      id,
      name,
      type,
      capabilities = [],
      priority = 'normal',
      maxConcurrentTasks = 5,
      dependencies = [],
      group = 'default'
    } = agentConfig;

    const agent = {
      id,
      name,
      type,
      capabilities,
      priority,
      maxConcurrentTasks,
      dependencies,
      group,
      status: 'idle',
      currentTasks: new Set(),
      completedTasks: 0,
      failedTasks: 0,
      lastActivity: new Date(),
      metrics: {
        taskCompletionTime: [],
        successRate: 1.0,
        resourceUsage: {},
        collaborationScore: 0
      }
    };

    this.agents.set(id, agent);
    this.agentCapabilities.set(id, capabilities);
    
    // Group assignment
    if (!this.agentGroups.has(group)) {
      this.agentGroups.set(group, new Set());
    }
    this.agentGroups.get(group).add(id);

    // Communication channel
    this.agentChannels.set(id, {
      inbox: [],
      outbox: [],
      subscriptions: new Set()
    });

    this.logger.info(`🤖 Agent registered: ${name} (${type}) in group ${group}`);
    this.emit('agent:registered', agent);

    return agent;
  }

  // Task Creation and Distribution
  async createTask(taskConfig) {
    const {
      id = this.generateTaskId(),
      type,
      priority = 'normal',
      payload,
      requirements = [],
      deadline,
      dependencies = [],
      collaboration = null,
      retryCount = 3
    } = taskConfig;

    const task = {
      id,
      type,
      priority,
      payload,
      requirements,
      deadline,
      dependencies,
      collaboration,
      retryCount,
      status: 'pending',
      createdAt: new Date(),
      assignedAgent: null,
      collaborators: new Set(),
      progress: 0,
      logs: []
    };

    this.taskQueue.push(task);
    this.logger.info(`📋 Task created: ${type} (${id})`);
    this.emit('task:created', task);

    // Try to assign immediately
    await this.assignTask(task);

    return task;
  }

  // Intelligent Task Assignment
  async assignTask(task) {
    const suitableAgents = this.findSuitableAgents(task);
    
    if (suitableAgents.length === 0) {
      this.logger.warn(`⚠️ No suitable agents found for task ${task.id}`);
      task.status = 'unassigned';
      return false;
    }

    // Select best agent based on multiple factors
    const bestAgent = this.selectBestAgent(suitableAgents, task);
    
    if (task.collaboration) {
      return await this.assignCollaborativeTask(task, bestAgent);
    } else {
      return await this.assignSingleTask(task, bestAgent);
    }
  }

  findSuitableAgents(task) {
    const suitable = [];

    for (const [agentId, agent] of this.agents) {
      // Check capabilities
      const hasCapabilities = task.requirements.every(req => 
        agent.capabilities.includes(req)
      );

      // Check availability
      const isAvailable = agent.currentTasks.size < agent.maxConcurrentTasks;
      const isNotFailed = agent.status !== 'failed';

      // Check dependencies
      const dependenciesMet = task.dependencies.every(dep => 
        this.completedTasks.some(t => t.id === dep)
      );

      if (hasCapabilities && isAvailable && isNotFailed && dependenciesMet) {
        suitable.push({
          agent,
          score: this.calculateAgentScore(agent, task)
        });
      }
    }

    return suitable.sort((a, b) => b.score - a.score);
  }

  calculateAgentScore(agent, task) {
    let score = 0;

    // Priority matching
    if (agent.priority === task.priority) score += 10;
    
    // Capability matching
    const matchingCapabilities = task.requirements.filter(req => 
      agent.capabilities.includes(req)
    ).length;
    score += matchingCapabilities * 5;

    // Performance metrics
    score += agent.metrics.successRate * 10;
    
    // Current load (lower is better)
    score += (agent.maxConcurrentTasks - agent.currentTasks.size) * 2;

    // Recent activity (more recent is better)
    const hoursSinceActivity = (Date.now() - agent.lastActivity) / (1000 * 60 * 60);
    score += Math.max(0, 10 - hoursSinceActivity);

    return score;
  }

  selectBestAgent(suitableAgents, task) {
    // Weighted selection considering multiple factors
    const weights = {
      score: 0.6,
      priority: 0.2,
      availability: 0.2
    };

    let bestAgent = suitableAgents[0];
    let bestScore = 0;

    for (const candidate of suitableAgents) {
      const score = 
        candidate.score * weights.score +
        (candidate.agent.priority === task.priority ? 10 : 0) * weights.priority +
        (candidate.agent.maxConcurrentTasks - candidate.agent.currentTasks.size) * weights.availability;

      if (score > bestScore) {
        bestScore = score;
        bestAgent = candidate.agent;
      }
    }

    return bestAgent;
  }

  // Single Task Assignment
  async assignSingleTask(task, agent) {
    task.assignedAgent = agent.id;
    task.status = 'assigned';
    agent.currentTasks.add(task.id);
    agent.status = 'busy';
    agent.lastActivity = new Date();

    this.activeTasks.set(task.id, task);
    
    this.logger.info(`🎯 Task ${task.id} assigned to agent ${agent.name}`);
    this.emit('task:assigned', { task, agent });

    // Notify agent
    await this.sendMessage(agent.id, {
      type: 'task_assignment',
      taskId: task.id,
      task: task
    });

    return true;
  }

  // Collaborative Task Assignment
  async assignCollaborativeTask(task, primaryAgent) {
    const { collaboration } = task;
    const collaborators = [];

    // Find additional agents for collaboration
    for (const requiredCapability of collaboration.requiredCapabilities) {
      if (requiredCapability !== primaryAgent.capabilities[0]) {
        const additionalAgents = this.findSuitableAgents({
          ...task,
          requirements: [requiredCapability]
        });

        if (additionalAgents.length > 0) {
          collaborators.push(additionalAgents[0].agent);
        }
      }
    }

    if (collaborators.length === 0) {
      this.logger.warn(`⚠️ No collaborators found for task ${task.id}`);
      return false;
    }

    // Set up collaboration
    task.assignedAgent = primaryAgent.id;
    task.collaborators = new Set([primaryAgent.id, ...collaborators.map(a => a.id)]);
    task.status = 'collaborating';

    const collaborationId = this.generateCollaborationId();
    this.activeCollaborations.set(collaborationId, {
      id: collaborationId,
      taskId: task.id,
      primaryAgent: primaryAgent.id,
      collaborators: task.collaborators,
      status: 'active',
      startTime: new Date(),
      communication: []
    });

    // Assign to all collaborators
    for (const agent of [primaryAgent, ...collaborators]) {
      agent.currentTasks.add(task.id);
      agent.status = 'busy';
      agent.lastActivity = new Date();

      await this.sendMessage(agent.id, {
        type: 'collaboration_invite',
        collaborationId,
        taskId: task.id,
        role: agent.id === primaryAgent.id ? 'primary' : 'collaborator',
        task
      });
    }

    this.logger.info(`🤝 Collaboration started for task ${task.id} with ${task.collaborators.size} agents`);
    this.emit('collaboration:started', { task, collaborationId, agents: task.collaborators });

    return true;
  }

  // Agent Communication
  async sendMessage(targetAgentId, message) {
    const channel = this.agentChannels.get(targetAgentId);
    
    if (!channel) {
      throw new Error(`Agent ${targetAgentId} not found`);
    }

    const enrichedMessage = {
      id: this.generateMessageId(),
      timestamp: new Date(),
      from: 'coordinator',
      to: targetAgentId,
      ...message
    };

    channel.inbox.push(enrichedMessage);
    
    this.logger.debug(`📨 Message sent to ${targetAgentId}: ${message.type}`);
    this.emit('message:sent', enrichedMessage);

    return enrichedMessage;
  }

  async broadcastMessage(groupId, message) {
    const group = this.agentGroups.get(groupId);
    
    if (!group) {
      throw new Error(`Agent group ${groupId} not found`);
    }

    const enrichedMessage = {
      id: this.generateMessageId(),
      timestamp: new Date(),
      from: 'coordinator',
      to: 'group',
      groupId,
      ...message
    };

    for (const agentId of group) {
      const channel = this.agentChannels.get(agentId);
      if (channel) {
        channel.inbox.push({...enrichedMessage, to: agentId});
      }
    }

    this.broadcastHistory.push(enrichedMessage);
    this.logger.info(`📢 Broadcast to group ${groupId}: ${message.type}`);
    this.emit('message:broadcast', enrichedMessage);

    return enrichedMessage;
  }

  // Task Progress Tracking
  updateTaskProgress(taskId, progress, agentId) {
    const task = this.activeTasks.get(taskId);
    
    if (!task) {
      this.logger.warn(`Task ${taskId} not found for progress update`);
      return false;
    }

    task.progress = progress;
    task.logs.push({
      timestamp: new Date(),
      agentId,
      progress,
      message: `Progress updated to ${progress}%`
    });

    this.emit('task:progress', { task, progress, agentId });

    // Check if task is complete
    if (progress >= 100) {
      return this.completeTask(taskId, agentId);
    }

    return true;
  }

  // Task Completion
  async completeTask(taskId, agentId) {
    const task = this.activeTasks.get(taskId);
    
    if (!task) {
      this.logger.warn(`Task ${taskId} not found for completion`);
      return false;
    }

    task.status = 'completed';
    task.completedAt = new Date();
    
    // Update agent metrics
    const agent = this.agents.get(agentId);
    if (agent) {
      agent.currentTasks.delete(taskId);
      agent.completedTasks++;
      agent.status = agent.currentTasks.size > 0 ? 'busy' : 'idle';
      agent.lastActivity = new Date();
      
      // Update metrics
      const completionTime = task.completedAt - task.createdAt;
      agent.metrics.taskCompletionTime.push(completionTime);
      agent.metrics.successRate = agent.completedTasks / (agent.completedTasks + agent.failedTasks);
    }

    // Move to completed
    this.activeTasks.delete(taskId);
    this.completedTasks.push(task);

    // Handle collaboration cleanup
    if (task.collaborators && task.collaborators.size > 1) {
      await this.endCollaboration(taskId);
    }

    this.logger.info(`✅ Task ${taskId} completed by agent ${agentId}`);
    this.emit('task:completed', { task, agentId });

    // Process next tasks in queue
    await this.processTaskQueue();

    return true;
  }

  // Task Failure Handling
  async failTask(taskId, agentId, error, retryable = true) {
    const task = this.activeTasks.get(taskId);
    
    if (!task) {
      this.logger.warn(`Task ${taskId} not found for failure handling`);
      return false;
    }

    task.status = 'failed';
    task.error = error;
    task.failedAt = new Date();

    // Update agent metrics
    const agent = this.agents.get(agentId);
    if (agent) {
      agent.currentTasks.delete(taskId);
      agent.failedTasks++;
      agent.status = agent.currentTasks.size > 0 ? 'busy' : 'idle';
      agent.lastActivity = new Date();
      agent.metrics.successRate = agent.completedTasks / (agent.completedTasks + agent.failedTasks);
    }

    // Retry logic
    if (retryable && task.retryCount > 0) {
      task.retryCount--;
      task.status = 'pending';
      task.assignedAgent = null;
      task.collaborators.clear();
      
      this.taskQueue.push(task);
      this.logger.info(`🔄 Task ${taskId} queued for retry (${task.retryCount} attempts left)`);
    } else {
      this.activeTasks.delete(taskId);
      this.failedTasks.push(task);
      
      // Handle collaboration cleanup
      if (task.collaborators && task.collaborators.size > 1) {
        await this.endCollaboration(taskId);
      }
    }

    this.emit('task:failed', { task, agentId, error });

    return true;
  }

  // Collaboration Management
  async endCollaboration(taskId) {
    for (const [collabId, collaboration] of this.activeCollaborations) {
      if (collaboration.taskId === taskId) {
        collaboration.status = 'completed';
        collaboration.endTime = new Date();
        
        // Update collaboration metrics
        for (const agentId of collaboration.collaborators) {
          const agent = this.agents.get(agentId);
          if (agent) {
            agent.metrics.collaborationScore += 1;
          }
        }
        
        this.collaborationHistory.push(collaboration);
        this.activeCollaborations.delete(collabId);
        
        this.logger.info(`🤝 Collaboration ${collabId} ended for task ${taskId}`);
        this.emit('collaboration:ended', { collaboration, taskId });
        
        break;
      }
    }
  }

  // Task Queue Processing
  async processTaskQueue() {
    while (this.taskQueue.length > 0) {
      const task = this.taskQueue.shift();
      
      if (task.status === 'pending') {
        await this.assignTask(task);
      }
    }
  }

  // Resource Management
  async acquireResource(resourceId, agentId, timeout = 30000) {
    if (this.resourceLocks.has(resourceId)) {
      const lock = this.resourceLocks.get(resourceId);
      
      if (lock.agentId !== agentId) {
        // Resource is locked by another agent
        return { success: false, reason: 'Resource locked by another agent' };
      }
      
      // Agent already has the lock
      return { success: true, lock };
    }

    // Acquire new lock
    const lock = {
      resourceId,
      agentId,
      acquiredAt: new Date(),
      timeout,
      expiresAt: new Date(Date.now() + timeout)
    };

    this.resourceLocks.set(resourceId, lock);
    
    this.logger.debug(`🔒 Resource ${resourceId} locked by agent ${agentId}`);
    this.emit('resource:acquired', { resourceId, agentId, lock });

    return { success: true, lock };
  }

  async releaseResource(resourceId, agentId) {
    const lock = this.resourceLocks.get(resourceId);
    
    if (!lock || lock.agentId !== agentId) {
      return { success: false, reason: 'No lock found or not owned by agent' };
    }

    this.resourceLocks.delete(resourceId);
    
    this.logger.debug(`🔓 Resource ${resourceId} released by agent ${agentId}`);
    this.emit('resource:released', { resourceId, agentId });

    return { success: true };
  }

  // Conflict Resolution
  async resolveConflict(conflict) {
    const { type, agents, resource, priority } = conflict;
    
    this.logger.warn(`⚔️ Conflict detected: ${type} between agents ${Array.from(agents).join(', ')}`);

    let resolution;

    switch (type) {
      case 'resource_contention':
        resolution = await this.resolveResourceContention(agents, resource, priority);
        break;
      
      case 'task_priority':
        resolution = await this.resolveTaskPriorityConflict(agents, priority);
        break;
      
      case 'communication_failure':
        resolution = await this.resolveCommunicationFailure(agents);
        break;
      
      default:
        resolution = { action: 'escalate', reason: 'Unknown conflict type' };
    }

    this.conflictResolution.set(conflict.id, {
      ...conflict,
      resolution,
      resolvedAt: new Date()
    });

    this.emit('conflict:resolved', { conflict, resolution });
    
    return resolution;
  }

  async resolveResourceContention(agents, resource, priority) {
    // Priority-based resolution
    const prioritizedAgents = Array.from(agents).sort((a, b) => {
      const agentA = this.agents.get(a);
      const agentB = this.agents.get(b);
      
      if (agentA.priority !== agentB.priority) {
        return agentB.priority === 'high' ? 1 : -1;
      }
      
      return agentB.metrics.successRate - agentA.metrics.successRate;
    });

    const winner = prioritizedAgents[0];
    const losers = prioritizedAgents.slice(1);

    // Force release from losers
    for (const loserId of losers) {
      await this.releaseResource(resource, loserId);
      
      await this.sendMessage(loserId, {
        type: 'conflict_resolution',
        conflict: 'resource_contention',
        action: 'resource_released',
        resource,
        reason: 'Priority-based resolution'
      });
    }

    return {
      action: 'priority_assignment',
      winner,
      losers,
      reason: 'Priority and performance-based resolution'
    };
  }

  // Status and Monitoring
  getCoordinatorStatus() {
    return {
      agents: Array.from(this.agents.entries()).map(([id, agent]) => ({
        id,
        name: agent.name,
        type: agent.type,
        status: agent.status,
        currentTasks: agent.currentTasks.size,
        completedTasks: agent.completedTasks,
        failedTasks: agent.failedTasks,
        successRate: agent.metrics.successRate,
        lastActivity: agent.lastActivity
      })),
      tasks: {
        pending: this.taskQueue.length,
        active: this.activeTasks.size,
        completed: this.completedTasks.length,
        failed: this.failedTasks.length
      },
      collaborations: {
        active: this.activeCollaborations.size,
        history: this.collaborationHistory.length
      },
      resources: {
        locked: this.resourceLocks.size
      },
      conflicts: {
        resolved: this.conflictResolution.size
      }
    };
  }

  // Utility Functions
  generateTaskId() {
    return `task_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  }

  generateCollaborationId() {
    return `collab_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  }

  generateMessageId() {
    return `msg_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  }

  initializeCoordinator() {
    // Start periodic cleanup
    setInterval(() => {
      this.cleanupExpiredLocks();
      this.processTaskQueue();
    }, 5000);

    this.logger.info('🧠 Agent Coordinator initialized');
    this.emit('coordinator:initialized');
  }

  cleanupExpiredLocks() {
    const now = new Date();
    
    for (const [resourceId, lock] of this.resourceLocks) {
      if (now > lock.expiresAt) {
        this.resourceLocks.delete(resourceId);
        
        this.logger.warn(`⏰ Resource lock expired: ${resourceId} (was held by ${lock.agentId})`);
        this.emit('resource:lock_expired', { resourceId, lock });
      }
    }
  }
}

module.exports = { AgentCoordinator };
