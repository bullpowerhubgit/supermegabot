const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8082;
const HTML_FILE = '/Users/rudolfsarkany/shopify-dashboard/public/rudibot-mega-dashboard-dark.html';

const server = http.createServer((req, res) => {
  if (req.url === '/') {
    fs.readFile(HTML_FILE, 'utf8', (err, data) => {
      if (err) {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        res.end('Fehler: ' + err.message);
        return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(data);
    });
  } else {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
  }
});

server.listen(PORT, () => {
  console.log(`✅ RudiBot Dashboard läuft auf http://localhost:${PORT}`);
  console.log(`📄 Serviert: ${HTML_FILE}`);
});
