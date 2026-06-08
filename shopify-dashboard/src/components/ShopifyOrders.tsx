import React, { useState, useEffect } from 'react';

interface Order {
  id: string;
  customer: string;
  email: string;
  total: string;
  status: 'paid' | 'pending' | 'refunded' | 'shipped';
  date: string;
  items: number;
  payment: string;
}

const ShopifyOrders: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Lade echte Bestellungen von Windsurf API
    fetch('http://localhost:3001/api/shopify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shopDomain: process.env.REACT_APP_SHOPIFY_SHOP_DOMAIN || 'suitenew.myshopify.com',
        accessToken: process.env.REACT_APP_SHOPIFY_ACCESS_TOKEN || '',
        action: 'getOrders'
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.result && data.result.orders) {
          const formattedOrders = data.result.orders.map((o: any) => ({
            id: o.id || o.order_number,
            customer: o.customer?.first_name + ' ' + o.customer?.last_name || 'Unbekannt',
            email: o.customer?.email || '',
            total: o.total_price || '0.00',
            status: o.financial_status || 'pending',
            date: o.created_at || new Date().toISOString(),
            items: o.line_items?.length || 0,
            payment: o.payment_gateway_names?.[0] || 'Unbekannt'
          }));
          setOrders(formattedOrders);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error('Shopify orders fetch failed:', err);
        setLoading(false);
      });
  }, []);

  const getStatusBadge = (status: Order['status']) => {
    const styles = {
      paid: 'bg-green-100 text-green-800',
      shipped: 'bg-blue-100 text-blue-800',
      pending: 'bg-yellow-100 text-yellow-800',
      refunded: 'bg-red-100 text-red-800',
    };
    const labels = { paid: 'Bezahlt', shipped: 'Versendet', pending: 'Offen', refunded: 'Storniert' };
    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[status]}`}>
        {labels[status]}
      </span>
    );
  };

  return (
    <div className="p-8 bg-gradient-to-br from-black via-blue-950/30 to-black min-h-screen">
      <div className="mb-8">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-green-400 bg-clip-text text-transparent">
          Bestellungen
        </h1>
        <p className="text-blue-300 mt-2">Verwalte deine Shopify-Bestellungen</p>
      </div>

      {/* Filter Bar */}
      <div className="bg-gradient-to-br from-blue-950/50 to-green-950/50 backdrop-blur-sm rounded-2xl p-4 border border-blue-800/30 flex gap-4 items-center mb-8">
        <input
          type="text"
          placeholder="Bestellung oder Kunde suchen..."
          className="flex-1 px-4 py-3 bg-blue-950/50 border border-blue-800/30 rounded-xl text-white placeholder-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-700"
        />
        <select className="px-4 py-3 bg-blue-950/50 border border-blue-800/30 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-700">
          <option>Alle Status</option>
          <option>Bezahlt</option>
          <option>Offen</option>
          <option>Versendet</option>
          <option>Storniert</option>
        </select>
      </div>

      {/* Orders Table */}
      <div className="bg-gradient-to-br from-blue-950/50 to-green-950/50 backdrop-blur-sm rounded-2xl border border-blue-800/30 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs font-medium text-blue-400 border-b border-blue-800/30">
              <th className="py-3 px-6">Bestellung</th>
              <th className="py-3 px-6">Kunde</th>
              <th className="py-3 px-6">Datum</th>
              <th className="py-3 px-6">Artikel</th>
              <th className="py-3 px-6">Betrag</th>
              <th className="py-3 px-6">Status</th>
            </tr>
          </thead>
          <tbody className="text-sm divide-y divide-blue-800/20">
            {orders.map((order) => (
              <tr key={order.id} className="hover:bg-blue-950/30 transition-colors">
                <td className="py-4 px-6 font-medium text-white">{order.id}</td>
                <td className="py-4 px-6">
                  <div>
                    <div className="font-medium text-white">{order.customer}</div>
                    <div className="text-xs text-blue-400">{order.email}</div>
                  </div>
                </td>
                <td className="py-4 px-6 text-blue-400">{order.date}</td>
                <td className="py-4 px-6 text-blue-400">{order.items} Artikel</td>
                <td className="py-4 px-6 font-medium text-white">{order.total}</td>
                <td className="py-4 px-6">{getStatusBadge(order.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {loading ? (
        <div className="text-center py-12 bg-gradient-to-br from-blue-950/50 to-green-950/50 backdrop-blur-sm rounded-2xl border border-blue-800/30">
          <div className="text-6xl mb-4">⏳</div>
          <p className="text-white text-lg">Lade Bestellungen...</p>
        </div>
      ) : orders.length === 0 ? (
        <div className="text-center py-12 bg-gradient-to-br from-blue-950/50 to-green-950/50 backdrop-blur-sm rounded-2xl border border-blue-800/30">
          <div className="text-6xl mb-4">📦</div>
          <p className="text-white text-lg">Keine Bestellungen gefunden</p>
          <p className="text-blue-400 mt-1">Verbinde deinen Shopify Store um Bestellungen anzuzeigen</p>
        </div>
      ) : null}
    </div>
  );
};

export default ShopifyOrders;
