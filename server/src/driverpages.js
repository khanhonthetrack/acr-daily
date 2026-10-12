// The drivers' pages: /d/<steamId> (a driver: rating, results, career, leagues, cups; their own name, picture and team
// when it is theirs), /ranking (the world ranking), /teams (every team, a new one, joining one) and /t/<id> (a team).
// In the leagues' look (src/leaguepages.js shell); the data from src/drivers.js and rating.js. Every name a driver
// wrote is put in with textContent (el, add), never as HTML.

import { AVATAR, NAME, TEAM } from './drivers.js';
import { shell } from './leaguepages.js';
import { RATING } from './rating.js';
import { ACH_PAGE_JS } from './achievements.js';

const CSS = `<style>
.dhead{display:flex;align-items:center;gap:22px;margin-top:14px}
.dhead h1{margin-top:0}
.bigav{width:96px;height:96px;border-radius:50%;object-fit:cover;flex:none;background:var(--panel);border:2px solid var(--line2)}
.bigav[hidden]{display:none}
.sub{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin-top:10px;color:var(--fg2);font-size:14px}
.sub a{text-decoration:none}.sub a:hover{text-decoration:underline}
.tagl{font:700 18px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:8px}
.tagb{font:700 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:6px}
.statgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));border-top:1px solid var(--line);border-left:1px solid var(--line)}
.statgrid div{padding:14px 16px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}
.statgrid b{display:block;font:700 26px/1.1 'Barlow Condensed',sans-serif;margin-top:6px;overflow-wrap:anywhere}
.statgrid small{display:block;color:var(--fg3);font-size:12px;margin-top:2px}
.chart{width:100%;height:auto;aspect-ratio:9/2;min-height:150px;display:block;border:1px solid var(--line);background:var(--panel)}
.chart .ln{fill:none;stroke:var(--acc);stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round}
.chart .ar{fill:rgba(227,6,19,.10)}
.chart .gd{stroke:var(--line);stroke-width:1}
.chart .st{stroke:var(--fg3);stroke-width:1;stroke-dasharray:4 4}
.chart .pt{fill:var(--panel);stroke:var(--fg2);stroke-width:2;cursor:default}
.chart .pt.up{stroke:var(--good)}.chart .pt.down{stroke:var(--bad)}
.chart .pt:hover{fill:var(--fg)}
.chart .pk{fill:none;stroke:#FFD60A;stroke-width:1.5}
.chart .pkt{fill:#FFD60A}
.chart text{fill:var(--fg3);font:600 12px Barlow,sans-serif}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;margin-top:8px;color:var(--fg3);font-size:12px}
.legend .sw{display:inline-block;width:14px;height:0;margin-right:5px;vertical-align:3px;border-top:2px solid var(--acc)}
.legend .sw.st{border-top:1px dashed var(--fg3)}
.legend .sw.up,.legend .sw.down{width:9px;height:9px;border:2px solid var(--good);border-radius:50%;vertical-align:-1px}
.legend .sw.down{border-color:var(--bad)}
.achn{font:600 15px/1 Barlow,sans-serif;color:var(--fg3);letter-spacing:0;text-transform:none;margin-left:8px}
.achgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:8px}
.ach{display:flex;gap:12px;align-items:center;padding:10px 12px;border:1px solid var(--line);background:var(--panel)}
.ach .ic{flex:none;width:56px;height:56px}.ach .ic svg{display:block}
.ach .tx{min-width:0;display:flex;flex-direction:column;gap:2px}
.ach b{font:700 17px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.02em}
.ach .d{font-size:12.5px;color:var(--fg2);line-height:1.3}
.ach .w{font-size:11.5px;color:var(--fg3)}
.ach:not(.on){opacity:.75}.ach:not(.on) b{color:var(--fg2)}
td.up{color:var(--good)}td.down{color:var(--bad)}
.editcard{margin-top:28px}
.editcard .twocol{align-items:start}
.avset{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:6px}
.avset img{width:72px;height:72px;border-radius:50%;object-fit:cover;border:1px solid var(--line2);background:#0E0E10}
.colors{display:flex;gap:6px;flex-wrap:wrap}
.colors label{margin:0}
.colors input{position:absolute;opacity:0}
.colors span{display:block;width:30px;height:30px;border:2px solid var(--line2);cursor:pointer}
.colors input:checked+span{border-color:var(--fg)}
.pager{display:flex;gap:10px;align-items:center;margin-top:14px;color:var(--fg2);font-size:14px}
tr.me td{background:#1A0B0C}
td.drv a{text-decoration:none}td.drv a:hover{text-decoration:underline}
.av{width:22px;height:22px;border-radius:50%;object-fit:cover;vertical-align:-6px;margin-right:8px}
@media (max-width:760px){.dhead{gap:14px}.bigav{width:64px;height:64px}}
</style>`;

// helpers of these pages: a driver's name with their flag and team tag, linking their page; a place; a rating change
const DRV_JS = `
function tag(p,t,cls){if(!t)return p;var s=el('span',cls||'tagb',t.tag||t.text);s.style.color=t.color;p.appendChild(s);return p}
function drv(p,x){flag(p,x.country);tag(p,x.team);var a=el('a',null,x.name||'a driver');a.href='/d/'+x.steamId;p.appendChild(a);return p}
function nth(n){var s=['th','st','nd','rd'],v=n%100;return n+(s[(v-20)%10]||s[v]||s[0])}
function day(d){return new Date(d+'T00:00:00Z').toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})}
function delta(v){return v==null?'':(v>0?'+':v<0?'−':'±')+Math.abs(v).toFixed(1)}
var START=${RATING.start};
`;

// ------------------------------------------------------------------ /d/<steamId>
export function driverPage(sid, env) {
  return shell('Driver · ACR Daily', `${CSS}
  <div class="top"><div class="kick"><a href="/ranking">Drivers</a></div>
    <div class="dhead"><img class="bigav" id="av" alt="" hidden><div style="min-width:0"><h1 id="name">…</h1><div class="sub" id="sub"></div></div></div>
    <div class="facts" id="facts"></div>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <div id="edit"></div>
  <h2>Rating</h2><div id="rating"></div>
  <h2 id="achievements">Achievements <span class="achn" id="achn"></span></h2><div class="achgrid" id="ach"></div>
  <h2>Career</h2><div class="statgrid" id="stats"></div>
  <h2>Recent dailies</h2><div class="tablewrap"><table id="recent"></table></div>
  <h2>Leagues</h2><div id="leagues"></div>
  <h2>Cups</h2><div id="cups"></div>`, `${DRV_JS}
  var SID=${JSON.stringify(sid)},D=null;
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  ${ACH_PAGE_JS}
  function load(){return api('/api/drivers/'+SID).then(render,function(e){$('name').textContent=e.status===404?'No such driver':'Driver';msg('m',e.message)})}
  function render(d){D=d;document.title=d.name+' · ACR Daily';var n=$('name');n.textContent=d.name;
    if(d.look&&d.look.color&&!d.look.grad)n.style.color=d.look.color;
    if(d.avatar){$('av').src=d.avatar;$('av').hidden=false}else $('av').hidden=true;
    var s=$('sub');s.innerHTML='';
    if(d.team){var ta=el('a');ta.href='/t/'+d.team.id;tag(ta,d.team,'tagl');add(ta,d.team.name);s.appendChild(ta)}
    if(d.country){var c=el('span');flag(c,d.country);add(c,d.country.toUpperCase());s.appendChild(c)}
    if(d.look&&d.look.badge)s.appendChild(el('span',null,d.look.badge));
    if(d.steamName)s.appendChild(el('span',null,'Steam: '+d.steamName));
    s.appendChild(el('span',null,'Driving since '+new Date(d.since).toLocaleDateString(undefined,{month:'long',year:'numeric'})));
    $('facts').innerHTML='';var r=d.rating,st=d.stats;
    if(r){fact('Rating',String(r.rating));fact('World rank','#'+r.rank+' of '+r.of);fact('Peak',String(r.peak))}
    fact('Dailies',String(st.dailies));fact('Wins',String(st.wins));fact('Podiums',String(st.podiums));
    fact('1V1s',st.oneVone.won+' – '+st.oneVone.lost+(st.oneVone.drawn?' – '+st.oneVone.drawn:''));
    var a=$('acts');a.innerHTML='';
    if(!d.me&&d.signedIn){var mg=el('a','btn ghost','Message');mg.href='/inbox?with='+d.steamId;
      var ch=el('a','btn','Challenge to a 1V1');ch.href='/1v1?to='+d.steamId+'&name='+encodeURIComponent(d.name);add(a,mg,ch)}
    var sp=el('a','btn ghost small','Steam profile');sp.href='https://steamcommunity.com/profiles/'+d.steamId;sp.target='_blank';sp.rel='noopener';a.appendChild(sp);
    if(d.me)edit(d);rating(d);achievements(d);stats(d);recent(d);leagues(d);cups(d);if(location.hash==='#achievements'&&!SCROLLED){SCROLLED=true;$('achievements').scrollIntoView()}}

  // ---- achievements, as Steam shows them: the unlocked ones first (newest first), each its tile, name, what it takes,
  // when, and how many drivers have it; the rest greyed with a lock
  var SCROLLED=false;
  function achievements(d){var box=$('ach');box.innerHTML='';var got={},n=0;(d.achievements||[]).forEach(function(a){got[a.id]=a;if(a.at)n++});
    $('achn').textContent=n+' of '+ACH.length;
    var list=ACH.slice().sort(function(x,y){var a=got[x.id]||{},b=got[y.id]||{};return (b.at||0)-(a.at||0)});
    list.forEach(function(a){var g=got[a.id]||{},on=!!g.at,c=el('div','ach'+(on?' on':''));c.title=a.name+': '+a.desc;
      var ic=el('div','ic');ic.innerHTML=achievementIcon(a,on,56);c.appendChild(ic);
      var t=el('div','tx');add(t,el('b',null,a.name),el('span','d',a.desc));
      add(t,el('span','w',(on?'Unlocked '+day(new Date(g.at).toISOString().slice(0,10))+' · ':'')+(g.rarity||0)+'% of drivers'));c.appendChild(t);box.appendChild(c)})}

  // ---- the rating over time (the last 60 changes): a line with a dot a race (pointed at or tapped: what, when, the
  // change), the start value and the peak marked, the first and last dates under it
  function race(h){var m=/^daily:(\\d{4}-\\d{2}-\\d{2})\\/(\\d)$/.exec(h.ref||'');return m?'Daily SS'+m[2]+' · '+day(m[1]):/^cup:/.test(h.ref||'')?'Cup match · '+day(new Date(h.at).toISOString().slice(0,10)):'Race'}
  function rating(d){var box=$('rating');box.innerHTML='';
    if(!d.ratingOn){box.appendChild(el('p','note','The driver rating starts soon: from then on both dailies and cup matches count, every driver from '+START+'.'));return}
    if(!d.rating){box.appendChild(el('p','note','Not rated yet: drive a daily (or a cup match) to get a rating. Everyone starts at '+START+'.'));return}
    var hs=d.history,first=hs.length?Math.round(hs[0].rating-hs[0].delta):START;
    var pts=[first].concat(hs.map(function(h){return h.rating}));
    var W=900,H=200,pl=44,pr=14,pt=16,pb=26,lo=Math.min.apply(null,pts.concat([START])),hi=Math.max.apply(null,pts.concat([START]));
    var pad=Math.max(10,(hi-lo)*.12);lo=Math.floor((lo-pad)/10)*10;hi=Math.ceil((hi+pad)/10)*10;
    var NS='http://www.w3.org/2000/svg';function sv(tag,attrs,text){var e=document.createElementNS(NS,tag);for(var k in attrs)e.setAttribute(k,attrs[k]);if(text!=null)e.textContent=text;return e}
    var svg=sv('svg',{viewBox:'0 0 '+W+' '+H,'class':'chart',role:'img','aria-label':'Rating history'});
    function y(v){return pt+(hi-v)/(hi-lo)*(H-pt-pb)}function x(i){return pts.length<2?(pl+W-pr)/2:pl+i*(W-pl-pr)/(pts.length-1)}
    // the scale: four lines, the start value dashed
    for(var k=0;k<=3;k++){var v=Math.round(lo+(hi-lo)*k/3);svg.appendChild(sv('line',{'class':'gd',x1:pl,x2:W-pr,y1:y(v),y2:y(v)}));svg.appendChild(sv('text',{x:pl-6,y:y(v)+4,'text-anchor':'end'},String(v)))}
    svg.appendChild(sv('line',{'class':'st',x1:pl,x2:W-pr,y1:y(START),y2:y(START)}));
    var line=pts.map(function(v,i){return x(i).toFixed(1)+','+y(v).toFixed(1)}).join(' ');
    svg.appendChild(sv('polygon',{'class':'ar',points:x(0).toFixed(1)+','+(H-pb)+' '+line+' '+x(pts.length-1).toFixed(1)+','+(H-pb)}));
    svg.appendChild(sv('polyline',{'class':'ln',points:line}));
    // the peak
    var pk=pts.indexOf(Math.max.apply(null,pts));if(pk>0){svg.appendChild(sv('circle',{'class':'pk',cx:x(pk),cy:y(pts[pk]),r:6}));
      svg.appendChild(sv('text',{'class':'pkt',x:Math.min(Math.max(x(pk),pl+30),W-pr-30),y:y(pts[pk])-11,'text-anchor':'middle'},'Peak '+pts[pk]))}
    // a dot a race, its tooltip: what, when, the change and the rating after it
    hs.forEach(function(h,i){var c=sv('circle',{'class':'pt '+(h.delta>0?'up':h.delta<0?'down':''),cx:x(i+1),cy:y(h.rating),r:hs.length>40?3:4});
      c.appendChild(sv('title',null,race(h)+': '+delta(h.delta)+' → '+h.rating));svg.appendChild(c)});
    // the dates: the first race and the last
    if(hs.length){svg.appendChild(sv('text',{x:x(1),y:H-8,'text-anchor':hs.length>1?'start':'middle'},day(new Date(hs[0].at).toISOString().slice(0,10))));
      if(hs.length>1)svg.appendChild(sv('text',{x:x(pts.length-1),y:H-8,'text-anchor':'end'},day(new Date(hs[hs.length-1].at).toISOString().slice(0,10))))}
    box.appendChild(svg);
    var lg=el('div','legend');add(lg,el('span','sw ln'),'Rating after each race ',el('span','sw st'),'The start ('+START+') ',el('span','sw up'),'Up ',el('span','sw down'),'Down');box.appendChild(lg);
    box.appendChild(el('p','note',d.rating.races+(d.rating.races===1?' rated race':' rated races')+'. Both dailies and cup matches count; a DNF counts as last. See the '));
    var rl=el('a',null,'world ranking');rl.href='/ranking';add(box.lastChild,rl,'.')}

  function stats(d){var st=d.stats,g=$('stats');g.innerHTML='';
    function cell(k,v,small){var c=el('div');add(c,el('span','k',k),el('b',null,v));if(small)c.appendChild(el('small',null,small));g.appendChild(c)}
    cell('Dailies driven',String(st.dailies),st.finishes+' finished');
    cell('Best place',st.best?nth(st.best):'–',st.wins?st.wins+(st.wins===1?' win':' wins'):'');
    cell('Distance',st.km.toLocaleString()+' km','finished runs, practice too');
    cell('Runs',String(st.runs),'every run, practice too');
    cell('Favourite car',st.cars.length?st.cars[0].car:'–',st.cars.length?st.cars[0].runs+' runs':'');
    cell('Favourite rally',st.rally||'–','');
    cell('1V1s',st.oneVone.won+' won',st.oneVone.lost+' lost'+(st.oneVone.drawn?', '+st.oneVone.drawn+' no contest':''))}

  function recent(d){var t=$('recent');t.innerHTML='';var h=el('tr');
    ['Day','','Stage','Car','Place','Time',d.ratingOn?'Rating':''].forEach(function(x,i){h.appendChild(el('th',i>=4?'r':null,x))});t.appendChild(h);
    if(!d.recent.length){var tr=el('tr'),td=el('td','empty','No dailies yet.');td.colSpan=7;tr.appendChild(td);t.appendChild(tr);return}
    d.recent.forEach(function(r){var tr=el('tr',r.place===1?'p1':'');
      var dl=el('a',null,day(r.date));dl.href='/?date='+r.date;add(tr,add(el('td'),dl),el('td','muted','SS'+r.slot),el('td',null,r.stage||''),el('td','muted',r.car||''));
      tr.appendChild(el('td','r'+(r.place===1?' tot':''),r.place?nth(r.place)+' / '+r.field:'DNF'));
      var tt=el('td','r t');if(r.totalMs!=null&&r.runId){var ta=el('a',null,ms(r.totalMs));ta.href='/run/'+r.runId;tt.appendChild(ta)}tr.appendChild(tt);
      tr.appendChild(el('td','r '+(r.delta>0?'up':r.delta<0?'down':'muted'),delta(r.delta)));t.appendChild(tr)})}

  function leagues(d){var b=$('leagues');b.innerHTML='';
    if(!d.leagues.length){b.appendChild(el('div','empty','No leagues'+(d.me?' yet: find one on the ':' to show.')));if(d.me){var l=el('a',null,'leagues page');l.href='/leagues';add(b.lastChild,l,'.')}return}
    d.leagues.forEach(function(l){var a=el('a','item');a.href='/l/'+l.id;var g=el('div','grow');add(g,el('div','t',l.name));
      var r=el('div','r');if(l.role!=='member')r.appendChild(el('span','badge '+l.role,l.role));if(!l.public)add(r,' ',el('span','badge private','private'));add(a,g,r);b.appendChild(a)})}

  function cups(d){var b=$('cups');b.innerHTML='';
    if(!d.cups.length){b.appendChild(el('div','empty','No cups yet.'));return}
    d.cups.forEach(function(c){var a=el('a','item');a.href='/cup/'+c.id;var g=el('div','grow');add(g,el('div','t',c.name),el('div','s',c.drivers+' drivers · '+new Date(c.starts).toLocaleDateString()));
      add(a,g,el('div','r',c.place?nth(c.place):c.status==='running'?'under way':c.status==='open'?'entered':''));b.appendChild(a)})}

  // ---- my own page: my name, my picture, my team
  function edit(d){var box=$('edit');box.innerHTML='';var me=d.me;var card=el('div','card editcard');box.appendChild(card);
    add(card,el('h3',null,'Your page'));var g=el('div','twocol');card.appendChild(g);
    var nl=el('label');add(nl,el('span',null,'Your name on ACR Daily'));var ni=el('input');ni.type='text';ni.maxLength=${NAME.max};ni.value=me.customName||'';ni.placeholder=me.steamName+' (your Steam name)';nl.appendChild(ni);g.appendChild(nl);
    var nb=el('div');g.appendChild(nb);nb.style.marginTop='30px';var sv=el('button','btn small','Save the name');var rs=el('button','btn ghost small','Use my Steam name');add(nb,sv,' ',me.customName?rs:null);
    var soon=me.nextNameChange&&me.nextNameChange>Date.now();
    card.appendChild(el('p','note','${NAME.min} to ${NAME.max} characters; no two drivers alike, and not another driver\\'s name. One change a week'+(soon?': the next from '+new Date(me.nextNameChange).toLocaleDateString()+'.':'.')+' Your Steam id stays who you are; the site\\'s admins can put a name back.'));
    if(soon){sv.disabled=true;rs.disabled=true}
    sv.onclick=function(){sv.disabled=true;api('/api/me/name',{name:ni.value}).then(function(){msg('em','Saved.',true);load();account()},function(e){sv.disabled=false;msg('em',e.message)})};
    rs.onclick=function(){if(!confirm('Go back to your Steam name? That counts as your change for the week.'))return;rs.disabled=true;api('/api/me/name',{name:null}).then(function(){load();account()},function(e){rs.disabled=false;msg('em',e.message)})};
    add(card,el('h3',null,'Your picture'));var av=el('div','avset');card.appendChild(av);var img=el('img');img.alt='';if(d.avatar)img.src=d.avatar;av.appendChild(img);
    var fb=el('span','btn ghost small filebtn','Upload a picture');var fi=el('input');fi.type='file';fi.accept='image/png,image/jpeg,image/webp';fb.appendChild(fi);av.appendChild(fb);
    if(me.ownAvatar){var sa=el('button','btn ghost small','Use my Steam picture');sa.onclick=function(){sa.disabled=true;
      api('/api/me/avatar',{remove:true}).then(function(){load();account()},function(e){sa.disabled=false;msg('em',e.message)})};av.appendChild(sa)}
    card.appendChild(el('p','note','Shown round, by your name and on the live map. Any picture: it is cut to a square of 256 pixels here.'));
    fi.onchange=function(){var f=fi.files&&fi.files[0];if(!f)return;square(f).then(function(b){
      return fetch('/api/me/avatar',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'image/jpeg'},body:b}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||'error '+r.status);return j})})})
      .then(function(){msg('em','Your picture is up.',true);load();account()},function(e){msg('em',e.message)});fi.value=''};
    add(card,el('h3',null,'Your team'));var tm=el('div','row');card.appendChild(tm);
    if(d.team){var tl=el('a');tl.href='/t/'+d.team.id;tag(tl,d.team,'tagl');add(tl,d.team.name);tl.style.textDecoration='none';add(tm,tl,d.team.captain?el('span','badge owner','captain'):null)}
    else{var ct=el('a','btn ghost small','Create or join a team');ct.href='/teams';add(tm,el('span','muted','No team: its tag shows by your name on the timing sheets and the live map.'),ct)}
    add(card,el('div','msg'));card.lastChild.id='em'}
  // a picture cut to its middle square, 256 x 256 JPEG, small enough to send
  function square(f){return new Promise(function(ok,no){var u=URL.createObjectURL(f),i=new Image();i.onload=function(){URL.revokeObjectURL(u);
      var s=Math.min(i.naturalWidth,i.naturalHeight),c=document.createElement('canvas');c.width=c.height=256;
      c.getContext('2d').drawImage(i,(i.naturalWidth-s)/2,(i.naturalHeight-s)/2,s,s,0,0,256,256);
      (function go(q){c.toBlob(function(b){if(!b)return no(new Error('that picture could not be read'));if(b.size>${AVATAR.maxBytes}&&q>0.4)return go(q-0.15);ok(b)},'image/jpeg',q)})(0.88)};
    i.onerror=function(){URL.revokeObjectURL(u);no(new Error('that file is not a picture'))};i.src=u})}
  account().then(load,load);
  `, env);
}

// ------------------------------------------------------------------ /ranking
export function rankingPage(env) {
  return shell('World ranking · ACR Daily', `${CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>World ranking</h1>
  <p class="note">Every driver with a rating, best first. The rating works like iRacing's iRating: everyone starts at
  ${RATING.start}; both dailies and cup matches count. In a daily you race everyone on its timing sheet, a DNF counting
  as last: finishing ahead of drivers rated above you gains the most, behind those rated below you costs the most. A
  driver's first ${RATING.newRaces} races move it faster. The dailies count once the day is over (by 01:30 UTC).</p>
  <div class="row" style="margin-top:18px"><select id="country" style="width:auto"></select><span id="mine"></span><a class="btn ghost small" href="/teams">Teams</a></div>
  <div class="msg" id="m"></div></div>
  <div class="tablewrap" style="margin-top:22px"><table id="rank"></table></div>
  <div class="pager" id="pager"></div>`, `${DRV_JS}
  var Q=new URLSearchParams(location.search),C=Q.get('country')||'',P=+(Q.get('page')||1)||1,R=null,FIRST=true;
  function go(c,p){C=c;P=p;history.replaceState(null,'','/ranking'+(C||P>1?'?'+(C?'country='+C:'')+(C&&P>1?'&':'')+(P>1?'page='+P:''):''));load()}
  function load(){return api('/api/ranking?page='+P+(C?'&country='+C:'')).then(render,function(e){msg('m',e.message)})}
  function render(r){R=r;var s=$('country');if(FIRST){FIRST=false;s.innerHTML='';var o=el('option',null,'Every country');o.value='';s.appendChild(o);
      r.countries.forEach(function(c){var o=el('option',null,c.code.toUpperCase()+' ('+c.drivers+')');o.value=c.code;s.appendChild(o)});s.value=C;s.onchange=function(){go(s.value,1)}}
    if(!r.ratingOn)msg('m','The driver rating is not on yet: it starts soon, every driver from ${RATING.start}.',true);
    var mi=$('mine');mi.innerHTML='';if(r.me&&r.me.rank){var b=el('button','btn ghost small','Me: #'+r.me.rank+' · '+r.me.rating);
      b.onclick=function(){go('',Math.ceil(r.me.rank/r.size))};mi.appendChild(b)}
    var t=$('rank');t.innerHTML='';var h=el('tr');['#','Driver','Rating','Races','Peak'].forEach(function(x,i){h.appendChild(el('th',i>=2?'r':null,x))});t.appendChild(h);
    if(!r.rows.length){var tr=el('tr'),td=el('td','empty','Nobody rated yet.');td.colSpan=5;tr.appendChild(td);t.appendChild(tr)}
    r.rows.forEach(function(x){var tr=el('tr',(x.rank===1?'p1':'')+(r.me&&x.steamId===r.me.steamId?' me':''));
      add(tr,el('td','pos',String(x.rank)));var d=el('td','drv');if(x.avatar){var i=el('img','av');i.src=x.avatar;i.alt='';d.appendChild(i)}drv(d,x);tr.appendChild(d);
      add(tr,el('td','r tot',String(x.rating)),el('td','r muted',String(x.races)),el('td','r muted',String(x.peak)));t.appendChild(tr)});
    var pg=$('pager');pg.innerHTML='';var pages=Math.max(1,Math.ceil(r.total/r.size));
    if(pages>1){var pv=el('button','btn ghost small','‹ Better');pv.disabled=P<=1;pv.onclick=function(){go(C,P-1)};
      var nx=el('button','btn ghost small','Next ›');nx.disabled=P>=pages;nx.onclick=function(){go(C,P+1)};add(pg,pv,el('span',null,'Page '+P+' of '+pages+' · '+r.total+' drivers'),nx)}
    else if(r.total)pg.appendChild(el('span',null,r.total+(r.total===1?' driver':' drivers')))}
  account().then(load,load);
  `, env);
}

// ------------------------------------------------------------------ /teams
export function teamsPage(env) {
  return shell('Teams · ACR Daily', `${CSS}
  <div class="top"><div class="kick"><a href="/ranking">Ranking</a></div><h1>Teams</h1>
  <p class="note">A team's coloured tag shows by its drivers' names on the timing sheets and the live map. A driver is in
  one team at a time; its captain hands out the invite code, can renew it, and can remove a driver. Up to ${TEAM.maxMembers}
  drivers a team.</p><div class="msg" id="m"></div></div>
  <div class="grid" style="margin-top:22px" id="forms"></div>
  <h2>Every team</h2><div class="tablewrap"><table id="teams"></table></div>`, `${DRV_JS}
  var T=null;
  function load(){return api('/api/teams').then(render,function(e){msg('m',e.message)})}
  function render(r){T=r;var t=$('teams');t.innerHTML='';var h=el('tr');['Tag','Team','Drivers','Rating'].forEach(function(x,i){h.appendChild(el('th',i>=2?'r':null,x))});t.appendChild(h);
    if(!r.teams.length){var tr=el('tr'),td=el('td','empty','No teams yet: make the first.');td.colSpan=4;tr.appendChild(td);t.appendChild(tr)}
    r.teams.forEach(function(x){var tr=el('tr',r.mine===x.id?'me':'');var tg=el('td');tag(tg,x,'tagl');var n=el('td','drv'),a=el('a',null,x.name);a.href='/t/'+x.id;n.appendChild(a);
      add(tr,tg,n,el('td','r',String(x.members)),el('td','r muted',x.rating!=null?String(x.rating):'–'));t.appendChild(tr)});
    forms(r)}
  function forms(r){var f=$('forms');f.innerHTML='';
    if(!ME){var c=el('div','card');add(c,el('h3',null,'Your team'),el('p','muted','Sign in with Steam to make or join a team.'));c.appendChild(steamBtn());f.appendChild(c);return}
    if(r.mine){var c2=el('div','card');add(c2,el('h3',null,'Your team'));var l=el('a','btn ghost','Go to your team');l.href='/t/'+r.mine;c2.appendChild(l);f.appendChild(c2);return}
    var mk=el('div','card');f.appendChild(mk);add(mk,el('h3',null,'Make a team'));
    var nl=el('label');add(nl,el('span',null,'Name'));var ni=el('input');ni.type='text';ni.maxLength=${TEAM.nameMax};ni.placeholder='e.g. Gravel Foxes';nl.appendChild(ni);mk.appendChild(nl);
    var tl=el('label');add(tl,el('span',null,'Tag (2 to 4 letters or digits)'));var ti=el('input');ti.type='text';ti.maxLength=4;ti.placeholder='e.g. GFX';ti.style.textTransform='uppercase';tl.appendChild(ti);mk.appendChild(tl);
    var cl=el('label');add(cl,el('span',null,'Its colour'));var cs=el('div','colors');r.colors.forEach(function(c,i){var l=el('label'),inp=el('input');inp.type='radio';inp.name='tc';inp.value=c;inp.checked=!i;
      var sw=el('span');sw.style.background=c;add(l,inp,sw);cs.appendChild(l)});cl.appendChild(cs);mk.appendChild(cl);
    var pv=el('p','note');mk.appendChild(pv);function prev(){pv.innerHTML='';var c=(document.querySelector('input[name=tc]:checked')||{}).value;var s=el('span','tagl',(ti.value||'TAG').toUpperCase());s.style.color=c;add(pv,'On the timing sheets: ',s,ME.name)}
    ti.oninput=prev;cs.onchange=prev;prev();
    var sb=el('button','btn','Make the team');sb.style.marginTop='12px';mk.appendChild(sb);
    sb.onclick=function(){sb.disabled=true;api('/api/teams',{name:ni.value,tag:ti.value,color:(document.querySelector('input[name=tc]:checked')||{}).value})
      .then(function(j){location.href='/t/'+j.id},function(e){sb.disabled=false;msg('m',e.message)})};
    var jn=el('div','card');f.appendChild(jn);add(jn,el('h3',null,'Join with an invite code'));
    var ci=el('input');ci.type='text';ci.maxLength=9;ci.placeholder='XXXX-XXXX';ci.value=new URLSearchParams(location.search).get('code')||'';jn.appendChild(ci);
    var jb=el('button','btn','Join');jb.style.marginTop='12px';jn.appendChild(jb);
    jb.onclick=function(){jb.disabled=true;api('/api/teams/join',{code:ci.value}).then(function(j){location.href='/t/'+j.id},function(e){jb.disabled=false;msg('m',e.message)})}}
  account().then(load,load);
  `, env);
}

// ------------------------------------------------------------------ /t/<id>
export function teamPage(id, env) {
  return shell('Team · ACR Daily', `${CSS}
  <div class="top"><div class="kick"><a href="/teams">Teams</a></div><h1 id="name">…</h1>
    <div class="facts" id="facts"></div>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <h2>Drivers</h2><div class="tablewrap"><table id="members"></table></div>
  <div id="captain"></div>`, `${DRV_JS}
  var ID=${JSON.stringify(id)},X=null;
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/teams/'+ID).then(render,function(e){$('name').textContent=e.status===404?'No such team':'Team';msg('m',e.message)})}
  function render(t){X=t;document.title=t.name+' · ACR Daily';var n=$('name');n.innerHTML='';tag(n,t,'tagl');n.lastChild.style.fontSize='inherit';n.lastChild.style.marginRight='14px';add(n,t.name);
    $('facts').innerHTML='';fact('Drivers',t.members.length+' of '+t.maxMembers);fact('Rating',t.rating!=null?String(t.rating):'–');
    var cap=t.members.filter(function(m){return m.captain})[0];if(cap)fact('Captain',cap.name);
    var a=$('acts');a.innerHTML='';var me=t.me;
    if(me&&me.member){add(a,el('span','k','Invite code'),el('span','code',t.code));
      var lv=el('button','btn ghost small','Leave the team');lv.onclick=function(){if(!confirm('Leave '+t.name+'?'+(me.captain&&t.members.length>1?' The captaincy goes to the driver who has been in it longest.':t.members.length===1?' You are its last driver: the team closes.':'')))return;
        lv.disabled=true;api('/api/teams/'+ID+'/leave',{}).then(function(j){location.href=j.closed?'/teams':'/t/'+ID},function(e){lv.disabled=false;msg('m',e.message)})};a.appendChild(lv)}
    else if(me){var jl=el('a','btn','Join with its invite code');jl.href='/teams'+(new URLSearchParams(location.search).get('code')?'?code='+encodeURIComponent(new URLSearchParams(location.search).get('code')):'');a.appendChild(jl)}
    else a.appendChild(steamBtn());
    var tb=$('members');tb.innerHTML='';var h=el('tr');['Driver','Rating','Races',''].forEach(function(x,i){h.appendChild(el('th',i&&i<3?'r':null,x))});tb.appendChild(h);
    t.members.forEach(function(m){var tr=el('tr',me&&m.steamId===me.steamId?'me':'');var d=el('td','drv');if(m.avatar){var i=el('img','av');i.src=m.avatar;i.alt='';d.appendChild(i)}
      flag(d,m.country);var l=el('a',null,m.name);l.href='/d/'+m.steamId;d.appendChild(l);if(m.captain)add(d,' ',el('span','badge owner','captain'));
      add(tr,d,el('td','r tot',m.rating!=null?String(m.rating):'–'),el('td','r muted',String(m.races)));var ac=el('td','r');
      if(me&&me.captain&&m.steamId!==me.steamId){var cp=el('button','btn ghost small','Make captain');cp.onclick=function(){if(!confirm('Make '+m.name+' the captain?'))return;
          api('/api/teams/'+ID+'/captain',{steamId:m.steamId}).then(load,function(e){msg('m',e.message)})};
        var kk=el('button','btn danger small','Remove');kk.onclick=function(){if(!confirm('Remove '+m.name+' from the team?'))return;
          api('/api/teams/'+ID+'/kick',{steamId:m.steamId}).then(load,function(e){msg('m',e.message)})};add(ac,cp,' ',kk)}
      tr.appendChild(ac);tb.appendChild(tr)});
    captain(t)}
  // ---- the captain: the name, tag and colour; a new invite code
  function captain(t){var box=$('captain');box.innerHTML='';if(!t.me||!t.me.captain)return;
    add(box,el('h2',null,'Captain'));var c=el('div','card');box.appendChild(c);var g=el('div','twocol');c.appendChild(g);
    var nl=el('label');add(nl,el('span',null,'Name'));var ni=el('input');ni.type='text';ni.maxLength=${TEAM.nameMax};ni.value=t.name;nl.appendChild(ni);g.appendChild(nl);
    var tl=el('label');add(tl,el('span',null,'Tag'));var ti=el('input');ti.type='text';ti.maxLength=4;ti.value=t.tag;ti.style.textTransform='uppercase';tl.appendChild(ti);g.appendChild(tl);
    var cs=el('div','colors');t.colors.forEach(function(col){var l=el('label'),inp=el('input');inp.type='radio';inp.name='tc';inp.value=col;inp.checked=col===t.color;
      var sw=el('span');sw.style.background=col;add(l,inp,sw);cs.appendChild(l)});var cl=el('label');add(cl,el('span',null,'Colour'),cs);c.appendChild(cl);
    var sv=el('button','btn','Save');var rn=el('button','btn ghost','New invite code');var row=el('div','row');row.style.marginTop='14px';add(row,sv,rn);c.appendChild(row);
    sv.onclick=function(){sv.disabled=true;api('/api/teams/'+ID+'/edit',{name:ni.value,tag:ti.value,color:(document.querySelector('input[name=tc]:checked')||{}).value})
      .then(function(){sv.disabled=false;msg('m','Saved.',true);load()},function(e){sv.disabled=false;msg('m',e.message)})};
    rn.onclick=function(){if(!confirm('A new invite code? The old one stops working.'))return;api('/api/teams/'+ID+'/code',{}).then(load,function(e){msg('m',e.message)})}}
  account().then(load,load);
  `, env);
}
