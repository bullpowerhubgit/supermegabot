#!/usr/bin/env node
/**
 * Printify API Test Script
 * Testet Printify Print-on-Demand API und Shop-Operationen
 */

import axios from 'axios';
import dotenv from 'dotenv';
dotenv.config();

const printifyApiKey = process.env.PRINTIFY_API_KEY;
const printifyShopId = process.env.PRINTIFY_SHOP_ID;

class PrintifyAPI {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseURL = 'https://api.printify.com/v1';
    this.client = axios.create({
      baseURL: this.baseURL,
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });
  }

  async testConnection() {
    console.log('\n🔍 Testing Printify connection...');
    
    try {
      const response = await this.client.get('/shops');
      console.log(`✅ Connected to ${response.data.length} shops`);
      response.data.forEach(shop => {
        console.log(`   - ${shop.title} (${shop.sales_channel}) - ID: ${shop.id}`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Connection failed: ${error.response?.data?.error || error.message}`);
      return false;
    }
  }

  async testProducts() {
    console.log('\n👕 Testing products...');
    
    try {
      const response = await this.client.get(`/shops/${printifyShopId}/products`, {
        params: { limit: 5 }
      });
      console.log(`📦 Products: ${response.data.data.length} found`);
      response.data.data.forEach(product => {
        console.log(`   - ${product.title} (${product.is_published ? 'published' : 'draft'})`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Products failed: ${error.response?.data?.error || error.message}`);
      return false;
    }
  }

  async testCatalog() {
    console.log('\n📚 Testing catalog...');
    
    try {
      const response = await this.client.get('/catalog/blueprints', {
        params: { limit: 5 }
      });
      console.log(`📚 Catalog blueprints: ${response.data.data.length} found`);
      response.data.data.forEach(blueprint => {
        console.log(`   - ${blueprint.title} (${blueprint.brand})`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Catalog failed: ${error.response?.data?.error || error.message}`);
      return false;
    }
  }

  async testOrders() {
    console.log('\n📋 Testing orders...');
    
    try {
      const response = await this.client.get(`/shops/${printifyShopId}/orders`, {
        params: { limit: 3 }
      });
      console.log(`📋 Orders: ${response.data.data.length} found`);
      response.data.data.forEach(order => {
        console.log(`   - Order #${order.id} (${order.status}) - $${order.total_price}`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Orders failed: ${error.response?.data?.error || error.message}`);
      return false;
    }
  }

  async testUploads() {
    console.log('\n📤 Testing upload capability...');
    
    try {
      // Just test the upload endpoint without actually uploading
      const response = await this.client.get('/uploads');
      console.log(`📤 Uploads: ${response.data.data.length} existing`);
      return true;
    } catch (error) {
      console.log(`❌ Uploads failed: ${error.response?.data?.error || error.message}`);
      return false;
    }
  }

  async testCreateProduct() {
    console.log('\n➕ Testing product creation...');
    
    try {
      // First get a blueprint to create from
      const blueprints = await this.client.get('/catalog/blueprints', {
        params: { limit: 1 }
      });
      
      if (!blueprints.data.data.length) {
        console.log('⚠️ No blueprints available for product creation test');
        return true;
      }
      
      const blueprint = blueprints.data.data[0];
      
      // Get print providers for this blueprint
      const providers = await this.client.get(`/catalog/blueprints/${blueprint.id}/print_providers`);
      
      if (!providers.data.length) {
        console.log('⚠️ No print providers available for this blueprint');
        return true;
      }
      
      const provider = providers.data[0];
      
      // Create a test product (but don't publish it)
      const testProduct = {
        title: `Test Product ${Date.now()}`,
        description: 'API Test Product - will be deleted',
        blueprint_id: blueprint.id,
        print_provider_id: provider.id,
        variants: [{
          id: 1,
          price: 1999, // $19.99
          is_enabled: true
        }],
        options: [{
          name: 'Size',
      values: ['S', 'M', 'L']
        }]
      };
      
      const response = await this.client.post(`/shops/${printifyShopId}/products`, testProduct);
      const productId = response.data.id;
      console.log(`✅ Created test product: ${productId}`);
      
      // Cleanup - delete the test product
      await this.client.delete(`/shops/${printifyShopId}/products/${productId}`);
      console.log(`🧹 Cleaned up test product`);
      
      return true;
    } catch (error) {
      console.log(`❌ Product creation failed: ${error.response?.data?.error || error.message}`);
      return false;
    }
  }
}

async function testPrintifyCredentials() {
  console.log('🔑 Printify Credential Validation');
  console.log('==============================');
  
  if (!printifyApiKey) {
    console.log('❌ PRINTIFY_API_KEY: Missing');
    return false;
  }
  
  // Validate key format (Printify uses JWT tokens)
  if (printifyApiKey.startsWith('eyJ') && printifyApiKey.length > 100) {
    console.log('✅ PRINTIFY_API_KEY: JWT token format');
  } else {
    console.log('⚠️ PRINTIFY_API_KEY: Unexpected format');
  }
  
  if (!printifyShopId) {
    console.log('⚠️ PRINTIFY_SHOP_ID: Missing (will auto-detect from shops)');
  } else {
    console.log(`✅ PRINTIFY_SHOP_ID: ${printifyShopId}`);
  }
  
  return true;
}

async function main() {
  console.log('🚀 Printify API Test Suite');
  console.log('========================');
  
  const credentialTest = await testPrintifyCredentials();
  
  if (!credentialTest) {
    console.log('\n❌ Printify credentials invalid');
    process.exit(1);
  }
  
  const printify = new PrintifyAPI(printifyApiKey);
  
  // Auto-detect shop ID if not provided
  if (!printifyShopId) {
    try {
      const shops = await printify.client.get('/shops');
      if (shops.data.length > 0) {
        printifyShopId = shops.data[0].id;
        console.log(`🔍 Auto-detected shop ID: ${printifyShopId}`);
      }
    } catch (error) {
      console.log('❌ Could not auto-detect shop ID');
    }
  }
  
  if (!printifyShopId) {
    console.log('❌ No shop ID available for testing');
    process.exit(1);
  }
  
  const tests = [
    printify.testConnection(),
    printify.testProducts(),
    printify.testCatalog(),
    printify.testOrders(),
    printify.testUploads(),
    printify.testCreateProduct()
  ];
  
  const results = await Promise.allSettled(tests);
  const passed = results.filter(r => r.status === 'fulfilled' && r.value).length;
  
  console.log('\n📊 Summary');
  console.log('===========');
  console.log(`✅ Passed tests: ${passed}/${tests.length}`);
  
  if (passed === tests.length) {
    console.log('🎉 Printify API integration ready!');
    console.log('👕 Ready for print-on-demand operations');
  } else {
    console.log('⚠️ Some tests failed - check permissions');
  }
}

main().catch(console.error);
