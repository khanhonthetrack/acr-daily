// /credits: a driver's credits (a prototype, src/credits.js): balance, the daily bonus, today's wager daily and the
// history. In the leagues' look (src/leaguepages.js shell, its cr() puts the coin by an amount), signed in with the
// website's Steam sign-in.

import { coinSvg } from './logo.js';
import { CREDITS, WAGER } from './credits.js';
import { shell } from './leaguepages.js';

const coin = (n) => `<span class="cr">${n}${coinSvg()}</span>`;

export function creditsPage(env) {
  const on = !!env.CREDITS_FROM;
  const free = 3 - WAGER.slot;
  return shell('Credits · ACR Daily', `
  <div class="top"><div class="kick">ACR Daily · prototype</div><h1>Credits</h1>
  <p class="note">Earned by driving. Spend them on the SS2 stake, 1V1s, cups and the shop. You can't buy them.</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <div class="grid" style="margin-top:26px">
    <div class="card"><h3>Earn</h3><ol class="steps">
      <li><b>${coin(CREDITS.welcome)}</b> after your first finished run.</li>
      <li><b>${coin(CREDITS.daily)}</b> a day for coming back (the app claims it when it starts).</li>
      <li><b>${coin(CREDITS.finish)}</b> for finishing the free daily (SS${free}): your first run of it, as soon as its time is in.</li></ol></div>
    <div class="card"><h3>Spend</h3><ol class="steps">
      <li><b>The wager daily (SS${WAGER.slot})</b> is driven with a stake of ${coin(WAGER.stake)}: no stake, no run on it. Stake
      before your first run (DRIVE in the app asks); your first run after it is your result. The house stakes too, so you
      can win on your own: the top half of the drivers (rounded up) get ${coin(2 * WAGER.stake)} back, the rest lose their
      stake, and anything left over goes to the fastest. Nobody finishing: stakes back, and so is a stake you never drive.
      A run under review holds the day's payout until it is decided (at most 3 days).</li>
      <li><b>The shop</b>: looks for your name on the timing sheets and the live map. <a href="/shop">Have a look ›</a></li></ol></div>
  </div>
  <h2>Today's wager daily</h2><div id="wager"></div>
  <h2>History</h2><div class="tablewrap"><table id="hist"></table></div>`, `
  var ON=${JSON.stringify(on)};
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/credits').then(render,function(e){msg('m',e.message)})}
  function render(c){$('facts').innerHTML='';$('acts').innerHTML='';
    if(!ON||!c.enabled){msg('m','Credits are not on yet on this server.');return}
    var w=$('wager');w.innerHTML='';var wg=c.wager;
    if(wg)add(w,add(el('p','note'),wg.entrants+(wg.entrants===1?' driver has':' drivers have')+' staked ',cr(wg.stake),' each, plus the house\\'s ',cr(wg.stake),
      ': the pot is ',cr(wg.pot+wg.stake),'.'+(c.signedIn&&wg.entered?' You are in.':'')));
    if(!c.signedIn){$('acts').appendChild(steamBtn('Sign in with Steam to see your credits'));return}
    fact('Balance',cr(c.balance));fact('Days in a row',String(c.streak));
    var sh=el('a','btn ghost','Shop: looks for your name ›');sh.href='/shop';
    if(!c.earning)add($('acts'),add(el('span','muted'),'Finish a run in the app to start earning: ',cr(c.nextBonus),' to begin with.'));
    else if(c.claimable){var cb=add(el('button','btn'),'Claim today\\'s ',cr(c.nextBonus));cb.onclick=function(){cb.disabled=true;
      api('/api/credits/claim',{}).then(function(r){msg('m','+'+r.amount+' credits',true);load()},function(e){cb.disabled=false;msg('m',e.message)})};$('acts').appendChild(cb)}
    else add($('acts'),el('span','muted','Today\\'s bonus is in: come back tomorrow for the next one.'));
    $('acts').appendChild(sh);
    if(wg&&!wg.entered){var sb=add(el('button','btn ghost'),'Stake ',cr(wg.stake),' on SS'+wg.slot);sb.title='Before your first run on it';sb.onclick=function(){
        if(!confirm('Stake '+wg.stake+' credits on today\\'s SS'+wg.slot+'? You can drive it once the stake is in. Top half of the drivers: '+2*wg.stake+' back; otherwise it is gone.'))return;sb.disabled=true;
        api('/api/credits/wager',{slot:wg.slot}).then(function(){msg('m','You are in the wager: drive SS'+wg.slot+' in the app.',true);load()},function(e){sb.disabled=false;msg('m',e.message)})};w.appendChild(sb)}
    var t=$('hist');t.innerHTML='';var h=el('tr');add(h,el('th',null,'When'),el('th',null,'What'),el('th',null,''),el('th','r','Credits'));t.appendChild(h);
    if(!c.ledger.length){var tr=el('tr'),td=el('td','empty','Nothing yet.');td.colSpan=4;tr.appendChild(td);t.appendChild(tr)}
    c.ledger.forEach(function(x){var tr=el('tr');add(tr,el('td','muted',when(x.created)),el('td',null,x.label),el('td','muted',[x.ref,x.note].filter(Boolean).join(' · ')),
      add(el('td','r tot'),cr((x.delta>0?'+':'')+x.delta)));t.appendChild(tr)})}
  account().then(load);
  `, env);
}
