/**
 * Klaviyo Webhook Handler für RUDIBOT
 * Empfängt Events von Shopify, Telegram etc. und leitet an Klaviyo weiter
 */

const KlaviyoService = require('./klaviyo');

const klaviyo = new KlaviyoService();

module.exports = async (req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { source, event, data } = req.body;

    switch (source) {
      case 'shopify':
        return await handleShopifyEvent(event, data, res);
      
      case 'telegram':
        return await handleTelegramEvent(event, data, res);
      
      default:
        return res.status(400).json({ error: 'Unknown source' });
    }
  } catch (error) {
    console.error('Klaviyo Webhook Error:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
};

async function handleShopifyEvent(event, data, res) {
  switch (event) {
    case 'order_created':
      const result = await klaviyo.trackShopifyOrder(data);
      return res.status(result.success ? 200 : 400).json(result);
    
    case 'customer_created':
      const profileResult = await klaviyo.createOrUpdateProfile(data.email, {
        first_name: data.first_name,
        last_name: data.last_name,
        phone: data.phone,
        accepts_marketing: data.accepts_marketing
      });
      return res.status(profileResult.success ? 200 : 400).json(profileResult);
    
    default:
      return res.status(400).json({ error: 'Unknown Shopify event' });
  }
}

async function handleTelegramEvent(event, data, res) {
  switch (event) {
    case 'newsletter_signup':
      const result = await klaviyo.createOrUpdateProfile(data.email, {
        source: 'telegram_bot',
        signup_date: new Date().toISOString()
      });
      
      if (result.success) {
        // Zur Newsletter-Liste hinzufügen
        const lists = await klaviyo.getLists();
        if (lists.success && lists.data.length > 0) {
          await klaviyo.addProfileToList(lists.data[0].id, [result.profile.data.id]);
        }
      }
      
      return res.status(result.success ? 200 : 400).json(result);
    
    default:
      return res.status(400).json({ error: 'Unknown Telegram event' });
  }
}
