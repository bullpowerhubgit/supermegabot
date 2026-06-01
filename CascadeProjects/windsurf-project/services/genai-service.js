/**
 * Google Cloud GenAI Service
 * Centralized service for Google AI Platform integration
 */

import axios from 'axios';
import centralConfig from '../config/central-api-config.js';

class GenAIService {
  constructor() {
    this.config = centralConfig.getGenAIConfig();
    this.client = null;
    this.isInitialized = false;
    
    if (centralConfig.isGenAIAvailable()) {
      this.initialize();
    }
  }

  /**
   * Initialize the GenAI client
   */
  initialize() {
    try {
      const clientConfig = centralConfig.createGenAIClientConfig();
      
      this.client = axios.create({
        baseURL: clientConfig.baseURL,
        timeout: 30000,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${clientConfig.apiKey}`
        }
      });

      this.config = clientConfig;
      this.isInitialized = true;
      
      console.log('[GenAI] Service initialized successfully');
    } catch (error) {
      console.error('[GenAI] Initialization failed:', error.message);
      this.isInitialized = false;
    }
  }

  /**
   * Generate content using Gemini model
   */
  async generateContent(prompt, options = {}) {
    if (!this.isInitialized) {
      throw new Error('GenAI service not initialized');
    }

    const requestData = {
      contents: [{
        parts: [{
          text: prompt
        }]
      }],
      generationConfig: {
        temperature: options.temperature || this.config.temperature,
        maxOutputTokens: options.maxTokens || this.config.maxTokens,
        topK: options.topK || 40,
        topP: options.topP || 0.95,
        candidateCount: 1,
        stopSequences: options.stopSequences || []
      },
      safetySettings: this.getDefaultSafetySettings()
    };

    try {
      const response = await this.client.post('', requestData);
      return this.parseResponse(response.data);
    } catch (error) {
      console.error('[GenAI] Content generation failed:', error.message);
      throw new Error(`GenAI generation failed: ${error.message}`);
    }
  }

  /**
   * Generate marketing copy
   */
  async generateMarketingCopy(productInfo, options = {}) {
    const prompt = `Generate compelling marketing copy for this product:
    
    Product: ${productInfo.name}
    Price: €${productInfo.price}
    Description: ${productInfo.description}
    Category: ${productInfo.category || 'N/A'}
    
    Generate:
    1. Short tagline (max 50 chars)
    2. Product description (100-150 words)
    3. 3 key benefits
    4. Call to action
    5. 5 SEO keywords
    
    Format as JSON with keys: tagline, description, benefits, callToAction, keywords`;

    const result = await this.generateContent(prompt, {
      temperature: options.temperature || 0.8,
      maxTokens: options.maxTokens || 800
    });

    try {
      return JSON.parse(result.text);
    } catch (parseError) {
      console.error('[GenAI] Failed to parse marketing copy JSON:', parseError.message);
      throw new Error('Failed to generate marketing copy');
    }
  }

  /**
   * Generate email content
   */
  async generateEmailContent(templateType, data, options = {}) {
    const prompt = `Generate ${templateType} email content:
    
    Template Type: ${templateType}
    Data: ${JSON.stringify(data)}
    
    Generate:
    1. Subject line (max 50 chars)
    2. Preheader (max 100 chars)
    3. Email body (engaging, persuasive)
    4. Call to action
    5. Personalization elements
    
    Format as JSON with keys: subject, preheader, body, callToAction, personalization`;

    const result = await this.generateContent(prompt, {
      temperature: options.temperature || 0.7,
      maxTokens: options.maxTokens || 1000
    });

    try {
      return JSON.parse(result.text);
    } catch (parseError) {
      console.error('[GenAI] Failed to parse email content JSON:', parseError.message);
      throw new Error('Failed to generate email content');
    }
  }

  /**
   * Generate social media content
   */
  async generateSocialMediaContent(productInfo, platforms, options = {}) {
    const prompt = `Generate social media content for this product:
    
    Product: ${productInfo.name}
    Price: €${productInfo.price}
    Description: ${productInfo.description}
    Platforms: ${platforms.join(', ')}
    
    Generate platform-specific content for each platform:
    - Facebook (engaging, shareable)
    - Instagram (visual-focused, hashtags)
    - Pinterest (inspirational, SEO keywords)
    - TikTok (trending, short-form)
    
    Include captions, hashtags, and posting suggestions.
    Format as JSON with platform names as keys`;

    const result = await this.generateContent(prompt, {
      temperature: options.temperature || 0.9,
      maxTokens: options.maxTokens || 1200
    });

    try {
      return JSON.parse(result.text);
    } catch (parseError) {
      console.error('[GenAI] Failed to parse social media content JSON:', parseError.message);
      throw new Error('Failed to generate social media content');
    }
  }

  /**
   * Analyze customer sentiment
   */
  async analyzeSentiment(text, options = {}) {
    const prompt = `Analyze the sentiment of this customer feedback:
    
    Feedback: "${text}"
    
    Provide:
    1. Overall sentiment (positive/neutral/negative)
    2. Sentiment score (-1 to 1)
    3. Key emotions detected
    4. Main topics mentioned
    5. Actionable insights
    
    Format as JSON with keys: sentiment, score, emotions, topics, insights`;

    const result = await this.generateContent(prompt, {
      temperature: options.temperature || 0.3,
      maxTokens: options.maxTokens || 500
    });

    try {
      return JSON.parse(result.text);
    } catch (parseError) {
      console.error('[GenAI] Failed to parse sentiment analysis JSON:', parseError.message);
      throw new Error('Failed to analyze sentiment');
    }
  }

  /**
   * Generate product recommendations
   */
  async generateProductRecommendations(customerProfile, products, options = {}) {
    const prompt = `Generate personalized product recommendations:
    
    Customer Profile: ${JSON.stringify(customerProfile)}
    Available Products: ${JSON.stringify(products.map(p => ({ id: p.id, name: p.name, category: p.category, price: p.price })))}
    
    Provide:
    1. Top 5 recommended products
    2. Reasoning for each recommendation
    3. Personalized message for each product
    4. Cross-sell opportunities
    
    Format as JSON with keys: recommendations, reasoning, messages, crossSell`;

    const result = await this.generateContent(prompt, {
      temperature: options.temperature || 0.6,
      maxTokens: options.maxTokens || 1000
    });

    try {
      return JSON.parse(result.text);
    } catch (parseError) {
      console.error('[GenAI] Failed to parse recommendations JSON:', parseError.message);
      throw new Error('Failed to generate recommendations');
    }
  }

  /**
   * Parse Gemini API response
   */
  parseResponse(data) {
    if (!data.candidates || data.candidates.length === 0) {
      throw new Error('No candidates in response');
    }

    const candidate = data.candidates[0];
    if (!candidate.content || !candidate.content.parts || candidate.content.parts.length === 0) {
      throw new Error('No content in candidate response');
    }

    const text = candidate.content.parts[0].text;
    
    return {
      text,
      finishReason: candidate.finishReason,
      safetyRatings: candidate.safetyRatings || [],
      tokenCount: this.extractTokenUsage(data)
    };
  }

  /**
   * Extract token usage from response
   */
  extractTokenUsage(data) {
    const metadata = data.usageMetadata;
    if (!metadata) return null;

    return {
      promptTokens: metadata.promptTokenCount,
      candidatesTokens: metadata.candidatesTokenCount,
      totalTokens: metadata.totalTokenCount
    };
  }

  /**
   * Get default safety settings
   */
  getDefaultSafetySettings() {
    return [
      {
        category: "HARM_CATEGORY_HARASSMENT",
        threshold: "BLOCK_MEDIUM_AND_ABOVE"
      },
      {
        category: "HARM_CATEGORY_HATE_SPEECH",
        threshold: "BLOCK_MEDIUM_AND_ABOVE"
      },
      {
        category: "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold: "BLOCK_MEDIUM_AND_ABOVE"
      },
      {
        category: "HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold: "BLOCK_MEDIUM_AND_ABOVE"
      }
    ];
  }

  /**
   * Health check
   */
  async healthCheck() {
    try {
      if (!this.isInitialized) {
        return {
          status: 'unhealthy',
          error: 'GenAI service not initialized',
          timestamp: new Date().toISOString()
        };
      }

      // Test with a simple prompt
      const testResult = await this.generateContent('Hello', { maxTokens: 10 });
      
      return {
        status: 'healthy',
        genaiAvailable: true,
        model: this.config.model,
        projectId: this.config.projectId,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        genaiAvailable: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Get service status
   */
  getStatus() {
    return {
      initialized: this.isInitialized,
      config: {
        projectId: this.config.projectId,
        region: this.config.region,
        model: this.config.model,
        temperature: this.config.temperature,
        maxTokens: this.config.maxTokens
      },
      available: centralConfig.isGenAIAvailable()
    };
  }
}

// Singleton instance
let genaiService = null;

function getGenAIService() {
  if (!genaiService) {
    genaiService = new GenAIService();
  }
  return genaiService;
}

export {
  GenAIService,
  getGenAIService
};
