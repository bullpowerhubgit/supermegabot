export const PLAN_LIMITS: Record<string, Record<string, number>> = {
  free: { products_per_day: 10, ai_calls: 0, shops: 1 },
  starter: { products_per_day: 100, ai_calls: 50, shops: 3 },
  pro: { products_per_day: -1, ai_calls: 500, shops: 10 },
};
export function checkPlanLimit(plan: string, metric: string, currentUsage: number): boolean {
  const limit = PLAN_LIMITS[plan]?.[metric];
  if (limit === -1) return true;
  return currentUsage < (limit || 0);
}
export function getPlanFeatures(plan: string): string[] {
  const features: Record<string, string[]> = {
    free: ['basic_dashboard', 'health_check'],
    starter: ['basic_dashboard', 'shopify_sync', 'email_automation'],
    pro: ['all_features', 'browser_automation', 'ai_assistant', 'webhook_automation'],
  };
  return features[plan] || features.free;
}
export function requireFeature(feature: string, userPlan: string): boolean {
  return getPlanFeatures(userPlan).includes(feature) || getPlanFeatures(userPlan).includes('all_features');
}
