const test = require('node:test');
const assert = require('node:assert/strict');

const { parseHttpUrl, progressPayload } = require('../视频嗅探面板.js');

test('download URLs only accept HTTP and HTTPS', () => {
  assert.equal(parseHttpUrl('https://example.com/video.m4s').protocol, 'https:');
  assert.equal(parseHttpUrl('http://example.com/video.mp4').protocol, 'http:');
  assert.throws(() => parseHttpUrl('file:///C:/secret.txt'), /HTTP\/HTTPS/);
  assert.throws(() => parseHttpUrl('not a url'), /下载地址无效/);
});

test('progress responses expose terminal errors to the page', () => {
  assert.deepEqual(progressPayload(undefined), {
    done: false,
    status: 'notfound',
    error: null,
  });
  assert.deepEqual(progressPayload({ status: 'error', error: 'FFmpeg failed' }), {
    done: false,
    status: 'error',
    error: 'FFmpeg failed',
  });
  assert.deepEqual(progressPayload({ status: 'done' }), {
    done: true,
    status: 'done',
    error: null,
  });
});
