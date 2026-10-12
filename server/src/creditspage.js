// /credits: a driver's credits (src/credits.js): balance, the daily bonus, the shop (src/shoppage.js), the history and
// how credits work. In the leagues' look (src/leaguepages.js shell, its cr() puts the coin by an amount), signed
// in with the website's Steam sign-in.

import { coinSvg } from './logo.js';
import { CREDITS, WAGER } from './credits.js';
import { shell } from './leaguepages.js';
import { SHOP_CSS, SHOP_HTML, SHOP_JS } from './shoppage.js';

const coin = (n) => `<span class="cr">${n}${coinSvg()}</span>`;

export function creditsPage(env) {
  const on = !!env.CREDITS_FROM;
  const free = 3 - WAGER.slot;
  return shell('Credits · ACR Daily', `${SHOP_CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>Credits</h1>
  <p class="note">Earned by driving. Spend them on the SS2 stake, 1V1s, cups and the shop. You can't buy them.</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  ${SHOP_HTML}
  <h2>History</h2><div class="tablewrap"><table id="hist"></table></div>
  <h2>How it works</h2>
  <div class="grid">
    <div class="card"><h3>Earn</h3><ol class="steps">
      <li><b>${coin(CREDITS.welcome)}</b> on your first day.</li>
      <li><b>${coin(CREDITS.daily)}</b> a day for coming back (the app claims it when it starts).</li>
      <li><b>${coin(CREDITS.finish)}</b> for finishing the free daily (SS${free}): your first run of it, as soon as its time is in.</li></ol></div>
    <div class="card"><h3>Spend</h3><ol class="steps">
      <li><b>The wager daily (SS${WAGER.slot})</b> is driven with a stake of ${coin(WAGER.stake)}: no stake, no run on it. Stake
      before your first run (DRIVE in the app asks); your first run after it is your result. The house stakes too, so you
      can win on your own: the top half of the drivers (rounded up) get ${coin(2 * WAGER.stake)} back, the rest lose their
      stake, and anything left over goes to the fastest. Nobody finishing: stakes back, and so is a stake you never drive.
      A run under review holds the day's payout until it is decided (at most 3 days).</li>
      <li><b>The shop</b> (above): looks for your name on the timing sheets and the live map, or a daily of your own.</li></ol></div>
  </div>`, `
  ${SHOP_JS}
  var ON=${JSON.stringify(on)};
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/credits').then(render,function(e){msg('m',e.message)})}
  function render(c){$('facts').innerHTML='';$('acts').innerHTML='';
    if(!ON||!c.enabled){msg('m','Credits are not on yet on this server.');return}
    if(!c.signedIn){$('acts').appendChild(steamBtn('Sign in with Steam to see your credits'));return}
    fact('Balance',cr(c.balance));fact('Days in a row',String(c.streak));
    if(!c.earning)add($('acts'),add(el('span','muted'),'Finish a run in the app to start earning: ',cr(c.nextBonus),' to begin with.'));
    else if(c.claimable){var cb=add(el('button','btn'),'Claim today\\'s ',cr(c.nextBonus));cb.onclick=function(){cb.disabled=true;
      api('/api/credits/claim',{}).then(function(r){msg('m','+'+r.amount+' credits',true);load()},function(e){cb.disabled=false;msg('m',e.message)})};$('acts').appendChild(cb)}
    else add($('acts'),el('span','muted','Today\\'s bonus is in: come back tomorrow for the next one.'));
    var t=$('hist');t.innerHTML='';var h=el('tr');add(h,el('th',null,'When'),el('th',null,'What'),el('th',null,''),el('th','r','Credits'));t.appendChild(h);
    if(!c.ledger.length){var tr=el('tr'),td=el('td','empty','Nothing yet.');td.colSpan=4;tr.appendChild(td);t.appendChild(tr)}
    // a 1V1's or a cup's entry: its label goes to its page (their ids mean nothing to anyone); a day's: the date
    c.ledger.forEach(function(x){var tr=el('tr'),m=/^(h2h|cup):(.+)$/.exec(x.ref||''),what=el('td');
      if(m){var a=el('a',null,x.label);a.href=m[1]==='h2h'?'/1v1':'/cup/'+encodeURIComponent(m[2]);what.appendChild(a)}else what.textContent=x.label;
      add(tr,el('td','muted',when(x.created)),what,el('td','muted',[m?null:x.ref,x.note].filter(Boolean).join(' · ')),
      add(el('td','r tot'),cr((x.delta>0?'+':'')+x.delta)));t.appendChild(tr)})}
  SHOP.onChange=load;                  // (a buy: the balance and the history here)
  account().then(function(){load();SHOP.load()});
  `, env);
}
