import React from 'react';

const Analytics: React.FC = () => (
  <div className="p-6">
    <h2 className="text-2xl font-bold text-gray-800 mb-6">Statistiken</h2>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      {[
        { label: 'Umsatz heute', value: '€0', icon: '💰', color: 'green' },
        { label: 'Bestellungen', value: '0', icon: '📦', color: 'blue' },
        { label: 'Neue Kunden', value: '0', icon: '👥', color: 'purple' },
      ].map(stat => (
        <div key={stat.label} className="bg-white rounded-xl p-6 shadow">
          <div className="flex items-center justify-between mb-2">
            <span className="text-2xl">{stat.icon}</span>
          </div>
          <div className="text-3xl font-bold text-gray-800">{stat.value}</div>
          <div className="text-sm text-gray-500 mt-1">{stat.label}</div>
        </div>
      ))}
    </div>
    <div className="bg-white rounded-xl p-6 shadow text-center text-gray-500">
      Analytics-Daten werden nach der ersten Bestellung angezeigt.
    </div>
  </div>
);

export default Analytics;
