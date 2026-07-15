import { Registry, Counter, Histogram, collectDefaultMetrics } from 'prom-client'
export const register = new Registry()
collectDefaultMetrics({ register })
export const httpRequestsTotal = new Counter({
  name: 'http_requests_total', help: 'Total HTTP requests',
  labelNames: ['method', 'route', 'status', 'service'], registers: [register]
})
export const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds', help: 'HTTP request duration',
  labelNames: ['method', 'route', 'service'],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5], registers: [register]
})
export const analyticsEventsTotal = new Counter({
  name: 'analytics_events_total', help: 'Total analytics events',
  labelNames: ['provider', 'event'], registers: [register]
})
export const marketingEmailsTotal = new Counter({
  name: 'marketing_emails_total', help: 'Total marketing emails',
  labelNames: ['provider', 'type'], registers: [register]
})
