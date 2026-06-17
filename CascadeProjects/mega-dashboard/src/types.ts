export interface SystemStats {
  totalmem: number;
  freemem: number;
  usedmem: number;
  percent: number;
  uptime: number;
  loadavg: number[];
  cpus: number;
  compressed: number;
}

export interface CPUUsage {
  usage: number;
  cores: number;
  loadavg: number[];
}

export interface DiskInfo {
  filesystem: string;
  size: string;
  used: string;
  available: string;
  usePercent: number;
  mountpoint: string;
  type: 'internal' | 'external';
  name: string;
}

export interface ProcessInfo {
  pid: string;
  name: string;
  memPercent: number;
  memMB: number;
  cpuPercent: number;
  time: string;
}

export interface CloudService {
  name: string;
  status: 'running' | 'stopped' | 'not_installed';
}

export interface Alert {
  type: 'critical' | 'warning';
  source: string;
  message: string;
  timestamp: string;
}

export interface HistoryPoint {
  time: number;
  value: number;
}

export interface DashboardHistory {
  memory: HistoryPoint[];
  cpu: HistoryPoint[];
  disk: HistoryPoint[];
}

export interface ServerInfo {
  name: string;
  version: string;
  uptime: number;
  pid: number;
}

export interface DashboardData {
  timestamp: string;
  server: ServerInfo;
  system: SystemStats;
  cpu: CPUUsage;
  disks: DiskInfo[];
  processes: ProcessInfo[];
  cloudStorage: CloudService[];
  alerts: Alert[];
  history: DashboardHistory;
}
