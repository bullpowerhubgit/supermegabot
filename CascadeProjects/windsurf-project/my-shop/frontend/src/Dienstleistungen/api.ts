const API_BASE = '/api';

async function fetchJSON(path: string) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export const api = {
  health: () => fetchJSON('/health'),
  dashboard: () => fetchJSON('/analytics/dashboard'),
  umsatzTrend: () => fetchJSON('/analytics/umsatz'),
  seo: () => fetchJSON('/analytics/seo'),

  produkte: (params?: string) => fetchJSON(`/produkte${params ? `?${params}` : ''}`),
  kategorien: () => fetchJSON('/produkte/kategorien'),
  produkt: (id: string) => fetchJSON(`/produkte/${id}`),

  bestellungen: (params?: string) => fetchJSON(`/bestellungen${params ? `?${params}` : ''}`),
  bestellungStats: () => fetchJSON('/bestellungen/statistiken'),

  kampagnen: () => fetchJSON('/marketing'),
  marketingPerformance: () => fetchJSON('/marketing/performance'),

  systemStatus: () => fetchJSON('/system/status'),
  einstellungen: () => fetchJSON('/system/einstellungen'),
};
