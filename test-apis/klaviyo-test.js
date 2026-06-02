#!/usr/bin/env node
/**
 * Klaviyo API Test Script
 * Testet Klaviyo Marketing API und Campaign-Operationen
 */

import axios from 'axios';
import dotenv from 'dotenv';
dotenv.config();

const klaviyoApiKey = process.env.KLAVIYO_API_KEY;

class KlaviyoAPI {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseURL = 'https://a.klaviyo.com/api';
    this.client = axios.create({
      baseURL: this.baseURL,
      headers: {
        'Authorization': `Klaviyo-API-Key ${apiKey}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'revision': '2023-08-15'
      }
    });
  }

  async testConnection() {
    console.log('\n🔍 Testing Klaviyo connection...');
    
    try {
      const response = await this.client.get('/accounts/');
      console.log(`✅ Connected to account: ${response.data.data[0].attributes.name}`);
      console.log(`   Account ID: ${response.data.data[0].id}`);
      return true;
    } catch (error) {
      console.log(`❌ Connection failed: ${error.response?.data?.errors?.[0]?.detail || error.message}`);
      return false;
    }
  }

  async testCampaigns() {
    console.log('\n📧 Testing campaigns...');
    
    try {
      const response = await this.client.get('/campaigns/', {
        params: { limit: 5 }
      });
      console.log(`📋 Campaigns: ${response.data.data.length} found`);
      response.data.data.forEach(campaign => {
        console.log(`   - ${campaign.attributes.name} (${campaign.attributes.status})`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Campaigns failed: ${error.response?.data?.errors?.[0]?.detail || error.message}`);
      return false;
    }
  }

  async testLists() {
    console.log('\n👥 Testing lists...');
    
    try {
      const response = await this.client.get('/lists/', {
        params: { limit: 5 }
      });
      console.log(`📝 Lists: ${response.data.data.length} found`);
      response.data.data.forEach(list => {
        console.log(`   - ${list.attributes.name} (${list.attributes.member_count} members)`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Lists failed: ${error.response?.data?.errors?.[0]?.detail || error.message}`);
      return false;
    }
  }

  async testProfiles() {
    console.log('\n👤 Testing profiles...');
    
    try {
      const response = await this.client.get('/profiles/', {
        params: { limit: 3 }
      });
      console.log(`👤 Profiles: ${response.data.data.length} found`);
      response.data.data.forEach(profile => {
        const email = profile.attributes.email || profile.attributes.phone_number || 'No contact';
        console.log(`   - ${email} (${profile.attributes.location?.country || 'No location'})`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Profiles failed: ${error.response?.data?.errors?.[0]?.detail || error.message}`);
      return false;
    }
  }

  async testMetrics() {
    console.log('\n📊 Testing metrics...');
    
    try {
      const response = await this.client.get('/metrics/', {
        params: { limit: 5 }
      });
      console.log(`📊 Metrics: ${response.data.data.length} found`);
      response.data.data.forEach(metric => {
        console.log(`   - ${metric.attributes.name} (${metric.attributes.integration?.name || 'Custom'})`);
      });
      return true;
    } catch (error) {
      console.log(`❌ Metrics failed: ${error.response?.data?.errors?.[0]?.detail || error.message}`);
      return false;
    }
  }

  async testCreateProfile() {
    console.log('\n➕ Testing profile creation...');
    
    try {
      const testEmail = `test_${Date.now()}@example.com`;
      const response = await this.client.post('/profiles/', {
        data: {
          type: 'profile',
          attributes: {
            email: testEmail,
            first_name: 'Test',
            last_name: 'User',
            location: {
              country: 'US'
            }
          }
        }
      });
      
      const profileId = response.data.data.id;
      console.log(`✅ Created test profile: ${profileId}`);
      
      // Cleanup - delete the test profile
      await this.client.delete(`/profiles/${profileId}/`);
      console.log(`🧹 Cleaned up test profile`);
      
      return true;
    } catch (error) {
      console.log(`❌ Profile creation failed: ${error.response?.data?.errors?.[0]?.detail || error.message}`);
      return false;
    }
  }
}

async function testKlaviyoCredentials() {
  console.log('🔑 Klaviyo Credential Validation');
  console.log('===============================');
  
  if (!klaviyoApiKey) {
    console.log('❌ KLAVIYO_API_KEY: Missing');
    return false;
  }
  
  // Validate key format
  if (klaviyoApiKey.startsWith('pk_')) {
    console.log('✅ KLAVIYO_API_KEY: Private API Key format');
  } else if (klaviyoApiKey.startsWith('sk_')) {
    console.log('✅ KLAVIYO_API_KEY: Secret API Key format');
  } else {
    console.log('⚠️ KLAVIYO_API_KEY: Unexpected format');
  }
  
  return true;
}

async function main() {
  console.log('🚀 Klaviyo API Test Suite');
  console.log('========================');
  
  const credentialTest = await testKlaviyoCredentials();
  
  if (!credentialTest) {
    console.log('\n❌ Klaviyo credentials invalid');
    process.exit(1);
  }
  
  const klaviyo = new KlaviyoAPI(klaviyoApiKey);
  
  const tests = [
    klaviyo.testConnection(),
    klaviyo.testCampaigns(),
    klaviyo.testLists(),
    klaviyo.testProfiles(),
    klaviyo.testMetrics(),
    klaviyo.testCreateProfile()
  ];
  
  const results = await Promise.allSettled(tests);
  const passed = results.filter(r => r.status === 'fulfilled' && r.value).length;
  
  console.log('\n📊 Summary');
  console.log('===========');
  console.log(`✅ Passed tests: ${passed}/${tests.length}`);
  
  if (passed === tests.length) {
    console.log('🎉 Klaviyo API integration ready!');
    console.log('📧 Ready for email marketing and automation');
  } else {
    console.log('⚠️ Some tests failed - check permissions');
  }
}

main().catch(console.error);
