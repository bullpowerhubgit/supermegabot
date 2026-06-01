import { useEffect, useState } from 'react';
import { api } from '../Dienstleistungen/api';

export default function Dashboard() {
  const [daten, setDaten] = useState<any>(null);
  const [bestellStats, setBestellStats] = useState<any>(null);

  useEffect(() => {
    api.dashboard().then(r => setDaten(r.dashboard));
    api.bestellungStats().then(r => setBestellStats(r.statistiken));
  }, []);

  if (!daten || !bestellStats) return <div className="content">Lade Dashboard...</div>;

  return (
    <div className="content">
      <h1>Dashboard</h1>

      <div className="kpi-row">
        <div className="card">
          <h3>Heutiger Umsatz</h3>
          <div className="value">{daten.umsatz.heute.toFixed(2)} EUR</div>
          <div className="change positive">
            +{((daten.umsatz.heute - daten.umsatz.gestern) / daten.umsatz.gestern * 100).toFixed(1)}%
          </div>
        </div>
        <div className="card">
          <h3>Besucher heute</h3>
          <div className="value">{daten.besucher.heute}</div>
          <div className="change positive">+{daten.besucher.heute - daten.besucher.gestern} vs. gestern</div>
        </div>
        <div className="card">
          <h3>Konversionsrate</h3>
          <div className="value">{daten.konversion.rate}</div>
          <div className="change">Avg. Warenkorb: {daten.konversion.durchschnittlicherWarenkorb} EUR</div>
        </div>
        <div className="card">
          <h3>Bestellungen</h3>
          <div className="value">{bestellStats.heuteBestellungen}</div>
          <div className="change">Gesamt: {bestellStats.gesamtBestellungen}</div>
        </div>
      </div>

      <h2>Top Produkte</h2>
      <table>
        <thead>
          <tr><th>Produkt</th><th>Verkauft</th><th>Umsatz</th></tr>
        </thead>
        <tbody>
          {daten.topProdukte.map((p: any) => (
            <tr key={p.name}>
              <td>{p.name}</td>
              <td>{p.verkauft}</td>
              <td>{p.umsatz.toFixed(2)} EUR</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Traffic Quellen</h2>
      <div className="card-grid">
        {daten.trafficQuellen.map((q: any) => (
          <div className="card" key={q.quelle}>
            <h3>{q.quelle}</h3>
            <div className="value">{q.anteil}%</div>
          </div>
        ))}
      </div>
    </div>
  );
}
