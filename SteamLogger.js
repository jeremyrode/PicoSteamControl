"use strict";
const http = require('http');
const fs = require('fs');

const LOG_FILE = '/home/pi/SteamControlLog.txt';
const PORT = 65432;
const API_KEY = 'STEAM_LOGGER_SECRET_KEY'; // Replace with a secure key in production

const logfile = fs.createWriteStream(LOG_FILE, { flags: 'a' });
logfile.on('error', (err) => {
  console.error('File stream error. Check permissions or path:', err);
});

const server = http.createServer((req, res) => {
  if (req.method !== 'POST') {
    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('Method Not Allowed: Send a POST request to this endpoint');
    console.log('Got something besides a POST:', req.method);
    return;
  }

  if (req.headers['x-api-key'] !== API_KEY) {
    res.writeHead(401, { 'Content-Type': 'text/plain' });
    res.end('Unauthorized');
    console.log('Unauthorized request access attempt from:', req.socket.remoteAddress);
    return;
  }

  let data = '';
  req.on('data', chunk => {
    data += chunk.toString();
    // Destroy connection if payload is too large (> 10KB)
    if (data.length > 10240) {
      res.writeHead(413, { 'Content-Type': 'text/plain' });
      res.end('Payload Too Large');
      req.connection.destroy();
    }
  });

  req.on('end', () => {
    if (res.writableEnded) return; // Ignore if response already destroyed
    let curDate = new Date();
    let dateStr = curDate.toLocaleString();
    
    // Process batch messages separated by newline
    let messages = data.split('\n').filter(msg => msg.trim() !== '');
    
    messages.forEach(msg => {
      let logLine = `${dateStr} ${msg}`;
      console.log(logLine);
      logfile.write(logLine + '\n');
    });

    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('OK');
  });
});

server.listen(PORT, () => {
  console.log('Server running on port ' + PORT);
});

