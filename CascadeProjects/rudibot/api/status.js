module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.json({
    status: 'running',
    version: '2.0.0',
    systems: 30,
    timestamp: new Date().toISOString(),
    env_check: {
      shopify:    !!process.env.SHOPIFY_STORE_DOMAIN,
      telegram:   !!process.env.TELEGRAM_BOT_TOKEN,
      anthropic:  !!process.env.ANTHROPIC_API_KEY,
      supabase:   !!process.env.SUPABASE_URL,
      printify:   !!process.env.PRINTIFY_API_KEY,
      perplexity: !!process.env.PERPLEXITY_API_KEY,
      resend:     !!process.env.RESEND_API_KEY,
    }
  })
}
