// ============================================================
// digistore-automation.js — Affiliate Marketing Automation
// Rudolf Sarkany · Automated Affiliate Content Distribution
// ============================================================
'use strict';
require('dotenv').config();

const fs = require('fs');
const path = require('path');

// ── Config ────────────────────────────────────────────────────
const DIGISTORE_API_KEY = process.env.DIGISTORE_API_KEY;
const DIGISTORE_API_SECRET = process.env.DIGISTORE_API_SECRET;

if (!DIGISTORE_API_KEY || DIGISTORE_API_KEY.includes('PLACEHOLDER')) {
  console.error('❌ DIGISTORE_API_KEY nicht konfiguriert!');
  process.exit(1);
}

const API_BASE = 'https://www.digistore24.com/api';

// ── Affiliate Content Templates ───────────────────────────────────
const CONTENT_TEMPLATES = {
  blog_post: {
    title: "Top {product_category} Products That Actually Work in 2025",
    structure: {
      intro: "Are you looking for the best {product_category} solutions? After extensive research...",
      benefits: "Here are the key benefits of {product_name}:",
      features: "What makes {product_name} stand out:",
      conclusion: "Based on our analysis, {product_name} offers exceptional value..."
    },
    cta: "Click here to get instant access to {product_name}"
  },
  social_media: {
    facebook: "🔥 Just discovered {product_name} - absolutely game-changing for {product_category}! 💯",
    instagram: "Transform your {product_category} with {product_name} ✨ Link in bio for exclusive discount!",
    twitter: "{product_name} is revolutionizing {product_category}. Here's why you need to check this out 👇"
  },
  email_campaign: {
    subject: "🎯 Exclusive: {product_name} - Limited Time Offer",
    body: `Hi {name},

I've been testing {product_name} for the past few weeks, and I'm absolutely impressed...

{product_benefits}

This is perfect for anyone looking to {solve_problem}.

{cta}

Best regards,
{sender_name}`
  }
};

// ── Product Categories ───────────────────────────────────────────
const PRODUCT_CATEGORIES = [
  'online business', 'digital marketing', 'health & fitness', 
  'personal development', 'software tools', 'trading & investing',
  'dating & relationships', 'language learning', 'productivity'
];

// ── Digistore API Helpers ───────────────────────────────────────
async function digistoreFetch(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = require('crypto')
    .createHmac('sha256', DIGISTORE_API_SECRET)
    .update(`${timestamp}${endpoint}`)
    .digest('hex');

  const response = await fetch(url, {
    ...options,
    headers: {
      'X-Api-Key': DIGISTORE_API_KEY,
      'X-Api-Signature': signature,
      'X-Api-Timestamp': timestamp.toString(),
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  });

  if (!response.ok) {
    throw new Error(`Digistore API ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

// ── Content Generation with AI ───────────────────────────────────
async function generateAffiliateContent(product, contentType = 'blog_post') {
  try {
    const template = CONTENT_TEMPLATES[contentType];
    if (!template) {
      throw new Error(`Template not found for ${contentType}`);
    }

    const prompt = `Generate compelling affiliate marketing content for:
    Product: ${product.name}
    Category: ${product.category}
    Commission: ${product.commission}%
    Price: ${product.price} EUR
    Description: ${product.description}
    
    Content Type: ${contentType}
    
    Follow this template structure:
    ${JSON.stringify(template, null, 2)}
    
    Make it persuasive, authentic, and include a strong call-to-action. 
    Focus on benefits, not just features. Use emotional triggers.
    Length: 500-800 words for blog posts, 100-200 for social media.`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1500,
        messages: [{ role: 'user', content: prompt }]
      })
    });

    const data = await response.json();
    return data.content?.[0]?.text || '';
  } catch (error) {
    console.error('Content Generation Error:', error.message);
    return null;
  }
}

// ── Get Top Converting Products ───────────────────────────────────
async function getTopProducts(category = null, limit = 10) {
  try {
    let endpoint = '/products/top';
    if (category) {
      endpoint += `?category=${encodeURIComponent(category)}`;
    }
    
    const products = await digistoreFetch(endpoint);
    return products.slice(0, limit);
  } catch (error) {
    console.error('Failed to fetch products:', error.message);
    return [];
  }
}

// ── Content Distribution ─────────────────────────────────────────
async function distributeContent(content, platforms = ['blog', 'social', 'email']) {
  const results = [];
  
  for (const platform of platforms) {
    try {
      switch (platform) {
        case 'blog':
          // Save to blog posts directory
          const blogPath = `content/blog/${Date.now()}.md`;
          fs.writeFileSync(blogPath, content);
          results.push({ platform: 'blog', status: 'published', path: blogPath });
          break;
          
        case 'social':
          // Queue for social media posting
          const socialPath = `content/social/${Date.now()}.json`;
          fs.writeFileSync(socialPath, JSON.stringify({
            content: content,
            platforms: ['facebook', 'instagram', 'twitter'],
            scheduled: new Date().toISOString()
          }, null, 2));
          results.push({ platform: 'social', status: 'queued', path: socialPath });
          break;
          
        case 'email':
          // Save to email campaigns
          const emailPath = `content/email/${Date.now()}.html`;
          fs.writeFileSync(emailPath, content);
          results.push({ platform: 'email', status: 'ready', path: emailPath });
          break;
      }
    } catch (error) {
      results.push({ platform, status: 'error', error: error.message });
    }
  }
  
  return results;
}

// ── Campaign Automation ───────────────────────────────────────────
async function runAffiliateCampaign(options = {}) {
  const {
    category = null,
    productCount = 5,
    contentTypes = ['blog_post', 'social_media'],
    platforms = ['blog', 'social']
  } = options;
  
  console.log(`🚀 Starting affiliate campaign...`);
  console.log(`📦 Products: ${productCount} | 📝 Content: ${contentTypes.join(', ')} | 📱 Platforms: ${platforms.join(', ')}`);
  
  // Get top products
  const products = await getTopProducts(category, productCount);
  console.log(`📊 Found ${products.length} products`);
  
  const campaignResults = [];
  
  for (let i = 0; i < products.length; i++) {
    const product = products[i];
    console.log(`\n${i + 1}/${products.length}: Processing ${product.name}`);
    
    // Generate content for each type
    for (const contentType of contentTypes) {
      console.log(`  📝 Generating ${contentType}...`);
      const content = await generateAffiliateContent(product, contentType);
      
      if (content) {
        // Distribute content
        const distribution = await distributeContent(content, platforms);
        campaignResults.push({
          product: product.name,
          contentType,
          distribution,
          timestamp: new Date().toISOString()
        });
        
        console.log(`  ✅ Content generated and distributed`);
      }
      
      // Rate limiting
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
  }
  
  // Save campaign results
  const campaignLog = {
    id: Date.now(),
    options,
    results: campaignResults,
    totalProducts: products.length,
    totalContent: campaignResults.length,
    estimatedRevenue: campaignResults.length * 25 * 30, // 25 EUR avg commission x 30 days
    createdAt: new Date().toISOString()
  };
  
  fs.writeFileSync('logs/affiliate-campaigns.json', JSON.stringify(campaignLog, null, 2));
  
  return campaignLog;
}

// ── Performance Tracking ───────────────────────────────────────
async function trackPerformance() {
  try {
    const stats = await digistoreFetch('/affiliate/stats');
    return {
      totalClicks: stats.clicks || 0,
      totalConversions: stats.conversions || 0,
      totalRevenue: stats.revenue || 0,
      conversionRate: stats.conversion_rate || 0,
      avgCommission: stats.avg_commission || 0
    };
  } catch (error) {
    console.error('Performance tracking error:', error.message);
    return null;
  }
}

// ── Main Execution ───────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  
  switch (command) {
    case 'campaign':
      const options = {
        category: args.includes('--category') ? args[args.indexOf('--category') + 1] : null,
        productCount: parseInt(args.find(arg => arg.startsWith('--count='))?.split('=')[1]) || 5,
        contentTypes: args.includes('--social') ? ['blog_post', 'social_media'] : ['blog_post'],
        platforms: args.includes('--email') ? ['blog', 'social', 'email'] : ['blog', 'social']
      };
      
      const campaign = await runAffiliateCampaign(options);
      console.log(`\n✅ Campaign completed!`);
      console.log(`📊 Generated ${campaign.totalContent} pieces of content`);
      console.log(`💰 Estimated monthly revenue: ${campaign.estimatedRevenue} EUR`);
      break;
      
    case 'products':
      const category = args[1];
      const products = await getTopProducts(category, 10);
      console.log('\n📦 Top Products:');
      products.forEach((p, i) => {
        console.log(`${i + 1}. ${p.name} - ${p.commission}% commission - ${p.price} EUR`);
      });
      break;
      
    case 'stats':
      const stats = await trackPerformance();
      if (stats) {
        console.log('\n📈 Affiliate Performance:');
        console.log(`🖱️  Clicks: ${stats.totalClicks}`);
        console.log(`💰 Conversions: ${stats.totalConversions}`);
        console.log(`💵 Revenue: ${stats.totalRevenue} EUR`);
        console.log(`📊 Conversion Rate: ${stats.conversionRate}%`);
        console.log(`💳 Avg Commission: ${stats.avgCommission} EUR`);
      }
      break;
      
    default:
      console.log(`
🤖 Digistore24 Automation Commands:

  campaign [options] - Run affiliate campaign
    --category [name]  - Filter by product category
    --count [number]   - Number of products (default: 5)
    --social          - Include social media content
    --email           - Include email campaigns
    
  products [category] - List top products
  stats              - Show performance statistics
  
Examples:
  node scripts/digistore-automation.js campaign --count 10 --social --email
  node scripts/digistore-automation.js products "online business"
      `);
  }
}

// ── START ────────────────────────────────────────────────────────
if (require.main === module) {
  main().catch(console.error);
}

module.exports = {
  runAffiliateCampaign,
  generateAffiliateContent,
  getTopProducts,
  trackPerformance
};
