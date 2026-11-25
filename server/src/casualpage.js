// CASUAL's pacenotes page (/n/<token>): for the person next to the driver (or on Discord) without the game. Phone-first,
// dark, big text: the lobby's stage's notes in a list, NEXT / BACK buttons, a tap on a note sets the current one, the place
// kept in localStorage. No login: the link (token) is the key. The script is a plain string (wrangler bundles with
// keepNames: a function stringified from server code would carry a helper that is not there in the browser).

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const CSS = `
:root{--bg:#0b0b0d;--bg2:#15151a;--line:#2a2a33;--fg:#f4f4f6;--fg2:#a9a9b4;--acc:#FF4655}
/* the note on now: the in-game notes' orange bar (seen on a phone 26 Nov 2026: a thin line, under the header) */
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--fg);font-family:'Barlow Condensed','Arial Narrow',Arial,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg2);border-bottom:2px solid var(--acc);padding:10px 16px;display:flex;
  align-items:center;gap:12px}
header .mark{font-weight:800;letter-spacing:.12em;color:var(--fg);font-size:15px;white-space:nowrap;border-bottom:3px solid var(--acc)}
header .t{min-width:0;flex:1}
header .t b{display:block;font-size:22px;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
header .t span{display:block;color:var(--fg2);font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
ol{list-style:none;margin:0;padding:34vh 0 42vh}
li.n{display:flex;align-items:baseline;gap:14px;padding:16px;border-bottom:1px solid var(--line);cursor:pointer;opacity:.55}
li.n .num{width:2.2em;color:var(--fg2);font-size:20px;text-align:right}
li.n .tx{flex:1;font-size:34px;font-weight:700;line-height:1.1;letter-spacing:.02em;text-transform:uppercase}
li.n .d{color:var(--fg2);font-size:20px;white-space:nowrap}
li.n.past{opacity:.3}
li.n.cur{opacity:1;background:#FF9F0A;color:#0b0b0d}
li.n.cur .num,li.n.cur .d{color:#0b0b0d}
li.n.cur .tx{font-size:44px}
nav{position:fixed;left:0;right:0;bottom:0;z-index:5;display:flex;gap:8px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));
  background:var(--bg2);border-top:1px solid var(--line)}
nav button{flex:1;min-height:64px;border:0;border-radius:6px;background:#26262e;color:var(--fg);font:800 26px 'Barlow Condensed',Arial,sans-serif;
  letter-spacing:.08em;cursor:pointer}
nav button.next{flex:2;background:var(--acc)}
nav button.jump{flex:0 0 72px;font-size:18px}
nav button:active{filter:brightness(1.25)}
.gone{max-width:420px;margin:18vh auto;padding:0 24px;text-align:center}
.gone b{display:block;color:var(--fg);letter-spacing:.12em;font-size:18px;margin-bottom:12px}
.gone p{font-size:24px;margin:0;color:var(--fg2)}
`;

const SCRIPT = `
(function(){
  var token=document.body.getAttribute('data-t')||'';
  var KEY='acrn:'+token;
  var items=[].slice.call(document.querySelectorAll('li.n'));
  var cur=0;
  try{var s=parseInt(localStorage.getItem(KEY),10);if(s>=0&&s<items.length)cur=s}catch(e){}
  function show(i,smooth){
    if(!items.length)return;
    cur=Math.max(0,Math.min(items.length-1,i));
    for(var k=0;k<items.length;k++){items[k].className='n'+(k<cur?' past':'')+(k===cur?' cur':'')}
    try{localStorage.setItem(KEY,String(cur))}catch(e){}
    center(smooth);
  }
  function center(smooth){
    var el=items[cur];if(!el)return;
    var r=el.getBoundingClientRect();
    var want=window.innerHeight/2-r.height/2;
    window.scrollTo({top:window.pageYOffset+r.top-want,behavior:smooth?'smooth':'auto'});
  }
  document.getElementById('next').onclick=function(){show(cur+1,true)};
  document.getElementById('back').onclick=function(){show(cur-1,true)};
  document.getElementById('jump').onclick=function(){center(true)};
  items.forEach(function(el,i){el.onclick=function(){show(i,true)}});
  document.addEventListener('keydown',function(e){
    var k=e.key;
    if(k==='ArrowRight'||k==='ArrowDown'||k===' '||k==='PageDown'){e.preventDefault();show(cur+1,true)}
    else if(k==='ArrowLeft'||k==='ArrowUp'||k==='PageUp'){e.preventDefault();show(cur-1,true)}
  });
  function wake(){try{if(navigator.wakeLock&&navigator.wakeLock.request){navigator.wakeLock.request('screen').catch(function(){})}}catch(e){}}
  wake();
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='visible')wake()});
  show(cur,false);
})();
`;

const head = (title) => `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#0b0b0d">
<title>${esc(title)}</title><style>${CSS}</style></head>`;

/** The notes page for a lobby's stage. info: {stage: {stageName, menuName, rally}, car: {name}, notes: [{n, at, text}]}. */
export function notesPage(token, info) {
  const notes = info.notes || [];
  const name = info.stage.menuName || info.stage.stageName || info.stage.track || '';
  const sub = [info.stage.rally, info.car && info.car.name].filter(Boolean).join(' · ');
  const rows = notes.map((x, i) => {
    const next = notes[i + 1];
    const d = next ? Math.max(0, Math.round(next.at - x.at)) : null;
    return `<li class="n"><span class="num">${esc(x.n)}</span><span class="tx">${esc(String(x.text).toUpperCase())}</span>` +
      `<span class="d">${d == null ? '' : esc(d) + ' m'}</span></li>`;
  }).join('');
  return `${head(name + ' pacenotes')}<body data-t="${esc(token)}">
<header><span class="mark">ACR DAILY</span><div class="t"><b>${esc(name)}</b><span>${esc(sub)}</span></div></header>
<ol>${rows}</ol>
<nav><button id="back" type="button">BACK</button><button id="jump" type="button">JUMP</button><button id="next" class="next" type="button">NEXT</button></nav>
<script>${SCRIPT}</script></body></html>`;
}

/** The friendly page for a token that is unknown or past its time. */
export function notesGonePage() {
  return `${head('Pacenotes')}<body><div class="gone"><b>ACR DAILY</b><p>These pacenotes are no longer available. Ask the driver for a new lobby link.</p></div></body></html>`;
}
