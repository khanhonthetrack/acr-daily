// The downloads (src/release.js): the apps' own UPDATE keeps the one-file exe; the website gives the installer's zip.
import test from 'node:test';
import assert from 'node:assert/strict';
import { downloadUrl, siteDownloadUrl } from '../src/release.js';
import { guidePage } from '../src/guidepage.js';

const REL = 'https://github.com/x/y/releases/download/v{version}';
const ENV = { LATEST_VERSION: '0.2.1', DOWNLOAD_URL: `${REL}/ACR-Daily.exe`, SITE_DOWNLOAD_URL: `${REL}/ACR-Daily-{version}.zip`,
  SOURCE_URL: 'https://github.com/x/y' };

test('the apps update from the exe, the website hands out the zip (every {version} filled in)', () => {
  assert.equal(downloadUrl(ENV), 'https://github.com/x/y/releases/download/v0.2.1/ACR-Daily.exe');
  assert.equal(siteDownloadUrl(ENV), 'https://github.com/x/y/releases/download/v0.2.1/ACR-Daily-0.2.1.zip');
  // without SITE_DOWNLOAD_URL: the exe, as before
  assert.equal(siteDownloadUrl({ ...ENV, SITE_DOWNLOAD_URL: '' }), downloadUrl(ENV));
});

test("the guide: the zip's button, the installer's step, the checks on the zip", () => {
  const h = guidePage(ENV);
  assert.ok(h.includes('href="https://github.com/x/y/releases/download/v0.2.1/ACR-Daily-0.2.1.zip"'));
  assert.ok(h.includes('ACR-Daily-Setup.exe'));
  assert.ok(h.includes('certutil -hashfile ACR-Daily-0.2.1.zip SHA256'));
  assert.ok(h.includes('gh attestation verify ACR-Daily-0.2.1.zip'));
  assert.ok(!h.includes('No install needed'));
});
