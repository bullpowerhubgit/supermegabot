/**
 * GCP Cloud Function - Vertex AI Proxy
 * Alternative zu Anthropic Claude API
 * Project: gen-lang-client-0895465231
 * Model: gemini-1.5-pro
 */

const { VertexAI } = require('@google-cloud/vertexai');

exports.vertexAIProxy = async (req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }
  
  const projectId = process.env.GCP_PROJECT_ID || 'gen-lang-client-0895465231';
  const location = process.env.GCP_LOCATION || 'us-central1';
  const model = process.env.VERTEX_MODEL || 'gemini-1.5-pro';
  
  try {
    const vertexAI = new VertexAI({
      project: projectId,
      location: location
    });
    
    const generativeModel = vertexAI.preview.getGenerativeModel({
      model: model
    });
    
    // Anthropic Format zu Vertex AI Format konvertieren
    const messages = req.body.messages || [];
    const prompt = messages.map(m => m.content).join('\n');
    
    const request = {
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        maxOutputTokens: req.body.max_tokens || 1000,
        temperature: req.body.temperature || 0.7
      }
    };
    
    const result = await generativeModel.generateContent(request);
    const response = result.response;
    const text = response.candidates[0].content.parts[0].text;
    
    // Vertex AI Response zu Anthropic Format konvertieren
    const anthropicFormat = {
      id: `msg_${Date.now()}`,
      type: 'message',
      role: 'assistant',
      content: [{
        type: 'text',
        text: text
      }],
      model: model,
      stop_reason: 'end_turn',
      usage: {
        input_tokens: response.usageMetadata?.promptTokenCount || 0,
        output_tokens: response.usageMetadata?.candidatesTokenCount || 0
      }
    };
    
    res.status(200).json(anthropicFormat);
  } catch (error) {
    console.error('Vertex AI error:', error);
    res.status(500).json({ 
      error: 'Vertex AI error',
      message: error.message
    });
  }
};
