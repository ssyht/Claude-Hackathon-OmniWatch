const { app, BrowserWindow } = require('electron');
const path = require('path');
const http = require('http');
const fs = require('fs');
const url = require('url');

// ── Serve frontend files on localhost:3000 ──
function startFileServer() {
  const MIME = {
    '.html': 'text/html', '.js': 'application/javascript',
    '.css': 'text/css', '.png': 'image/png',
    '.jpg': 'image/jpeg', '.mp4': 'video/mp4', '.json': 'application/json'
  };
  http.createServer((req, res) => {
    let filePath = path.join(__dirname, url.parse(req.url).pathname);
    if (filePath.endsWith('/')) filePath += 'index.html';
    const ext = path.extname(filePath);
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end('Not found'); return; }
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      res.end(data);
    });
  }).listen(3000);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1200,
    minHeight: 700,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#05040a',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  win.loadURL('http://localhost:3000/index.html');
}

app.whenReady().then(() => {
  startFileServer();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});