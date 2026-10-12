// The shop: the looks bought with credits (src/shop.js): a colour, a badge, a frame. A section of /credits
// (src/creditspage.js; /shop goes there): its style, its HTML and its script, which keeps to itself (SHOP.load();
// SHOP.onChange, if set, runs after a buy or a change: the page's balance and history).

export const SHOP_CSS = `<style>
.looks{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}
.look{background:var(--panel);border:1px solid var(--line);padding:14px;display:flex;flex-direction:column;gap:10px}
.look.worn{border-color:var(--good)}
.look .pv{height:52px;display:flex;align-items:center;justify-content:center;font:700 22px/1 'Barlow Condensed',sans-serif;text-transform:uppercase}
.look .pv.emoji{font-size:34px}
.look .nm{font:600 14px/1.2 Barlow,sans-serif}
.look .row{justify-content:space-between}
.look .btn{padding:7px 10px;font-size:12px}
.preview{display:flex;flex-wrap:wrap;gap:28px;align-items:center;margin-top:14px;background:var(--panel);border:1px solid var(--line);padding:16px 18px}
.pvrow{display:flex;align-items:center;gap:12px;font:600 16px/1 Barlow,sans-serif}
.pvrow .pos{font:600 18px/1 'Barlow Condensed',sans-serif;color:var(--acc)}
.pvrow .tm{font:700 19px/1 'Barlow Condensed',sans-serif;margin-left:18px}
.pvmap{display:flex;align-items:center;gap:8px;font:600 13px/1 Barlow,sans-serif}
.took{font-size:12px}
.shop h3{margin-top:24px}
/* a daily of your own (src/shop.js DAILY_SET) */
.dset{background:var(--panel);border:1px solid #FFD60A55;padding:16px 18px}
.dset .f{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:0 14px}
.dset input[type=date]{width:100%;background:#0E0E10;border:1px solid var(--line2);color:var(--fg);font:15px/1.3 Barlow,sans-serif;padding:8px 10px;color-scheme:dark}
.dset .go{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:16px}
.dset .mine{font:600 15px/1.4 Barlow,sans-serif;margin:0 0 4px}
</style>`;

export const SHOP_HTML = `
  <h2 id="shop">Shop</h2><div class="shop">
  <p class="note">Colours, badges and frames for your name. Buy once, keep forever. Looks only.</p>
  <div class="msg" id="shm"></div><div class="preview" id="preview"></div>
  <h3>Colours</h3><p class="note" style="margin:-6px 0 12px">Your name on the timing sheets, and your dot on the live map.</p><div class="looks" id="sh-color"></div>
  <h3>Badges</h3><p class="note" style="margin:-6px 0 12px">By your name on the timing sheets and the live map.</p><div class="looks" id="sh-badge"></div>
  <h3>Frames</h3><p class="note" style="margin:-6px 0 12px">Round your picture on the live map.</p><div class="looks" id="sh-frame"></div>
  <h3>A daily of your own</h3><p class="note" style="margin:-6px 0 12px">Pick the stage, car, weather and time of a day's free daily (SS1),
  at least a week ahead. Your name goes on it. One at a time.</p><div class="dset" id="sh-daily"></div></div>`;

export const SHOP_JS = `
  var SHOP=(function(){var S=null,NS='http://www.w3.org/2000/svg',self={load:load,onChange:null};
  function paint(e,it){if(it&&it.grad){e.style.backgroundImage='linear-gradient(90deg,'+it.grad.join(',')+')';e.style.webkitBackgroundClip='text';
    e.style.backgroundClip='text';e.style.color='transparent'}else if(it&&it.color)e.style.color=it.color}
  function sv(t,a){var e=document.createElementNS(NS,t);for(var k in a)e.setAttribute(k,a[k]);return e}
  // a driver on the live map: the picture in a circle, ringed in the colour (or the frame)
  function dot(colour,frame,avatar){var s=sv('svg',{width:34,height:34,viewBox:'-17 -17 34 34'});
    var ring=sv('circle',{r:13,fill:colour||'#5BA8FF',stroke:frame?frame.ring:(colour||'#5BA8FF'),'stroke-width':frame?frame.width:1.5});
    if(frame&&frame.dash)ring.setAttribute('stroke-dasharray','3 2');s.appendChild(ring);
    if(avatar){var cp=sv('clipPath',{id:'pc'+Math.random().toString(36).slice(2)});cp.appendChild(sv('circle',{r:11}));s.appendChild(cp);
      var im=sv('image',{x:-11,y:-11,width:22,height:22,'clip-path':'url(#'+cp.id+')',preserveAspectRatio:'xMidYMid slice'});im.setAttribute('href',avatar);s.appendChild(im)}
    return s}
  function item(id){for(var i=0;i<S.items.length;i++)if(S.items[i].id===id)return S.items[i];return null}
  function preview(){var p=$('preview');p.innerHTML='';var w=S.worn||{},c=item(w.color),b=item(w.badge),f=item(w.frame);
    var name=ME?ME.name:'Your name';
    var r=el('div','pvrow');r.appendChild(el('span','pos','1'));var n=el('span',null,name);paint(n,c);r.appendChild(n);
    if(b)r.appendChild(el('span',null,b.badge));r.appendChild(el('span','tm','5:02.417'));p.appendChild(r);
    var m=el('div','pvmap');m.appendChild(dot(c&&c.color,f,ME&&ME.avatar));var mn=el('span',null,(b?b.badge+' ':'')+name);mn.style.color=c?c.color:'#5BA8FF';m.appendChild(mn);
    p.appendChild(m);p.appendChild(el('span','muted took',ME?'How you look now':'Sign in to see yourself'))}
  function card(it){var w=S.worn||{},worn=w[it.kind]===it.id,k=el('div','look'+(worn?' worn':''));
    var pv=el('div','pv'+(it.kind==='badge'?' emoji':''));
    if(it.kind==='color'){var t=el('span',null,ME?ME.name:'Driver');paint(t,it);pv.appendChild(t)}
    else if(it.kind==='badge')pv.textContent=it.badge;
    else pv.appendChild(dot('#2B2B31',it,ME&&ME.avatar));
    k.appendChild(pv);k.appendChild(el('div','nm',it.name));
    var row=el('div','row');row.appendChild(cr(it.price));
    if(!S.signedIn||!S.enabled){}
    else if(worn){var off=el('button','btn ghost','Take off');off.onclick=function(){go('/api/shop/wear',{kind:it.kind,item:null},off)};row.appendChild(off)}
    else if(it.owned){var wb=el('button','btn','Wear');wb.onclick=function(){go('/api/shop/wear',{kind:it.kind,item:it.id},wb)};row.appendChild(wb)}
    else{var bb=el('button','btn','Buy');bb.disabled=(S.balance||0)<it.price;bb.title=bb.disabled?'Not enough credits yet':'';
      bb.onclick=function(){if(!confirm('Buy '+it.name+' for '+it.price+' credits? It is yours for good.'))return;go('/api/shop/buy',{item:it.id},bb)};row.appendChild(bb)}
    k.appendChild(row);return k}
  function go(path,body,b){b.disabled=true;api(path,body).then(function(){msg('shm','');load();if(self.onChange)self.onChange()},function(e){b.disabled=false;msg('shm',e.message)})}
  // a daily of your own: mine (changed for free until its week comes), or the form to set one
  function daily(d){var box=$('sh-daily');box.innerHTML='';if(!d)return;
    // mine: listed (a fixed one comes up on its day); the form changes the one not fixed yet, or sets a new one
    var price=cr(d.price.toLocaleString('en-GB')),mine=d.mine||[],cur=mine.filter(function(x){return x.editable})[0]||null;
    function nm(list,id,key){var x=list.filter(function(i){return i[key||'id']===id})[0];return x?(x.label||x.name):id}
    mine.forEach(function(x){add(box,el('p','mine','Your daily: '+x.date+' · SS'+x.slot+' · '+nm(d.tracks,x.track,'track')+' · '+x.car+' · '+
      nm(d.weathers,x.weather)+' · '+nm(d.times,x.time)+(x.editable?'':' · fixed')))});
    if(!S.signedIn||!S.enabled){add(box,add(el('p','note'),'Costs ',price,'.'));return}
    var f=el('div','f');box.appendChild(f);
    var di=el('input');di.type='date';di.min=d.from;di.max=d.to;di.value=cur?cur.date:d.from;di.disabled=!!cur;field(f,'Day (UTC)',di);
    function sel(label,items,val,txt,cur0){var s=el('select');items.forEach(function(i){var o=el('option',null,txt(i));o.value=val(i);o.selected=val(i)===cur0;s.appendChild(o)});field(f,label,s);return s}
    var ts=sel('Stage',d.tracks,function(t){return t.track},function(t){return t.rally+' · '+t.name},cur&&cur.track);
    var cs=sel('Car',d.cars,function(c){return c.name},function(c){return c.name+' · '+c.cls},cur&&cur.car);
    var ws=sel('Weather',d.weathers,function(w){return w.id},function(w){return w.label},cur?cur.weather:'Clear');
    var tm=sel('Time of day',d.times,function(t){return t.id},function(t){return t.label},cur?cur.time:'midday');
    var go=el('div','go'),b=el('button','btn');go.appendChild(b);box.appendChild(go);
    if(cur)b.textContent='Save changes';else{add(b,'Set it for ',price);b.disabled=(S.balance||0)<d.price;if(b.disabled)add(go,el('span','muted','You have '+(S.balance||0).toLocaleString('en-GB')+'.'))}
    var m=el('div','msg');m.id='dsm';box.appendChild(m);
    b.onclick=function(){var body={date:di.value,track:ts.value,car:cs.value,weather:ws.value,time:tm.value};
      if(!cur&&!confirm('Set the '+body.date+' free daily for '+d.price.toLocaleString('en-GB')+' credits? You can change it until a week before.'))return;
      b.disabled=true;api('/api/shop/daily',body).then(function(){msg('shm',cur?'Saved.':'Your daily is set: '+body.date+'.',true);load();if(self.onChange)self.onChange()},
        function(e){b.disabled=false;msg('dsm',e.message)})}}
  function field(p,label,node){var l=el('label');add(l,el('span',null,label),node);p.appendChild(l);return l}
  function render(s){S=s;if(!s.enabled)msg('shm','The shop opens with credits.');
    preview();
    ['color','badge','frame'].forEach(function(kind){var box=$('sh-'+kind);box.innerHTML='';s.items.filter(function(i){return i.kind===kind}).forEach(function(i){box.appendChild(card(i))})});
    daily(s.daily)}
  function load(){return api('/api/shop').then(render,function(e){msg('shm',e.message)})}
  return self})();
`;
