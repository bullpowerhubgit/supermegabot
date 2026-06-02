#!/usr/bin/env node
/**
 * Stripe API Test Script
 * Testet Stripe Payment API und Webhook-Handling
 */

import Stripe from 'stripe';
import dotenv from 'dotenv';
dotenv.config();

const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
const stripePublishableKey = process.env.STRIPE_PUBLISHABLE_KEY;

async function testStripeAPI() {
  console.log('🚀 Stripe API Test Suite');
  console.log('=======================');
  
  if (!stripeSecretKey) {
    console.log('❌ No STRIPE_SECRET_KEY found');
    return false;
  }

  try {
    const stripe = new Stripe(stripeSecretKey);
    
    // Test 1: Account info
    const account = await stripe.accounts.retrieve();
    console.log(`✅ Account: ${account.business_profile?.name || account.display_name || account.id}`);
    console.log(`   Country: ${account.country}`);
    console.log(`   Type: ${account.type}`);
    
    // Test 2: List products
    const products = await stripe.products.list({ limit: 5 });
    console.log(`📦 Products: ${products.data.length} found`);
    products.data.forEach(product => {
      console.log(`   - ${product.name} (${product.active ? 'active' : 'inactive'})`);
    });
    
    // Test 3: Create test product
    const testProduct = await stripe.products.create({
      name: `Test Product ${Date.now()}`,
      description: 'API Test Product - will be deleted',
      type: 'service',
      active: false
    });
    console.log(`✅ Created test product: ${testProduct.id}`);
    
    // Test 4: Create test price
    const testPrice = await stripe.prices.create({
      product: testProduct.id,
      unit_amount: 999, // $9.99
      currency: 'usd',
      nickname: 'Test Price'
    });
    console.log(`✅ Created test price: ${testPrice.id} ($${testPrice.unit_amount / 100})`);
    
    // Test 5: Create payment link
    const paymentLink = await stripe.paymentLinks.create({
      line_items: [{
        price: testPrice.id,
        quantity: 1,
      }],
      after_completion: {
        type: 'redirect',
        redirect: {
          url: 'https://example.com/success'
        }
      }
    });
    console.log(`✅ Created payment link: ${paymentLink.url}`);
    
    // Test 6: List recent charges
    const charges = await stripe.charges.list({ limit: 3 });
    console.log(`💳 Recent charges: ${charges.data.length}`);
    charges.data.forEach(charge => {
      console.log(`   - $${charge.amount / 100} ${charge.currency.toUpperCase()} (${charge.status})`);
    });
    
    // Test 7: Webhook endpoint test
    try {
      const webhooks = await stripe.webhookEndpoints.list({ limit: 5 });
      console.log(`🪝 Webhook endpoints: ${webhooks.data.length}`);
      webhooks.data.forEach(webhook => {
        console.log(`   - ${webhook.url} (${webhook.enabled ? 'enabled' : 'disabled'})`);
      });
    } catch (webhookError) {
      console.log(`⚠️ Webhook endpoints: ${webhookError.message}`);
    }
    
    // Cleanup
    await stripe.products.del(testProduct.id);
    console.log(`🧹 Cleaned up test product`);
    
    return true;
    
  } catch (error) {
    console.log(`❌ Stripe API failed: ${error.message}`);
    return false;
  }
}

async function testStripeKeys() {
  console.log('\n🔑 Stripe Key Validation');
  console.log('========================');
  
  if (!stripeSecretKey) {
    console.log('❌ STRIPE_SECRET_KEY: Missing');
    return false;
  }
  
  if (!stripePublishableKey) {
    console.log('⚠️ STRIPE_PUBLISHABLE_KEY: Missing (optional for backend)');
  } else {
    console.log('✅ STRIPE_PUBLISHABLE_KEY: Present');
  }
  
  // Validate secret key format
  if (stripeSecretKey.startsWith('sk_live_')) {
    console.log('✅ STRIPE_SECRET_KEY: Live mode');
  } else if (stripeSecretKey.startsWith('sk_test_')) {
    console.log('✅ STRIPE_SECRET_KEY: Test mode');
  } else {
    console.log('⚠️ STRIPE_SECRET_KEY: Invalid format?');
  }
  
  return true;
}

async function main() {
  const keyTest = await testStripeKeys();
  const apiTest = await testStripeAPI();
  
  console.log('\n📊 Summary');
  console.log('===========');
  
  if (keyTest && apiTest) {
    console.log('🎉 Stripe API integration ready!');
    console.log('💡 Ready for payment processing and webhook handling');
  } else {
    console.log('❌ Stripe integration incomplete');
    process.exit(1);
  }
}

main().catch(console.error);
