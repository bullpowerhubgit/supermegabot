#!/usr/bin/env node
/**
 * GitHub API Test Script
 * Testet GitHub Personal Access Tokens (Classic + Fine-Grained)
 */

import { Octokit } from '@octokit/rest';
import dotenv from 'dotenv';
dotenv.config();

const tokens = {
  classic: process.env.GITHUB_TOKEN_CLASSIC,
  fine: process.env.GITHUB_TOKEN_FINE,
  fine_alt: process.env.GITHUB_TOKEN_FINE_ALT
};

async function testGitHubToken(token, label) {
  console.log(`\n🔍 Testing ${label} Token...`);
  
  if (!token) {
    console.log(`❌ ${label}: No token found`);
    return false;
  }

  try {
    const octokit = new Octokit({ auth: token });
    
    // Test 1: Get authenticated user
    const { data: user } = await octokit.rest.users.getAuthenticated();
    console.log(`✅ ${label}: Authenticated as ${user.login} (${user.name})`);
    
    // Test 2: List repositories
    const { data: repos } = await octokit.rest.repos.listForAuthenticatedUser({ per_page: 5 });
    console.log(`📦 ${label}: Found ${repos.length} recent repos`);
    repos.forEach(repo => console.log(`   - ${repo.full_name} (${repo.private ? 'private' : 'public'})`));
    
    // Test 3: Create a test issue (if we have write permissions)
    try {
      const { data: issue } = await octokit.rest.issues.create({
        owner: 'bullpowerhubgit',
        repo: 'windsurf-telegram-bot',
        title: `API Test ${new Date().toISOString()}`,
        body: `Test issue created via ${label} token at ${new Date().toISOString()}`
      });
      console.log(`🎯 ${label}: Created issue #${issue.number}`);
      
      // Clean up - close the test issue
      await octokit.rest.issues.update({
        owner: 'bullpowerhubgit',
        repo: 'windsurf-telegram-bot',
        issue_number: issue.number,
        state: 'closed'
      });
      console.log(`🧹 ${label}: Closed test issue #${issue.number}`);
      
    } catch (issueError) {
      console.log(`⚠️ ${label}: Cannot create issues (permissions?): ${issueError.message}`);
    }
    
    return true;
    
  } catch (error) {
    console.log(`❌ ${label}: Failed - ${error.message}`);
    return false;
  }
}

async function main() {
  console.log('🚀 GitHub API Test Suite');
  console.log('========================');
  
  const results = [];
  
  if (tokens.classic) {
    results.push(await testGitHubToken(tokens.classic, 'Classic'));
  }
  
  if (tokens.fine) {
    results.push(await testGitHubToken(tokens.fine, 'Fine-Grained'));
  }
  
  if (tokens.fine_alt) {
    results.push(await testGitHubToken(tokens.fine_alt, 'Fine-Grained Alt'));
  }
  
  console.log('\n📊 Summary');
  console.log('===========');
  const working = results.filter(r => r).length;
  console.log(`✅ Working tokens: ${working}/${results.length}`);
  
  if (working === 0) {
    console.log('❌ No working GitHub tokens found!');
    process.exit(1);
  } else {
    console.log('🎉 GitHub API integration ready!');
  }
}

main().catch(console.error);
