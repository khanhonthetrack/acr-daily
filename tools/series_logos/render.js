// The ranked series' logos (client/acr_daily/series): logos.html drawn by Chromium (its fonts from Google Fonts, all
// under the SIL Open Font License), each logo with its transparency (<key>-logo.png, then cut to 600 x 340) and on its
// coloured tile (tiles.html: <key>.png, 640 x 360). Run from this folder: node render.js, then copy the PNGs over.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ deviceScaleFactor: 2, viewport: { width: 620, height: 1500 } });
  await p.goto('file://' + __dirname + '/logos.html');
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(800);
  for (const id of ['rally2', 'junior', 'classic', 'sixties']) await p.locator('#' + id).screenshot({ path: id + '-logo.png', omitBackground: true });
  const t = await b.newPage({ deviceScaleFactor: 1, viewport: { width: 640, height: 1500 } });
  await t.goto('file://' + __dirname + '/tiles.html');
  await t.waitForTimeout(500);
  for (const id of ['rally2', 'junior', 'classic', 'sixties']) await t.locator('#' + id).screenshot({ path: id + '.png' });
  await b.close();
})();
