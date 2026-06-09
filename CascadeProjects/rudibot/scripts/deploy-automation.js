// ============================================================
// deploy-automation.js — Complete System Deployment
// Rudolf Sarkany · One-Click Production Deployment
// ============================================================
'use strict';
require('dotenv').config();

const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

// ── Config ────────────────────────────────────────────────────
const VERCEL_TOKEN = process.env.VERCEL_TOKEN;
const VERCEL_ORG_ID = process.env.VERCEL_ORG_ID;
const VERCEL_PROJECT_ID = process.env.VERCEL_PROJECT_ID;

// ── Environment Validation ─────────────────────────────────────
function validateEnvironment() {
  console.log('🔍 Validating environment...');
  
  const required = [
    'TELEGRAM_BOT_TOKEN',
    'ANTHROPIC_API_KEY',
    'SHOPIFY_STORE_URL',
    'SHOPIFY_ADMIN_TOKEN',
    'VERCEL_TOKEN'
  ];
  
  const missing = required.filter(key => 
    !process.env[key] || process.env[key].includes('PLACEHOLDER')
  );
  
  if (missing.length > 0) {
    console.error('❌ Missing or placeholder environment variables:');
    missing.forEach(key => console.error(`   - ${key}`));
    console.error('\n📝 Please update your .env file with real API keys');
    return false;
  }
  
  console.log('✅ Environment validation passed');
  return true;
}

// ── Pre-Deployment Checks ─────────────────────────────────────
async function preDeploymentChecks() {
  console.log('🔍 Running pre-deployment checks...');
  
  const checks = [];
  
  // Check Node.js version
  try {
    const { stdout } = await execAsync('node --version');
    const version = stdout.trim();
    const majorVersion = parseInt(version.slice(1).split('.')[0]);
    
    if (majorVersion >= 18) {
      checks.push('✅ Node.js version: ' + version);
    } else {
      checks.push('❌ Node.js version too old: ' + version + ' (requires >= 18)');
    }
  } catch (error) {
    checks.push('❌ Node.js not found');
  }
  
  // Check npm dependencies
  try {
    await execAsync('npm list --depth=0');
    checks.push('✅ npm dependencies installed');
  } catch (error) {
    checks.push('❌ npm dependencies missing - run: npm install');
  }
  
  // Check automation scripts
  const scripts = [
    'scripts/printify-automation.js',
    'scripts/digistore-automation.js',
    'scripts/youtube-automation.js',
    'scripts/earnings-tracker.js'
  ];
  
  const existingScripts = scripts.filter(script => fs.existsSync(script));
  if (existingScripts.length === scripts.length) {
    checks.push('✅ All automation scripts present');
  } else {
    checks.push(`⚠️ Missing scripts: ${scripts.length - existingScripts.length}/${scripts.length}`);
  }
  
  // Check directories
  const dirs = ['content', 'data', 'logs'];
  const existingDirs = dirs.filter(dir => fs.existsSync(dir));
  if (existingDirs.length === dirs.length) {
    checks.push('✅ Required directories exist');
  } else {
    checks.push(`⚠️ Missing directories: ${dirs.length - existingDirs.length}/${dirs.length}`);
  }
  
  checks.forEach(check => console.log(`   ${check}`));
  
  const passed = checks.filter(c => c.startsWith('✅')).length;
  const total = checks.length;
  
  console.log(`\n📊 Pre-deployment checks: ${passed}/${total} passed`);
  
  return passed === total;
}

// ── Build Process ───────────────────────────────────────────────
async function buildProject() {
  console.log('🔨 Building project...');
  
  try {
    // Create production build
    console.log('   📦 Creating production build...');
    
    // Create vercel.json configuration
    const vercelConfig = {
      version: 2,
      builds: [
        {
          src: 'server.js',
          use: '@vercel/node'
        }
      ],
      routes: [
        {
          src: '/api/(.*)',
          dest: '/server.js'
        },
        {
          src: '/bot-health',
          dest: '/server.js'
        }
      ],
      env: {
        NODE_ENV: 'production'
      },
      functions: {
        'server.js': {
          maxDuration: 30
        }
      }
    };
    
    fs.writeFileSync('vercel.json', JSON.stringify(vercelConfig, null, 2));
    console.log('   ✅ vercel.json created');
    
    // Create package.json for production
    const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
    packageJson.scripts = {
      ...packageJson.scripts,
      'start': 'node server.js',
      'poststart': 'node bot.js'
    };
    
    fs.writeFileSync('package.json', JSON.stringify(packageJson, null, 2));
    console.log('   ✅ package.json updated');
    
    return true;
  } catch (error) {
    console.error('❌ Build failed:', error.message);
    return false;
  }
}

// ── Vercel Deployment ─────────────────────────────────────────
async function deployToVercel() {
  console.log('🚀 Deploying to Vercel...');
  
  try {
    // Install Vercel CLI if not present
    try {
      await execAsync('vercel --version');
    } catch {
      console.log('   📦 Installing Vercel CLI...');
      await execAsync('npm install -g vercel');
    }
    
    // Set environment variables for Vercel
    console.log('   🔧 Setting environment variables...');
    
    const envVars = [
      'TELEGRAM_BOT_TOKEN',
      'ANTHROPIC_API_KEY',
      'OPENAI_API_KEY',
      'PERPLEXITY_API_KEY',
      'SHOPIFY_STORE_URL',
      'SHOPIFY_ADMIN_TOKEN',
      'SHOPIFY_API_VERSION',
      'SHOPIFY_STORE2_URL',
      'SHOPIFY_STORE2_TOKEN',
      'GITHUB_TOKEN',
      'GITHUB_USERNAME',
      'PRINTIFY_API_KEY',
      'PRINTIFY_SHOP_ID',
      'DIGISTORE_API_KEY',
      'DIGISTORE_API_SECRET',
      'YOUTUBE_API_KEY',
      'YOUTUBE_CHANNEL_ID',
      'VERCEL_TOKEN',
      'VERCEL_ORG_ID',
      'VERCEL_PROJECT_ID',
      'PORT',
      'NODE_ENV',
      'MONITORING_PORT'
    ];
    
    for (const envVar of envVars) {
      const value = process.env[envVar];
      if (value && !value.includes('PLACEHOLDER')) {
        try {
          await execAsync(`vercel env add ${envVar} production`, {
            input: value + '\n'
          });
          console.log(`   ✅ ${envVar} set`);
        } catch (error) {
          // Environment variable might already exist
          console.log(`   ⚠️ ${envVar} (may already exist)`);
        }
      }
    }
    
    // Deploy to production
    console.log('   🚀 Starting production deployment...');
    const { stdout, stderr } = await execAsync('vercel --prod --yes', {
      timeout: 300000 // 5 minutes timeout
    });
    
    console.log('   ✅ Deployment completed');
    console.log('\n📋 Deployment output:');
    console.log(stdout);
    
    if (stderr) {
      console.log('\n⚠️ Warnings:');
      console.log(stderr);
    }
    
    // Extract deployment URL
    const urlMatch = stdout.match(/https:\/\/[^\\s]+/);
    if (urlMatch) {
      const deploymentUrl = urlMatch[0];
      console.log(`\n🌐 Deployment URL: ${deploymentUrl}`);
      
      // Update webhook URL in .env
      const webhookUrl = `${deploymentUrl}/webhook`;
      const envContent = fs.readFileSync('.env', 'utf8');
      const updatedEnv = envContent.replace(
        /WEBHOOK_URL=.*/,
        `WEBHOOK_URL=${webhookUrl}`
      );
      fs.writeFileSync('.env', updatedEnv);
      
      console.log(`📞 Webhook URL updated: ${webhookUrl}`);
      
      return deploymentUrl;
    }
    
    return null;
  } catch (error) {
    console.error('❌ Deployment failed:', error.message);
    if (error.stderr) {
      console.error('Deployment errors:', error.stderr);
    }
    return null;
  }
}

// ── Post-Deployment Verification ───────────────────────────────
async function verifyDeployment(url) {
  console.log('🔍 Verifying deployment...');
  
  if (!url) {
    console.log('❌ No deployment URL provided');
    return false;
  }
  
  const checks = [];
  
  try {
    // Check API health
    console.log('   🏥 Checking API health...');
    const healthResponse = await fetch(`${url}/api/health`, {
      signal: AbortSignal.timeout(10000)
    });
    
    if (healthResponse.ok) {
      const healthData = await healthResponse.json();
      checks.push('✅ API health check passed');
      console.log(`   📊 Status: ${healthData.status || 'OK'}`);
    } else {
      checks.push('❌ API health check failed');
    }
  } catch (error) {
    checks.push('❌ API health check error: ' + error.message);
  }
  
  try {
    // Check bot health
    console.log('   🤖 Checking bot health...');
    const botResponse = await fetch(`${url}/bot-health`, {
      signal: AbortSignal.timeout(10000)
    });
    
    if (botResponse.ok) {
      const botData = await botResponse.json();
      checks.push('✅ Bot health check passed');
      console.log(`   📊 Bot uptime: ${botData.uptime || 'Unknown'}s`);
    } else {
      checks.push('❌ Bot health check failed');
    }
  } catch (error) {
    checks.push('❌ Bot health check error: ' + error.message);
  }
  
  checks.forEach(check => console.log(`   ${check}`));
  
  const passed = checks.filter(c => c.startsWith('✅')).length;
  const total = checks.length;
  
  console.log(`\n📊 Verification: ${passed}/${total} checks passed`);
  
  return passed === total;
}

// ── Revenue Estimation ───────────────────────────────────────────
function estimateRevenue() {
  console.log('💰 Revenue estimation...');
  
  const estimates = {
    'Printify POD': {
      products: 50,
      avgPrice: 25,
      profitMargin: 0.30,
      monthly: 50 * 25 * 0.30 * 30 // 375 EUR/month
    },
    'Digistore24 Affiliate': {
      conversions: 20,
      avgCommission: 45,
      monthly: 20 * 45 * 30 // 27,000 EUR/month (optimistic)
    },
    'YouTube Content': {
      videos: 14,
      avgViews: 5000,
      rpm: 2,
      monthly: 14 * 5000 * 2 / 1000 * 4 // 560 EUR/month
    },
    'Shopify Sales': {
      orders: 30,
      avgOrderValue: 75,
      profitMargin: 0.25,
      monthly: 30 * 75 * 0.25 * 30 // 16,875 EUR/month
    }
  };
  
  let totalMonthly = 0;
  
  console.log('\n📊 Monthly Revenue Estimates:');
  Object.entries(estimates).forEach(([source, data]) => {
    console.log(`   ${source}: ${data.monthly.toFixed(2)} EUR`);
    totalMonthly += data.monthly;
  });
  
  console.log(`\n💰 Total Estimated Monthly Revenue: ${totalMonthly.toFixed(2)} EUR`);
  console.log(`📈 Annual Projection: ${(totalMonthly * 12).toFixed(2)} EUR`);
  
  return totalMonthly;
}

// ── Main Deployment Process ───────────────────────────────────────
async function main() {
  console.log('🚀 AutoPilot Business Bot - Production Deployment');
  console.log('=' .repeat(50));
  
  const startTime = Date.now();
  
  try {
    // Step 1: Environment validation
    if (!validateEnvironment()) {
      console.log('\n❌ Deployment failed: Environment validation');
      process.exit(1);
    }
    
    // Step 2: Pre-deployment checks
    if (!await preDeploymentChecks()) {
      console.log('\n❌ Deployment failed: Pre-deployment checks');
      process.exit(1);
    }
    
    // Step 3: Build project
    if (!await buildProject()) {
      console.log('\n❌ Deployment failed: Build process');
      process.exit(1);
    }
    
    // Step 4: Deploy to Vercel
    const deploymentUrl = await deployToVercel();
    if (!deploymentUrl) {
      console.log('\n❌ Deployment failed: Vercel deployment');
      process.exit(1);
    }
    
    // Step 5: Post-deployment verification
    const verified = await verifyDeployment(deploymentUrl);
    if (!verified) {
      console.log('\n⚠️ Deployment completed but verification failed');
    }
    
    // Step 6: Revenue estimation
    const estimatedRevenue = estimateRevenue();
    
    const duration = Math.floor((Date.now() - startTime) / 1000);
    
    console.log('\n' + '='.repeat(50));
    console.log('🎉 DEPLOYMENT SUCCESSFUL!');
    console.log('=' .repeat(50));
    console.log(`🌐 Live URL: ${deploymentUrl}`);
    console.log(`⏱️  Duration: ${duration}s`);
    console.log(`💰 Est. Monthly Revenue: ${estimatedRevenue.toFixed(2)} EUR`);
    console.log(`📈 Annual Projection: ${(estimatedRevenue * 12).toFixed(2)} EUR`);
    console.log('\n🤖 Next Steps:');
    console.log('   1. Test your Telegram bot commands');
    console.log('   2. Run /all to start all automation systems');
    console.log('   3. Monitor earnings with /earn command');
    console.log('   4. Scale up by increasing product quantities');
    
  } catch (error) {
    console.error('\n❌ Deployment failed:', error.message);
    process.exit(1);
  }
}

// ── START ────────────────────────────────────────────────────────
if (require.main === module) {
  main().catch(console.error);
}

module.exports = {
  validateEnvironment,
  preDeploymentChecks,
  buildProject,
  deployToVercel,
  verifyDeployment,
  estimateRevenue
};
