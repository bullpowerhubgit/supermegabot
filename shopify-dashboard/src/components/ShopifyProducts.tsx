import React, { useEffect, useState } from 'react';
import axios from 'axios';

const ShopifyProducts: React.FC = () => {
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get('/api/shopify/products?limit=50').then(r => setProducts(r.data?.products || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-gray-500">Lade Produkte...</div>;

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-800 mb-6">Produkte ({products.length})</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {products.length === 0 ? (
          <div className="col-span-3 bg-white rounded-xl p-8 text-center text-gray-500 shadow">Keine Produkte gefunden.</div>
        ) : products.map((p: any) => (
          <div key={p.id} className="bg-white rounded-xl p-4 shadow">
            {p.images?.[0] && <img src={p.images[0].src} alt={p.title} className="w-full h-40 object-cover rounded-lg mb-3" />}
            <h3 className="font-semibold text-gray-800 truncate">{p.title}</h3>
            <p className="text-green-600 font-bold mt-1">{p.variants?.[0]?.price ? `€${p.variants[0].price}` : '—'}</p>
            <span className={`text-xs px-2 py-1 rounded-full mt-2 inline-block ${p.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
              {p.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ShopifyProducts;
