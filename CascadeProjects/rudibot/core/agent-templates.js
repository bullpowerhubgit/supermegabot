/**
 * RUDIBOT Agent Templates
 * Vordefinierte Agent-Typen für verschiedene Business-Bereiche
 */

class AgentTemplate {
  constructor(config) {
    this.id = config.id;
    this.name = config.name;
    this.type = config.type;
    this.description = config.description;
    this.capabilities = config.capabilities;
    this.defaultPriority = config.priority || 'normal';
    this.maxConcurrentTasks = config.maxConcurrentTasks || 5;
    this.dependencies = config.dependencies || [];
    this.group = config.group || 'default';
    this.communicationStyle = config.communicationStyle || 'formal';
    this.decisionMaking = config.decisionMaking || 'autonomous';
    this.collaborationPreference = config.collaborationPreference || 'selective';
  }

  createAgent(customConfig = {}) {
    return {
      ...this,
      ...customConfig,
      id: customConfig.id || this.id,
      name: customConfig.name || this.name
    };
  }
}

// Commerce Agents
const ShopifyAgent = new AgentTemplate({
  id: 'shopify-agent',
  name: 'Shopify Commerce Agent',
  type: 'commerce',
  description: 'Verwaltet Shopify-Shop, Bestellungen, Produkte und Kunden',
  capabilities: [
    'shopify_orders_read',
    'shopify_orders_write', 
    'shopify_products_read',
    'shopify_products_write',
    'shopify_customers_read',
    'shopify_inventory_read',
    'order_processing',
    'product_management',
    'customer_service'
  ],
  priority: 'high',
  maxConcurrentTasks: 10,
  group: 'commerce',
  communicationStyle: 'professional',
  decisionMaking: 'semi_autonomous',
  collaborationPreference: 'active'
});

const PrintifyAgent = new AgentTemplate({
  id: 'printify-agent',
  name: 'Printify Production Agent',
  type: 'production',
  description: 'Managt Print-on-Demand Produktion über Printify',
  capabilities: [
    'printify_products_read',
    'printify_products_write',
    'printify_orders_create',
    'production_tracking',
    'quality_control',
    'inventory_sync'
  ],
  priority: 'medium',
  maxConcurrentTasks: 8,
  group: 'production',
  communicationStyle: 'efficient',
  decisionMaking: 'autonomous',
  collaborationPreference: 'reactive'
});

// Finance Agents
const FinanceAgent = new AgentTemplate({
  id: 'finance-agent',
  name: 'Finance Management Agent',
  type: 'finance',
  description: 'Überwacht Finanzen, Kosten, Einnahmen und Budgets',
  capabilities: [
    'revenue_tracking',
    'expense_monitoring',
    'budget_management',
    'cost_analysis',
    'profit_calculation',
    'financial_reporting',
    'payment_processing'
  ],
  priority: 'high',
  maxConcurrentTasks: 6,
  group: 'finance',
  communicationStyle: 'analytical',
  decisionMaking: 'cautious',
  collaborationPreference: 'strategic'
});

const CostKillerAgent = new AgentTemplate({
  id: 'cost-killer-agent',
  name: 'Cost Optimization Agent',
  type: 'optimization',
  description: 'Identifiziert und eliminiert unnötige Kosten',
  capabilities: [
    'subscription_analysis',
    'cost_audit',
    'service_evaluation',
    'cancellation_planning',
    'negotiation_support',
    'savings_tracking'
  ],
  priority: 'medium',
  maxConcurrentTasks: 4,
  group: 'finance',
  communicationStyle: 'direct',
  decisionMaking: 'aggressive',
  collaborationPreference: 'selective'
});

// Customer Service Agents
const SupportAgent = new AgentTemplate({
  id: 'support-agent',
  name: 'Customer Support Agent',
  type: 'support',
  description: 'Behandelt Kundenanfragen und Support-Fälle',
  capabilities: [
    'ticket_management',
    'customer_communication',
    'problem_resolution',
    'faq_handling',
    'escalation_management',
    'satisfaction_tracking'
  ],
  priority: 'high',
  maxConcurrentTasks: 12,
  group: 'support',
  communicationStyle: 'empathetic',
  decisionMaking: 'scripted_with_flexibility',
  collaborationPreference: 'collaborative'
});

const WISMOAgent = new AgentTemplate({
  id: 'wismo-agent',
  name: 'WISMO Specialist Agent',
  type: 'support',
  description: 'Spezialist für "Where Is My Order" Anfragen',
  capabilities: [
    'order_tracking',
    'shipping_status',
    'delivery_estimates',
    'carrier_communication',
    'customer_updates',
    'exception_handling'
  ],
  priority: 'high',
  maxConcurrentTasks: 15,
  group: 'support',
  communicationStyle: 'reassuring',
  decisionMaking: 'procedural',
  collaborationPreference: 'coordinated'
});

// Marketing Agents
const MarketingAgent = new AgentTemplate({
  id: 'marketing-agent',
  name: 'Marketing Automation Agent',
  type: 'marketing',
  description: 'Automatisiert Marketing-Kampagnen und Kunden-Interaktion',
  capabilities: [
    'email_campaigns',
    'social_media_management',
    'content_scheduling',
    'audience_segmentation',
    'performance_tracking',
    'a_b_testing'
  ],
  priority: 'medium',
  maxConcurrentTasks: 8,
  group: 'marketing',
  communicationStyle: 'creative',
  decisionMaking: 'data_driven',
  collaborationPreference: 'innovative'
});

const RetargetingAgent = new AgentTemplate({
  id: 'retargeting-agent',
  name: 'Retargeting Specialist Agent',
  type: 'marketing',
  description: 'Führt gezielte Retargeting-Kampagnen durch',
  capabilities: [
    'cart_recovery',
    'abandoned_checkout',
    'product_remarketing',
    'behavioral_targeting',
    'conversion_optimization',
    'attribution_tracking'
  ],
  priority: 'medium',
  maxConcurrentTasks: 10,
  group: 'marketing',
  communicationStyle: 'persuasive',
  decisionMaking: 'algorithmic',
  collaborationPreference: 'data_sharing'
});

// Analytics Agents
const AnalyticsAgent = new AgentTemplate({
  id: 'analytics-agent',
  name: 'Business Analytics Agent',
  type: 'analytics',
  description: 'Analysiert Business-Daten und erstellt Insights',
  capabilities: [
    'data_analysis',
    'trend_identification',
    'kpi_tracking',
    'report_generation',
    'predictive_modeling',
    'performance_monitoring'
  ],
  priority: 'medium',
  maxConcurrentTasks: 6,
  group: 'analytics',
  communicationStyle: 'insightful',
  decisionMaking: 'evidence_based',
  collaborationPreference: 'consultative'
});

const RevenueAgent = new AgentTemplate({
  id: 'revenue-agent',
  name: 'Revenue Intelligence Agent',
  type: 'analytics',
  description: 'Spezialisiert auf Umsatz-Analyse und -Optimierung',
  capabilities: [
    'revenue_forecasting',
    'customer_lifetime_value',
    'churn_prediction',
    'upsell_opportunities',
    'price_optimization',
    'market_analysis'
  ],
  priority: 'high',
  maxConcurrentTasks: 4,
  group: 'analytics',
  communicationStyle: 'strategic',
  decisionMaking: 'analytical',
  collaborationPreference: 'advisory'
});

// Legal/Tax Agents
const TaxAgent = new AgentTemplate({
  id: 'tax-agent',
  name: 'Tax Compliance Agent',
  type: 'legal_tax',
  description: 'Verwaltet steuerliche Pflichten und ELSTER-Kommunikation',
  capabilities: [
    'tax_calculation',
    'vat_reporting',
    'elster_communication',
    'tax_deadline_tracking',
    'compliance_monitoring',
    'document_generation'
  ],
  priority: 'high',
  maxConcurrentTasks: 3,
  group: 'legal_tax',
  communicationStyle: 'precise',
  decisionMaking: 'rule_based',
  collaborationPreference: 'authoritative'
});

const ComplianceAgent = new AgentTemplate({
  id: 'compliance-agent',
  name: 'Compliance Monitoring Agent',
  type: 'legal_tax',
  description: 'Überwacht rechtliche Compliance und Risiken',
  capabilities: [
    'regulatory_monitoring',
    'risk_assessment',
    'policy_enforcement',
    'audit_preparation',
    'documentation_management',
    'incident_reporting'
  ],
  priority: 'medium',
  maxConcurrentTasks: 5,
  group: 'legal_tax',
  communicationStyle: 'formal',
  decisionMaking: 'conservative',
  collaborationPreference: 'protective'
});

// Security Agents
const SecurityAgent = new AgentTemplate({
  id: 'security-agent',
  name: 'Security Operations Agent',
  type: 'security',
  description: 'Schützt Systeme und Daten vor Sicherheitsbedrohungen',
  capabilities: [
    'threat_detection',
    'access_control',
    'security_monitoring',
    'incident_response',
    'vulnerability_management',
    'security_audit'
  ],
  priority: 'high',
  maxConcurrentTasks: 8,
  group: 'security',
  communicationStyle: 'alert',
  decisionMaking: 'protective',
  collaborationPreference: 'coordinated'
});

const PrivacyAgent = new AgentTemplate({
  id: 'privacy-agent',
  name: 'Data Privacy Agent',
  type: 'security',
  description: 'Schützt personenbezogene Daten und Datenschutz-Compliance',
  capabilities: [
    'data_protection',
    'privacy_policy_enforcement',
    'consent_management',
    'data_minimization',
    'privacy_impact_assessment',
    'breach_response'
  ],
  priority: 'high',
  maxConcurrentTasks: 4,
  group: 'security',
  communicationStyle: 'confidential',
  decisionMaking: 'privacy_first',
  collaborationPreference: 'cautious'
});

// Communication Agents
const NotificationAgent = new AgentTemplate({
  id: 'notification-agent',
  name: 'Notification Agent',
  type: 'communication',
  description: 'Verwaltet Benachrichtigungen über verschiedene Kanäle',
  capabilities: [
    'email_notifications',
    'sms_notifications',
    'push_notifications',
    'telegram_messaging',
    'slack_integration',
    'message_template_management'
  ],
  priority: 'medium',
  maxConcurrentTasks: 10,
  group: 'communication',
  communicationStyle: 'clear',
  decisionMaking: 'automated',
  collaborationPreference: 'broadcast'
});

const ReportAgent = new AgentTemplate({
  id: 'report-agent',
  name: 'Report Generation Agent',
  type: 'communication',
  description: 'Erstellt und verteilt Business-Berichte',
  capabilities: [
    'report_creation',
    'data_visualization',
    'dashboard_updates',
    'scheduled_reports',
    'executive_summaries',
    'distribution_management'
  ],
  priority: 'low',
  maxConcurrentTasks: 6,
  group: 'communication',
  communicationStyle: 'informative',
  decisionMaking: 'scheduled',
  collaborationPreference: 'informative'
});

// Integration Agents
const APIAgent = new AgentTemplate({
  id: 'api-agent',
  name: 'API Integration Agent',
  type: 'integration',
  description: 'Verwaltet externe API-Verbindungen und Daten-Synchronisation',
  capabilities: [
    'api_communication',
    'data_synchronization',
    'webhook_processing',
    'rate_limit_management',
    'error_handling',
    'connection_monitoring'
  ],
  priority: 'high',
  maxConcurrentTasks: 15,
  group: 'integration',
  communicationStyle: 'technical',
  decisionMaking: 'procedural',
  collaborationPreference: 'service_oriented'
});

const DatabaseAgent = new AgentTemplate({
  id: 'database-agent',
  name: 'Database Management Agent',
  type: 'integration',
  description: 'Verwaltet Datenbank-Operationen und Daten-Integrität',
  capabilities: [
    'data_storage',
    'data_retrieval',
    'backup_management',
    'data_migration',
    'query_optimization',
    'data_consistency'
  ],
  priority: 'high',
  maxConcurrentTasks: 8,
  group: 'integration',
  communicationStyle: 'structured',
  decisionMaking: 'transactional',
  collaborationPreference: 'consistent'
});

// Agent Registry
const AgentTemplates = {
  // Commerce
  shopify: ShopifyAgent,
  printify: PrintifyAgent,
  
  // Finance
  finance: FinanceAgent,
  costkiller: CostKillerAgent,
  
  // Support
  support: SupportAgent,
  wismo: WISMOAgent,
  
  // Marketing
  marketing: MarketingAgent,
  retargeting: RetargetingAgent,
  
  // Analytics
  analytics: AnalyticsAgent,
  revenue: RevenueAgent,
  
  // Legal/Tax
  tax: TaxAgent,
  compliance: ComplianceAgent,
  
  // Security
  security: SecurityAgent,
  privacy: PrivacyAgent,
  
  // Communication
  notification: NotificationAgent,
  report: ReportAgent,
  
  // Integration
  api: APIAgent,
  database: DatabaseAgent
};

// Agent Factory
class AgentFactory {
  static createAgent(templateKey, customConfig = {}) {
    const template = AgentTemplates[templateKey];
    
    if (!template) {
      throw new Error(`Agent template '${templateKey}' not found`);
    }
    
    return template.createAgent(customConfig);
  }
  
  static getAvailableTemplates() {
    return Object.keys(AgentTemplates).map(key => ({
      key,
      name: AgentTemplates[key].name,
      type: AgentTemplates[key].type,
      description: AgentTemplates[key].description,
      capabilities: AgentTemplates[key].capabilities
    }));
  }
  
  static getTemplatesByType(type) {
    return Object.entries(AgentTemplates)
      .filter(([key, template]) => template.type === type)
      .map(([key, template]) => ({
        key,
        name: template.name,
        description: template.description,
        capabilities: template.capabilities
      }));
  }
  
  static createAgentGroup(groupName, agentConfigs) {
    return agentConfigs.map(config => {
      const agent = this.createAgent(config.template, config.custom);
      agent.group = groupName;
      return agent;
    });
  }
}

module.exports = {
  AgentTemplate,
  AgentTemplates,
  AgentFactory
};
