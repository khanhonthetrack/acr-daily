// The credits in the website's header, and the daily bonus: the first page a signed-in driver opens that day claims it
// (POST /api/credits/claim, once a day) and says so in a popup; the welcome bonus comes with the first. Used by the home
// page (src/site.js) and every page in the leagues' shell (src/leaguepages.js). Both define COIN (the coin's SVG).

export const BONUS_CSS = `
.crchip{display:inline-flex;align-items:center;gap:1px;font:600 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.02em;color:#FFD60A;text-decoration:none;white-space:nowrap}
.crchip:hover{color:#FFE45C}
.crchip .coin{width:15px;height:15px;margin-left:3px;vertical-align:0}
.bonustoast{position:fixed;top:18px;right:18px;z-index:60;max-width:calc(100vw - 36px);display:flex;flex-direction:column;gap:5px;padding:14px 18px;
  background:#141417;border:1px solid #FFD60A;color:#F4F4F5;font:15px/1.3 Barlow,sans-serif;box-shadow:0 10px 32px rgba(0,0,0,.55);cursor:pointer;transition:opacity .5s,transform .5s}
.bonustoast b{font:700 26px/1 'Barlow Condensed',sans-serif;color:#FFD60A}
.bonustoast .coin{width:.85em;height:.85em;margin-left:.15em;vertical-align:-.08em}
.bonustoast small{color:#A1A1AA;font-size:13px}
.bonustoast.out{opacity:0;transform:translateY(-8px)}
`;

// creditsChip(host, credits): the balance (with the coin) in host, linking /credits; claimBonus(host, credits): today's
// bonus if it is still to claim, then the popup and the new balance
export const BONUS_JS = `
function creditsChip(host,c){if(!host||!c)return;var a=document.getElementById('crchip');
  if(!a){a=document.createElement('a');a.id='crchip';a.className='crchip';a.href='/credits';a.title='Your credits';host.insertBefore(a,host.firstChild)}
  a.textContent=String(c.balance);a.insertAdjacentHTML('beforeend',COIN)}
function claimBonus(host,c){if(!c||!c.claimable)return;c.claimable=false;
  fetch('/api/credits/claim',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'})
  .then(function(r){return r.ok?r.json():null}).then(function(r){if(!r||!r.claimed)return;c.balance=r.balance;creditsChip(host,c);
    var t=document.createElement('div');t.className='bonustoast';t.setAttribute('role','status');t.title='Close';
    var b=document.createElement('b');b.textContent='+'+r.amount;b.insertAdjacentHTML('beforeend',COIN);
    var w=document.createElement('span');w.textContent=r.welcome?'Welcome bonus and daily bonus':'Daily bonus';
    var s=document.createElement('small');s.textContent='You have '+r.balance+' credits.';
    t.appendChild(b);t.appendChild(w);t.appendChild(s);document.body.appendChild(t);
    function go(){t.classList.add('out');setTimeout(function(){t.remove()},500)}t.onclick=go;setTimeout(go,7000)}).catch(function(){})}
`;
