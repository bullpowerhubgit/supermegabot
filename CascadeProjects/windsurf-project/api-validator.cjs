#!/usr/bin/env node

/**
 * API Validation Script
 * Tests all configured APIs for validity
 */

const https = require('https');
const http = require('http');

// Load API config
const apiConfig = require('./api-config.json');

// Colors for console output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function logSection(title) {
  console.log('\n' + '='.repeat(60));
  log(title, 'blue');
  console.log('='.repeat(60));
}

function makeRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    const urlObj = new URL(url);
    
    const reqOptions = {
      hostname: urlObj.hostname,
      port: urlObj.port || (url.startsWith('https') ? 443 : 80),
      path: urlObj.pathname + urlObj.search,
      method: options.method || 'GET',
      headers: options.headers || {}
    };

    const req = protocol.request(reqOptions, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: data
        });
      });
    });

    req.on('error', reject);
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    req.end();
  });
}

// Test OpenAI API
async function testOpenAI() {
  logSection('Testing OpenAI API');
  
  const apiKey = apiConfig.openai.apiKey;
  
  // Check key format
  const keyFormat = apiKey.startsWith('sk-proj-');
  log(`Key Format: ${keyFormat ? '✅ Valid (sk-proj-)' : '❌ Invalid'}`, keyFormat ? 'green' : 'red');
  
  if (!keyFormat) {
    log('Error: OpenAI API key should start with "sk-proj-"', 'red');
    return false;
  }
  
  try {
    const response = await makeRequest('https://api.openai.com/v1/models', {
      headers: {
        'Authorization': `Bearer ${apiKey}`
      }
    });
    
    if (response.statusCode === 200) {
      log('✅ OpenAI API is working', 'green');
      log(`Status: ${response.statusCode}`, 'green');
      return true;
    } else if (response.statusCode === 401) {
      log('❌ OpenAI API key is invalid or expired', 'red');
      log(`Status: ${response.statusCode}`, 'red');
      return false;
    } else {
      log(`⚠️ OpenAI API returned status ${response.statusCode}`, 'yellow');
      return false;
    }
  } catch (error) {
    log(`❌ OpenAI API test failed: ${error.message}`, 'red');
    return false;
  }
}

// Test Shopify API
async function testShopify() {
  logSection('Testing Shopify API');
  
  const apiKey = apiConfig.shopify.apiKey;
  const storeUrl = apiConfig.shopify.storeUrl;
  
  log(`Store URL: ${storeUrl}`, 'blue');
  log(`API Key: ${apiKey.substring(0, 10)}...`, 'blue');
  
  try {
    const response = await makeRequest(
      `https://${storeUrl}/admin/api/2026-04/shop.json`,
      {
        headers: {
          'X-Shopify-Access-Token': apiKey
        }
      }
    );
    
    if (response.statusCode === 200) {
      log('✅ Shopify API is working', 'green');
      log(`Status: ${response.statusCode}`, 'green');
      try {
        const shopData = JSON.parse(response.body);
        log(`Shop Name: ${shopData.shop.name}`, 'green');
      } catch (e) {
        log('Could not parse shop data', 'yellow');
      }
      return true;
    } else if (response.statusCode === 401) {
      log('❌ Shopify API token is invalid or expired', 'red');
      log(`Status: ${response.statusCode}`, 'red');
      log('Action: Generate new token from Shopify Admin', 'yellow');
      return false;
    } else if (response.statusCode === 404) {
      log('❌ Shopify store not found', 'red');
      log(`Status: ${response.statusCode}`, 'red');
      return false;
    } else {
      log(`⚠️ Shopify API returned status ${response.statusCode}`, 'yellow');
      return false;
    }
  } catch (error) {
    log(`❌ Shopify API test failed: ${error.message}`, 'red');
    return false;
  }
}

// Test Etsy API
async function testEtsy() {
  logSection('Testing Etsy API');
  
  const apiKey = apiConfig.etsy.apiKey;
  
  log(`API Key: ${apiKey}`, 'blue');
  
  try {
    // Test with a simple ping request
    const response = await makeRequest(
      `https://openapi.etsy.com/v3/application/openapi-ping`,
      {
        headers: {
          'x-api-key': apiKey
        }
      }
    );
    
    if (response.statusCode === 200) {
      log('✅ Etsy API is accessible', 'green');
      log(`Status: ${response.statusCode}`, 'green');
      return true;
    } else if (response.statusCode === 401 || response.statusCode === 403) {
      log('❌ Etsy API key is invalid', 'red');
      log(`Status: ${response.statusCode}`, 'red');
      return false;
    } else {
      log(`⚠️ Etsy API returned status ${response.statusCode}`, 'yellow');
      return false;
    }
  } catch (error) {
    log(`❌ Etsy API test failed: ${error.message}`, 'red');
    return false;
  }
}

// Test Perplexity API
async function testPerplexity() {
  logSection('Testing Perplexity API');
  
  const apiKey = apiConfig.perplexity.apiKey;
  
  log(`API Key: ${apiKey.substring(0, 10)}...`, 'blue');
  
  try {
    // Use chat completions endpoint instead of models
    const response = await makeRequest('https://api.perplexity.ai/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });
    
    // 401 means invalid key, 422/400 means missing body (expected - key is valid), 200+ means key is valid
    if (response.statusCode === 401) {
      log('❌ Perplexity API key is invalid', 'red');
      log(`Status: ${response.statusCode}`, 'red');
      return false;
    } else if (response.statusCode === 422 || response.statusCode === 400) {
      log('✅ Perplexity API key is valid (endpoint accessible)', 'green');
      log(`Status: ${response.statusCode} (expected - missing request body)`, 'green');
      return true;
    } else if (response.statusCode === 200) {
      log('✅ Perplexity API is working', 'green');
      log(`Status: ${response.statusCode}`, 'green');
      return true;
    } else {
      log(`⚠️ Perplexity API returned status ${response.statusCode}`, 'yellow');
      return false;
    }
  } catch (error) {
    log(`❌ Perplexity API test failed: ${error.message}`, 'red');
    return false;
  }
}

// Test Printful API
async function testPrintful() {
  logSection('Testing Printful API');
  
  const apiKey = apiConfig.printful.apiKey;
  
  log(`API Key: ${apiKey.substring(0, 10)}...`, 'blue');
  
  try {
    const response = await makeRequest('https://api.printful.com/orders', {
      headers: {
        'Authorization': `Bearer ${apiKey}`
      }
    });
    
    if (response.statusCode === 200) {
      log('✅ Printful API is working', 'green');
      log(`Status: ${response.statusCode}`, 'green');
      try {
        const data = JSON.parse(response.body);
        log(`Orders found: ${data.code}`, 'green');
      } catch (e) {
        log('Could not parse response data', 'yellow');
      }
      return true;
    } else if (response.statusCode === 401) {
      log('❌ Printful API key is invalid', 'red');
      log(`Status: ${response.statusCode}`, 'red');
      return false;
    } else {
      log(`⚠️ Printful API returned status ${response.statusCode}`, 'yellow');
      return false;
    }
  } catch (error) {
    log(`❌ Printful API test failed: ${error.message}`, 'red');
    return false;
  }
}

// Main execution
async function main() {
  log('🔍 API Validation Script', 'blue');
  log('Testing all configured APIs...\n', 'blue');
  
  const results = {
    openai: await testOpenAI(),
    shopify: await testShopify(),
    etsy: await testEtsy(),
    perplexity: await testPerplexity(),
    printful: await testPrintful()
  };
  
  // Summary
  logSection('Summary');
  
  const working = Object.values(results).filter(r => r).length;
  const total = Object.keys(results).length;
  
  log(`Working APIs: ${working}/${total}`, working === total ? 'green' : 'yellow');
  
  Object.entries(results).forEach(([api, status]) => {
    const symbol = status ? '✅' : '❌';
    const color = status ? 'green' : 'red';
    log(`${symbol} ${api.toUpperCase()}: ${status ? 'PASS' : 'FAIL'}`, color);
  });
  
  // Recommendations
  logSection('Recommendations');
  
  if (!results.openai) {
    log('• OpenAI: Generate new API key from https://platform.openai.com/api-keys', 'yellow');
  }
  if (!results.shopify) {
    log('• Shopify: Generate new token from Shopify Admin > Apps > Manage private apps', 'yellow');
  }
  if (!results.etsy) {
    log('• Etsy: Verify API key from https://developer.etsy.com/my-apps', 'yellow');
  }
  if (!results.perplexity) {
    log('• Perplexity: Generate new API key from https://www.perplexity.ai/settings/api', 'yellow');
  }
  if (!results.printful) {
    log('• Printful: Verify API key from https://www.printful.com/dashboard/integrations', 'yellow');
  }
  
  console.log('\n');
}

main().catch(error => {
  log(`Fatal error: ${error.message}`, 'red');
  process.exit(1);
});
