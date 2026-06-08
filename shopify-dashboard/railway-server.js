const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 8082;

// Serve static files from build directory
app.use(express.static(path.join(__dirname, 'build')));

// API health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'RudiBot Shopify Suite', port: PORT });
});

// Serve index.html for all other routes (SPA support)
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'build', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`✅ RudiBot Shopify Suite läuft auf Port ${PORT}`);
  console.log(`📄 Static files: ${path.join(__dirname, 'build')}`);
});
