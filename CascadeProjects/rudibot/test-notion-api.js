// Notion API Test Script
const { Client } = require('@notionhq/client');

// Load environment variables
require('dotenv').config();

const apiKey = process.env.NOTION_API_KEY;
const databaseId = process.env.NOTION_DATABASE_ID;

console.log('═══════════════════════════════════════════');
console.log('  NOTION API TEST');
console.log('═══════════════════════════════════════════');

if (!apiKey) {
  console.log('❌ NOTION_API_KEY nicht gesetzt');
  console.log('📝 Bitte in .env eintragen:');
  console.log('   NOTION_API_KEY=secret_...');
  process.exit(1);
}

if (apiKey === 'secret_YOUR_NOTION_API_KEY_HERE') {
  console.log('❌ NOTION_API_KEY ist noch ein Platzhalter');
  console.log('📝 Echten Key von https://www.notion.so/my-integrations eintragen');
  process.exit(1);
}

if (!databaseId || databaseId === 'YOUR_DATABASE_ID_HERE') {
  console.log('⚠️  NOTION_DATABASE_ID nicht gesetzt');
  console.log('📝 Optional: Database ID in .env eintragen für volle Funktionalität');
}

// Initialize Notion client
const notion = new Client({ auth: apiKey });

async function testNotionAPI() {
  try {
    console.log('🔍 Teste Notion API Verbindung...');
    
    // Test 1: Get user info
    console.log('\n1. User Info abrufen...');
    const user = await notion.users.me();
    console.log(`✅ User: ${user.name} (${user.type})`);
    
    // Test 2: If database ID is set, test database access
    if (databaseId && databaseId !== 'YOUR_DATABASE_ID_HERE') {
      console.log('\n2. Database Info abrufen...');
      try {
        const database = await notion.databases.retrieve({ database_id: databaseId });
        console.log(`✅ Database: ${database.title[0]?.plain_text || 'Kein Titel'}`);
        console.log(`📊 Properties: ${Object.keys(database.properties).join(', ')}`);
      } catch (dbError) {
        console.log(`⚠️  Database Zugriff fehlgeschlagen: ${dbError.message}`);
        console.log('💡 Tipp: Database ID prüfen oder Bot zur Database einladen');
      }
    } else {
      console.log('\n2. Database Test übersprungen (keine Database ID)');
    }
    
    // Test 3: Search for pages (always works)
    console.log('\n3. Search Test...');
    const search = await notion.search({
      filter: { property: 'object', value: 'page' },
      page_size: 1
    });
    console.log(`✅ Search funktioniert: ${search.results.length} Seiten gefunden`);
    
    console.log('\n═══════════════════════════════════════════');
    console.log('🎉 NOTION API FUNKTIONIERT!');
    console.log('═══════════════════════════════════════════');
    
  } catch (error) {
    console.log('\n❌ NOTION API FEHLER:');
    console.log(`   ${error.message}`);
    
    if (error.code === 'unauthorized') {
      console.log('\n💡 Lösung:');
      console.log('   1. API Key von https://www.notion.so/my-integrations kopieren');
      console.log('   2. Integration in Notion Seiten einladen');
    }
    
    process.exit(1);
  }
}

// Test API endpoints directly
async function testAPIEndpoints() {
  console.log('\n🌐 Teste API Endpunkte...');
  
  const baseUrl = 'http://localhost:3200';
  
  try {
    // Test database endpoint
    const dbResponse = await fetch(`${baseUrl}/api/notion/database`);
    const dbData = await dbResponse.json();
    
    if (dbData.success) {
      console.log('✅ /api/notion/database funktioniert');
    } else {
      console.log(`⚠️  /api/notion/database: ${dbData.error}`);
    }
    
    // Test page creation (with sample data)
    const pageResponse = await fetch(`${baseUrl}/api/notion/page`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Test Page from RudiBot',
        content: 'Automatisch erstellte Test-Seite'
      })
    });
    
    const pageData = await pageResponse.json();
    
    if (pageData.success) {
      console.log('✅ /api/notion/page funktioniert');
      console.log(`   Page ID: ${pageData.data.id}`);
    } else {
      console.log(`⚠️  /api/notion/page: ${pageData.error}`);
    }
    
  } catch (error) {
    console.log(`❌ API Endpunkt Test: ${error.message}`);
    console.log('💡 Server muss auf Port 3200 laufen');
  }
}

// Run tests
testNotionAPI()
  .then(() => testAPIEndpoints())
  .catch(console.error);
