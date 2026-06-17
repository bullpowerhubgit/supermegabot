import React, { useState } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import Overview from './Overview';
import Customers from './Customers';
import Analytics from './Analytics';
import ShopifyOrders from './ShopifyOrders';
import ShopifyProducts from './ShopifyProducts';
import AIAssistant from './AIAssistant';

import { User } from '../middleware/auth';

interface DashboardProps {
  user: User;
  onLogout: () => void;
}

const Dashboard: React.FC<DashboardProps> = ({ user, onLogout }) => {
  const [activePage, setActivePage] = useState('overview');

  const renderPage = () => {
    switch (activePage) {
      case 'overview':
        return <Overview />;
      case 'assistant':
        return <AIAssistant />;
      case 'orders':
        return <ShopifyOrders />;
      case 'products':
        return <ShopifyProducts />;
      case 'customers':
        return <Customers />;
      case 'analytics':
        return <Analytics />;
      default:
        return <Overview />;
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar activePage={activePage} onPageChange={setActivePage} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header user={user} onLogout={onLogout} />
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-gray-100 p-6">
          {renderPage()}
        </main>
      </div>
    </div>
  );
};

export default Dashboard;
