export interface KPIData {
  label: string;
  value: string;
  change: number;
  trend: 'up' | 'down' | 'neutral';
  automated: boolean;
}

export interface AutomationItem {
  name: string;
  status: 'running' | 'paused' | 'error';
  lastRun: string;
  frequency: string;
  impact: string;
}

export interface ChartPoint {
  name: string;
  value1: number;
  value2: number;
}

export interface ActionItem {
  priority: 'high' | 'medium' | 'low';
  title: string;
  assignee: string;
  due: string;
  autoTriggered: boolean;
}

export const kpis: KPIData[] = [
  { label: 'System-Verfügbarkeit', value: '99.97%', change: 0.02, trend: 'up', automated: true },
  { label: 'API-Latenz (p95)', value: '42 ms', change: -8, trend: 'up', automated: true },
  { label: 'Fehlerrate', value: '0.03%', change: -0.01, trend: 'up', automated: true },
  { label: 'Deployments / Woche', value: '34', change: 12, trend: 'up', automated: true },
  { label: 'Kosten / Request', value: '€0.0004', change: -15, trend: 'up', automated: true },
  { label: 'MTTR (Mean Time to Repair)', value: '4.2 min', change: -22, trend: 'up', automated: true },
];

export const automationFlows: AutomationItem[] = [
  { name: 'Health-Check & Alerting', status: 'running', lastRun: 'vor 30 Sek.', frequency: 'kontinuierlich', impact: '98% der Incidents selbstheilend' },
  { name: 'Cost-Anomaly Detection', status: 'running', lastRun: 'vor 2 Min.', frequency: 'stündlich', impact: '€12.400/qtr. eingespart' },
  { name: 'Security-Scan Pipeline', status: 'running', lastRun: 'vor 15 Min.', frequency: 'pro Commit', impact: '0 kritische CVEs in Produktion' },
  { name: 'Capacity Forecasting', status: 'running', lastRun: 'vor 1 Std.', frequency: 'täglich', impact: 'Over-Provisioning um 34% reduziert' },
  { name: 'Auto-Scaling Logik', status: 'running', lastRun: 'vor 5 Min.', frequency: 'Echtzeit', impact: 'Peak-Traffic +340% abgefangen' },
];

export const chartData: ChartPoint[] = [
  { name: 'Mo', value1: 4200, value2: 2400 },
  { name: 'Di', value1: 5100, value2: 2800 },
  { name: 'Mi', value1: 4800, value2: 3100 },
  { name: 'Do', value1: 6200, value2: 3500 },
  { name: 'Fr', value1: 7500, value2: 4100 },
  { name: 'Sa', value1: 5400, value2: 3200 },
  { name: 'So', value1: 4900, value2: 2900 },
];

export const actionItems: ActionItem[] = [
  { priority: 'high', title: 'Database-Connection-Pool auf 80% – Auto-Scale wird ausgelöst', assignee: 'Auto', due: 'Echtzeit', autoTriggered: true },
  { priority: 'high', title: 'Neue CVE in nginx – Patch wird in Staging deployed', assignee: 'SRE-Bot', due: 'in 10 Min.', autoTriggered: true },
  { priority: 'medium', title: 'Q3 Capacity-Review – Trend deutet auf 20% Wachstum', assignee: 'Platform Team', due: 'Freitag', autoTriggered: false },
  { priority: 'medium', title: 'Dokumentation: Neue Onboarding-Flows für Dev-Teams', assignee: 'Tech Writing', due: 'nächste Woche', autoTriggered: false },
  { priority: 'low', title: 'Cleanup: 14 verwaiste Load-Balancer identifiziert', assignee: 'Auto', due: 'Sonntag Nacht', autoTriggered: true },
];

export const dashboardComparison = {
  before: {
    dashboards: 47,
    manualChecks: 23,
    avgDiscoveryTime: '8.5 min',
    maintenanceHours: 14,
    alertFatigue: 'hoch',
  },
  after: {
    dashboards: 2,
    manualChecks: 0,
    avgDiscoveryTime: '12 sek.',
    maintenanceHours: 1.5,
    alertFatigue: 'minimal',
  },
};
