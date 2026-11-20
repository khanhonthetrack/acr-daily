// A long list on the website a page of 30 at a time (the user, 20 Nov 2026: "top 30, then a page for every 30 entries:
// with 90 entries scrolling takes time"): the timing sheets, the time trial's boards, a league's standings and drivers,
// an event's results, the teams, the liveries. The list is built as before; paginate() then shows one page of its rows
// and puts the page buttons under it, named by the places they hold (1–30, 31–60 ...), so no words to translate.
// Each list's page is kept by its key while the page is open: a board drawn again every minute stays on its page.
// Put into every page's script by leaguepages.js shell() (JS) and the home page (site.js).

export const PAGE_SIZE = 30;

export const PAGER_CSS = `
.pager{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0 6px}
.pager button{background:none;border:1px solid var(--line2);color:var(--fg2);font:600 14px/1 'Barlow Condensed',sans-serif;
  letter-spacing:.04em;padding:8px 10px;min-width:36px;border-radius:3px;cursor:pointer}
.pager button:hover:not(:disabled){color:var(--fg);border-color:var(--fg3)}
.pager button[aria-current="page"]{color:var(--fg);border-color:var(--acc);background:rgba(227,6,19,.12)}
.pager button:disabled{opacity:.35;cursor:default}
.pager .gap{color:var(--fg3);padding:0 2px}`;

/** paginate(box, key, anchor, per, onpage): box's children (table rows, cards) shown `per` (30) at a time, a row marked
 *  data-nopage always; the page buttons go right after anchor (box by default: for a table's rows, its table). key: the
 *  list's name, its page kept while the page is open. box.pageTo(row) turns to the page that row is on (my row).
 *  onpage(): after each page is shown (what needs the shown rows' sizes). */
export const PAGER_JS = () => `
  var PAGER={};
  function paginate(box,key,anchor,per,onpage){per=per||${PAGE_SIZE};anchor=anchor||box;
    var nx=anchor.nextElementSibling;if(nx&&nx.className==='pager')nx.parentNode.removeChild(nx);
    var rows=[].filter.call(box.children,function(r){return !r.hasAttribute('data-nopage')});
    var n=Math.ceil(rows.length/per);box.pageTo=function(){};
    if(n<2){rows.forEach(function(r){r.style.display=''});if(onpage)onpage();return}
    var nav=document.createElement('nav');nav.className='pager';
    anchor.parentNode.insertBefore(nav,anchor.nextSibling);
    var p=Math.min(PAGER[key]||0,n-1);
    function go(q,jump){p=PAGER[key]=q;rows.forEach(function(r,i){r.style.display=Math.floor(i/per)===p?'':'none'});draw();
      if(onpage)onpage();
      if(jump&&anchor.getBoundingClientRect().top<0)anchor.scrollIntoView({block:'start'})}
    function btn(label,q,cur){var b=document.createElement('button');b.type='button';b.textContent=label;
      if(cur)b.setAttribute('aria-current','page');if(q==null)b.disabled=true;else b.onclick=function(){go(q,true)};nav.appendChild(b)}
    function draw(){nav.innerHTML='';btn('\\u2039',p>0?p-1:null);var last=-1;
      for(var i=0;i<n;i++){if(i>1&&i<n-2&&Math.abs(i-p)>1)continue;   // (many pages: the first two, the last two, mine and its neighbours)
        if(last>=0&&i>last+1){var g=document.createElement('span');g.className='gap';g.textContent='\\u2026';nav.appendChild(g)}
        btn((i*per+1)+'\\u2013'+Math.min(rows.length,(i+1)*per),i,i===p);last=i}
      btn('\\u203a',p<n-1?p+1:null)}
    box.pageTo=function(r){var i=rows.indexOf(r);if(i>=0&&Math.floor(i/per)!==p)go(Math.floor(i/per))};
    go(p)}
`;
