import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import axios from 'axios';

dotenv.config();

const app = express();
const PORT = process.env.QUICKCASH_PORT || 3001;

app.use(cors());
app.use(express.json());

// API Key validation middleware
const validateApiKey = (req, res, next) => {
  const apiKey = req.headers['x-api-key'];
  const validKey = process.env.QUICKCASH_API_KEY || process.env.ANTHROPIC_API_KEY;
  
  if (!apiKey || apiKey !== validKey) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
};

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Claude API proxy
app.post('/api/claude', validateApiKey, async (req, res) => {
  try {
    const { prompt, model = 'claude-sonnet-4-20250514', maxTokens = 1000 } = req.body;
    
    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    if (!anthropicKey) {
      return res.status(400).json({ error: 'Anthropic API key not configured' });
    }

    const response = await axios.post('https://api.anthropic.com/v1/messages', {
      model: model,
      max_tokens: maxTokens,
      messages: [{ role: 'user', content: prompt }]
    }, {
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01'
      }
    });

    res.json({
      success: true,
      text: response.data.content[0].text,
      inputTokens: response.data.usage?.input_tokens || 0,
      outputTokens: response.data.usage?.output_tokens || 0
    });
  } catch (error) {
    console.error('Claude error:', error.response?.data || error.message);
    res.status(500).json({ error: error.response?.data || 'Failed to call Claude API' });
  }
});

// QuickCash Tool 1 - Service Offering Generator
app.post('/api/quickcash/1', validateApiKey, async (req, res) => {
  try {
    const { service, price, turnaround } = req.body;
    
    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    if (!anthropicKey) {
      return res.status(400).json({ error: 'Anthropic API key not configured' });
    }

    const prompt = `Generate a professional ${service} offering with ${turnaround} hour turnaround, priced at $${price}. Include:
1. A compelling title
2. Detailed description
3. Key features/benefits
4. Deliverables list
5. Pricing breakdown`;

    const response = await axios.post('https://api.anthropic.com/v1/messages', {
      model: 'claude-sonnet-4-20250514',
      max_tokens: 2000,
      messages: [{ role: 'user', content: prompt }]
    }, {
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01'
      }
    });

    res.json({
      output: response.data.content[0].text,
      stats: {
        calls: 1,
        inputTokens: response.data.usage?.input_tokens || 0,
        outputTokens: response.data.usage?.output_tokens || 0,
        cost: ((response.data.usage?.input_tokens || 0) / 1_000_000 * 3.0 + (response.data.usage?.output_tokens || 0) / 1_000_000 * 15.0)
      }
    });
  } catch (error) {
    console.error('QuickCash Tool 1 error:', error.response?.data || error.message);
    res.status(500).json({ error: error.response?.data || 'Failed to generate service offering' });
  }
});

// QuickCash Tool 2 - Lead Generation Strategy
app.post('/api/quickcash/2', validateApiKey, async (req, res) => {
  try {
    const { industry, location, leadPrice } = req.body;
    
    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    if (!anthropicKey) {
      return res.status(400).json({ error: 'Anthropic API key not configured' });
    }

    const prompt = `Generate a lead generation strategy for ${industry} businesses in ${location}. Each lead is priced at $${leadPrice}. Include:
1. Target customer profile
2. Outreach strategy
3. Value proposition
4. Email templates
5. Follow-up sequence`;

    const response = await axios.post('https://api.anthropic.com/v1/messages', {
      model: 'claude-sonnet-4-20250514',
      max_tokens: 2000,
      messages: [{ role: 'user', content: prompt }]
    }, {
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01'
      }
    });

    res.json({
      output: response.data.content[0].text,
      stats: {
        calls: 1,
        inputTokens: response.data.usage?.input_tokens || 0,
        outputTokens: response.data.usage?.output_tokens || 0,
        cost: ((response.data.usage?.input_tokens || 0) / 1_000_000 * 3.0 + (response.data.usage?.output_tokens || 0) / 1_000_000 * 15.0)
      }
    });
  } catch (error) {
    console.error('QuickCash Tool 2 error:', error.response?.data || error.message);
    res.status(500).json({ error: error.response?.data || 'Failed to generate lead strategy' });
  }
});

// QuickCash Tool 3 - Upwork Gig Profile
app.post('/api/quickcash/3', validateApiKey, async (req, res) => {
  try {
    const { gigType, hourlyRate, deliverables } = req.body;
    
    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    if (!anthropicKey) {
      return res.status(400).json({ error: 'Anthropic API key not configured' });
    }

    const prompt = `Create an optimized Upwork gig profile for ${gigType} with hourly rate $${hourlyRate}. Deliverables: ${deliverables}. Include:
1. Compelling gig title
2. Professional description
3. Skills list
4. Portfolio suggestions
5. Pricing tiers`;

    const response = await axios.post('https://api.anthropic.com/v1/messages', {
      model: 'claude-sonnet-4-20250514',
      max_tokens: 2000,
      messages: [{ role: 'user', content: prompt }]
    }, {
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01'
      }
    });

    res.json({
      output: response.data.content[0].text,
      stats: {
        calls: 1,
        inputTokens: response.data.usage?.input_tokens || 0,
        outputTokens: response.data.usage?.output_tokens || 0,
        cost: ((response.data.usage?.input_tokens || 0) / 1_000_000 * 3.0 + (response.data.usage?.output_tokens || 0) / 1_000_000 * 15.0)
      }
    });
  } catch (error) {
    console.error('QuickCash Tool 3 error:', error.response?.data || error.message);
    res.status(500).json({ error: error.response?.data || 'Failed to generate gig profile' });
  }
});

app.listen(PORT, () => {
  console.log(`🚀 QuickCash Backend läuft auf Port ${PORT}`);
  console.log(`📡 API Endpunkte:`);
  console.log(`   - /health`);
  console.log(`   - /api/claude`);
  console.log(`   - /api/quickcash/1`);
  console.log(`   - /api/quickcash/2`);
  console.log(`   - /api/quickcash/3`);
});
