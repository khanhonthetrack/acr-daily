// Trackmania-style formatting for team tags and names: $RGB a colour (3 hex digits, e.g. $f00 red), $o bold, $i italic,
// $w wide, $n narrow, $t capitals, $s a shadow, $g back to the normal colour, $z everything back to normal, $$ a dollar
// sign. Links ($l[...], $h[...]) and any other code are dropped. A colour too dark for the dark pages is lightened.
// The pages run the same parser (TM_JS: tmSpans' own source) and the app has its twin (client/acr_daily/tmtext.py).

/** The styled pieces of a formatted text: [{t, c, b, i, w, n, u, s}] (t: the text; c: '#RRGGBB' or null; b bold, i
 *  italic, w wide, n narrow, u capitals, s shadow: 0 / 1). */
export function tmSpans(raw) {
  function lift(h) {
    var v = [0, 1, 2].map(function (i) { return parseInt(h[i], 16) * 17; });
    var L = (0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]) / 255;
    if (L < 0.3) { var k = (0.3 - L) / (1 - L); v = v.map(function (c) { return Math.round(c + (255 - c) * k); }); }
    return '#' + v.map(function (c) { return ('0' + c.toString(16)).slice(-2); }).join('').toUpperCase();
  }
  var out = [], buf = '', s = String(raw == null ? '' : raw);
  var st = { c: null, b: 0, i: 0, w: 0, n: 0, u: 0, s: 0 };
  function push() {
    if (buf) out.push({ t: buf, c: st.c, b: st.b, i: st.i, w: st.w, n: st.n, u: st.u, s: st.s });
    buf = '';
  }
  for (var k = 0; k < s.length; k++) {
    var ch = s[k];
    if (ch !== '$') { buf += ch; continue; }
    var x = s[k + 1];
    if (x === undefined) break;
    if (x === '$') { buf += '$'; k++; continue; }
    var hex = s.slice(k + 1, k + 4);
    push();
    if (/^[0-9a-fA-F]{3}$/.test(hex)) { st.c = lift(hex); k += 3; continue; }
    k++;
    var c = x.toLowerCase();
    if (c === 'o') st.b = 1;
    else if (c === 'i') st.i = 1;
    else if (c === 'w') { st.w = 1; st.n = 0; } else if (c === 'n') { st.n = 1; st.w = 0; } else if (c === 't') st.u = 1;
    else if (c === 's') st.s = 1;
    else if (c === 'g') st.c = null;
    else if (c === 'z') st = { c: null, b: 0, i: 0, w: 0, n: 0, u: 0, s: 0 };
    else if ((c === 'l' || c === 'h') && s[k + 1] === '[') { var e = s.indexOf(']', k + 1); k = e < 0 ? s.length : e; }
  }
  push();
  return out;
}

/** The text a formatted one reads as (capitals applied): what is checked, compared and shown where styles can't be. */
export const tmPlain = (raw) => tmSpans(raw).map((x) => (x.u ? x.t.toUpperCase() : x.t)).join('');

/** Does it have any formatting at all? */
export const tmStyled = (raw) => /\$(?!\$)./.test(String(raw || '').replace(/\$\$/g, ''));

/** For a page's script: tmSpans, and tmInto(parent, raw, plain, colour, cls) putting a formatted text in as spans (with
 *  textContent, never as HTML; the colour: the text's own where it sets none). (wrangler's bundle keeps function names
 *  with __name(fn, 'name') calls inside tmSpans' source: the page gets a stand-in.) */
export const TM_JS = `var __name=function(f){return f};
${tmSpans.toString()}
function tmInto(p,raw,plain,color,cls){var w=document.createElement('span');w.className='tmt'+(cls?' '+cls:'');if(color)w.style.color=color;
  (raw?tmSpans(raw):[{t:plain||''}]).forEach(function(x){var e=document.createElement('span');e.textContent=x.u?x.t.toUpperCase():x.t;
    if(x.c)e.style.color=x.c;if(x.b)e.style.fontWeight='800';if(x.i)e.style.fontStyle='italic';
    if(x.w)e.style.letterSpacing='.2em';if(x.n){e.style.letterSpacing='-.03em';e.style.fontStretch='condensed'}
    if(x.s)e.style.textShadow='1px 1px 0 rgba(0,0,0,.9)';w.appendChild(e)});p.appendChild(w);return w}
`;
