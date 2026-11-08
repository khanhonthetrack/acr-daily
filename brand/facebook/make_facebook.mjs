// Draws the Facebook page artwork: the cover banner and the profile picture. Everything in them is drawn here
// (night sky, mountain ridges, a hairpin road with a long-exposure light trail, dust in the air) from the logo's
// own paths (server/src/logo.js), so no outside image is used. Lettering: Barlow Condensed (SIL Open Font
// License), as in the logo. Run from the repository folder:
//   node brand/facebook/make_facebook.mjs
// It needs Playwright with Chromium (`npm i -g playwright`) and fetches the fonts from Google Fonts with curl the
// first time (kept in brand/facebook/.fonts, not committed). Writes, next to this script:
//   acr-daily-facebook-cover.png    1640 x 624  (Facebook shows 820 x 312 on computers, the middle 16:9 on phones)
//   acr-daily-facebook-profile.png  1080 x 1080 (Facebook shows it as a circle)
//   acr-daily-facebook-cover.svg, acr-daily-facebook-profile.svg  the same drawings (lettering needs the fonts)
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';

const here = new URL('.', import.meta.url);
const require = createRequire(import.meta.url);

// ---- the logo (server/src/logo.js: the D-car and the letters, viewBox 0 0 163.6 200) ----
const logoSrc = readFileSync(new URL('../../server/src/logo.js', import.meta.url), 'utf8');
const pathOf = (name) => logoSrc.match(new RegExp(`const ${name} = '([^']+)'`))[1];
const CAR = pathOf('CAR'), ACR = pathOf('ACR');
const RED = '#E30613', WHITE = '#F4F4F5', BLACK = '#0A0A0B';
const LOGO_W = 163.6, LOGO_H = 200;

// ---- fonts ----
const FONT_DIR = process.env.BARLOW_DIR ? new URL(`file://${process.env.BARLOW_DIR}/`) : new URL('.fonts/', here);
const FONTS = {   // file -> [weight, style, Google Fonts file]
  'BarlowCondensed-900i.ttf': [900, 'italic', 'HTxyL3I-JCGChYJ8VI-L6OO_au7B6xTrW3bWvA'],
  'BarlowCondensed-800i.ttf': [800, 'italic', 'HTxyL3I-JCGChYJ8VI-L6OO_au7B6xTrf3fWvA'],
  'BarlowCondensed-500.ttf': [500, 'normal', 'HTxwL3I-JCGChYJ8VI-L6OO_au7B4-Lw_3E'],
  'BarlowCondensed-700.ttf': [700, 'normal', 'HTxwL3I-JCGChYJ8VI-L6OO_au7B46r2_3E'],
};
function fontFaces() {
  mkdirSync(FONT_DIR, { recursive: true });
  return Object.entries(FONTS).map(([file, [weight, style, id]]) => {
    const f = new URL(file, FONT_DIR);
    if (!existsSync(f)) execFileSync('curl', ['-sSfo', f.pathname, `https://fonts.gstatic.com/s/barlowcondensed/v13/${id}.ttf`]);
    const b64 = readFileSync(f).toString('base64');
    return `@font-face{font-family:'Barlow Condensed';font-weight:${weight};font-style:${style};src:url(data:font/ttf;base64,${b64})}`;
  }).join('\n');
}

// ---- helpers ----
function rng(seed) {   // mulberry32: the same drawing every run
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const r1 = (n) => Math.round(n * 10) / 10;
const lerp = (a, b, t) => a + (b - a) * t;

/** A ridge line: bumps (x, height, width) on a base line, roughened by octaves of noise. Returns y for each x. */
function ridge(rand, w, base, bumps, rough) {
  const oct = [[0.004, rough], [0.011, rough * 0.45], [0.029, rough * 0.18], [0.07, rough * 0.07]]
    .map(([f, a]) => [f, a, rand() * 1000]);
  return (x) => {
    let y = base;
    for (const [bx, bh, bw] of bumps) y -= bh * Math.exp(-(((x - bx) / bw) ** 2));
    for (const [f, a, p] of oct) y += a * (Math.sin(x * f + p) * 0.6 + Math.sin(x * f * 2.13 + p * 1.7) * 0.4);
    return y;
  };
}
function ridgePath(fy, w, h, step = 4) {
  let d = `M-20 ${h + 20}L-20 ${r1(fy(-20))}`;
  for (let x = -20; x <= w + 20; x += step) d += `L${x} ${r1(fy(x))}`;
  return d + `L${w + 20} ${h + 20}Z`;
}
function ridgeLine(fy, w, step = 4) {
  let d = `M-20 ${r1(fy(-20))}`;
  for (let x = -20; x <= w + 20; x += step) d += `L${x} ${r1(fy(x))}`;
  return d;
}

/** A road of legs joined by hairpins: [x, y] points, a leg's end marked 'turn' when a hairpin takes it round to
 *  the next point. Returns {d, depth} pieces, so far ones can be drawn thinner. */
function roadPieces(pts, bulge = 0.6) {
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
    if (pts[i][2] === 'turn') continue;
    if (pts[i + 1][2] === 'turn') {   // a hairpin: from here round the turn point to the one after
      const [x2, y2] = pts[i + 2];
      const dir = Math.sign(x1 - x0) || 1, k = Math.abs(y2 - y1) * bulge + 6;
      out.push({ d: `M${r1(x0)} ${r1(y0)}L${r1(x1)} ${r1(y1)}C${r1(x1 + dir * k)} ${r1(y1)} ${r1(x2 + dir * k)} ${r1(y2)} ${r1(x2)} ${r1(y2)}`,
        depth: (y0 + y2) / 2 });
    } else {
      const mx = (x0 + x1) / 2, my = (y0 + y1) / 2 - Math.abs(x1 - x0) * 0.03;
      out.push({ d: `M${r1(x0)} ${r1(y0)}Q${r1(mx)} ${r1(my)} ${r1(x1)} ${r1(y1)}`, depth: (y0 + y1) / 2 });
    }
  }
  return out;
}

function stars(rand, n, w, h, maxY) {
  let s = '';
  for (let i = 0; i < n; i++) {
    const x = rand() * w, y = Math.pow(rand(), 1.4) * maxY, r = 0.4 + rand() * rand() * 1.6;
    s += `<circle cx="${r1(x)}" cy="${r1(y)}" r="${r1(r)}" fill="${WHITE}" opacity="${(0.15 + rand() * 0.6 * (1 - y / maxY)).toFixed(2)}"/>`;
  }
  return s;
}

function dust(rand, n, cx, cy, sx, sy, maxR) {   // lit specks of dust drifting over the stage
  let s = '';
  for (let i = 0; i < n; i++) {
    const u = rand() * 2 - 1, v = rand() * 2 - 1;
    const x = cx + u * sx, y = cy + v * sy, r = 0.5 + Math.pow(rand(), 3) * maxR;
    const warm = rand() < 0.5 ? '#FFD9C2' : '#FF6A55';
    s += `<circle cx="${r1(x)}" cy="${r1(y)}" r="${r1(r)}" fill="${warm}" opacity="${(0.08 + rand() * 0.35 * (1 - Math.abs(u) * 0.7)).toFixed(2)}"/>`;
  }
  return s;
}

/** A line of pines standing on a ridge, as one silhouette path (fill it as the ridge). */
function pines(rand, fy, x0, x1, hMin, hMax, gap = 0) {
  let d = '';
  for (let x = x0; x <= x1;) {
    const h = hMin + rand() * (hMax - hMin), base = fy(x) + h * 0.12, top = base - h, T = 5;
    if (rand() >= gap) {
      const right = [];
      for (let i = 1; i <= T; i++) {
        const yi = top + h * 0.9 * i / T, wi = h * (0.05 + 0.19 * i / T) * (0.85 + rand() * 0.3);
        right.push([x + wi, yi]);
        if (i < T) right.push([x + wi * 0.3, yi - h * 0.03]);
      }
      right.push([x + h * 0.035, base + 6]);
      const left = right.map(([px, py]) => [2 * x - px, py]).reverse();
      d += `M${r1(x)} ${r1(top)}` + [...right, ...left].map(([px, py]) => `L${r1(px)} ${r1(py)}`).join('') + 'Z';
    }
    x += h * (0.14 + rand() * 0.22);
  }
  return d;
}

/** The light trail along the road: a wide red haze, a red streak and a white-hot core; far pieces thinner. */
function trail(pieces, near, far, scale = 1) {
  const wAt = (depth) => scale * lerp(0.55, 2.6, Math.max(0, Math.min(1, (depth - far) / (near - far))));
  let road = '', haze = '', streak = '', core = '';
  for (const { d, depth } of pieces) {
    const w = wAt(depth);
    road += `<path d="${d}" stroke="#2A1416" stroke-width="${r1(w * 7)}" opacity=".85"/>`;
    haze += `<path d="${d}" stroke="${RED}" stroke-width="${r1(w * 9)}"/>`;
    streak += `<path d="${d}" stroke="#FF2A1F" stroke-width="${r1(w * 2.4)}"/>`;
    core += `<path d="${d}" stroke="#FFE6D6" stroke-width="${r1(Math.max(0.5, w * 0.8))}"/>`;
  }
  return `<g fill="none" stroke-linecap="round" stroke-linejoin="round">${road}` +
    `<g filter="url(#haze)" opacity=".55">${haze}</g><g filter="url(#soft)">${streak}</g>${core}</g>`;
}

const filters = `
  <filter id="haze" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
  <filter id="soft" x="-10%" y="-50%" width="120%" height="200%"><feGaussianBlur stdDeviation="1.6"/></filter>
  <filter id="grain" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="7" result="n"/>
    <feColorMatrix in="n" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .9 -.35"/>
  </filter>
  <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="14"/></filter>`;

const logo = (x, y, h) => {
  const s = h / LOGO_H;
  return `<g transform="translate(${r1(x)} ${r1(y)}) scale(${s.toFixed(4)})">` +
    `<g filter="url(#shadow)" opacity=".75"><path fill="#000" fill-rule="evenodd" d="${CAR}"/><path fill="#000" d="${ACR}"/></g>` +
    `<path fill="${RED}" fill-rule="evenodd" d="${CAR}"/><path fill="${WHITE}" d="${ACR}"/></g>`;
};

// ---- the cover: 1640 x 624 ----
function cover() {
  const W = 1640, H = 624, rand = rng(20261108);
  // ridges, far to near; the hairpin mountain stands on the right, beyond what a phone shows of the middle
  const far = ridge(rand, W, 336, [[240, 80, 170], [760, 45, 230], [1180, 70, 160]], 20);
  const mid = ridge(rand, W, 420, [[110, 70, 170], [620, 34, 200], [1495, 205, 230]], 14);
  const near = ridge(rand, W, 526, [[30, 130, 210], [470, 40, 240], [930, 24, 200], [1650, 30, 120]], 10);
  // the road: a sweep across the foot of the picture, then hairpins up the mountain and over its shoulder
  const pts = [[-40, 652], [520, 612], [1020, 592], [1565, 552, 'turn'], [1534, 507], [1372, 494, 'turn'],
    [1388, 459], [1604, 447, 'turn'], [1588, 418], [1424, 410, 'turn'], [1436, 388], [1584, 380, 'turn'],
    [1572, 360], [1464, 356, 'turn'], [1472, 340], [1562, 334, 'turn'], [1555, 321], [1494, 318, 'turn'],
    [1500, 308], [1548, 299]];
  const pieces = roadPieces(pts);

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
<defs>${filters}
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#040405"/><stop offset=".38" stop-color="#10070A"/>
    <stop offset=".54" stop-color="#3A0B12"/><stop offset=".66" stop-color="#6A1018"/><stop offset="1" stop-color="#1A0709"/>
  </linearGradient>
  <radialGradient id="ember" cx="1420" cy="300" r="620" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#FF3B2A" stop-opacity=".6"/><stop offset=".3" stop-color="${RED}" stop-opacity=".22"/>
    <stop offset="1" stop-color="${RED}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="fog" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FF4A3A" stop-opacity="0"/><stop offset=".5" stop-color="#FF4A3A" stop-opacity=".09"/>
    <stop offset="1" stop-color="#FF4A3A" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#050506" stop-opacity=".9"/><stop offset=".3" stop-color="#050506" stop-opacity=".62"/>
    <stop offset=".62" stop-color="#050506" stop-opacity=".25"/><stop offset=".8" stop-color="#050506" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
    <stop offset=".7" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/>
  </linearGradient>
</defs>
<rect width="${W}" height="${H}" fill="url(#sky)"/>
${stars(rand, 200, W, H, 290)}
<rect width="${W}" height="${H}" fill="url(#ember)"/>
<path d="${ridgePath(far, W, H)}" fill="#33101A"/>
<path d="${ridgeLine(far, W)}" fill="none" stroke="#FF5A48" stroke-opacity=".3" stroke-width="1.2"/>
<rect y="300" width="${W}" height="150" fill="url(#fog)"/>
<path d="${ridgePath(mid, W, H)}${pines(rand, mid, -10, 1380, 9, 20, 0.15)}" fill="#1D0A0F"/>
<path d="${ridgeLine(mid, W)}" fill="none" stroke="#FF5A48" stroke-opacity=".35" stroke-width="1.3"/>
<rect y="390" width="${W}" height="150" fill="url(#fog)"/>
${trail(pieces.filter((p) => p.depth < 540), 640, 300)}
<path d="${ridgePath(near, W, H)}${pines(rand, near, -10, 1660, 26, 64, 0.08)}" fill="#0C0608"/>
${trail(pieces.filter((p) => p.depth >= 540), 640, 300)}
${dust(rand, 300, 1420, 470, 420, 160, 2.6)}
<rect width="${W}" height="${H}" fill="url(#fade)"/>
<rect width="${W}" height="${H}" fill="url(#floor)"/>
${logo(318, 118, 388)}
<g font-family="Barlow Condensed" fill="${WHITE}">
  <text x="690" y="190" font-weight="700" font-size="29" letter-spacing="7" fill="${RED}">FOR ASSETTO CORSA RALLY</text>
  <text x="682" y="312" font-weight="900" font-style="italic" font-size="145" letter-spacing="1">YOUR DAILY</text>
  <text x="684" y="390" font-weight="900" font-style="italic" font-size="78" letter-spacing="1">COMPETITIVE PORTAL</text>
  <text x="690" y="444" font-weight="500" font-size="30" letter-spacing="2" fill="#D4D4D8">Daily stages <tspan fill="${RED}">·</tspan> Leagues <tspan fill="${RED}">·</tspan> 1V1s <tspan fill="${RED}">·</tspan> Cups <tspan fill="${RED}">·</tspan> Live timing</text>
  <g transform="translate(690 470)">
    <path d="M10 0H196L186 40H0Z" fill="${RED}"/>
    <text x="96" y="30" text-anchor="middle" font-weight="800" font-style="italic" font-size="29" letter-spacing="2">ACRDAILY.COM</text>
  </g>
</g>
<rect width="${W}" height="${H}" filter="url(#grain)" opacity=".05"/>
</svg>`;
  return { svg, W, H };
}

// ---- the profile picture: 720 x 720 drawn, rendered at 1080 ----
function profile() {
  const W = 720, H = 720, rand = rng(1108);
  const far = ridge(rand, W, 452, [[110, 70, 120], [590, 100, 150]], 12);
  const mid = ridge(rand, W, 530, [[350, 80, 220]], 9);
  const near = ridge(rand, W, 668, [[-20, 90, 140], [740, 80, 130]], 6);
  const pts = [[-30, 752], [420, 714], [640, 692, 'turn'], [602, 652], [150, 628, 'turn'], [178, 597], [520, 580, 'turn'],
    [502, 557], [252, 546, 'turn'], [262, 529], [440, 520, 'turn'], [432, 508], [330, 503]];
  const pieces = roadPieces(pts);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
<defs>${filters}
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#040405"/><stop offset=".36" stop-color="#10070A"/>
    <stop offset=".56" stop-color="#3A0B12"/><stop offset=".68" stop-color="#6A1018"/><stop offset="1" stop-color="#120607"/>
  </linearGradient>
  <radialGradient id="ember" cx="360" cy="450" r="440" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#FF3B2A" stop-opacity=".55"/><stop offset=".35" stop-color="${RED}" stop-opacity=".18"/>
    <stop offset="1" stop-color="${RED}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="fog" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FF4A3A" stop-opacity="0"/><stop offset=".5" stop-color="#FF4A3A" stop-opacity=".09"/>
    <stop offset="1" stop-color="#FF4A3A" stop-opacity="0"/>
  </linearGradient>
  <radialGradient id="vignette" cx="360" cy="360" r="380" gradientUnits="userSpaceOnUse">
    <stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/>
  </radialGradient>
</defs>
<rect width="${W}" height="${H}" fill="url(#sky)"/>
${stars(rand, 110, W, H, 360)}
<rect width="${W}" height="${H}" fill="url(#ember)"/>
<path d="${ridgePath(far, W, H, 3)}" fill="#33101A"/>
<path d="${ridgeLine(far, W, 3)}" fill="none" stroke="#FF5A48" stroke-opacity=".3" stroke-width="1.2"/>
<rect y="420" width="${W}" height="120" fill="url(#fog)"/>
<path d="${ridgePath(mid, W, H, 3)}${pines(rand, mid, -10, 730, 8, 17, 0.2)}" fill="#1D0A0F"/>
<path d="${ridgeLine(mid, W, 3)}" fill="none" stroke="#FF5A48" stroke-opacity=".35" stroke-width="1.3"/>
${trail(pieces, 720, 490, 1.15)}
<path d="${ridgePath(near, W, H, 3)}${pines(rand, near, -20, 150, 40, 90)}${pines(rand, near, 590, 740, 40, 90)}" fill="#0C0608"/>
${dust(rand, 140, 360, 590, 330, 110, 2.4)}
<rect width="${W}" height="${H}" fill="url(#vignette)"/>
${logo(360 - LOGO_W * 2.2 / 2 - 6, 360 - LOGO_H * 2.2 / 2 - 28, LOGO_H * 2.2)}
<rect width="${W}" height="${H}" filter="url(#grain)" opacity=".05"/>
</svg>`;
  return { svg, W, H };
}

// ---- render ----
const faces = fontFaces();
const { chromium } = require('playwright');
const browser = await chromium.launch();
for (const [name, art, px] of [['cover', cover(), 1640], ['profile', profile(), 1080]]) {
  writeFileSync(new URL(`acr-daily-facebook-${name}.svg`, here), art.svg + '\n');
  const scale = px / art.W;
  const page = await browser.newPage({ viewport: { width: art.W, height: art.H }, deviceScaleFactor: scale });
  await page.setContent(`<!doctype html><html><head><style>${faces}html,body{margin:0;background:${BLACK}}svg{display:block}</style></head><body>${art.svg}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: new URL(`acr-daily-facebook-${name}.png`, here).pathname });
  await page.close();
  console.log(`acr-daily-facebook-${name}.png: ${Math.round(art.W * scale)} x ${Math.round(art.H * scale)}`);
}
await browser.close();
