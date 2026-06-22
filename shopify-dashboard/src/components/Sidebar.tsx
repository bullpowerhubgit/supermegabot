import React from 'react';

interface SidebarProps {
  activePage: string;
  onPageChange: (page: string) => void;
}

const MENU = [
  { id: 'overview', label: 'Übersicht', icon: '📊' },
  { id: 'orders', label: 'Bestellungen', icon: '📦' },
  { id: 'products', label: 'Produkte', icon: '🛍️' },
  { id: 'customers', label: 'Kunden', icon: '👥' },
  { id: 'analytics', label: 'Statistiken', icon: '📈' },
  { id: 'assistant', label: 'KI-Assistent', icon: '🤖' },
];

const Sidebar: React.FC<SidebarProps> = ({ activePage, onPageChange }) => (
  <div className="w-64 bg-gray-900 text-white flex flex-col">
    <div className="p-6 border-b border-gray-700">
      <h2 className="text-xl font-bold text-green-400">AutoSuite RudiBot</h2>
      <p className="text-gray-400 text-sm mt-1">Shopify Dashboard</p>
    </div>
    <nav className="flex-1 p-4">
      {MENU.map(item => (
        <button key={item.id} onClick={() => onPageChange(item.id)}
          className={`w-full text-left px-4 py-3 rounded-lg mb-1 flex items-center gap-3 transition-colors ${
            activePage === item.id ? 'bg-green-600 text-white' : 'text-gray-300 hover:bg-gray-800'
          }`}>
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  </div>
);

export default Sidebar;
