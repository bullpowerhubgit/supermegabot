import { useEffect, useState } from 'react';
import { api } from '../Dienstleistungen/api';

export default function Produkte() {
  const [produkte, setProdukte] = useState<any[]>([]);
  const [kategorien, setKategorien] = useState<string[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    api.produkte().then(r => setProdukte(r.produkte));
    api.kategorien().then(r => setKategorien(r.kategorien));
  }, []);

  const gefiltert = produkte.filter(p =>
    p.name.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="content">
      <h1>Produkte</h1>

      <input
        type="text"
        placeholder="Suchen..."
        value={filter}
        onChange={e => setFilter(e.target.value)}
        style={{
          padding: '0.6rem 1rem',
          borderRadius: '8px',
          border: '1px solid #334155',
          background: '#1e293b',
          color: '#e2e8f0',
          width: '300px',
          fontSize: '0.9rem'
        }}
      />

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Kategorie</th>
            <th>Preis</th>
            <th>Lager</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {gefiltert.map(p => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td><span className="badge">{p.kategorie}</span></td>
              <td>{p.preis.toFixed(2)} EUR</td>
              <td>{p.lager}</td>
              <td>
                <span className={`status status-${p.status}`}>{p.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Kategorien</h2>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {kategorien.map(k => (
          <span key={k} className="badge" style={{ fontSize: '0.85rem', padding: '0.4rem 0.75rem' }}>
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}
