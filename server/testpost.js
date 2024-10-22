const http = require('http');

const server = http.createServer((req, res) => {
  if (req.method === 'POST') {
    let data = '';
    req.on('data', chunk => {
      data += chunk.toString();
    });
    req.on('end', () => {
      console.log('POST data:', data);
      res.end('Data received');
    });
  } else {
    res.end('Send a POST request to this endpoint');
  }
});

server.listen(65432, () => {
  console.log('Server running on port 3000');
});