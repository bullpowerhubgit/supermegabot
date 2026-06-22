import React, { useEffect, useState } from 'react';
import axios from 'axios';

const Customers: React.FC = () => {
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('/api/shopify/customers').then(r => setCustomers(r.data?.customers || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-gray-500">Lade Kunden...</div>;

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-800 mb-6">Kunden</h2>
      {customers.length === 0 ? (
        <div className="bg-white rounded-xl p-8 text-center text-gray-500 shadow">Noch keine Kunden vorhanden.</div>
      ) : (
        <div className="bg-white rounded-xl shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50"><tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">E-Mail</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Bestellungen</th>
            </tr></thead>
            <tbody className="divide-y divide-gray-200">
              {customers.map((c: any) => (
                <tr key={c.id}>
                  <td className="px-6 py-4">{c.first_name} {c.last_name}</td>
                  <td className="px-6 py-4">{c.email}</td>
                  <td className="px-6 py-4">{c.orders_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Customers;
