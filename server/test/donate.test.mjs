// /donate (src/donatepage.js): COMMUNITY's Donate, Buy Me a Coffee and PayPal.
import test from 'node:test';
import assert from 'node:assert/strict';
import { donatePage } from '../src/donatepage.js';

test('the donate page: both buttons, each to its own site in a new tab, and the supporters under them', () => {
  const h = donatePage({});
  assert.match(h, /<a class="go bmc" href="https:\/\/www\.buymeacoffee\.com\/acrdaily" target="_blank" rel="noopener"><img src="https:\/\/cdn\.buymeacoffee\.com\/buttons\/v2\/default-yellow\.png"/);
  assert.match(h, /<a class="go pp" href="https:\/\/paypal\.me\/blugyke" target="_blank" rel="noopener"/);
  assert.match(h, /fetch\('\/api\/supporters'\)/);
  assert.match(h, /THANK YOU TO OUR SUPPORTERS/);
  assert.match(h, /class="roll"/);
  assert.match(h, /data-k="donate"/);
});
