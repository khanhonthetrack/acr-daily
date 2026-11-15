// /liveries: the drivers' liveries (src/liveries.js). Each a card: its preview (opens full size), the car, who painted
// it, the stars (a click votes, signed in), its description, DOWNLOAD (its link, counted) and "Link not working?".
// The car and the order picked at the top (?car=<id> opens on one car). How to put one into the game by hand, and the
// app's one click (COMMUNITY > LIVERIES). Below: the form to send one (signed in with Steam; it shows once the admin
// has published it) and the driver's own, with where each stands. In the leagues' look (src/leaguepages.js shell).

import { t, tq, tqp } from './i18n.js';
import { shell } from './leaguepages.js';
import { LIVERY } from './liveries.js';

// ACR Livery Tool, the 3D livery editor (by Adriano Gastaldello, ACRK Challenge): its exports are what the game reads
export const LIVERY_TOOL = 'https://github.com/agastal/AcrLiveryTool-Release/releases/latest';
// (an ordinary string: one backslash each)
export const LIVERIES_DIR = 'Documents\\My Games\\acr\\Liveries';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const CSS = `<style>
.lv-top{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
.lv-filters{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;margin-top:26px;padding:14px 16px;background:var(--panel);border:1px solid var(--line)}
.lv-filters label{margin:0;min-width:220px}
.lv-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:14px}
.lv{background:var(--panel);border:1px solid var(--line);display:flex;flex-direction:column;min-width:0}
.lv .shot{display:block;width:100%;aspect-ratio:16/9;padding:0;border:0;background:#0E0E10;cursor:zoom-in;overflow:hidden}
.lv .shot img{display:block;width:100%;height:100%;object-fit:cover;transition:filter .15s}
.lv .shot:hover img{filter:brightness(1.08)}
.lv .bd{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;flex:1}
.lv .car{font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--acc)}
.lv h3{font:700 24px/1.05 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.01em;color:var(--fg);margin:0;overflow-wrap:anywhere}
.lv .by{color:var(--fg2);font-size:13px}
.lv .by a{color:var(--fg)}
.lv .desc{margin:0;color:var(--fg2);font-size:14px;white-space:pre-line;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.lv .desc.open{display:block}
.lv .more,.lv .flag{align-self:flex-start;padding:0;border:0;background:none;color:var(--fg2);font:inherit;font-size:13px;cursor:pointer;text-decoration:underline}
.lv .flag{color:var(--fg3);font-size:12px}
.lv .flag[disabled]{text-decoration:none;cursor:default}
.lv .foot{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:auto;padding-top:8px}
.lv .foot .s{color:var(--fg3);font-size:13px}
.lv .foot2{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:20px}
.badge.app{border-color:var(--good);color:var(--good)}
.stars{display:flex;align-items:center;gap:1px;flex-wrap:wrap;font-size:13px}
.stars button{padding:0 1px;border:0;background:none;color:#3A3A42;font-size:22px;line-height:1;cursor:pointer}
.stars button.on{color:#FFD60A}
.stars.mine button.on{color:var(--acc)}
.stars.can:hover button{color:var(--acc)}
.stars.can button:hover~button{color:#3A3A42}
.stars button[disabled]{cursor:default}
.stars .s{margin-left:8px;color:var(--fg3)}
.howto{margin-top:18px;padding:14px 16px;border:1px solid var(--line);border-left:3px solid var(--good);background:var(--panel);color:var(--fg2);font-size:14px}
.howto b{color:var(--fg)}
.howto code{font:500 13px/1.4 ui-monospace,Consolas,monospace;color:var(--fg);background:#0E0E10;border:1px solid var(--line2);padding:2px 6px;word-break:break-all}
.lvform{max-width:860px}
.lvform .two{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
@media(max-width:760px){.lvform .two{grid-template-columns:1fr}}
.hint{color:var(--fg3);font-size:13px;margin-top:5px}
input[type=url]{width:100%;background:#0E0E10;border:1px solid var(--line2);color:var(--fg);font:15px/1.3 Barlow,sans-serif;padding:9px 10px;border-radius:0;color-scheme:dark}
input[type=file]{color:var(--fg2);font:14px Barlow,sans-serif}
#f-prev{display:block;margin-top:10px;max-width:320px;border:1px solid var(--line2)}
.st{display:inline-block;border:1px solid var(--line2);padding:3px 7px;font:600 11px/1 Barlow,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:var(--fg2)}
.st.published{border-color:var(--good);color:var(--good)}
.st.rejected,.st.hidden{border-color:var(--bad);color:var(--bad)}
.mine .item .t{font-size:18px}
.mine .nt{color:var(--fg2);font-size:13px;white-space:pre-wrap;margin-top:4px}
.mine img{width:120px;aspect-ratio:16/9;object-fit:cover;border:1px solid var(--line);flex:none;background:#0E0E10}
.zoom{position:fixed;inset:0;background:rgba(0,0,0,.88);display:flex;align-items:center;justify-content:center;padding:24px;z-index:50;cursor:zoom-out}
.zoom img{max-width:100%;max-height:100%;box-shadow:0 10px 40px rgba(0,0,0,.6)}
.zoom[hidden]{display:none}
</style>`;

export function liveriesPage(env) {
  const mb = (LIVERY.maxShotBytes / 1e6).toFixed(1);
  return shell(t('Liveries') + ' · ACR Daily', `${CSS}
  <div class="top"><div class="kick">ACR Daily · ${t('community')}</div><h1>${t('Liveries')}</h1>
  <p class="note">${t('Liveries painted by the drivers, ready to put on your car. Pick the car, look at the previews, download and rate them. The ACR Daily app puts one into the game in one click: <b>COMMUNITY › LIVERIES</b>.')}</p>
  <div class="lv-top"><a class="btn" href="#send">${t('Publish your livery')}</a>
    <a class="btn ghost" href="${LIVERY_TOOL}" target="_blank" rel="noopener">${t('Get ACR Livery Tool')}</a></div></div>

  <div class="lv-filters">
    <label><span>${t('Car')}</span><select id="car"></select></label>
    <label><span>${t('Sort by')}</span><select id="sort"><option value="top">${t('Top rated')}</option><option value="new">${t('Newest')}</option><option value="clicks">${t('Most downloaded')}</option></select></label>
  </div>
  <div id="list"><div class="empty">${t('Loading…')}</div></div>

  <div class="howto">${t("<b>To put one into the game by hand:</b> unzip it into the car's folder in {0}, one folder per livery (the game takes {1} a car at most). The game sees a new livery when it starts. <b>With the ACR Daily app:</b> COMMUNITY › LIVERIES › INSTALL does it for you (where the link gives the zip itself: a GitHub release, Dropbox, Google Drive) and takes it out again.", `<code>${esc(LIVERIES_DIR)}\\&lt;car&gt;\\</code>`, LIVERY.perCar)}</div>

  <h2 id="send">${t('Publish your livery')}</h2>
  <p class="note">${t('The file stays where you uploaded it: here goes its card, with your preview and the link. It shows once the admin has published it, and you are told in your inbox.')}</p>
  <div id="signin"></div>
  <form class="lvform" id="f" hidden onsubmit="return false" novalidate>
    <div class="two">
      <label><span>${t('Car')}</span><select id="f-car"></select></label>
      <label><span>${t('Livery name')}</span><input type="text" id="f-title" maxlength="${LIVERY.title[1]}" placeholder="Martini Racing 1983"></label>
      <label><span>${t('Painted by')}</span><input type="text" id="f-author" maxlength="${LIVERY.author[1]}"></label>
    </div>
    <label><span>${t('Download link (optional)')}</span><input type="url" id="f-link" maxlength="${LIVERY.link}" placeholder="https://">
      <div class="hint">${t('Overtake.gg, Google Drive, Dropbox, MEGA, MediaFire or a GitHub release. Upload the zip of the exported folder (not the .acrlivery project); on Google Drive share it with "Anyone with the link". The app installs it in one click from GitHub, Dropbox and Google Drive. Leave it empty to show it only.')}</div></label>
    <label><span>${t('Description (optional)')}</span><textarea id="f-desc" maxlength="${LIVERY.description}" placeholder="${t('The inspiration, the sponsors, what makes it special.')}"></textarea></label>
    <label><span>${t('Preview')}</span><input type="file" id="f-shot" accept="image/png,image/jpeg,image/webp">
      <div class="hint">${t('A screenshot of the car wearing it, ideally from the game (photo mode) and 16:9. Made smaller in your browser before it goes ({0} MB at most).', mb)}</div><img id="f-prev" alt="" hidden></label>
    <div class="row" style="margin-top:16px"><button class="btn" id="f-send" type="submit">${t('Send for approval')}</button></div>
    <div class="msg" id="f-msg"></div>
  </form>

  <div id="minebox" hidden><h2>${t('Your liveries')}</h2><div class="mine" id="mine"></div></div>
  <div class="zoom" id="zoom" hidden><img id="zoomimg" alt=""></div>`, `
  var L={all:[],cars:[],car:'',sort:'top',signedIn:false,shot:''};
  function remember(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function recall(k){try{return localStorage.getItem(k)||''}catch(e){return ''}}
  var params=new URLSearchParams(location.search);
  L.car=params.get('car')||'';
  L.sort=['top','new','clicks'].indexOf(recall('acr-livery-sort'))>=0?recall('acr-livery-sort'):'top';
  $('sort').value=L.sort;

  var VOTES=${tqp('{0} vote', '{0} votes')},DLS=${tqp('{0} download', '{0} downloads')};
  function votesText(l){var n=!l.votes?${tq('No votes')}:P(VOTES,l.votes,l.votes);return l.votes?l.stars.toFixed(1)+' · '+n:n}
  function sorted(list){var by={top:function(a,b){return b.stars-a.stars||b.votes-a.votes||b.published-a.published},
    new:function(a,b){return b.published-a.published},clicks:function(a,b){return b.clicks-a.clicks||b.published-a.published}}[L.sort];
    return list.slice().sort(by)}
  function day(t){return new Date(t).toLocaleDateString(LOC,{day:'numeric',month:'short',year:'numeric'})}

  // five stars: my own vote when there is one (red), else the average (gold); a click votes (signed in, not on my own)
  function stars(l){var own=ME&&l.by&&l.by.steamId===ME.steamId,can=!!ME&&!own;
    var box=el('div','stars'+(l.mine?' mine':'')+(can?' can':''));var shown=l.mine||Math.round(l.stars);
    for(var n=1;n<=5;n++)(function(n){var b=el('button',n<=shown?'on':null,'★');b.type='button';
      b.title=!ME?${tq('Sign in with Steam to rate it')}:own?${tq('Your own livery')}:P(${tqp('{0} star', '{0} stars')},n,n);b.setAttribute('aria-label',b.title);
      if(own)b.disabled=true;
      b.onclick=function(){if(!ME){location.href=signin();return}if(!can)return;
        api('/api/liveries/'+l.id+'/vote',{stars:n}).then(function(d){l.votes=d.votes;l.stars=d.stars;l.mine=d.mine;box.replaceWith(stars(l))},
          function(e){alert(e.message)})};
      box.appendChild(b)})(n);
    box.appendChild(el('span','s',votesText(l)+(l.mine?' · '+F(${tq('your vote: {0}')},l.mine):'')));return box}

  function card(l){var c=el('article','lv');
    var sh=el('button','shot');sh.type='button';sh.title=${tq('See it full size')};
    if(l.shot){var im=el('img');im.loading='lazy';im.alt=l.title;im.src=l.shot;sh.appendChild(im);sh.onclick=function(){zoom(l.shot)}}
    c.appendChild(sh);var bd=el('div','bd');
    var by=el('div','by',F(${tq('by {0}')},l.author)+' · '+day(l.published));
    if(l.by&&l.by.steamId&&l.by.name&&l.by.name!==l.author){var a=el('a',null,l.by.name);a.href='/d/'+encodeURIComponent(l.by.steamId);by.appendChild(document.createTextNode(' · '));add(by,FN(${tq('sent by {0}')},a))}
    add(bd,el('div','car',l.carName),el('h3',null,l.title),by,stars(l));
    if(l.description){var p=el('p','desc',l.description),more=el('button','more',${tq('Show all')});more.type='button';more.hidden=true;
      more.onclick=function(){var o=p.classList.toggle('open');more.textContent=o?${tq('Show less')}:${tq('Show all')}};add(bd,p,more)}
    var f=el('div','foot');
    if(l.go){var info=function(){return F(${tq('from {0}')},l.hostName||l.host)+' · '+P(DLS,l.clicks,l.clicks)};
      var d=el('a','btn small',${tq('Download')}),cnt=el('span','s',info());d.href=l.go;d.target='_blank';d.rel='noopener nofollow';
      d.onclick=function(){l.clicks++;setTimeout(function(){cnt.textContent=info()},50)};add(f,d,cnt);
      bd.appendChild(f);var f2=el('div','foot2');
      var fl=el('button','flag',${tq('Link not working?')});fl.type='button';
      fl.onclick=function(){if(!ME){location.href=signin();return}fl.disabled=true;
        api('/api/liveries/'+l.id+'/flag',{}).then(function(){fl.textContent=${tq('Reported, thanks: we will look into it.')}},function(e){fl.disabled=false;alert(e.message)})};
      f2.appendChild(fl);
      if(l.direct){var ap=el('span','badge app',${tq('App installs it')});ap.title=${tq('The ACR Daily app puts it into the game in one click: COMMUNITY › LIVERIES')};f2.appendChild(ap)}
      bd.appendChild(f2)}
    else{f.appendChild(el('span','s',${tq('Shown only: the author has not shared the file')}));bd.appendChild(f)}
    c.appendChild(bd);return c}

  function render(){var box=$('list');box.innerHTML='';
    var list=sorted(L.car?L.all.filter(function(l){return l.car===L.car}):L.all);
    if(!list.length){box.appendChild(el('div','empty',L.all.length?${tq('No liveries for this car yet.')}:${tq('No liveries yet: publish the first one!')}));return}
    var g=el('div','lv-grid');list.forEach(function(l){g.appendChild(card(l))});box.appendChild(g);
    // "Show all" only under a description the card had to cut
    [].forEach.call(g.querySelectorAll('.desc'),function(p){p.nextSibling.hidden=p.scrollHeight<=p.clientHeight+1})}

  function carOptions(sel,all){var s=$(sel);s.innerHTML='';
    if(all){var o=el('option',null,F(${tq('All cars ({0})')},L.all.length));o.value='';s.appendChild(o)}
    else{var o2=el('option',null,${tq('Pick the car')});o2.value='';s.appendChild(o2)}
    L.cars.slice().sort(function(a,b){return a.name.localeCompare(b.name)}).forEach(function(c){
      if(all&&!c.count&&c.id!==L.car)return;var o=el('option',null,c.name+(all?' ('+c.count+')':''));o.value=c.id;s.appendChild(o)});
    s.value=all?L.car:(L.car||'')}

  function zoom(src){$('zoomimg').src=src;$('zoom').hidden=false}
  $('zoom').onclick=function(){$('zoom').hidden=true};
  document.addEventListener('keydown',function(e){if(e.key==='Escape')$('zoom').hidden=true});

  $('car').onchange=function(){L.car=this.value;var u=new URL(location.href);if(L.car)u.searchParams.set('car',L.car);else u.searchParams.delete('car');
    history.replaceState(null,'',u);if(L.car)$('f-car').value=L.car;render()};
  $('sort').onchange=function(){L.sort=this.value;remember('acr-livery-sort',L.sort);render()};

  // ---- the form: the preview made smaller here (a JPEG at most 1600 px wide), then sent with the card's fields
  function shrink(file,w,q){return new Promise(function(ok,no){var img=new Image();img.onload=function(){
      var k=Math.min(1,w/img.width),c=document.createElement('canvas');c.width=Math.round(img.width*k);c.height=Math.round(img.height*k);
      c.getContext('2d').drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(img.src);ok(c.toDataURL('image/jpeg',q))};
    img.onerror=function(){no(new Error(${tq('That picture cannot be read: a PNG, JPEG or WebP')}))};img.src=URL.createObjectURL(file)})}
  var MAX=${LIVERY.maxShotBytes};
  $('f-shot').onchange=function(){var file=this.files[0],pv=$('f-prev');L.shot='';pv.hidden=true;msg('f-msg','');if(!file)return;
    shrink(file,1600,.85).then(function(d){return d.length*.75>MAX?shrink(file,1280,.7):d}).then(function(d){
      if(d.length*.75>MAX)throw new Error(${tq('That picture is too big even made smaller')});L.shot=d;pv.src=d;pv.hidden=false},function(e){msg('f-msg',e.message)})};
  $('f-send').onclick=function(){var b=this;
    if(!L.shot){msg('f-msg',${tq('Add the preview picture.')});return}
    var body={car:$('f-car').value,title:$('f-title').value,author:$('f-author').value,link:$('f-link').value,description:$('f-desc').value,shot:L.shot};
    b.disabled=true;msg('f-msg',${tq('Sending…')},true);
    api('/api/liveries',body).then(function(){remember('acr-livery-author',body.author.trim());
      ['f-title','f-link','f-desc','f-shot'].forEach(function(i){$(i).value=''});$('f-prev').hidden=true;L.shot='';
      msg('f-msg',${tq('Received, thanks! It shows here once the admin has published it (you are told in your inbox).')},true);mine()},
      function(e){msg('f-msg',e.message)}).then(function(){b.disabled=false})};

  // ---- my own: where each stands; delete one
  var SAID={pending:${tq('Waiting for the admin')},published:${tq('Published')},rejected:${tq('Not published')},hidden:${tq('Taken off')}};
  function mine(){api('/api/liveries/mine').then(function(j){var box=$('mine');box.innerHTML='';$('minebox').hidden=!j.liveries.length;
    j.liveries.forEach(function(l){var it=el('div','item');it.id='l'+l.id;var im=el('img');im.alt='';if(l.status==='published'&&l.shot)im.src=l.shot;
      var d=el('div','grow');add(d,el('div','t',l.title),el('div','s',l.carName+' · '+F(${tq('sent {0}')},day(l.created))+(l.status==='published'?' · '+votesText(l)+' · '+P(DLS,l.clicks,l.clicks):'')));
      if(l.note)d.appendChild(el('div','nt',l.note));
      var r=el('div','r');var st=el('span','st '+l.status,SAID[l.status]||l.status);var del=el('button','linkbtn',${tq('delete')});del.type='button';
      del.onclick=function(){if(!confirm(F(${tq('Delete {0}? Its card, votes and downloads go.')},l.title)))return;
        api('/api/liveries/'+l.id+'/delete',{}).then(function(){mine();load()},function(e){alert(e.message)})};
      add(r,st,el('br'),del);add(it,im,d,r);box.appendChild(it)})},function(){})}

  function load(){return api('/api/liveries').then(function(j){L.all=j.liveries;L.cars=j.cars;
    if(L.car&&!L.cars.some(function(c){return c.id===L.car}))L.car='';carOptions('car',true);render()},
    function(e){$('list').innerHTML='';$('list').appendChild(el('div','empty',F(${tq('Could not load the liveries: {0}')},e.message)))})}

  account().then(function(me){
    if(!me){var s=$('signin');add(s,el('p','note',${tq('Sign in with Steam to publish a livery and to rate them.')}+' '),steamBtn())}
    else{$('f').hidden=false;$('f-author').value=recall('acr-livery-author')||me.name||'';mine()}
    return load()}).then(function(){carOptions('f-car',false)});`, env);
}
