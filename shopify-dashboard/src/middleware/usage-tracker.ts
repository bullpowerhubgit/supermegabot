export interface UsageRecord { user_id: string; metric: string; date: string; count: number; }
export async function trackUsage(userId: string, metric: string): Promise<number> {
  const today = new Date().toISOString().split('T')[0];
  const key = `usage:${userId}:${metric}:${today}`;
  const current = parseInt(localStorage.getItem(key) || '0');
  const next = current + 1;
  localStorage.setItem(key, next.toString());
  return next;
}
export function getUsage(userId: string, metric: string): number {
  const today = new Date().toISOString().split('T')[0];
  const key = `usage:${userId}:${metric}:${today}`;
  return parseInt(localStorage.getItem(key) || '0');
}
export function resetUsage(userId: string, metric: string): void {
  const today = new Date().toISOString().split('T')[0];
  const key = `usage:${userId}:${metric}:${today}`;
  localStorage.removeItem(key);
}
