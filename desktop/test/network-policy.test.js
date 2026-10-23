'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { configureEarly, guardSession, isLoopbackRequest, sameOrigin } = require('../electron/network-policy');

test('strict mode accepts only loopback web requests', () => {
  for (const url of ['http://127.0.0.1:8760/', 'https://localhost:1234/a', 'ws://[::1]:9000/']) {
    assert.equal(isLoopbackRequest(url), true, url);
  }
  for (const url of ['https://example.com/', 'http://localhost.evil.test/',
    'https://192.168.1.5/', 'https://127.0.0.1.evil.test/', 'not a URL']) {
    assert.equal(isLoopbackRequest(url), false, url);
  }
});

test('navigation rejects lookalike origins', () => {
  assert.equal(sameOrigin('http://127.0.0.1:8760/page', 'http://127.0.0.1:8760'), true);
  assert.equal(sameOrigin('http://127.0.0.1:8760.evil.test/', 'http://127.0.0.1:8760'), false);
  assert.equal(sameOrigin('https://example.com/', 'http://127.0.0.1:8760'), false);
});

test('strict Chromium policy disables background network services before launch', () => {
  const flags = [];
  const app = { commandLine: { appendSwitch: (flag) => flags.push(flag) } };
  configureEarly(app, 'strict');
  assert.ok(flags.includes('disable-background-networking'));
  assert.ok(flags.includes('disable-component-update'));
  configureEarly(app, 'connected');
  assert.equal(flags.length, 6);
});

test('strict session cancels external requests but preserves local UI and API', () => {
  let listener;
  const session = { webRequest: { onBeforeRequest: (_filter, callback) => { listener = callback; } } };
  guardSession(session, 'strict');
  for (const [url, expected] of [
    ['http://127.0.0.1:8760/api/providers', false],
    ['file:///C:/RedForge/splash.html', false],
    ['https://example.com/telemetry', true],
    ['not-a-url:', false],
  ]) {
    let decision;
    listener({ url }, (result) => { decision = result; });
    assert.deepEqual(decision, { cancel: expected }, url);
  }
});

test('connected session does not install strict interceptor', () => {
  let installed = false;
  const session = { webRequest: { onBeforeRequest: () => { installed = true; } } };
  guardSession(session, 'connected');
  assert.equal(installed, false);
});
