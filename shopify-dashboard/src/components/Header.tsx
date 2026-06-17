import React from 'react';
import { User } from '../middleware/auth';

interface HeaderProps {
  user: User;
  onLogout: () => void;
}

const Header: React.FC<HeaderProps> = ({ user, onLogout }) => {
  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center space-x-4">
          <h1 className="text-xl font-semibold text-gray-800">Dashboard</h1>
          <span className="bg-green-100 text-green-800 text-xs font-medium px-2.5 py-0.5 rounded">
            Online
          </span>
        </div>
        
        <div className="flex items-center space-x-4">
          <span className="bg-blue-100 text-blue-800 text-xs font-medium px-2 py-1 rounded">{user.plan}</span>
          <span className="text-sm text-gray-600">{user.email}</span>
          <div className="text-sm text-gray-600">{new Date().toLocaleDateString('de-DE')}</div>
          <button onClick={onLogout} className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium">Logout</button>
        </div>
      </div>
    </header>
  );
};

export default Header;
