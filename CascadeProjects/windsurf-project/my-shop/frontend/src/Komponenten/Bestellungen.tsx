import { useEffect, useState } from 'react';
import { api } from '../Dienstleistungen/api';

export default function Bestellungen() {
  const [bestellungen, setBestellungen] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    api.bestellungen().then(r => setBestellungen(r.bestellungen));
    api.bestellungStats().then(r => setStats(r.statistiken));
  }, []);

  if (!stats) return <div className="content">Lade Bestellungen...</div>;

  return (
    <div className="content">
      <h1>Bestellungen</h1>

      <div className="kpi-row">
        <div className="card">
          <h3>Gesamtumsatz</h3>
          <div className="value">{stats.gesamtUmsatz.toFixed(2)} EUR</div>
        </div>
        <div className="card">
          <h3>Bezahlt</h3>
          <div className="value">{stats.statusVerteilung.bezahlt}</div>
        </div>
        <div className="card">
          <h3>In Bearbeitung</h3>
          <div className="value">{stats.statusVerteilung.bearbeitung}</div>
        </div>
        <div className="card">
          <h3>Versendet</h3>
          <div className="value">{stats.statusVerteilung.versendet}</div>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Kunde</th>
            <th>Produkte</th>
            <th>Betrag</th>
            <th>Status</th>
            <th>Datum</th>
          </tr>
        </thead>
        <tbody>
          {bestellungen.map(b => (
            <tr key={b.id}>
              <td>{b.id}</td>
              <td>{b.kunde}</td>
              <td>{b.produkte.length} Artikel</td>
              <td>{b.gesamtbetrag.toFixed(2)} EUR</td>
              <td>
                <span className={`status status-${b.status}`}>{b.status}</span>
              </td>
              <td>{new Date(b.erstelltAm).toLocaleDateString('de-DE')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
