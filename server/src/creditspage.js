// /credits: a driver's credits (src/credits.js): balance, the daily bonus, the shop (src/shoppage.js), the history and
// how credits work. In the leagues' look (src/leaguepages.js shell, its cr() puts the coin by an amount), signed
// in with the website's Steam sign-in.

import { coinSvg } from './logo.js';
import { CREDITS, LABELS, WAGER } from './credits.js';
import { shell } from './leaguepages.js';
import { SHOP_CSS, SHOP_HTML, SHOP_JS } from './shoppage.js';
import { ITEMS } from './shop.js';
import { TT } from './timetrial.js';
import { t, tq, wordsJs } from './i18n.js';

const coin = (n) => `<span class="cr">${n}${coinSvg()}</span>`;

export function creditsPage(env) {
  const on = !!env.CREDITS_FROM;
  const free = 3 - WAGER.slot;
  return shell(t('Credits') + ' · ACR Daily', `${SHOP_CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>${t('Credits')}</h1>
  <p class="note">${t("Earned by driving. Spend them on the SS2 stake, 1V1s, cups and the shop. You can't buy them.")}</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  ${SHOP_HTML()}
  <h2>${t('History')}</h2><div class="tablewrap"><table id="hist"></table></div>
  <h2>${t('How it works')}</h2>
  <div class="grid">
    <div class="card"><h3>${t('Earn')}</h3><ol class="steps">
      <li>${t('{0} on your first day.', `<b>${coin(CREDITS.welcome)}</b>`)}</li>
      <li>${t('{0} a day for coming back (the app claims it when it starts).', `<b>${coin(CREDITS.daily)}</b>`)}</li>
      <li>${t('{0} for finishing the free daily (SS{1}): your first run of it, as soon as its time is in.', `<b>${coin(CREDITS.finish)}</b>`, free)}</li></ol></div>
    <div class="card"><h3>${t('Spend')}</h3><ol class="steps">
      <li>${t('<b>The wager daily (SS{0})</b> is driven with a stake of {1}: no stake, no run on it. Stake before your first run (DRIVE in the app asks); your first run after it is your result. The house stakes too, so you can win on your own: the top half of the drivers (rounded up) get {2} back, the rest lose their stake, and anything left over goes to the fastest. Nobody finishing: stakes back, and so is a stake you never drive.', WAGER.slot, coin(WAGER.stake), coin(2 * WAGER.stake))}</li>
      <li>${t("<b>{0}</b>: TT{1} is free. The other stage is {2} to enter for the week: the top half of its drivers with a time get their fee back plus a share of the others' fees, more the higher they place; no time set: the fee back.", `<a href="/tt">${t('The time trial')}</a>`, TT.freeSlot, coin(TT.fee))}</li>
      <li>${t('<b>The shop</b> (above): looks for your name on the timing sheets and the live map, or a daily of your own.')}</li></ol></div>
  </div>`, `
  ${wordsJs([...Object.values(LABELS), ...ITEMS.map((i) => i.name)])}
  ${SHOP_JS()}
  var ON=${JSON.stringify(on)};
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/credits').then(render,function(e){msg('m',e.message)})}
  function render(c){$('facts').innerHTML='';$('acts').innerHTML='';
    if(!ON||!c.enabled){msg('m',${tq('Credits are not on yet on this server.')});return}
    if(!c.signedIn){$('acts').appendChild(steamBtn(${tq('Sign in with Steam to see your credits')}));return}
    fact(${tq('Balance')},cr(c.balance));fact(${tq('Days in a row')},String(c.streak));
    if(!c.earning)add($('acts'),add(el('span','muted'),FN(${tq('Finish a run in the app to start earning: {0} to begin with.')},cr(c.nextBonus))));
    else if(c.claimable){var cb=add(el('button','btn'),FN(${tq("Claim today's {0}")},cr(c.nextBonus)));cb.onclick=function(){cb.disabled=true;
      api('/api/credits/claim',{}).then(function(r){msg('m',F(${tq('+{0} credits')},r.amount),true);load()},function(e){cb.disabled=false;msg('m',e.message)})};$('acts').appendChild(cb)}
    else add($('acts'),el('span','muted',${tq("Today's bonus is in: come back tomorrow for the next one.")}));
    var t=$('hist');t.innerHTML='';var h=el('tr');add(h,el('th',null,${tq('When')}),el('th',null,${tq('What')}),el('th',null,''),el('th','r',${tq('Credits')}));t.appendChild(h);
    if(!c.ledger.length){var tr=el('tr'),td=el('td','empty',${tq('Nothing yet.')});td.colSpan=4;tr.appendChild(td);t.appendChild(tr)}
    // a 1V1's or a cup's entry: its label goes to its page (their ids mean nothing to anyone); a day's: the date
    c.ledger.forEach(function(x){var tr=el('tr'),m=/^(h2h|cup):(.+)$/.exec(x.ref||''),what=el('td');
      if(m){var a=el('a',null,TD(x.label));a.href=m[1]==='h2h'?'/1v1':'/cup/'+encodeURIComponent(m[2]);what.appendChild(a)}else what.textContent=TD(x.label);
      add(tr,el('td','muted',when(x.created)),what,el('td','muted',[m?null:x.ref,x.note].filter(Boolean).join(' · ')),
      add(el('td','r tot'),cr((x.delta>0?'+':'')+x.delta)));t.appendChild(tr)})}
  SHOP.onChange=load;                  // (a buy: the balance and the history here)
  account().then(function(){load();SHOP.load()});
  `, env);
}
