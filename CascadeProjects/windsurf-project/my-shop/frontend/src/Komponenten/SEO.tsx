import { useEffect, useState } from 'react';
import { api } from '../Dienstleistungen/api';

export default function SEO() {
  const [seo, setSeo] = useState<any>(null);
  const [trend, setTrend] = useState<any[]>([]);

  useEffect(() => {
    api.seo().then(r => setSeo(r.seo));
    api.umsatzTrend().then(r => setTrend(r.trend));
  }, []);

  if (!seo) return <div className="content">Lade SEO-Daten...</div>;

  const maxUmsatz = Math.max(...trend.map((t: any) => t.umsatz));

  return (
    <div className="content">
      <h1>SEO & Analytics</h1>

      <h2>Keyword Rankings</h2>
      <table>
        <thead>
          <tr><th>Keyword</th><th>Position</th><th>Suchvolumen</th></tr>
        </thead>
        <tbody>
          {seo.rankingKeywords.map((kw: any) => (
            <tr key={kw.keyword}>
              <td>{kw.keyword}</td>
              <td>{kw.position <= 10 ? (
                <span className="positive" style={{ fontWeight: 600 }}>#{kw.position}</span>
              ) : `#${kw.position}`}</td>
              <td>{kw.volumen.toLocaleString('de-DE')}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Technisches SEO</h2>
      <div className="card-grid">
        <div className="card">
          <h3>Ladezeit</h3>
          <div className="value">{seo.technischeSEO.ladezeit}</div>
        </div>
        <div className="card">
          <h3>Mobile Score</h3>
          <div className="value">{seo.technischeSEO.mobileScore}/100</div>
        </div>
        <div className="card">
          <h3>Core Web Vitals</h3>
          <div className="value" style={{ fontSize: '1.2rem' }}>{seo.technischeSEO.coreWebVitals}</div>
        </div>
      </div>

      <h2>Umsatz Trend (7 Tage)</h2>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '200px', padding: '1rem', background: '#1e293b', borderRadius: '12px' }}>
        {trend.map((t: any) => {
          const height = (t.umsatz / maxUmsatz) * 100;
          return (
            <div key={t.datum} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
              <div style={{
                width: '100%',
                height: `${height}%`,
                background: '#38bdf8',
                borderRadius: '4px 4px 0 0',
                minHeight: '4px'
              }} />
              <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>
                {t.datum.slice(5)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
