/**
 * KIVO Layer - Intent, Sprache, Command Routing, LLM-Fallback
 * Gehirn von RUDIBOT: Intentionserkennung und Befehlsverarbeitung
 */

const EventEmitter = require('events');

class KIVOLayer extends EventEmitter {
  constructor(options = {}) {
    super();
    this.logger = options.logger || console;
    this.orchestrator = options.orchestrator || null;
    
    // Language Processing
    this.languageProcessor = new LanguageProcessor();
    this.intentClassifier = new IntentClassifier();
    this.commandRouter = new CommandRouter();
    
    // Fallback Systems
    this.llmFallback = new LLMFallback(options.llmConfig || {});
    this.patternMatcher = new PatternMatcher();
    
    // Command Registry
    this.commands = new Map();
    this.intents = new Map();
    this.patterns = new Map();
    
    // Session Management
    this.sessions = new Map();
    
    this.initializeCommands();
  }

  // Initialize Built-in Commands
  initializeCommands() {
    // System Commands
    this.registerCommand('status', {
      intent: 'system_status',
      handler: this.handleStatusCommand.bind(this),
      description: 'System status anzeigen',
      examples: ['status', 'system status', 'wie geht es dem system?']
    });

    this.registerCommand('help', {
      intent: 'help',
      handler: this.handleHelpCommand.bind(this),
      description: 'Hilfe anzeigen',
      examples: ['help', 'hilfe', 'was kannst du?']
    });

    // Job Commands
    this.registerCommand('run_job', {
      intent: 'execute_job',
      handler: this.handleRunJobCommand.bind(this),
      description: 'Job ausführen',
      examples: ['run job sync_orders', 'starte job calculate_revenue', 'führe job aus']
    });

    this.registerCommand('list_jobs', {
      intent: 'list_jobs',
      handler: this.handleListJobsCommand.bind(this),
      description: 'Jobs auflisten',
      examples: ['list jobs', 'zeige jobs', 'welche jobs gibt es?']
    });

    // Approval Commands
    this.registerCommand('approve', {
      intent: 'approve_request',
      handler: this.handleApproveCommand.bind(this),
      description: 'Approval erteilen',
      examples: ['approve abc123', 'genehmige xyz789', 'approve request']
    });

    this.registerCommand('reject', {
      intent: 'reject_request',
      handler: this.handleRejectCommand.bind(this),
      description: 'Approval ablehnen',
      examples: ['reject abc123', 'lehne ab xyz789', 'reject request']
    });

    // Query Commands
    this.registerCommand('query', {
      intent: 'query_data',
      handler: this.handleQueryCommand.bind(this),
      description: 'Daten abfragen',
      examples: ['query orders today', 'zeige revenue letzte woche', 'abfrage daten']
    });

    // Security Commands
    this.registerCommand('security_scan', {
      intent: 'security_scan',
      handler: this.handleSecurityScanCommand.bind(this),
      description: 'Security-Scan durchführen',
      examples: ['security scan', 'scanne system', 'sicherheitscheck']
    });

    // Finance Commands
    this.registerCommand('finance_report', {
      intent: 'finance_report',
      handler: this.handleFinanceReportCommand.bind(this),
      description: 'Finanzbericht erstellen',
      examples: ['finance report', 'finanzbericht', 'revenue anzeigen']
    });

    this.logger.info('🧠 KIVO Layer Commands initialisiert');
  }

  // Main Processing Entry Point
  async processInput(input, context = {}) {
    const sessionId = context.sessionId || 'default';
    const session = this.getOrCreateSession(sessionId);
    
    try {
      // Input preprocessing
      const processedInput = this.languageProcessor.preprocess(input);
      
      // Intent classification
      const intent = await this.classifyIntent(processedInput, session);
      
      // Command routing
      const command = this.routeCommand(intent, processedInput);
      
      // Execute command
      const result = await this.executeCommand(command, processedInput, context, session);
      
      // Update session
      this.updateSession(session, processedInput, intent, result);
      
      // Log interaction
      this.logInteraction(sessionId, processedInput, intent, result);
      
      return {
        success: true,
        intent,
        command: command.name,
        result,
        sessionId
      };
    } catch (error) {
      this.logger.error(`KIVO Processing Error:`, error);
      
      // Fallback zu LLM
      const fallbackResult = await this.llmFallback.process(input, error, context);
      
      return {
        success: false,
        error: error.message,
        fallback: fallbackResult,
        sessionId
      };
    }
  }

  // Intent Classification
  async classifyIntent(input, session) {
    // Pattern matching first
    const patternMatch = this.patternMatcher.match(input);
    if (patternMatch.confidence > 0.8) {
      return {
        intent: patternMatch.intent,
        confidence: patternMatch.confidence,
        method: 'pattern',
        entities: patternMatch.entities
      };
    }

    // Machine learning classification
    const mlResult = await this.intentClassifier.classify(input, session);
    
    // Context-based enhancement
    const contextEnhanced = this.enhanceWithContext(mlResult, session);
    
    return contextEnhanced;
  }

  // Command Routing
  routeCommand(intent, input) {
    const command = this.commands.get(intent.intent);
    
    if (!command) {
      throw new Error(`Kein Command für Intent gefunden: ${intent.intent}`);
    }

    return {
      name: intent.intent,
      handler: command.handler,
      intent: intent,
      input: input,
      confidence: intent.confidence
    };
  }

  // Command Execution
  async executeCommand(command, input, context, session) {
    const startTime = Date.now();
    
    try {
      // Parameter extraction
      const parameters = this.extractParameters(command.intent, input);
      
      // Execute handler
      const result = await command.handler({
        input,
        parameters,
        context,
        session,
        intent: command.intent
      });
      
      const duration = Date.now() - startTime;
      
      return {
        ...result,
        execution: {
          duration,
          command: command.name,
          confidence: command.confidence
        }
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      
      throw new Error(`Command Execution fehlgeschlagen (${command.name}): ${error.message}`);
    }
  }

  // Command Handlers
  async handleStatusCommand({ context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const status = await this.orchestrator.getSystemStatus();
    
    return {
      message: '🤖 RUDIBOT System Status',
      status: 'ok',
      data: status,
      formatted: this.formatStatus(status)
    };
  }

  async handleHelpCommand({ context, session }) {
    const commands = Array.from(this.commands.entries()).map(([name, cmd]) => ({
      name,
      description: cmd.description,
      examples: cmd.examples
    }));

    return {
      message: '📚 RUDIBOT Commands',
      status: 'ok',
      data: commands,
      formatted: this.formatHelp(commands)
    };
  }

  async handleRunJobCommand({ input, parameters, context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const jobName = parameters.jobName || this.extractJobNameFromInput(input);
    
    if (!jobName) {
      return {
        message: 'Job Name erforderlich',
        status: 'error',
        examples: ['run job sync_orders', 'starte job calculate_revenue']
      };
    }

    try {
      const result = await this.orchestrator.executeJob(jobName, {
        triggeredBy: 'kivo',
        sessionId: session.id
      });
      
      return {
        message: `✅ Job ${jobName} gestartet`,
        status: 'ok',
        data: result
      };
    } catch (error) {
      return {
        message: `❌ Job ${jobName} fehlgeschlagen: ${error.message}`,
        status: 'error'
      };
    }
  }

  async handleListJobsCommand({ context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const jobs = [];
    
    for (const [moduleName, module] of this.orchestrator.moduleRegistry) {
      for (const [jobName, job] of module.jobs) {
        jobs.push({
          id: `${moduleName}.${jobName}`,
          name: jobName,
          module: moduleName,
          class: job.class,
          schedule: job.schedule,
          requiresApproval: job.requiresApproval,
          lastRun: job.lastRun,
          runCount: job.runCount,
          status: job.status
        });
      }
    }

    return {
      message: `📋 ${jobs.length} Jobs gefunden`,
      status: 'ok',
      data: jobs,
      formatted: this.formatJobs(jobs)
    };
  }

  async handleApproveCommand({ input, parameters, context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const approvalId = parameters.approvalId || this.extractApprovalIdFromInput(input);
    const approver = context.userId || 'user';
    
    if (!approvalId) {
      return {
        message: 'Approval ID erforderlich',
        status: 'error',
        examples: ['approve abc123', 'genehmige xyz789']
      };
    }

    try {
      const result = await this.orchestrator.approveJob(approvalId, approver);
      
      return {
        message: `✅ Approval ${approvalId} erteilt`,
        status: 'ok',
        data: result
      };
    } catch (error) {
      return {
        message: `❌ Approval ${approvalId} fehlgeschlagen: ${error.message}`,
        status: 'error'
      };
    }
  }

  async handleRejectCommand({ input, parameters, context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const approvalId = parameters.approvalId || this.extractApprovalIdFromInput(input);
    const approver = context.userId || 'user';
    const reason = parameters.reason || this.extractReasonFromInput(input);
    
    if (!approvalId) {
      return {
        message: 'Approval ID erforderlich',
        status: 'error',
        examples: ['reject abc123', 'lehne ab xyz789']
      };
    }

    try {
      const result = await this.orchestrator.rejectJob(approvalId, approver, reason);
      
      return {
        message: `❌ Approval ${approvalId} abgelehnt`,
        status: 'ok',
        data: result
      };
    } catch (error) {
      return {
        message: `❌ Reject ${approvalId} fehlgeschlagen: ${error.message}`,
        status: 'error'
      };
    }
  }

  async handleQueryCommand({ input, parameters, context, session }) {
    const query = parameters.query || input;
    
    try {
      // Query processing (Platzhalter)
      const result = await this.executeQuery(query, context);
      
      return {
        message: `📊 Query ausgeführt`,
        status: 'ok',
        data: result,
        formatted: this.formatQueryResult(result)
      };
    } catch (error) {
      return {
        message: `❌ Query fehlgeschlagen: ${error.message}`,
        status: 'error'
      };
    }
  }

  async handleSecurityScanCommand({ input, parameters, context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const scanType = parameters.type || 'quick';
    
    try {
      const result = await this.orchestrator.executeJob('security.deepscan_security', {
        type: scanType,
        triggeredBy: 'kivo',
        sessionId: session.id
      });
      
      return {
        message: `🔒 Security Scan (${scanType}) gestartet`,
        status: 'ok',
        data: result
      };
    } catch (error) {
      return {
        message: `❌ Security Scan fehlgeschlagen: ${error.message}`,
        status: 'error'
      };
    }
  }

  async handleFinanceReportCommand({ input, parameters, context, session }) {
    if (!this.orchestrator) {
      return {
        message: 'Orchestrator nicht verfügbar',
        status: 'error'
      };
    }

    const reportType = parameters.type || 'daily';
    
    try {
      const result = await this.orchestrator.executeJob('finance.cost_killer_report', {
        type: reportType,
        triggeredBy: 'kivo',
        sessionId: session.id
      });
      
      return {
        message: `💰 Finance Report (${reportType}) erstellt`,
        status: 'ok',
        data: result
      };
    } catch (error) {
      return {
        message: `❌ Finance Report fehlgeschlagen: ${error.message}`,
        status: 'error'
      };
    }
  }

  // Command Registration
  registerCommand(name, config) {
    this.commands.set(name, config);
    this.logger.info(`📝 Command registriert: ${name}`);
  }

  // Session Management
  getOrCreateSession(sessionId) {
    if (!this.sessions.has(sessionId)) {
      this.sessions.set(sessionId, {
        id: sessionId,
        createdAt: new Date(),
        lastActivity: new Date(),
        interactions: [],
        context: {}
      });
    }
    
    return this.sessions.get(sessionId);
  }

  updateSession(session, input, intent, result) {
    session.lastActivity = new Date();
    session.interactions.push({
      timestamp: new Date(),
      input,
      intent,
      result: result.success ? 'success' : 'error'
    });
    
    // Keep only last 50 interactions
    if (session.interactions.length > 50) {
      session.interactions = session.interactions.slice(-50);
    }
  }

  // Parameter Extraction
  extractParameters(intent, input) {
    const parameters = {};
    
    // Job Name extraction
    if (intent.intent === 'execute_job') {
      parameters.jobName = this.extractJobNameFromInput(input);
    }
    
    // Approval ID extraction
    if (intent.intent === 'approve_request' || intent.intent === 'reject_request') {
      parameters.approvalId = this.extractApprovalIdFromInput(input);
    }
    
    // Query extraction
    if (intent.intent === 'query_data') {
      parameters.query = this.extractQueryFromInput(input);
    }
    
    return parameters;
  }

  extractJobNameFromInput(input) {
    const patterns = [
      /run\s+job\s+(\w+)/i,
      /starte?\s+job\s+(\w+)/i,
      /führe?\s+job\s+(\w+)/i,
      /execute\s+(\w+)/i
    ];
    
    for (const pattern of patterns) {
      const match = input.match(pattern);
      if (match) {
        return match[1];
      }
    }
    
    return null;
  }

  extractApprovalIdFromInput(input) {
    const patterns = [
      /approve\s+(\w+)/i,
      /genehmige\s+(\w+)/i,
      /reject\s+(\w+)/i,
      /lehne\s+(\w+)\s+ab/i
    ];
    
    for (const pattern of patterns) {
      const match = input.match(pattern);
      if (match) {
        return match[1];
      }
    }
    
    return null;
  }

  extractReasonFromInput(input) {
    const patterns = [
      /reason:\s*(.+)/i,
      /grund:\s*(.+)/i,
      /weil\s+(.+)/i
    ];
    
    for (const pattern of patterns) {
      const match = input.match(pattern);
      if (match) {
        return match[1].trim();
      }
    }
    
    return null;
  }

  extractQueryFromInput(input) {
    // Remove command words and return the rest
    return input.replace(/^(query|abfrage|zeige|show)\s+/i, '').trim();
  }

  // Context Enhancement
  enhanceWithContext(intent, session) {
    // Enhance based on session history
    if (session.interactions.length > 0) {
      const lastInteraction = session.interactions[session.interactions.length - 1];
      
      // If user asks follow-up questions, maintain context
      if (intent.confidence < 0.7 && lastInteraction.intent) {
        intent.contextIntent = lastInteraction.intent;
        intent.confidence += 0.1;
      }
    }
    
    return intent;
  }

  // Formatting Functions
  formatStatus(status) {
    let formatted = '🤖 **RUDIBOT Status**\n\n';
    
    formatted += `**Module:** ${status.modules.length}\n`;
    formatted += `**Running Jobs:** ${status.runningJobs}\n`;
    formatted += `**Pending Approvals:** ${status.pendingApprovals}\n`;
    
    if (status.modules.length > 0) {
      formatted += '\n**Module Details:**\n';
      for (const module of status.modules) {
        formatted += `- ${module.name}: ${module.jobs} jobs\n`;
      }
    }
    
    return formatted;
  }

  formatHelp(commands) {
    let formatted = '📚 **RUDIBOT Commands**\n\n';
    
    for (const cmd of commands) {
      formatted += `**${cmd.name}**\n`;
      formatted += `  ${cmd.description}\n`;
      formatted += `  Examples: ${cmd.examples.join(', ')}\n\n`;
    }
    
    return formatted;
  }

  formatJobs(jobs) {
    let formatted = `📋 **${jobs.length} Jobs**\n\n`;
    
    // Group by module
    const byModule = {};
    for (const job of jobs) {
      if (!byModule[job.module]) {
        byModule[job.module] = [];
      }
      byModule[job.module].push(job);
    }
    
    for (const [module, moduleJobs] of Object.entries(byModule)) {
      formatted += `**${module}**\n`;
      for (const job of moduleJobs) {
        const status = job.lastRun ? `✅ (${job.runCount}x)` : '⏳';
        const approval = job.requiresApproval ? '🔒' : '';
        formatted += `  ${status} ${job.name} ${approval}\n`;
      }
      formatted += '\n';
    }
    
    return formatted;
  }

  formatQueryResult(result) {
    // TODO: Implementieren mit echtem Query-Formatting
    return `📊 Query Result: ${JSON.stringify(result, null, 2)}`;
  }

  // Query Execution (Platzhalter)
  async executeQuery(query, context) {
    // TODO: Implementieren mit echtem Query-System
    return {
      query,
      results: [],
      count: 0
    };
  }

  // Logging
  logInteraction(sessionId, input, intent, result) {
    this.logger.info(`🧠 KIVO Interaction [${sessionId}]:`, {
      input: input.substring(0, 100),
      intent: intent.intent,
      confidence: intent.confidence,
      success: result.success
    });
  }
}

// Supporting Classes

class LanguageProcessor {
  preprocess(input) {
    return input
      .toLowerCase()
      .trim()
      .replace(/[^\w\säöüß]/g, ' ') // Special chars für Deutsch
      .replace(/\s+/g, ' ')
      .trim();
  }
}

class IntentClassifier {
  async classify(input, session) {
    // TODO: Implementieren mit echtem ML-Model
    const intents = [
      { intent: 'system_status', confidence: 0.1 },
      { intent: 'execute_job', confidence: 0.1 },
      { intent: 'list_jobs', confidence: 0.1 },
      { intent: 'approve_request', confidence: 0.1 },
      { intent: 'reject_request', confidence: 0.1 },
      { intent: 'query_data', confidence: 0.1 },
      { intent: 'security_scan', confidence: 0.1 },
      { intent: 'finance_report', confidence: 0.1 },
      { intent: 'help', confidence: 0.1 }
    ];

    // Simple keyword-based classification
    if (input.includes('status') || input.includes('wie geht')) {
      return { intent: 'system_status', confidence: 0.9, entities: {} };
    }
    
    if (input.includes('job') || input.includes('starte') || input.includes('run')) {
      return { intent: 'execute_job', confidence: 0.8, entities: {} };
    }
    
    if (input.includes('hilfe') || input.includes('help') || input.includes('was kannst')) {
      return { intent: 'help', confidence: 0.9, entities: {} };
    }

    // Return highest confidence
    return intents.reduce((best, current) => 
      current.confidence > best.confidence ? current : best
    );
  }
}

class CommandRouter {
  route(intent, input) {
    return {
      command: intent.intent,
      confidence: intent.confidence
    };
  }
}

class PatternMatcher {
  constructor() {
    this.patterns = [
      {
        pattern: /status|wie geht/i,
        intent: 'system_status',
        confidence: 0.9
      },
      {
        pattern: /run\s+job|starte\s+job/i,
        intent: 'execute_job',
        confidence: 0.8
      },
      {
        pattern: /hilfe|help|was kannst/i,
        intent: 'help',
        confidence: 0.9
      },
      {
        pattern: /approve|genehmige/i,
        intent: 'approve_request',
        confidence: 0.8
      },
      {
        pattern: /reject|lehne\s+ab/i,
        intent: 'reject_request',
        confidence: 0.8
      }
    ];
  }

  match(input) {
    for (const pattern of this.patterns) {
      if (pattern.pattern.test(input)) {
        return {
          intent: pattern.intent,
          confidence: pattern.confidence,
          entities: {}
        };
      }
    }
    
    return { intent: null, confidence: 0, entities: {} };
  }
}

class LLMFallback {
  constructor(config) {
    this.config = config;
  }

  async process(input, error, context) {
    // TODO: Implementieren mit echtem LLM (OpenAI, Anthropic, etc.)
    return {
      fallback: true,
      message: `Ich konnte deine Anfrage nicht verstehen. Fehler: ${error.message}`,
      suggestions: [
        'Versuche "help" für verfügbare Commands',
        'Nutze "status" für System-Status',
        'Frage nach "list jobs" für alle Jobs'
      ]
    };
  }
}

module.exports = KIVOLayer;
