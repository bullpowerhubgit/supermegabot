import { useEffect, useState } from 'react';
import { api } from '../Dienstleistungen/api';

export default function Marketing() {
  const [kampagnen, setKampagnen] = useState<any[]>([]);
  const [performance, setPerformance] = useState<any>(null);

  useEffect(() => {
    api.kampagnen().then(r => setKampagnen(r.kampagnen));
    api.marketingPerformance().then(r => setPerformance(r.performance));
  }, []);

  if (!performance) return <div className="content">Lade Marketing...</div>;

  return (
    <div className="content">
      <h1>Marketing</h1>

      <div className="kpi-row">
        <div className="card">
          <h3>Gesamtausgaben</h3>
          <div className="value">{performance.ausgaben.toFixed(2)} EUR</div>
        </div>
        <div className="card">
          <h3>CTR</h3>
          <div className="value">{performance.ctr}%</div>
        </div>
        <div className="card">
          <h3>Konversionsrate</h3>
          <div className="value">{performance.cvr}%</div>
        </div>
        <div className="card">
          <h3>ROAS</h3>
          <div className="value">{performance.roas}x</div>
        </div>
      </div>

      <h2>Kampagnen</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Plattform</th>
            <th>Budget</th>
            <th>Ausgaben</th>
            <th>Impressions</th>
            <th>Clicks</th>
            <th>Konversionen</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {kampagnen.map(k => (
            <tr key={k.id}>
              <td>{k.name}</td>
              <td>{k.plattform}</td>
              <td>{k.budget.toFixed(2)} EUR</td>
              <td>{k.ausgaben.toFixed(2)} EUR</td>
              <td>{k.impressions.toLocaleString('de-DE')}</td>
              <td>{k.clicks}</td>
              <td>{k.konversionen}</td>
              <td>
                <span className={`status status-${k.status}`}>{k.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
