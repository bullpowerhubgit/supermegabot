#!/usr/bin/env node
/**
 * Supabase API Test Script
 * Testet Supabase Datenbankverbindung und CRUD-Operationen
 */

import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';
dotenv.config();

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseAnonKey = process.env.SUPABASE_ANON_KEY;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;

async function testSupabaseConnection(key, label) {
  console.log(`\n🔍 Testing Supabase with ${label} key...`);
  
  if (!supabaseUrl || !key) {
    console.log(`❌ ${label}: Missing URL or key`);
    return false;
  }

  try {
    const supabase = createClient(supabaseUrl, key);
    
    // Test 1: Basic connection - get service status
    const { data, error } = await supabase.from('_test_connection').select('*').limit(1);
    if (error && error.code !== 'PGRST116') { // PGRST116 = table doesn't exist (expected)
      console.log(`❌ ${label}: Connection failed - ${error.message}`);
      return false;
    }
    console.log(`✅ ${label}: Connection successful`);
    
    // Test 2: Create test table if it doesn't exist
    const { error: createError } = await supabase.rpc('create_test_table_if_not_exists');
    if (createError && !createError.message.includes('function')) {
      console.log(`⚠️ ${label}: Could not create test table - ${createError.message}`);
    }
    
    // Test 3: Insert test record
    const testRecord = {
      id: `test_${Date.now()}`,
      message: `Test from ${label} at ${new Date().toISOString()}`,
      created_at: new Date().toISOString()
    };
    
    const { data: insertData, error: insertError } = await supabase
      .from('api_tests')
      .insert([testRecord])
      .select();
      
    if (insertError) {
      console.log(`❌ ${label}: Insert failed - ${insertError.message}`);
      return false;
    }
    
    console.log(`✅ ${label}: Inserted test record: ${insertData[0].id}`);
    
    // Test 4: Query records
    const { data: queryData, error: queryError } = await supabase
      .from('api_tests')
      .select('*')
      .eq('id', testRecord.id)
      .single();
      
    if (queryError) {
      console.log(`❌ ${label}: Query failed - ${queryError.message}`);
      return false;
    }
    
    console.log(`✅ ${label}: Queried record: ${queryData.message}`);
    
    // Test 5: Update record
    const { data: updateData, error: updateError } = await supabase
      .from('api_tests')
      .update({ message: `Updated by ${label}` })
      .eq('id', testRecord.id)
      .select();
      
    if (updateError) {
      console.log(`❌ ${label}: Update failed - ${updateError.message}`);
      return false;
    }
    
    console.log(`✅ ${label}: Updated record`);
    
    // Test 6: Delete record (cleanup)
    const { error: deleteError } = await supabase
      .from('api_tests')
      .delete()
      .eq('id', testRecord.id);
      
    if (deleteError) {
      console.log(`❌ ${label}: Delete failed - ${deleteError.message}`);
      return false;
    }
    
    console.log(`✅ ${label}: Cleaned up test record`);
    
    // Test 7: Real-time subscription test
    const subscription = supabase
      .channel('test-subscription')
      .on('postgres_changes', 
        { event: '*', schema: 'public', table: 'api_tests' },
        (payload) => console.log(`📡 ${label}: Real-time event: ${payload.eventType}`)
      )
      .subscribe(subscription => {
        console.log(`✅ ${label}: Real-time subscription active`);
        subscription.unsubscribe();
      });
    
    return true;
    
  } catch (error) {
    console.log(`❌ ${label}: Exception - ${error.message}`);
    return false;
  }
}

async function testSupabaseAuth() {
  console.log('\n🔐 Testing Supabase Auth...');
  
  try {
    const supabase = createClient(supabaseUrl, supabaseAnonKey);
    
    // Test auth with anon key
    const { data: { user }, error } = await supabase.auth.getUser();
    if (error) {
      console.log(`ℹ️ Auth: No authenticated user (expected with anon key)`);
    } else {
      console.log(`✅ Auth: User ${user?.email}`);
    }
    
    return true;
  } catch (error) {
    console.log(`❌ Auth: ${error.message}`);
    return false;
  }
}

async function main() {
  console.log('🚀 Supabase API Test Suite');
  console.log('==========================');
  
  const results = [];
  
  if (supabaseAnonKey) {
    results.push(await testSupabaseConnection(supabaseAnonKey, 'Anon'));
  }
  
  if (supabaseServiceKey) {
    results.push(await testSupabaseConnection(supabaseServiceKey, 'Service'));
  }
  
  results.push(await testSupabaseAuth());
  
  console.log('\n📊 Summary');
  console.log('===========');
  const working = results.filter(r => r).length;
  console.log(`✅ Working connections: ${working}/${results.length}`);
  
  if (working === 0) {
    console.log('❌ No working Supabase connections found!');
    process.exit(1);
  } else {
    console.log('🎉 Supabase API integration ready!');
    console.log(`🔗 Project URL: ${supabaseUrl}`);
  }
}

main().catch(console.error);
