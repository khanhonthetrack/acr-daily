// /credits: a driver's credits (a prototype, src/credits.js): balance, streak, the daily bonus, today's wager daily and
// the history. In the leagues' look (src/leaguepages.js shell), signed in with the website's Steam sign-in.

import { CREDITS, WAGER } from './credits.js';
import { shell } from './leaguepages.js';

export function creditsPage(env) {
  const on = !!env.CREDITS_FROM;
  return shell('Credits · ACR Daily', `
  <div class="top"><div class="kick">ACR Daily · prototype</div><h1>Credits</h1>
  <p class="note">Points you earn by driving and coming back, and stake on the wager daily and on league events with an
  entry fee. They are only ever earned: they can't be bought, cashed out or given to another driver.</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <div class="grid" style="margin-top:26px">
    <div class="card"><h3>Earn</h3><ol class="steps">
      <li><b>${CREDITS.welcome}</b> to start with, once you have finished a run (either daily; a practice run counts).</li>
      <li><b>${CREDITS.daily}</b> a day for coming back (the app claims it when it starts), <b>+${CREDITS.streakStep}</b> for each day in a row, up to <b>${CREDITS.daily + CREDITS.streakMax}</b>.</li>
      <li><b>${CREDITS.finish}</b> for finishing the free daily (SS${3 - WAGER.slot}), once the day is over.</li></ol></div>
    <div class="card"><h3>Stake</h3><ol class="steps">
      <li><b>The wager daily (SS${WAGER.slot})</b>: stake ${WAGER.stake} before your first run on it. Finish in the top half of everyone who staked and you get ${2 * WAGER.stake} back; otherwise the stake is gone. Anything left over goes to the fastest; fewer than two in, or nobody finishing: stakes back, and so is a stake you never drive. Your run counts on the board as always. A run under review holds the day's payout until it is decided (at most 3 days).</li>
      <li><b>League events with an entry fee</b>: paid when you DRIVE. The fees make a pot: 50 / 30 / 20 % to the top three (all to the winner when fewer finish), paid a day after the event closes, once the stewards are done. Leave the league or get removed before you start it, and your fee comes back.</li></ol></div>
  </div>
  <h2>Today's wager daily</h2><div id="wager"></div>
  <h2>History</h2><div class="tablewrap"><table id="hist"></table></div>`, `
  var ON=${JSON.stringify(on)};
  function fact(k,v){var d=el('div');add(d,el('span','k',k),el('b',null,v));$('facts').appendChild(d)}
  function load(){return api('/api/credits').then(render,function(e){msg('m',e.message)})}
  function render(c){$('facts').innerHTML='';$('acts').innerHTML='';
    if(!ON||!c.enabled){msg('m','Credits are not on yet on this server.');return}
    var w=$('wager');w.innerHTML='';var wg=c.wager;
    if(wg)add(w,el('p','note',wg.entrants+(wg.entrants===1?' driver has':' drivers have')+' staked '+wg.stake+' each: the pot is '+wg.pot+' credits.'+(c.signedIn&&wg.entered?' You are in.':'')));
    if(!c.signedIn){$('acts').appendChild(steamBtn('Sign in with Steam to see your credits'));return}
    fact('Balance',c.balance+' credits');fact('Streak',c.streak+(c.streak===1?' day':' days'));
    if(!c.earning)add($('acts'),el('span','muted','Finish a run on either daily in the app (a practice run counts) and your credits start: '+c.nextBonus+' to begin with.'));
    else if(c.claimable){var cb=el('button','btn','Claim today\\'s '+c.nextBonus);cb.onclick=function(){cb.disabled=true;
      api('/api/credits/claim',{}).then(function(r){msg('m','+'+r.amount+' credits',true);load()},function(e){cb.disabled=false;msg('m',e.message)})};$('acts').appendChild(cb)}
    else add($('acts'),el('span','muted','Today\\'s bonus is in: come back tomorrow for the next one.'));
    if(wg&&!wg.entered){var sb=el('button','btn ghost','Stake '+wg.stake+' on SS'+wg.slot);sb.title='Before your first run on it';sb.onclick=function(){
        if(!confirm('Stake '+wg.stake+' credits on today\\'s SS'+wg.slot+'? Top half of the drivers who staked: '+2*wg.stake+' back; otherwise it is gone.'))return;sb.disabled=true;
        api('/api/credits/wager',{slot:wg.slot}).then(function(){msg('m','You are in the wager: drive SS'+wg.slot+' in the app.',true);load()},function(e){sb.disabled=false;msg('m',e.message)})};w.appendChild(sb)}
    var t=$('hist');t.innerHTML='';var h=el('tr');add(h,el('th',null,'When'),el('th',null,'What'),el('th',null,''),el('th','r','Credits'));t.appendChild(h);
    if(!c.ledger.length){var tr=el('tr'),td=el('td','empty','Nothing yet.');td.colSpan=4;tr.appendChild(td);t.appendChild(tr)}
    c.ledger.forEach(function(x){var tr=el('tr');add(tr,el('td','muted',when(x.created)),el('td',null,x.label),el('td','muted',[x.ref,x.note].filter(Boolean).join(' · ')),
      el('td','r tot',(x.delta>0?'+':'')+x.delta));t.appendChild(tr)})}
  account().then(load);
  `, env);
}
