#!/usr/bin/env node
/**
 * Shopify API Test Script
 * Testet Shopify Admin API und Store-Operationen
 */

import { Shopify, DataType } from '@shopify/shopify-api';
import dotenv from 'dotenv';
dotenv.config();

const shopifyStoreUrl = process.env.SHOPIFY_STORE_URL;
const shopifyAccessToken = process.env.SHOPIFY_ACCESS_TOKEN;
const shopifyClientId = process.env.SHOPIFY_CLIENT_ID;
const shopifyClientSecret = process.env.SHOPIFY_CLIENT_SECRET;

async function testShopifyAPI() {
  console.log('🚀 Shopify API Test Suite');
  console.log('========================');
  
  if (!shopifyStoreUrl || !shopifyAccessToken) {
    console.log('❌ Missing SHOPIFY_STORE_URL or SHOPIFY_ACCESS_TOKEN');
    return false;
  }

  try {
    // Initialize Shopify client
    const shopify = new Shopify({
      adminApiAccessToken: shopifyAccessToken,
      customShopDomains: [shopifyStoreUrl],
    });
    
    console.log(`🏪 Store: ${shopifyStoreUrl}`);
    
    // Test 1: Get shop info
    const shop = await shopify.rest.resources.Shop.all({
      session: {
        id: 'test-session',
        shop: shopifyStoreUrl,
        accessToken: shopifyAccessToken,
      }
    });
    console.log(`✅ Shop: ${shop[0].name} (${shop[0].currency})`);
    
    // Test 2: List products
    const products = await shopify.rest.resources.Product.all({
      session: {
        id: 'test-session',
        shop: shopifyStoreUrl,
        accessToken: shopifyAccessToken,
      },
      limit: 5
    });
    console.log(`📦 Products: ${products.length} found`);
    products.forEach(product => {
      console.log(`   - ${product.title} (${product.status}) - $${product.variants?.[0]?.price || 'N/A'}`);
    });
    
    // Test 3: Create test product
    const testProduct = new shopify.rest.resources.Product({
      session: {
        id: 'test-session',
        shop: shopifyStoreUrl,
        accessToken: shopifyAccessToken,
      }
    });
    
    testProduct.title = `Test Product ${Date.now()}`;
    testProduct.body_html = '<p>API Test Product - will be deleted</p>';
    testProduct.status = 'draft';
    testProduct.product_type = 'API Test';
    
    await testProduct.save({
      update: true,
    });
    console.log(`✅ Created test product: ${testProduct.id}`);
    
    // Test 4: Update product
    testProduct.tags = 'api-test, automated';
    await testProduct.save({
      update: true,
    });
    console.log(`✅ Updated product with tags`);
    
    // Test 5: List orders
    const orders = await shopify.rest.resources.Order.all({
      session: {
        id: 'test-session',
        shop: shopifyStoreUrl,
        accessToken: shopifyAccessToken,
      },
      limit: 3,
      status: 'any'
    });
    console.log(`📋 Orders: ${orders.length} recent`);
    orders.forEach(order => {
      console.log(`   - #${order.orderNumber} (${order.financialStatus}) - $${order.totalPrice}`);
    });
    
    // Test 6: List customers
    const customers = await shopify.rest.resources.Customer.all({
      session: {
        id: 'test-session',
        shop: shopifyStoreUrl,
        accessToken: shopifyAccessToken,
      },
      limit: 3
    });
    console.log(`👥 Customers: ${customers.length} recent`);
    customers.forEach(customer => {
      console.log(`   - ${customer.firstName} ${customer.lastName} (${customer.email || 'no email'})`);
    });
    
    // Test 7: Create webhook (if we have client credentials)
    if (shopifyClientId && shopifyClientSecret) {
      try {
        const webhook = new shopify.rest.resources.Webhook({
          session: {
            id: 'test-session',
            shop: shopifyStoreUrl,
            accessToken: shopifyAccessToken,
          }
        });
        
        webhook.topic = 'orders/create';
        webhook.address = 'https://webhook.example.com/shopify';
        webhook.format = 'json';
        
        await webhook.save({
          update: true,
        });
        console.log(`✅ Created webhook: ${webhook.id}`);
        
        // Cleanup webhook
        await webhook.delete({
          session: {
            id: 'test-session',
            shop: shopifyStoreUrl,
            accessToken: shopifyAccessToken,
          }
        });
        console.log(`🧹 Cleaned up webhook`);
        
      } catch (webhookError) {
        console.log(`⚠️ Webhook creation failed: ${webhookError.message}`);
      }
    }
    
    // Cleanup test product
    await testProduct.delete({
      session: {
        id: 'test-session',
        shop: shopifyStoreUrl,
        accessToken: shopifyAccessToken,
      }
    });
    console.log(`🧹 Cleaned up test product`);
    
    return true;
    
  } catch (error) {
    console.log(`❌ Shopify API failed: ${error.message}`);
    return false;
  }
}

async function testShopifyCredentials() {
  console.log('\n🔑 Shopify Credential Validation');
  console.log('===============================');
  
  if (!shopifyStoreUrl) {
    console.log('❌ SHOPIFY_STORE_URL: Missing');
    return false;
  } else {
    console.log(`✅ SHOPIFY_STORE_URL: ${shopifyStoreUrl}`);
  }
  
  if (!shopifyAccessToken) {
    console.log('❌ SHOPIFY_ACCESS_TOKEN: Missing');
    return false;
  } else {
    const tokenType = shopifyAccessToken.startsWith('shpat_') ? 'Admin API Token' : 'Custom App Token';
    console.log(`✅ SHOPIFY_ACCESS_TOKEN: ${tokenType}`);
  }
  
  if (shopifyClientId) {
    console.log(`✅ SHOPIFY_CLIENT_ID: Present`);
  } else {
    console.log(`⚠️ SHOPIFY_CLIENT_ID: Missing (optional for basic operations)`);
  }
  
  if (shopifyClientSecret) {
    console.log(`✅ SHOPIFY_CLIENT_SECRET: Present`);
  } else {
    console.log(`⚠️ SHOPIFY_CLIENT_SECRET: Missing (optional for basic operations)`);
  }
  
  return true;
}

async function main() {
  const credentialTest = await testShopifyCredentials();
  const apiTest = await testShopifyAPI();
  
  console.log('\n📊 Summary');
  console.log('===========');
  
  if (credentialTest && apiTest) {
    console.log('🎉 Shopify API integration ready!');
    console.log('🛍️ Ready for store management and webhook handling');
  } else {
    console.log('❌ Shopify integration incomplete');
    process.exit(1);
  }
}

main().catch(console.error);
