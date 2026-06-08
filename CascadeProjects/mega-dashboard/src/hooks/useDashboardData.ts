import { useState, useEffect, useCallback } from 'react';
import type { DashboardData } from '../types';

const API_URL = 'http://localhost:9001/api/status';
const REFRESH_INTERVAL = 3000;

const initialData: DashboardData = {
  timestamp: new Date().toISOString(),
  server: { name: 'Super Server', version: '1.0.0', uptime: 0, pid: 0 },
  system: { totalmem: 0, freemem: 0, usedmem: 0, percent: 0, uptime: 0, loadavg: [0, 0, 0], cpus: 0, compressed: 0 },
  cpu: { usage: 0, cores: 0, loadavg: [0, 0, 0] },
  disks: [],
  processes: [],
  cloudStorage: [],
  alerts: [],
  history: { memory: [], cpu: [], disk: [] }
};

export function useDashboardData() {
  const [data, setData] = useState<DashboardData>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const response = await fetch(API_URL);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const json = await response.json() as DashboardData;
      setData(json);
      setError(null);
      setConnected(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed');
      setConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { data, loading, error, connected, refetch: fetchData };
}
