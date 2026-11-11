// /report: tell us what went wrong (src/reports.js). Signed in with Steam (their name comes with it), the app version
// (from the app's link ?v=, else the latest), where it happened, what happened; screenshots (picked, dropped or pasted)
// and the game's log, save and the app's files, packed by the browser before they go (pictures as JPEG, the rest
// gzipped; a long log keeps its end). Where each file is, step by step. Below: the driver's own reports and how far
// each has got. In the leagues' look (src/leaguepages.js shell).

import { shell } from './leaguepages.js';
import { latestVersion } from './release.js';
import { AREAS, REPORT } from './reports.js';
import { N_, t, tq } from './i18n.js';

// (ordinary strings: one backslash each)
export const PATHS = {
  logs: '%LOCALAPPDATA%\\acr\\Saved\\Logs',
  crashes: '%LOCALAPPDATA%\\acr\\Saved\\Crashes',
  saves: '%LOCALAPPDATA%\\acr\\Saved\\SaveGames',
  app: '%APPDATA%\\ACR Daily',
  backups: '%APPDATA%\\ACR Daily\\save-backups',
};
const AREA_NAMES = { daily: N_('Daily stages'), 'time trial': N_('Time trial'), league: N_('A league event'), '1v1': N_('A 1V1'),
  cup: N_('A cup match'), app: N_('The app (timer, overlays, DRIVE, AUTO)'), website: N_('The website'), other: N_('Something else') };
const areaNames = () => Object.fromEntries(Object.entries(AREA_NAMES).map(([k, v]) => [k, t(v)]));

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const path = (p) => `<span class="path"><code>${esc(p)}</code><button type="button" class="copy" data-copy="${esc(p)}">${t('Copy')}</button></span>`;

const CSS = `<style>
.rp{max-width:760px}
.rp .two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:640px){.rp .two{grid-template-columns:1fr}}
.rp label{display:block;margin:14px 0 0}
.rp textarea{min-height:150px}
.hint{color:var(--fg3);font-size:13px;margin-top:5px}
.drop{margin-top:14px;border:1px dashed var(--line2);padding:18px;text-align:center;color:var(--fg2);cursor:pointer}
.drop.on{border-color:var(--fg2);background:#141417}
.drop input{display:none}
.files{list-style:none;padding:0;margin:10px 0 0}
.files li{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
.files li .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.files select{width:auto;padding:4px 6px;font-size:13px}
.linkbtn{background:none;border:0;color:var(--fg2);cursor:pointer;text-decoration:underline;font:inherit;padding:0}
.path{display:inline-flex;align-items:center;gap:8px;margin:4px 0;flex-wrap:wrap}
.path code{font:500 13px/1.4 ui-monospace,Consolas,monospace;letter-spacing:0;background:#0E0E10;border:1px solid var(--line2);padding:3px 7px;word-break:break-all}
.copy{background:none;border:1px solid var(--line2);color:var(--fg2);font:600 11px/1 Barlow,sans-serif;letter-spacing:.08em;text-transform:uppercase;padding:5px 8px;cursor:pointer}
.how li{margin-bottom:6px}
.how code{font:500 14px/1.4 ui-monospace,Consolas,monospace;letter-spacing:0;color:var(--fg)}
.how p{color:var(--fg2);margin:6px 0 0;font-size:14px}
.st{display:inline-block;border:1px solid var(--line2);padding:3px 7px;font:600 11px/1 Barlow,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:var(--fg2)}
.st.pr,.st.fixed{border-color:var(--good);color:var(--good)}
.st.needs-info{border-color:var(--slow);color:var(--slow)}
.mine td{vertical-align:top}
.mine .nt{color:var(--fg2);font-size:13px;white-space:pre-wrap;margin-top:4px}
</style>`;

export function reportPage(env) {
  const latest = latestVersion(env);
  const mb = (REPORT.maxFileBytes / 1e6).toFixed(1);
  const AN = areaNames();
  return shell(t('Report a problem') + ' · ACR Daily', `${CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>${t('Report a problem')}</h1>
  <p class="note">${t("Something broke, a time went missing, the game got stuck? Tell us what happened and attach what you can: a screenshot, the game's log, the game's save. We look at every report, and you see here (and in your inbox) how far yours has got.")}</p></div>

  <div class="rp">
  <div id="signin"></div>
  <form id="f" hidden onsubmit="return false">
    <p class="note" id="who"></p>
    <div class="two">
      <label><span>${t('Where')}</span><select id="area"><option value="">${t('Pick one')}</option>${AREAS.map((a) => `<option value="${esc(a)}">${esc(AN[a] || a)}</option>`).join('')}</select></label>
      <label><span>${t('App version')}</span><input type="text" id="ver" maxlength="20" placeholder="${esc(latest)}">
        <div class="hint">${t('At the bottom of the app window, e.g. v{0}.', esc(latest))}</div></label>
    </div>
    <label><span>${t('In a few words')}</span><input type="text" id="title" maxlength="${REPORT.title[1]}" placeholder="${t('Stuck on the loading screen after SS2')}"></label>
    <label><span>${t('What happened')}</span><textarea id="body" maxlength="${REPORT.body[1]}" placeholder="${t('What you did, what you expected, and what happened instead. Step by step if you can. Anything the app or the game said.')}"></textarea></label>
    <div class="two">
      <label><span>${t('The event, run or page (if any)')}</span><input type="text" id="ev" maxlength="200" placeholder="${t("acrdaily.com/e/24, today's SS1, ...")}"></label>
      <label><span>${t('When')}</span><input type="text" id="when" maxlength="60" placeholder="${t('today about 18:45, after SS2')}"></label>
    </div>
    <label><span>${t('Your PC (if it may matter)')}</span><input type="text" id="sys" maxlength="200" placeholder="${t('Windows 11, 2560x1440, Fanatec wheel, ...')}"></label>

    <div class="drop" id="drop">${t('<b>Add files</b>: click, drop them here, or paste a screenshot (Ctrl+V).')}
      <div class="hint">${t("Up to {0}: screenshots, the game's log and save, ACR Daily's files (see below). Packed in your browser before they go, {1} MB each at most once packed; a long log keeps its end.", REPORT.maxFiles, mb)}</div>
      <input type="file" id="pick" multiple></div>
    <ul class="files" id="files"></ul><div class="msg" id="fm"></div>

    <p class="hint">${t("Logs and saves can hold your Windows user name and your in-game driver's name. Only ACR Daily's admin sees your files, never other drivers, and they are deleted after {0} days. Fixes are made in the open on GitHub without your files or your name.", REPORT.keepDays)}</p>
    <div style="margin-top:16px"><button class="btn" id="send" type="button">${t('Send the report')}</button></div>
    <div class="msg" id="m"></div>
  </form>

  <h2>${t('Where the files are')}</h2>
  <p class="note">${t("Press <b>Win+R</b>, paste a folder's path (Copy), press Enter: Explorer opens it. Then drag the file onto this page.")}</p>
  <ol class="steps how">
    <li>${t("<b>A screenshot.</b> <b>Win+Shift+S</b>, pick the part of the screen, then <b>Ctrl+V</b> on this page. Or <b>PrtScn</b>, or Steam's F12 screenshots (Steam › View › Screenshots). A photo of the screen is fine too.")}</li>
    <li>${t("<b>The game's log</b>, {0}, in {1}", '<code>acr.log</code>', path(PATHS.logs))}
      <p>${t('If the game froze or crashed, take it <b>before you start the game again</b>: the game renames it to {0} when it starts. Already started it? Attach the newest {1} file. After a crash, the newest folder in {2} holds a copy of the log too.', '<code>acr-backup-&lt;date&gt;.log</code>', '<code>acr-backup</code>', path(PATHS.crashes))}</p></li>
    <li>${t("<b>The game's save</b>, {0}, in {1}", '<code>PlayerDataSaveSlot.sav</code>', path(PATHS.saves))}
      <p>${t('For anything about times, DRIVE, the weather, a Rally Weekend, leagues, 1V1s and cups.')}</p></li>
    <li>${t("<b>ACR Daily's own files</b>, in {0}", path(PATHS.app))}
      <p>${t("The newest few files in {0} (the game's save as it was before each DRIVE), {1} and {2} (where AUTO stopped), and {3} (runs waiting for the game's official time).", path(PATHS.backups), '<code>autodrive-last.txt</code>', '<code>autodrive-last.jpg</code>', '<code>awaiting.json</code>')}</p></li>
  </ol>

  <h2>${t('Your reports')}</h2>
  <div class="tablewrap"><table class="mine" id="mine"></table></div>
  </div>`, `
  var LATEST=${JSON.stringify(latest)},MAXF=${REPORT.maxFiles},MAXB=${REPORT.maxFileBytes};
  var AREA_NAMES=${JSON.stringify(AN).replace(/</g, '\\u003c')};
  var ST={'new':${tq('Sent')},'seen':${tq('Being looked at')},'needs-info':${tq('Needs more from you')},'pr':${tq('Fix on the way')},'fixed':${tq('Fixed')},'closed':${tq('Closed')}};
  var KIND={screenshot:${tq('screenshot')},log:${tq('log')},save:${tq('save')},other:${tq('other')}};
  var FILES=[];
  [].forEach.call(document.querySelectorAll('[data-copy]'),function(b){b.onclick=function(){var t=b.getAttribute('data-copy');
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){b.textContent=${tq('Copied')};setTimeout(function(){b.textContent=${tq('Copy')}},1500)},
      function(){window.prompt(${tq('Copy this:')},t)})}});
  var q=new URLSearchParams(location.search),v=q.get('v');
  $('ver').value=v&&/^v?[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}$/.test(v)?v.replace('v',''):LATEST;
  if(q.get('area')&&AREA_NAMES[q.get('area')])$('area').value=q.get('area');

  function ext(n){var p=String(n||'').toLowerCase().split('.');return p.length>1?p.pop():''}
  function kindOf(f){var e=ext(f.name);if((f.type||'').indexOf('image/')===0||['png','jpg','jpeg','webp','bmp','gif'].indexOf(e)>=0)return 'screenshot';
    if(['log','txt'].indexOf(e)>=0)return 'log';if(e==='sav')return 'save';return 'other'}
  function size(n){return n>=1e6?(n/1e6).toFixed(1)+' MB':Math.max(1,Math.round(n/1e3))+' KB'}
  function addFiles(list){for(var i=0;i<list.length;i++){var f=list[i];if(FILES.length>=MAXF){msg('fm',F(${tq('{0} files at most.')},MAXF));break}
      if(f.size>300e6){msg('fm',F(${tq('{0} is too big.')},f.name));continue}FILES.push({file:f,kind:kindOf(f)})}drawFiles()}
  function drawFiles(){var u=$('files');u.innerHTML='';FILES.forEach(function(x,i){var li=el('li'),s=el('select');
      ['screenshot','log','save','other'].forEach(function(k){var o=el('option',null,KIND[k]);o.value=k;if(k===x.kind)o.selected=true;s.appendChild(o)});
      s.onchange=function(){x.kind=s.value};var rm=el('button','linkbtn',${tq('remove')});rm.type='button';rm.onclick=function(){FILES.splice(i,1);drawFiles()};
      add(li,el('span','nm',x.file.name),el('span','muted',size(x.file.size)),s,rm);u.appendChild(li)})}
  var d=$('drop');d.onclick=function(e){if(e.target===d||e.target.parentNode===d)$('pick').click()};
  $('pick').onchange=function(){addFiles(this.files);this.value=''};
  d.ondragover=function(e){e.preventDefault();d.classList.add('on')};d.ondragleave=function(){d.classList.remove('on')};
  d.ondrop=function(e){e.preventDefault();d.classList.remove('on');addFiles(e.dataTransfer.files)};
  document.addEventListener('paste',function(e){if($('f').hidden)return;var it=(e.clipboardData||{}).items||[],got=[];
    for(var i=0;i<it.length;i++)if(it[i].kind==='file'){var f=it[i].getAsFile();if(f){var n=new Date().toISOString().slice(0,19).split(':').join('-');
      got.push(new File([f],'screenshot-'+n+'-'+(i+1)+'.'+(ext(f.name)||'png'),{type:f.type}))}}
    if(got.length){e.preventDefault();addFiles(got)}});

  // packing: pictures as JPEG (smaller each try until they fit), the rest gzipped (a log keeps its end if it must)
  function packImage(f){return createImageBitmap(f).then(function(bm){var tries=[[1920,.85],[1600,.75],[1280,.7],[1024,.6]];
    function go(k){var t=tries[k],s=Math.min(1,t[0]/Math.max(bm.width,bm.height)),c=document.createElement('canvas');
      c.width=Math.max(1,Math.round(bm.width*s));c.height=Math.max(1,Math.round(bm.height*s));c.getContext('2d').drawImage(bm,0,0,c.width,c.height);
      return new Promise(function(res){c.toBlob(res,'image/jpeg',t[1])}).then(function(b){return b.size<=MAXB||k===tries.length-1?{blob:b}:go(k+1)})}
    // (a screenshot of menus is often smaller as it came, and sharper: then it goes as it is)
    return go(0).then(function(p){return ['image/png','image/jpeg','image/webp'].indexOf(f.type)>=0&&f.size<=MAXB&&f.size<=p.blob.size?{blob:f}:p})},function(){throw new Error(${tq('this picture could not be read: save it as PNG or JPEG')})})}
  function gz(b){if(!window.CompressionStream)return Promise.reject(new Error(${tq('this browser cannot pack files: try Chrome, Edge or Firefox')}));
    return new Response(b.stream().pipeThrough(new CompressionStream('gzip'))).blob()}
  function packOther(f,isLog){var keep=isLog?[Infinity,16e6,8e6,4e6,2e6]:[Infinity];
    function go(k){var part=f.size>keep[k]?f.slice(f.size-keep[k]):f;return gz(part).then(function(b){
      return b.size<=MAXB||k===keep.length-1?{blob:b,cut:part.size<f.size}:go(k+1)})}
    return go(0)}
  function sendFile(id,x){return (x.kind==='screenshot'?packImage(x.file):packOther(x.file,x.kind==='log')).then(function(p){
      if(p.blob.size>MAXB)throw new Error(${tq('too big even packed')});
      return fetch('/api/reports/'+id+'/files?kind='+encodeURIComponent(x.kind)+'&name='+encodeURIComponent(x.file.name)+'&size='+x.file.size,
        {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream'},body:p.blob})
      .then(function(r){return r.json().catch(function(){return{}}).then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return p.cut})})})}

  $('send').onclick=function(){var b=$('send'),body={area:$('area').value,appVersion:$('ver').value.trim().replace(/^v/,''),title:$('title').value,
      body:$('body').value,eventUrl:$('ev').value,happened:$('when').value,system:$('sys').value};
    if(!body.area){msg('m',${tq('Pick where it happened.')});return}
    b.disabled=true;msg('m',${tq('Sending...')},true);
    api('/api/reports',body).then(function(r){var id=r.id,failed=[],cut=[];
      return FILES.reduce(function(p,x){return p.then(function(){msg('m',F(${tq('Packing and sending {0}...')},x.file.name),true);
          return sendFile(id,x).then(function(c){if(c)cut.push(x.file.name)},function(e){failed.push(x.file.name+' ('+e.message+')')})})},Promise.resolve())
        .then(function(){FILES=[];drawFiles();['title','body','ev','when','sys'].forEach(function(k){$(k).value=''});
          msg('m',(failed.length?F(${tq('Thanks! Report #{0} is in, without {1}: attach it to a new report, or send it on Discord.')},id,failed.join(', ')):F(${tq('Thanks! Report #{0} is in.')},id))+
            (cut.length?' '+F(${tq('(The end of {0} was kept: it was long.)')},cut.join(', ')):''),!failed.length);loadMine()})},
      function(e){msg('m',e.message)}).then(function(){b.disabled=false})};

  function loadMine(){return api('/api/reports/mine').then(function(j){var t=$('mine');t.innerHTML='';var h=el('tr');
      add(h,el('th',null,'#'),el('th',null,${tq('Sent')}),el('th',null,${tq('Report')}),el('th',null,${tq('Where')}),el('th',null,${tq('Status')}));t.appendChild(h);
      if(!j.reports.length){var tr=el('tr'),td=el('td','empty',${tq('None yet.')});td.colSpan=5;tr.appendChild(td);t.appendChild(tr);return}
      j.reports.forEach(function(r){var tr=el('tr'),w=el('td');tr.id='r'+r.id;add(w,el('div',null,r.title));
        if(r.note)w.appendChild(el('div','nt',r.note));
        if(r.prUrl){var a=el('a',null,${tq('The fix on GitHub')});a.href=r.prUrl;a.target='_blank';a.rel='noopener';add(w,el('div','nt'),a)}
        add(tr,el('td','muted','#'+r.id),el('td','muted',when(r.created)),w,el('td','muted',AREA_NAMES[r.area]||r.area),
          add(el('td'),el('span','st '+r.status,ST[r.status]||r.status)));t.appendChild(tr)});
      if(location.hash){var x=document.getElementById(location.hash.slice(1));if(x)x.scrollIntoView()}},function(e){msg('m',e.message)})}

  account().then(function(me){if(!me){$('signin').appendChild(add(el('p','note'),${tq('Sign in with Steam to send a report, so we can tell you when it is fixed.')}+' '));
      $('signin').appendChild(steamBtn(${tq('Sign in with Steam')}));$('mine').parentNode.previousElementSibling.hidden=true;return}
    $('who').textContent=F(${tq('Sending as {0}.')},me.name);$('f').hidden=false;loadMine()});
  `, env);
}
