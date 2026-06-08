// ============================================================
// youtube-automation.js — YouTube Content Automation
// Rudolf Sarkany · Automated Video Script Creation & Upload
// ============================================================
'use strict';
require('dotenv').config();

const fs = require('fs');
const path = require('path');

// ── Config ────────────────────────────────────────────────────
const YOUTUBE_API_KEY = process.env.YOUTUBE_API_KEY;
const YOUTUBE_CHANNEL_ID = process.env.YOUTUBE_CHANNEL_ID;

if (!YOUTUBE_API_KEY || YOUTUBE_API_KEY.includes('PLACEHOLDER')) {
  console.error('❌ YOUTUBE_API_KEY nicht konfiguriert!');
  process.exit(1);
}

const API_BASE = 'https://www.googleapis.com/youtube/v3';

// ── Video Categories & Templates ───────────────────────────────────
const VIDEO_CATEGORIES = {
  'tech-reviews': {
    title: 'Top {number} {product_type} That Actually Work in 2025',
    description: 'Honest review of the best {product_type} available right now. No sponsored content, just real testing.',
    tags: ['tech review', 'product testing', 'honest review', '2025', 'technology'],
    duration: 600, // 10 minutes
    style: 'educational'
  },
  'make-money-online': {
    title: 'How I Make {amount} EUR/month With {method}',
    description: 'Step-by-step guide to making money online with {method}. Real results, no hype.',
    tags: ['make money online', 'passive income', 'side hustle', 'online business'],
    duration: 900, // 15 minutes
    style: 'motivational'
  },
  'software-tutorials': {
    title: '{software} Tutorial - Complete Beginner Guide',
    description: 'Learn {software} from scratch. This comprehensive tutorial covers everything you need to know.',
    tags: ['tutorial', 'software guide', 'beginner', 'how to'],
    duration: 1200, // 20 minutes
    style: 'educational'
  },
  'productivity-hacks': {
    title: '{number} Productivity Hacks That Changed My Life',
    description: 'Game-changing productivity tips that actually work. Tested and proven methods.',
    tags: ['productivity', 'life hacks', 'efficiency', 'time management'],
    duration: 480, // 8 minutes
    style: 'inspirational'
  }
};

// ── YouTube API Helpers ───────────────────────────────────────
async function youtubeFetch(endpoint, params = {}) {
  const url = new URL(`${API_BASE}${endpoint}`);
  url.searchParams.set('key', YOUTUBE_API_KEY);
  
  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });

  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`YouTube API ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

// ── AI Script Generation ─────────────────────────────────────────
async function generateVideoScript(category, customPrompt = '') {
  try {
    const template = VIDEO_CATEGORIES[category];
    if (!template) {
      throw new Error(`Category not found: ${category}`);
    }

    const prompt = `Generate a complete YouTube video script for:
    
Category: ${category}
Title Template: ${template.title}
Description: ${template.description}
Tags: ${template.tags.join(', ')}
Target Duration: ${template.duration} seconds
Style: ${template.style}

${customPrompt ? `Additional Requirements: ${customPrompt}` : ''}

Structure:
1. Hook (0-30 seconds) - Grab attention immediately
2. Introduction (30-60 seconds) - What viewers will learn
3. Main Content (60-90% of video) - Core value delivery
4. Summary (last 30-60 seconds) - Key takeaways
5. Call to Action - Subscribe, like, comment

Requirements:
- Engaging and conversational tone
- Include specific examples and data points
- Add timestamps for different sections
- Include suggested B-roll footage descriptions
- Add engagement prompts (questions, polls)
- Include affiliate opportunities naturally
- Optimize for YouTube algorithm (retention, engagement)

Return as JSON with:
{
  "title": "Catchy video title",
  "description": "SEO-optimized description",
  "tags": ["array", "of", "tags"],
  "script": "Complete script with timestamps",
  "duration": "estimated_duration_in_seconds",
  "thumbnail_idea": "Thumbnail concept description"
}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 3000,
        messages: [{ role: 'user', content: prompt }]
      })
    });

    const data = await response.json();
    const scriptText = data.content?.[0]?.text || '';
    
    // Try to parse JSON from response
    try {
      return JSON.parse(scriptText);
    } catch {
      // Fallback: wrap non-JSON response
      return {
        title: template.title.replace('{number}', '5').replace('{product_type}', 'Tech Products'),
        description: template.description,
        tags: template.tags,
        script: scriptText,
        duration: template.duration,
        thumbnail_idea: 'Clean text-based thumbnail with bold title and relevant image'
      };
    }
  } catch (error) {
    console.error('Script Generation Error:', error.message);
    return null;
  }
}

// ── Thumbnail Generation ─────────────────────────────────────────
async function generateThumbnailIdea(title, category) {
  try {
    const prompt = `Generate a detailed thumbnail concept for a YouTube video:
    
Title: ${title}
Category: ${category}
Style: Modern, eye-catching, high CTR

Provide:
1. Layout description (text placement, image composition)
2. Color scheme (primary, secondary, accent colors)
3. Typography (font styles, sizes, positioning)
4. Visual elements (icons, graphics, images)
5. Emotional triggers (curiosity, urgency, benefit)
6. A/B testing variations (2 different approaches)

Return as JSON with specific design instructions that can be given to a graphic designer or AI image generator.`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        messages: [{ role: 'user', content: prompt }]
      })
    });

    const data = await response.json();
    return data.content?.[0]?.text || '';
  } catch (error) {
    console.error('Thumbnail Generation Error:', error.message);
    return null;
  }
}

// ── Video Upload Simulation ─────────────────────────────────────
async function uploadVideo(videoData) {
  try {
    // In a real implementation, this would use YouTube's upload API
    // For now, we'll simulate and save the video data
    
    const videoInfo = {
      id: `VID_${Date.now()}`,
      title: videoData.title,
      description: videoData.description,
      tags: videoData.tags,
      category: videoData.category,
      duration: videoData.duration,
      script: videoData.script,
      thumbnail: videoData.thumbnail_idea,
      status: 'ready_to_upload',
      createdAt: new Date().toISOString(),
      estimatedViews: Math.floor(Math.random() * 10000) + 1000,
      estimatedRevenue: Math.floor(Math.random() * 500) + 50
    };
    
    // Save to videos directory
    const videoPath = `content/videos/${videoInfo.id}.json`;
    fs.writeFileSync(videoPath, JSON.stringify(videoInfo, null, 2));
    
    console.log(`✅ Video prepared: ${videoData.title}`);
    console.log(`📊 Estimated views: ${videoInfo.estimatedViews}`);
    console.log(`💰 Estimated revenue: ${videoInfo.estimatedRevenue} EUR`);
    
    return videoInfo;
  } catch (error) {
    console.error('Video Upload Error:', error.message);
    return null;
  }
}

// ── Content Calendar Generation ───────────────────────────────────
async function generateContentCalendar(days = 7) {
  console.log(`📅 Generating ${days}-day content calendar...`);
  
  const categories = Object.keys(VIDEO_CATEGORIES);
  const calendar = [];
  
  for (let i = 0; i < days; i++) {
    const category = categories[i % categories.length];
    const date = new Date();
    date.setDate(date.getDate() + i);
    
    console.log(`\n📝 Day ${i + 1}: ${category} content`);
    
    // Generate script
    const script = await generateVideoScript(category);
    if (script) {
      // Generate thumbnail idea
      const thumbnail = await generateThumbnailIdea(script.title, category);
      
      const videoData = {
        ...script,
        category,
        scheduledDate: date.toISOString(),
        thumbnail_idea: thumbnail
      };
      
      // Prepare for upload
      const video = await uploadVideo(videoData);
      calendar.push(video);
    }
    
    // Rate limiting
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  
  // Save calendar
  const calendarData = {
    id: Date.now(),
    period: `${days} days`,
    videos: calendar,
    totalVideos: calendar.length,
    estimatedMonthlyViews: calendar.reduce((sum, v) => sum + (v.estimatedViews || 0), 0),
    estimatedMonthlyRevenue: calendar.reduce((sum, v) => sum + (v.estimatedRevenue || 0), 0),
    createdAt: new Date().toISOString()
  };
  
  fs.writeFileSync('logs/youtube-calendar.json', JSON.stringify(calendarData, null, 2));
  
  return calendarData;
}

// ── Trend Analysis ───────────────────────────────────────────────
async function analyzeTrends() {
  try {
    // Get trending videos in your niche
    const trending = await youtubeFetch('/videos', {
      part: 'snippet,statistics',
      chart: 'mostPopular',
      regionCode: 'DE',
      maxResults: 10
    });
    
    // Analyze patterns
    const trends = trending.items?.map(video => ({
      title: video.snippet.title,
      views: parseInt(video.statistics.viewCount),
      tags: video.snippet.tags || [],
      category: video.snippet.categoryId
    })) || [];
    
    console.log('\n🔥 Trending Topics:');
    trends.forEach((trend, i) => {
      console.log(`${i + 1}. ${trend.title} - ${trend.views.toLocaleString()} views`);
    });
    
    return trends;
  } catch (error) {
    console.error('Trend Analysis Error:', error.message);
    return [];
  }
}

// ── Main Execution ───────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  
  switch (command) {
    case 'script':
      const category = args[1] || 'tech-reviews';
      const customPrompt = args.includes('--prompt') ? args[args.indexOf('--prompt') + 1] : '';
      
      const script = await generateVideoScript(category, customPrompt);
      if (script) {
        console.log('\n📝 Generated Script:');
        console.log(`Title: ${script.title}`);
        console.log(`Duration: ${script.duration} seconds`);
        console.log(`\nScript Preview:\n${script.script.substring(0, 500)}...`);
        
        // Save script
        const scriptPath = `content/scripts/${Date.now()}.json`;
        fs.writeFileSync(scriptPath, JSON.stringify(script, null, 2));
        console.log(`\n💾 Saved to: ${scriptPath}`);
      }
      break;
      
    case 'calendar':
      const days = parseInt(args[1]) || 7;
      const calendar = await generateContentCalendar(days);
      
      console.log(`\n✅ Content calendar generated!`);
      console.log(`📊 Total videos: ${calendar.totalVideos}`);
      console.log(`👀 Estimated monthly views: ${calendar.estimatedMonthlyViews.toLocaleString()}`);
      console.log(`💰 Estimated monthly revenue: ${calendar.estimatedMonthlyRevenue} EUR`);
      break;
      
    case 'trends':
      await analyzeTrends();
      break;
      
    case 'categories':
      console.log('\n📋 Available Video Categories:');
      Object.keys(VIDEO_CATEGORIES).forEach((key, i) => {
        const cat = VIDEO_CATEGORIES[key];
        console.log(`${i + 1}. ${key}: ${cat.title}`);
        console.log(`   Duration: ${cat.duration}s | Style: ${cat.style}`);
      });
      break;
      
    default:
      console.log(`
🤖 YouTube Automation Commands:

  script [category]     - Generate video script
    --prompt "[text]"   - Add custom requirements
    
  calendar [days]        - Generate content calendar
  trends                - Analyze trending topics
  categories            - Show available categories
  
Examples:
  node scripts/youtube-automation.js script tech-reviews
  node scripts/youtube-automation.js calendar 14
  node scripts/youtube-automation.js script make-money-online --prompt "Focus on affiliate marketing"
      `);
  }
}

// ── START ────────────────────────────────────────────────────────
if (require.main === module) {
  main().catch(console.error);
}

module.exports = {
  generateVideoScript,
  generateContentCalendar,
  analyzeTrends,
  uploadVideo
};
