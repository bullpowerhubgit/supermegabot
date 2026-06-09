import React, { useState, useEffect } from 'react';

const Overview: React.FC = () => {
  const [stats, setStats] = useState([
    { title: 'Bestellungen', value: '0', change: '0', positive: true },
    { title: 'Aktive Produkte', value: '0', change: '0', positive: true },
    { title: 'Kunden', value: '0', change: '0', positive: true },
    { title: 'Artikel verkauft', value: '0', change: '0', positive: true },
  ]);

  useEffect(() => {
    // Lade echte Daten von Windsurf API
    fetch('http://localhost:3001/health')
      .then(res => res.json())
      .then(data => {
        console.log('System health:', data);
      })
      .catch(err => console.error('Health check failed:', err));
  }, []);

  return (
    <div className="p-8 bg-gradient-to-br from-black via-blue-950/30 to-black min-h-screen">
      <div className="mb-8">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-green-400 bg-clip-text text-transparent">
          Dashboard Übersicht
        </h1>
        <p className="text-blue-300 mt-2">RudiBot AI-Powered Control Center</p>
      </div>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat, index) => (
          <div key={index} className="bg-gradient-to-br from-blue-950/50 to-green-950/50 backdrop-blur-sm rounded-2xl p-6 border border-blue-800/30 shadow-lg shadow-blue-900/20">
            <p className="text-blue-400 text-sm mb-2 font-medium">{stat.title}</p>
            <p className="text-3xl font-bold text-white mb-2">{stat.value}</p>
            <p className={`text-sm ${stat.positive ? 'text-green-400' : 'text-red-400'}`}>
              {stat.change}
            </p>
          </div>
        ))}
      </div>

      {/* AI Assistant Card */}
      <div className="bg-gradient-to-br from-blue-950/60 to-green-950/60 backdrop-blur-sm rounded-2xl p-6 border border-blue-800/30 shadow-lg shadow-blue-900/20 mb-8">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-green-600 rounded-2xl flex items-center justify-center text-3xl">
            🤖
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-bold text-white mb-1">RudiBot AI-Assistent</h3>
            <p className="text-blue-400 text-sm">Sprich mit mir - ich kann alles steuern, überwachen und automatisieren!</p>
          </div>
          <button className="bg-gradient-to-r from-blue-700 to-green-700 text-white px-6 py-3 rounded-xl font-medium hover:shadow-lg hover:shadow-blue-900/30 transition-all">
            Jetzt starten
          </button>
        </div>
      </div>

      {/* System Status */}
      <div className="bg-gradient-to-br from-blue-950/50 to-green-950/50 backdrop-blur-sm rounded-2xl p-6 border border-blue-800/30 shadow-lg shadow-blue-900/20">
        <h3 className="text-xl font-bold text-white mb-4">System-Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-blue-950/50 rounded-xl p-4 border border-blue-800/20">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-green-400 text-sm font-medium">Online</span>
            </div>
            <p className="text-white font-medium">Telegram Bot</p>
          </div>
          <div className="bg-blue-950/50 rounded-xl p-4 border border-blue-800/20">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-green-400 text-sm font-medium">Verbunden</span>
            </div>
            <p className="text-white font-medium">Shopify API</p>
          </div>
          <div className="bg-blue-950/50 rounded-xl p-4 border border-blue-800/20">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-green-400 text-sm font-medium">Aktiv</span>
            </div>
            <p className="text-white font-medium">Monetization</p>
          </div>
          <div className="bg-blue-950/50 rounded-xl p-4 border border-blue-800/20">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-green-400 text-sm font-medium">Bereit</span>
            </div>
            <p className="text-white font-medium">API Gateway</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Overview;
