const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const htmlPath = path.join(__dirname, '..', '视频播放器.html');
const html = fs.readFileSync(htmlPath, 'utf8');

test('the inline player script remains valid JavaScript', () => {
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 1);
  assert.doesNotThrow(() => new Function(scripts[0][1]));
});

test('the saved playlist selection is restored', () => {
  assert.match(html, /saved\.activePlaylistId/);
  assert.match(html, /library\.activePlaylistId = saved\.activePlaylistId/);
});
