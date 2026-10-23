'use strict';

// Electron can make Chromium background requests even when RedForge's API and
// updater are offline. Install these guards before the first window/session.
const net = require('node:net');

function isLoopbackRequest(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return false;
    const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
    return host === 'localhost' || host === '::1' ||
      (net.isIP(host) === 4 && host.startsWith('127.'));
  } catch {
    return false;
  }
}

function sameOrigin(left, right) {
  try { return new URL(left).origin === new URL(right).origin; } catch { return false; }
}

function configureEarly(app, profile) {
  if (profile !== 'strict') return;
  for (const flag of [
    'disable-background-networking',
    'disable-component-update',
    'disable-domain-reliability',
    'disable-sync',
    'no-default-browser-check',
    'no-pings',
  ]) app.commandLine.appendSwitch(flag);
}

function guardSession(session, profile, log = () => {}) {
  if (profile !== 'strict') return;
  session.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, done) => {
    // Local HTML, data URLs, and Chromium internals are not network requests.
    const networkUrl = /^(https?|wss?):/i.test(details.url);
    const blocked = networkUrl && !isLoopbackRequest(details.url);
    if (blocked) log('strict mode blocked external web request');
    done({ cancel: blocked });
  });
}

module.exports = { configureEarly, guardSession, isLoopbackRequest, sameOrigin };
