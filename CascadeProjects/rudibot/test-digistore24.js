// ============================================================
// test-digistore24.js — Digistore24 API Test Suite
// Rudolf Sarkany · Test endpoints for Digistore24 integration
// ============================================================

const BASE_URL = 'http://localhost:3200';

// Test configuration
const TEST_CONFIG = {
    timeout: 10000,
    retries: 3
};

// Helper function for API calls
async function apiCall(endpoint, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    const opts = {
        timeout: TEST_CONFIG.timeout,
        headers: { 'Content-Type': 'application/json' },
        ...options
    };

    console.log(`🔍 Testing: ${opts.method || 'GET'} ${url}`);
    
    try {
        const response = await fetch(url, opts);
        const data = await response.json();
        
        console.log(`📊 Status: ${response.status}`);
        console.log(`📄 Response:`, JSON.stringify(data, null, 2));
        
        return { status: response.status, data, success: response.ok };
    } catch (error) {
        console.error(`❌ Error: ${error.message}`);
        return { status: 0, data: { error: error.message }, success: false };
    }
}

// Test suite
async function runTests() {
    console.log('\n🚀 Starting Digistore24 API Tests...\n');

    // Test 1: Health check
    console.log('=== Test 1: Health Check ===');
    await apiCall('/api/health');

    // Test 2: Status endpoint (should show Digistore24)
    console.log('\n=== Test 2: API Status ===');
    await apiCall('/api/status');

    // Test 3: Get products (will fail without API key)
    console.log('\n=== Test 3: Get Products ===');
    await apiCall('/api/digistore/products?limit=5');

    // Test 4: Get specific product (will fail without API key)
    console.log('\n=== Test 4: Get Product by ID ===');
    await apiCall('/api/digistore/products/123');

    // Test 5: Get orders (will fail without API key)
    console.log('\n=== Test 5: Get Orders ===');
    await apiCall('/api/digistore/orders?limit=5');

    // Test 6: Get statistics (will fail without API key)
    console.log('\n=== Test 6: Get Statistics ===');
    await apiCall('/api/digistore/stats');

    // Test 7: Get affiliates (will fail without API key)
    console.log('\n=== Test 7: Get Affiliates ===');
    await apiCall('/api/digistore/affiliates?limit=5');

    // Test 8: Webhook test (simulate webhook)
    console.log('\n=== Test 8: Webhook Test ===');
    const webhookPayload = {
        order_id: 'TEST-123',
        amount: '99.99',
        currency: 'EUR',
        status: 'paid'
    };
    await apiCall('/webhooks/digistore24/order_created', {
        method: 'POST',
        body: JSON.stringify(webhookPayload)
    });

    console.log('\n✅ Digistore24 API Tests Complete!');
    console.log('\n📝 To use the Digistore24 API:');
    console.log('1. Set DIGISTORE_API_KEY in your .env file');
    console.log('2. Get your API key from: https://www.digistore24.com/account/api');
    console.log('3. Restart the server to load the new environment variable');
}

// Example usage with real API key
async function exampleUsage() {
    console.log('\n📚 Example Usage with API Key:');
    console.log('// Set your API key in .env file');
    console.log('DIGISTORE_API_KEY=your_api_key_here');
    console.log('');
    console.log('// Then you can use these endpoints:');
    console.log('');
    console.log('// Get all active products');
    console.log('GET /api/digistore/products?status=active&limit=10');
    console.log('');
    console.log('// Get specific product');
    console.log('GET /api/digistore/products/12345');
    console.log('');
    console.log('// Create new product');
    console.log('POST /api/digistore/products');
    console.log('Body: { name: "Product Name", price: 99.99, ... }');
    console.log('');
    console.log('// Get orders with date range');
    console.log('GET /api/digistore/orders?from_date=2024-01-01&to_date=2024-12-31');
    console.log('');
    console.log('// Get order details');
    console.log('GET /api/digistore/orders/12345/details');
    console.log('');
    console.log('// Cancel an order');
    console.log('POST /api/digistore/orders/12345/cancel');
    console.log('Body: { reason: "Customer request" }');
    console.log('');
    console.log('// Get sales statistics');
    console.log('GET /api/digistore/stats?from_date=2024-01-01');
    console.log('');
    console.log('// Get affiliates');
    console.log('GET /api/digistore/affiliates');
    console.log('');
    console.log('// Webhook endpoints');
    console.log('POST /webhooks/digistore24/order_created');
    console.log('POST /webhooks/digistore24/order_paid');
    console.log('POST /webhooks/digistore24/order_cancelled');
    console.log('POST /webhooks/digistore24/refund_requested');
}

// Run tests if this file is executed directly
if (require.main === module) {
    runTests()
        .then(() => exampleUsage())
        .catch(console.error);
}

module.exports = { apiCall, runTests, exampleUsage };
