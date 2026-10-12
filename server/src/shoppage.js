// /shop: the looks bought with credits (src/shop.js): a colour, a badge, a frame. In the leagues' look
// (src/leaguepages.js shell, its cr() puts the coin by an amount), signed in with the website's Steam sign-in.

import { shell } from './leaguepages.js';

const CSS = `<style>
.looks{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}
.look{background:var(--panel);border:1px solid var(--line);padding:14px;display:flex;flex-direction:column;gap:10px}
.look.worn{border-color:var(--good)}
.look .pv{height:52px;display:flex;align-items:center;justify-content:center;font:700 22px/1 'Barlow Condensed',sans-serif;text-transform:uppercase}
.look .pv.emoji{font-size:34px}
.look .nm{font:600 14px/1.2 Barlow,sans-serif}
.look .row{justify-content:space-between}
.look .btn{padding:7px 10px;font-size:12px}
.preview{display:flex;flex-wrap:wrap;gap:28px;align-items:center;margin-top:18px;background:var(--panel);border:1px solid var(--line);padding:16px 18px}
.pvrow{display:flex;align-items:center;gap:12px;font:600 16px/1 Barlow,sans-serif}
.pvrow .pos{font:600 18px/1 'Barlow Condensed',sans-serif;color:var(--acc)}
.pvrow .tm{font:700 19px/1 'Barlow Condensed',sans-serif;margin-left:18px}
.pvmap{display:flex;align-items:center;gap:8px;font:600 13px/1 Barlow,sans-serif}
.took{font-size:12px}
</style>`;

export function shopPage(env) {
  return shell('Shop · ACR Daily', `${CSS}
  <div class="top"><div class="kick"><a href="/credits">Credits</a> · prototype</div><h1>Shop</h1>
  <p class="note">Colours, badges and frames for your name. Buy once, keep forever. Looks only.</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:14px" id="acts"></div><div class="msg" id="m"></div>
  <div class="preview" id="preview"></div></div>
  <h2>Colours</h2><p class="note" style="margin:-6px 0 12px">Your name on the timing sheets, and your dot on the live map.</p><div class="looks" id="color"></div>
  <h2>Badges</h2><p class="note" style="margin:-6px 0 12px">By your name on the timing sheets and the live map.</p><div class="looks" id="badge"></div>
  <h2>Frames</h2><p class="note" style="margin:-6px 0 12px">Round your picture on the live map.</p><div class="looks" id="frame"></div>`, `
  var S=null;
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function paint(e,it){if(it&&it.grad){e.style.backgroundImage='linear-gradient(90deg,'+it.grad.join(',')+')';e.style.webkitBackgroundClip='text';
    e.style.backgroundClip='text';e.style.color='transparent'}else if(it&&it.color)e.style.color=it.color}
  var NS='http://www.w3.org/2000/svg';
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
  function go(path,body,b){b.disabled=true;api(path,body).then(function(){msg('m','');load()},function(e){b.disabled=false;msg('m',e.message)})}
  function render(s){S=s;$('facts').innerHTML='';$('acts').innerHTML='';
    if(!s.enabled)msg('m','The shop opens with credits.');
    if(!s.signedIn)$('acts').appendChild(steamBtn('Sign in with Steam to shop'));
    else fact('Balance',cr(s.balance));
    preview();
    ['color','badge','frame'].forEach(function(kind){var box=$(kind);box.innerHTML='';s.items.filter(function(i){return i.kind===kind}).forEach(function(i){box.appendChild(card(i))})})}
  function load(){return api('/api/shop').then(render,function(e){msg('m',e.message)})}
  account().then(load);
  `, env);
}
