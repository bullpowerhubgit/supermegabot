/**
 * GCP Cloud Function - Anthropic Claude Proxy
 * Alternative zu Vercel API Route
 * Project: gen-lang-client-0895465231
 */

const { Anthropic } = require('@anthropic-ai/sdk');

exports.claudeProxy = async (req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-api-key');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }
  
  const apiKey = process.env.ANTHROPIC_API_KEY;
  
  if (!apiKey) {
    console.error('ANTHROPIC_API_KEY not set in environment variables');
    return res.status(500).json({ 
      error: 'API configuration error',
      message: 'ANTHROPIC_API_KEY not configured'
    });
  }
  
  try {
    const anthropic = new Anthropic({
      apiKey: apiKey
    });
    
    const response = await anthropic.messages.create(req.body);
    
    res.status(200).json(response);
  } catch (error) {
    console.error('Claude API error:', error);
    res.status(500).json({ 
      error: 'Proxy error',
      message: error.message
    });
  }
};
