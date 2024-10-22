const http = require('http');
const fs = require('fs');

const LOG_FILE = '/home/pi/SteamControlLog.txt';
const PORT = 65432;

const logfile = fs.createWriteStream(LOG_FILE, {flags:'a'});

const server = http.createServer((req, res) => {
  if (req.method === 'POST') {
    let data = '';
    req.on('data', chunk => {
      data += chunk.toString();
    });
    req.on('end', () => {
      let curDate = new Date();
      let dateStr = curDate.toString();
      message = dateStr.slice(0,dateStr.length-33) + ' ' + data; //Prepend Time to message
      console.log(message);
      logfile.write(message + '\n')
      res.end('OK');
    });
  } else {
    res.end('Send a POST request to this endpoint');
    console.log('Got something besides a POST');
  }
});

server.listen(PORT, () => {
  console.log('Server running on port ' + PORT);
});

