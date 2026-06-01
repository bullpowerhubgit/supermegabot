#!/usr/bin/env node

/**
 * API Update Helper Script
 * Interactive script to update API keys in the system
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function logSection(title) {
  console.log('\n' + '='.repeat(60));
  log(title, 'cyan');
  console.log('='.repeat(60));
}

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(prompt) {
  return new Promise((resolve) => {
    rl.question(prompt, resolve);
  });
}

// Load current config
const configPath = path.join(__dirname, 'api-config.json');
const apiConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const secureApiPath = path.join(__dirname, 'RudiBot-Secure-API', 'api-keys.txt');
let secureApiContent = '';
if (fs.existsSync(secureApiPath)) {
  secureApiContent = fs.readFileSync(secureApiPath, 'utf8');
}

async function updateShopify() {
  logSection('Shopify API Token Update');
  
  log('Current Token:', 'yellow');
  log(apiConfig.shopify.apiKey.substring(0, 15) + '...', 'yellow');
  
  const newToken = await question('\nEnter new Shopify Admin API Access Token (or press Enter to skip): ');
  
  if (newToken.trim()) {
    apiConfig.shopify.apiKey = newToken.trim();
    apiConfig.shopify.password = newToken.trim();
    
    // Update secure API file
    secureApiContent = secureApiContent.replace(
      /SHOPIFY_ACCESS_TOKEN=.*/,
      `SHOPIFY_ACCESS_TOKEN=${newToken.trim()}`
    );
    
    log('✅ Shopify token updated', 'green');
    return true;
  } else {
    log('⏭️  Skipped Shopify update', 'yellow');
    return false;
  }
}

async function updateEtsy() {
  logSection('Etsy API Key Update');
  
  log('Current API Key:', 'yellow');
  log(apiConfig.etsy.apiKey, 'yellow');
  
  const newKey = await question('\nEnter new Etsy API Key String (or press Enter to skip): ');
  
  if (newKey.trim()) {
    apiConfig.etsy.apiKey = newKey.trim();
    
    const newSecret = await question('Enter new Etsy Shared Secret (or press Enter to keep current): ');
    if (newSecret.trim()) {
      apiConfig.etsy.sharedSecret = newSecret.trim();
    }
    
    log('✅ Etsy API key updated', 'green');
    return true;
  } else {
    log('⏭️  Skipped Etsy update', 'yellow');
    return false;
  }
}

async function updatePerplexity() {
  logSection('Perplexity API Key Update');
  
  log('Current API Key:', 'yellow');
  log(apiConfig.perplexity.apiKey.substring(0, 15) + '...', 'yellow');
  
  const newKey = await question('\nEnter new Perplexity API Key (or press Enter to skip): ');
  
  if (newKey.trim()) {
    apiConfig.perplexity.apiKey = newKey.trim();
    
    // Update secure API file
    secureApiContent = secureApiContent.replace(
      /PERPLEXITY_API_KEY=.*/,
      `PERPLEXITY_API_KEY=${newKey.trim()}`
    );
    
    log('✅ Perplexity API key updated', 'green');
    return true;
  } else {
    log('⏭️  Skipped Perplexity update', 'yellow');
    return false;
  }
}

async function updatePrintful() {
  logSection('Printful API Key Update');
  
  log('Current API Key:', 'yellow');
  log(apiConfig.printful.apiKey.substring(0, 15) + '...', 'yellow');
  
  const newKey = await question('\nEnter new Printful API Key (or press Enter to skip): ');
  
  if (newKey.trim()) {
    apiConfig.printful.apiKey = newKey.trim();
    
    log('✅ Printful API key updated', 'green');
    return true;
  } else {
    log('⏭️  Skipped Printful update', 'yellow');
    return false;
  }
}

async function saveChanges() {
  logSection('Saving Changes');
  
  // Save api-config.json
  fs.writeFileSync(configPath, JSON.stringify(apiConfig, null, 2));
  log('✅ api-config.json updated', 'green');
  
  // Save secure API file
  if (fs.existsSync(secureApiPath)) {
    fs.writeFileSync(secureApiPath, secureApiContent);
    log('✅ RudiBot-Secure-API/api-keys.txt updated', 'green');
  }
  
  log('\nAll changes saved successfully!', 'green');
}

async function runValidation() {
  logSection('Running Validation');
  
  log('Running api-validator.cjs to test all APIs...', 'blue');
  
  const { exec } = require('child_process');
  
  return new Promise((resolve) => {
    exec('node api-validator.cjs', (error, stdout, stderr) => {
      if (stdout) console.log(stdout);
      if (stderr) console.error(stderr);
      resolve(!error);
    });
  });
}

async function main() {
  log('🔧 API Update Helper', 'cyan');
  log('This script will help you update your API keys\n', 'cyan');
  
  log('⚠️  Make sure you have your new API keys ready before proceeding', 'yellow');
  log('📖 Follow the instructions in API_RENEWAL_GUIDE.md to get new keys\n', 'yellow');
  
  const proceed = await question('Do you want to proceed? (yes/no): ');
  
  if (proceed.toLowerCase() !== 'yes' && proceed.toLowerCase() !== 'y') {
    log('❌ Cancelled', 'red');
    rl.close();
    return;
  }
  
  const updates = [];
  
  updates.push(await updateShopify());
  updates.push(await updateEtsy());
  updates.push(await updatePerplexity());
  updates.push(await updatePrintful());
  
  const hasUpdates = updates.some(u => u);
  
  if (hasUpdates) {
    await saveChanges();
    
    const runValidation = await question('\nDo you want to run validation test now? (yes/no): ');
    
    if (runValidation.toLowerCase() === 'yes' || runValidation.toLowerCase() === 'y') {
      await runValidation();
    }
  } else {
    log('\nNo updates were made', 'yellow');
  }
  
  logSection('Complete');
  log('Thank you for using the API Update Helper!', 'green');
  log('For detailed instructions, see API_RENEWAL_GUIDE.md', 'blue');
  
  rl.close();
}

main().catch(error => {
  log(`Error: ${error.message}`, 'red');
  rl.close();
  process.exit(1);
});
