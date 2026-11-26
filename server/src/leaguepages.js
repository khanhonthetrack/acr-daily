// The league pages: /rallies (every championship and rally, create, a private rally's code), /l/:id (a championship:
// join, or ask to join a private one; its staff answer the requests), /l/:id/new and /e/:id/edit (the event builder),
// /e/:id (an event: itinerary and standings; a private rally's asks for its code), /join/:code (a private rally's
// invite). Static shells; the data comes from the API (src/leagues.js), signed in with the website's Steam sign-in
// (/login, a session cookie).

import { coinSvg, FAVICON } from './logo.js';
import { BANNER, POINTS_PRESETS, POWER_PRESET } from './leagues.js';
import { TEAM } from './drivers.js';
import { CHAMP_METHODS } from './teamscore.js';
import { SCORING_JS } from './teampages.js';
import { downloadUrl } from './release.js';
import { BONUS_CSS, BONUS_JS } from './bonus.js';
import { TM_JS } from './tmtext.js';
import { I18N_JS, LANG_CSS, langTag, N_, t, tq, tqp, ts } from './i18n.js';
import { HEADER_CSS, siteHeader } from './header.js';
import { EVENT_LIVE_CSS, EVENT_LIVE_JS } from './eventlive.js';
import { escMeta, metaTags } from './pagemeta.js';
import { PAGER_CSS, PAGER_JS } from './pager.js';

const CSS = `
:root{--bg:#0A0A0B;--panel:#111113;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#85858E;--acc:#E30613;--acct:#FF4655;--bad:#FF453A;--slow:#FF9F0A;--good:#30D158;--steam:#171A21}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px 64px}
/* Rallies (0033): a championship (a league) in the leagues' blue, a rally (one event, anyone's) in pink */
.k-champ{--k:#5BA8FF}.k-rally{--k:#FF7AC6}.k-off{--k:var(--acc)}
/* a list as a server browser (the rallies, the championships, the cups): a row a line, no banners, no descriptions,
   each kind's colour down its left; a column sorts when its heading is pressed (they were cards, a banner and a
   description each: messy). A narrower screen leaves out the .mid columns; a tablet or a phone has no headings, each row
   its name and a line of what it is under it, each count with its words (.sbw, not .sbv: "12 drivers") */
.sb{margin-top:6px;border-top:1px solid var(--line2)}.sbgap{margin-top:18px}
.sbh,.sbr{display:flex;align-items:stretch;border-left:3px solid var(--k,transparent)}
.sbh{border-bottom:1px solid var(--line2);border-left-color:transparent}
.sbh .g,.sbl{flex:1;min-width:0;display:grid;grid-template-columns:var(--cols);gap:0 16px;align-items:center;padding:0 12px 0 13px}
.sbh .sbc{background:none;border:0;padding:0;min-height:38px;text-align:left;color:var(--fg3);font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;cursor:pointer}
.sbh .sbc:hover,.sbh .sbc[aria-sort]{color:var(--fg)}
.sbh .sbc[aria-sort=ascending]:after{content:' \\25B2';font-size:8px;vertical-align:1px}.sbh .sbc[aria-sort=descending]:after{content:' \\25BC';font-size:8px;vertical-align:1px}
.sbr{border-bottom:1px solid var(--line)}
.sbr:hover{background:var(--panel)}
.sbl{text-decoration:none;min-height:48px;padding-top:8px;padding-bottom:8px}
.sbc{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px;color:var(--fg2)}
.sbc.sb-num,.sbc.sb-st{text-align:right;font-variant-numeric:tabular-nums}
.sbh .sbc.sb-num,.sbh .sbc.sb-st{text-align:right}
.sbl .sbc.sb-nm{display:flex;align-items:center;gap:8px;color:var(--fg);font:600 16px/1.25 Barlow,sans-serif}
.sbl .sb-nm .sbt{min-width:0;overflow:hidden;text-overflow:ellipsis}.sbc.sb-nm .badge{flex:none}
.sbr:hover .sbc.sb-nm .sbt{color:var(--acct)}
.sbc .sbw{display:none}
.sbx{flex:none;width:var(--act,0);display:flex;align-items:center;justify-content:flex-end;padding-right:12px}
@media (max-width:1080px){.sbh .g,.sbl{grid-template-columns:var(--colsm)}.sb .sb-mid{display:none}}
@media (max-width:860px){.sbh{display:none}
  .sbl{display:block;padding:10px 10px 10px 12px;font-size:13px;line-height:1.6}
  .sbc{display:inline;white-space:normal;overflow:visible;font-size:13px;text-align:left!important}
  .sbc:empty{display:none!important}
  .sbl .sbc.sb-nm{display:flex;flex-wrap:wrap;gap:4px 8px;margin-bottom:3px}.sbl .sbc.sb-nm .sbt{overflow:visible;overflow-wrap:anywhere}
  .sbc.sb-nm~.sbc:before{content:'\\00B7';margin:0 6px;color:var(--fg3)}.sbc.sb-nm+.sbc:before{content:none}
  .sbc .sbv{display:none}.sbc .sbw{display:inline}
  .sbx{width:auto;padding-left:6px}}
.kindtag{font:700 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;margin-bottom:5px}
.kindtag.champ{color:#5BA8FF}.kindtag.rally{color:#FF7AC6}.legend{display:flex;gap:18px;margin-top:16px}
.badge.org{border-color:#5BA8FF;color:#5BA8FF}.legend .kindtag{margin:0}.legend .kindtag:before{content:'';display:inline-block;width:10px;height:10px;margin-right:7px;background:currentColor;vertical-align:-1px}
/* a count of unread messages (the inbox's threads) */
.unread{display:inline-block;min-width:17px;margin-left:6px;padding:2px 4px;background:var(--acc);color:#fff;font:700 11px/1 Barlow,sans-serif;letter-spacing:0;text-align:center;vertical-align:1px}
.unread[hidden]{display:none}
.linkbtn{background:none;border:0;color:var(--fg3);font:inherit;cursor:pointer;padding:0;text-decoration:underline}
.linkbtn:hover{color:var(--fg)}
.steam{display:inline-flex;align-items:center;gap:8px;background:var(--steam);color:#fff;border:1px solid #2A475E;padding:8px 14px;font:600 13px/1 Barlow,sans-serif;text-decoration:none;white-space:nowrap}
.steam:hover{background:#2A475E}
.top{margin-top:28px;padding-top:20px;border-top:2px solid var(--fg)}
.kick{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acct,#FF4655);text-transform:uppercase}
.kick a{text-decoration:none}
.kick a:hover{text-decoration:underline}
h1{font:700 clamp(36px,6vw,64px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;margin-top:12px;overflow-wrap:anywhere}
h2{font:700 24px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em;margin:36px 0 14px}
h3{font:600 15px/1.2 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.1em;color:var(--fg2);margin:18px 0 8px}
.note{color:var(--fg2);font-size:14px;margin:12px 0 0;max-width:760px}
.about{color:var(--fg);margin-top:14px;max-width:760px;white-space:pre-line}
.muted{color:var(--fg3)}
.k{font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3)}
.facts{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:18px}
.facts div{min-width:120px}
.facts b{display:block;font:600 18px/1.2 'Barlow Condensed',sans-serif;margin-top:5px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.chip{border:1px solid var(--line2);padding:4px 9px;font:600 12px/1 Barlow,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:var(--fg2)}
.badge{display:inline-block;padding:3px 7px;font:700 11px/1 Barlow,sans-serif;letter-spacing:.1em;text-transform:uppercase;border:1px solid var(--line2);color:var(--fg2);vertical-align:2px}
.badge.open{background:var(--acc);border-color:var(--acc);color:#fff}
.badge.upcoming{border-color:var(--fg2);color:var(--fg)}
.badge.private{border-color:var(--slow);color:var(--slow)}.badge.private svg{vertical-align:-1px}
.badge.ask{border-color:#5BA8FF;color:#5BA8FF}
.badge.official{background:var(--acc);border-color:var(--acc);color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);padding:18px}
.card h3{margin-top:0}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.item{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid var(--line);text-decoration:none}
.item:hover .t{color:var(--acct,#FF4655)}
.item .t{font:700 20px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase}
.item .s{color:var(--fg2);font-size:13px;margin-top:4px}
.item .r{text-align:right;color:var(--fg2);font-size:13px;white-space:nowrap}
.empty{color:var(--fg3);padding:16px 0;border-bottom:1px solid var(--line)}
label{display:block;margin:12px 0 0}
label>span{display:block;font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3);margin-bottom:6px}
input[type=text],input[type=number],input[type=time],input[type=datetime-local],select,textarea{width:100%;background:#0E0E10;border:1px solid var(--line2);color:var(--fg);font:15px/1.3 Barlow,sans-serif;padding:9px 10px;border-radius:0;color-scheme:dark}
textarea{min-height:76px;resize:vertical}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--fg2)}
.radio{display:flex;gap:6px;flex-wrap:wrap}
.radio label{margin:0}
.radio input{position:absolute;opacity:0}
.radio span{display:block;border:1px solid var(--line2);padding:8px 12px;font:600 13px/1 Barlow,sans-serif;color:var(--fg2);cursor:pointer;margin:0;letter-spacing:.02em;text-transform:none}
.radio input:checked+span{border-color:var(--acc);color:var(--fg);background:#1A0B0C}
.btn{display:inline-block;background:var(--acc);color:#fff;border:1px solid var(--acc);padding:10px 18px;font:700 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;text-decoration:none;white-space:nowrap}
.btn:hover{filter:brightness(1.12)}
.btn.ghost{background:none;color:var(--fg);border-color:var(--line2)}
.btn.ghost:hover{border-color:var(--fg2)}
.btn.small{padding:6px 10px;font-size:12px}
.btn.danger{background:none;color:var(--bad);border-color:#5a1f1c}
.btn:disabled{opacity:.45;cursor:default;filter:none}
.cr{white-space:nowrap}
.coin{display:inline-block;width:.95em;height:.95em;margin-left:.22em;vertical-align:-.12em}
.msg{margin-top:10px;font-size:14px;min-height:1px}
.msg.bad{color:var(--bad)}
.msg.good{color:var(--good)}
.code{font:700 26px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tablewrap.more{box-shadow:inset -22px 0 18px -16px rgba(255,255,255,.22)}.tablewrap.less.more{box-shadow:inset -22px 0 18px -16px rgba(255,255,255,.22),inset 22px 0 18px -16px rgba(255,255,255,.12)}
.tablewrap.less:not(.more){box-shadow:inset 22px 0 18px -16px rgba(255,255,255,.12)}
.swipe{font:600 11px/1 Barlow,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--fg2);margin:4px 0 8px}.swipe[hidden]{display:none}
table.phone th:first-child,table.phone td.pos{position:sticky;left:0;z-index:1;background:var(--bg);min-width:34px;width:34px;padding-right:6px}
table.phone th:nth-child(2),table.phone td.drv{position:sticky;left:34px;z-index:1;background:var(--bg);max-width:42vw;overflow:hidden;text-overflow:ellipsis}
table.phone tr.me td.pos,table.phone tr.me td.drv{background:#2A0A0E}
table.phone td.tot small.why{max-width:none;min-width:8.5em}
table{border-collapse:collapse;width:100%;font-feature-settings:'tnum'}
th{font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3);padding:8px 10px 10px 0;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line2)}
th.r,td.r{text-align:right}
td{padding:10px 10px 10px 0;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:middle}
td.pos{width:40px;font:600 18px/1 'Barlow Condensed',sans-serif;color:var(--fg2)}
tr.p1 td.pos{color:var(--acct,#FF4655)}
td.drv{font-weight:500}
td.drv a.dname{text-decoration:none}td.drv a.dname:hover{text-decoration:underline}
.cmt{white-space:normal;font:italic 400 12.5px/1.35 Barlow,sans-serif;color:var(--fg2);margin-top:3px;max-width:520px;overflow-wrap:anywhere}   /* a driver's comment on the run (src/comments.js) */
.cmt .only{font-style:normal;color:var(--fg3)}   /* my own, before the week is over: only I see it */
td.tot{font:700 19px/1 'Barlow Condensed',sans-serif}
td.t{font:600 15px/1 'Barlow Condensed',sans-serif}
td.t small{display:block;font:500 11px/1.2 Barlow,sans-serif;color:var(--fg3);margin-top:3px}
td.t small.pen{color:var(--slow)}
td.muted small{display:block;font:500 11px/1.2 Barlow,sans-serif;color:var(--fg3);margin-top:3px}
td.tot small.why{display:block;font:500 11px/1.25 Barlow,sans-serif;color:var(--fg3);margin-top:3px;white-space:normal;max-width:200px;margin-left:auto}
td.t.w{color:var(--acct,#FF4655)}
.dnf{color:var(--bad);font:600 13px/1 Barlow,sans-serif;letter-spacing:.04em}
.run{color:var(--slow);font:600 13px/1 Barlow,sans-serif}
tr.me td.drv{color:var(--acct,#FF4655)}tr.me td{background:rgba(227,6,19,.12)}   /* my row, signed in (as the dailies' sheets) */
.flagimg{width:18px;height:12px;margin-right:8px;vertical-align:-1px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
.teamtag{font:700 1.02em/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:6px;white-space:nowrap}
.itin td{white-space:normal}
.itin tr.day td{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--fg);padding-top:20px}
.itin tr.sp td{color:var(--fg3);font-size:13px}
.steps{counter-reset:s;margin-top:10px;padding:0;list-style:none}
.steps li{counter-increment:s;padding:6px 0 6px 30px;position:relative;color:var(--fg2)}
.steps li:before{content:counter(s);position:absolute;left:0;top:6px;width:20px;height:20px;border:1px solid var(--line2);text-align:center;font:600 12px/18px Barlow,sans-serif;color:var(--fg)}
.steps b{color:var(--fg);font-weight:600}
.builder .day{border:1px solid var(--line);background:var(--panel);padding:14px 14px 10px;margin-top:12px}
.builder .dayhead{display:flex;justify-content:space-between;align-items:center}
.builder .dayhead b{font:700 18px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.06em}
.builder .sprow{color:var(--fg3);font-size:13px;padding:10px 0 6px;border-bottom:1px solid var(--line)}
.builder .st{display:grid;grid-template-columns:44px minmax(160px,2.4fr) 92px minmax(120px,1.3fr) auto auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}
.builder .st .no{font:700 16px/1 'Barlow Condensed',sans-serif;color:var(--fg2)}
.builder .st .sp{font-size:12px;color:var(--fg2);display:flex;align-items:center;gap:5px;margin:0;white-space:nowrap}
.builder .st .tools{display:flex;gap:4px}
.builder .st .tools button{background:none;border:1px solid var(--line2);color:var(--fg2);width:28px;height:28px;cursor:pointer}
.builder .st .tools button:hover{color:var(--fg);border-color:var(--fg2)}
.builder .between{font-size:12px;color:var(--fg3);padding:4px 0 0 52px}
.imp{border:1px solid var(--line2);background:var(--panel);margin:18px 0 6px}
.imp>summary{cursor:pointer;padding:14px 16px;font:700 16px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;text-transform:uppercase;list-style:none}
.imp>summary::-webkit-details-marker{display:none}
.imp>summary:before{content:'+';display:inline-block;width:18px;color:var(--acct)}
.imp[open]>summary:before{content:'\\2013'}
.imp .impbody{padding:0 16px 16px}
.imp .dl{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.imp .drop{display:block;border:1px dashed var(--line2);padding:20px 14px;text-align:center;color:var(--fg2);cursor:pointer;margin-top:4px}
.imp .drop:hover,.imp .drop.over{border-color:var(--acct);color:var(--fg)}
.imp .drop input{display:none}
.imp table{margin-top:10px}.imp td{white-space:normal;vertical-align:top;line-height:1.35}
.imp td.rw{width:54px;font:700 17px/1.2 'Barlow Condensed',sans-serif;color:var(--fg2)}
.imp td.cl{width:120px;color:var(--fg2)}
.imp td small{display:block;color:var(--fg3);margin-top:3px}
.imp .imphead{font:700 16px/1.3 Barlow,sans-serif;margin:18px 0 4px}.imp .imphead.bad{color:var(--bad)}.imp .imphead.good{color:var(--good)}
.imp .warns{margin:10px 0 0;padding-left:18px;color:var(--slow);font-size:13px}
.sheetdl{display:inline-flex;gap:8px;flex-wrap:wrap;vertical-align:middle}
.imp .acts{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.sum{margin-top:14px;color:var(--fg2)}
.danger-zone{margin-top:40px;padding-top:16px;border-top:1px solid var(--line)}
.banner{display:block;width:100%;aspect-ratio:3/1;object-fit:cover;margin-top:24px;background:var(--panel);border:1px solid var(--line)}
.banner[hidden]{display:none}
.banner:not([hidden])+.top{margin-top:0;border-top:0}
.item .grow{flex:1;min-width:0}
.bannerset{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-top:6px}
.bannerset .prev{width:300px;max-width:100%;aspect-ratio:3/1;object-fit:cover;border:1px solid var(--line2);background:#0E0E10}
.bannerset .none{width:300px;max-width:100%;aspect-ratio:3/1;border:1px dashed var(--line2);display:flex;align-items:center;justify-content:center;color:var(--fg3);font-size:13px}
.filebtn{position:relative;overflow:hidden}
.filebtn input{position:absolute;inset:0;opacity:0;cursor:pointer}
.tabs{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.tab{background:none;border:1px solid var(--line2);color:var(--fg2);padding:7px 12px;font:600 13px/1 Barlow,sans-serif;cursor:pointer}
.tab:hover{color:var(--fg);border-color:var(--fg2)}
.tab.on{border-color:var(--acc);color:var(--fg);background:#1A0B0C}
/* a team's colour (league teams), drivers ticked (nominations) */
.colors{display:flex;gap:6px;flex-wrap:wrap}
.colors label{margin:0;position:relative}
.colors input{position:absolute;opacity:0}
.colors span{display:block;width:30px;height:30px;border:2px solid var(--line2);cursor:pointer;margin:0}
.colors input:checked+span{border-color:var(--fg)}
.ticks{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px}
.ticks label{display:flex;gap:6px;align-items:center;margin:0;text-transform:none;letter-spacing:0;font:500 14px Barlow,sans-serif;color:var(--fg)}
.ticks input{width:auto}
/* the standings within a class or a division (Overall, Rally4, PRO...) */
.tabs.sub{margin:10px 0 8px}.tabs.sub .tab{padding:5px 10px;font-size:12px}
.builder .classes{margin-top:8px}
.builder .classes label{display:flex;align-items:center;gap:8px;margin:6px 0 0;font-size:14px;color:var(--fg2)}
.builder .classes b{color:var(--fg);font-weight:600}
select.div{width:auto;padding:5px 8px;font-size:13px}
td.dropped{color:var(--fg3);text-decoration:line-through}
td small.ps{display:block;font:500 11px/1.2 Barlow,sans-serif;color:var(--good);margin-top:3px}
td.t small.st{color:var(--bad)}
td.t small.st.back{color:var(--good)}
.badge.admin{border-color:var(--fg2);color:var(--fg)}
.badge.owner{background:var(--acc);border-color:var(--acc);color:#fff}
.badge.season{border-color:var(--line2);color:var(--fg2)}
.decision{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:11px 0;border-bottom:1px solid var(--line)}
.decision b{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:8px}
.decision .bad{color:var(--bad)}
.decision .good{color:var(--good)}
.stewform{display:grid;grid-template-columns:minmax(160px,1.4fr) 120px 110px minmax(180px,2fr) auto;gap:8px;align-items:end;margin-top:12px}
.stewform label{margin:0}
.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
@media (max-width:760px){.stewform{grid-template-columns:1fr 1fr}}
/* a list's rows on a phone: the name across the width, what it is under it, the drivers and the time left on their own
   line (the name had a third of a 360 px screen, one to four words a line, and the page went sideways: a UI review) */
@media (max-width:560px){.item{flex-wrap:wrap;align-items:flex-start;gap:8px 12px}
  .item .grow{flex:1 1 180px;min-width:0}.item .t{overflow-wrap:anywhere}
  .item .s{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
  .item .r{flex:1 1 100%;display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;text-align:left;white-space:normal}
  .item .r br{display:none}
  }
/* a finger's room on a touch screen: 44 px at least (WCAG's target size) */
@media (pointer:coarse){.tab,.btn.small,.linkbtn,.radio span{min-height:44px;display:inline-flex;align-items:center}.tabs.sub .tab{padding:5px 12px}}
@media (max-width:760px){.wrap{padding:0 16px 48px}.twocol{grid-template-columns:1fr}
  .builder .st{grid-template-columns:34px 1fr 108px;}.builder .st .w{grid-column:2/4}.builder .st .sp{grid-column:2/3}.builder .st .tools{grid-column:3/4;justify-content:flex-end}}
${PAGER_CSS}
`;

// helpers every page's script uses: $, el, api (JSON, the session cookie), times, sign-in state in the header
// the pages' own helpers, in the language the page is made in (src/i18n.js); a long list 30 at a time (src/pager.js)
const JS = () => `
${I18N_JS()}
${PAGER_JS()}
function $(id){return document.getElementById(id)}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function add(p){for(var i=1;i<arguments.length;i++){var c=arguments[i];if(c==null)continue;if(Array.isArray(c)){add.apply(null,[p].concat(c));continue}p.appendChild(typeof c==='string'?document.createTextNode(c):c)}return p}
function api(path,body){var o={credentials:'same-origin',cache:'no-store',headers:{}};
  if(body!==undefined){o.method='POST';o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  return fetch(path,o).then(function(r){return r.json().catch(function(){return{}}).then(function(j){if(!r.ok){var e=new Error(j.error||('error '+r.status));e.status=r.status;e.body=j;throw e}return j})})}
function signin(){return '/login?next='+encodeURIComponent(location.pathname+location.search)}
function steamBtn(text){var a=el('a','steam',text||${tq('Sign in with Steam')});a.href=signin();return a}
function ms(t){if(t==null)return '';var s=Math.floor(t/1000),m=Math.floor(s/60);return m+':'+String(s%60).padStart(2,'0')+'.'+String(t%1000).padStart(3,'0')}
function gap(t){return t?'+'+(t<60000?(t/1000).toFixed(3):ms(t)):''}
function pen(t){return t?'+'+Math.round(t/1000)+' s':''}
function secs(t){var a=Math.abs(t)/1000;return (t<0?'−':'+')+(a%1?a.toFixed(1):a)+' s'}
function when(t){return FDATETIME(t)}
function left(t){var d=t-Date.now();if(d<=0)return '';var h=Math.floor(d/3600000),m=Math.floor(d%3600000/60000);
  return h>=48?P(${tqp('{0} day', '{0} days')},Math.floor(h/24)):h>=1?F(${tq('{0} h {1} min')},h,m):F(${tq('{0} min')},m)}
function km(m){return m==null?${tq('hidden')}:(m/1000).toFixed(1)+' km'}
// links to download events as a sheet (src/eventsheet.js): base = '/api/events/<id>/sheet' or '/api/leagues/<id>/sheet'; the dates in the visitor's time zone
function sheetLinks(base,cls){var tz='';try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||''}catch(e){}var q=tz?'tz='+encodeURIComponent(tz):'',w=el('span','sheetdl');
  [[${tq('Excel')},'.xlsx?'+q,''],[${tq('CSV')},'.csv?'+q,' ghost'],[${tq('CSV with semicolons')},'.csv?sep=;&'+q,' ghost']].forEach(function(x){
    var a=el('a','btn small'+x[2]+(cls||''),x[0]);a.href=base+x[1];a.setAttribute('download','');w.appendChild(a);w.appendChild(document.createTextNode(' '))});return w}
// a hidden event (src/hidden.js): what it keeps until it ends -> "Stage names, weather and times are hidden until it ends." or ''
var HIDDEN_NOTE=${JSON.stringify({ s: t('Stage names are hidden until it ends.'), w: t('The weather is hidden until it ends.'),
    t: t('The times are hidden until it ends.'), sw: t('Stage names and weather are hidden until it ends.'),
    st: t('Stage names and times are hidden until it ends.'), wt: t('Weather and times are hidden until it ends.'),
    swt: t('Stage names, weather and times are hidden until it ends.') }).replace(/</g, '\\u003c')};
function hiddenNote(h){if(!h)return '';var k=(h.stages?'s':'')+(h.weather?'w':'')+(h.times?'t':'');return k?HIDDEN_NOTE[k]:''}
function hid(v){return v==null?${tq('Hidden')}:v}
// how a season scores, in words (src/leagues.js describeSeason, in the page's language)
function seasonAbout(s){if(!s||!s.points)return (s&&s.about)||'';var t=s.points.table,o=F(${tq('{0} points for P1–P{1}')},t.join('-'),t.length);
  if(s.points.finisher)o+=F(${tq(', then {0} for every finisher')},s.points.finisher);
  if(s.power&&s.power.length)o+=F(${tq("; Power Stage (each event's last stage): {0} bonus points")},s.power.join('-'));
  if(s.drop)o+=P(${tqp("; each driver's worst round is dropped", "; each driver's {0} worst rounds are dropped")},s.drop);
  return o+${tq('. A DNF or DSQ scores nothing.')}}
var COIN=${JSON.stringify(coinSvg())};   // an amount of credits (the credits pages): the coin by it
${BONUS_JS()}function cr(n,cls){var s=el('span','cr'+(cls?' '+cls:''),String(n));s.insertAdjacentHTML('beforeend',COIN);return s}
function flag(p,c){if(!c)return;var i=el('img','flagimg');i.src='https://flagcdn.com/w40/'+c+'.png';i.alt=c.toUpperCase();p.appendChild(i)}
${TM_JS}
// a driver's team tag before their name: x.team {tag, color, tagFmt} (src/drivers.js), or x.look.tag {text, color, fmt}
function teamTag(p,x){var t=x&&(x.team||(x.look&&x.look.tag));if(t&&(t.tag||t.text))tmInto(p,t.tagFmt||t.fmt,t.tag||t.text,t.color,'teamtag');return p}
// a phone's width (the standings' columns: the totals first) and a table wider than its place: a shade on the side that
// has more and a line saying it scrolls, until it is scrolled (scrollHint(wrap))
var NARROW=window.matchMedia?matchMedia('(max-width:760px)'):{matches:false};
function scrollHint(w,text){if(!w)return;var hint=w.previousElementSibling&&w.previousElementSibling.classList.contains('swipe')?w.previousElementSibling:null;
  if(!hint){hint=el('div','swipe',(text||${tq('Swipe the table sideways for each stage')})+'  →');w.parentNode.insertBefore(hint,w)}
  function mark(){var more=w.scrollWidth>w.clientWidth+2;w.classList.toggle('more',more&&w.scrollLeft+w.clientWidth<w.scrollWidth-2);w.classList.toggle('less',w.scrollLeft>2);hint.hidden=!more||w.scrollLeft>2}
  if(!w._hinted){w._hinted=true;w.addEventListener('scroll',mark,{passive:true});window.addEventListener('resize',mark)}mark()}
// a driver's name, to their driver page (as on every other board: the standings had it as plain words, a UI review)
function driverName(p,x){var a=el(x.steamId?'a':'span','dname',x.name||${tq('a driver')});if(x.steamId){a.href='/d/'+x.steamId;a.title=${tq('Driver page')}}p.appendChild(a);return p}
function msg(id,text,good){var m=$(id);if(m){m.textContent=text||'';m.className='msg'+(text?(good?' good':' bad'):'')}}
function showBanner(img,url){if(url){img.src=url;img.hidden=false}else{img.removeAttribute('src');img.hidden=true}}
function officialBadge(){var b=el('span','badge official',${tq('official')});b.title=${tq('Run by ACR Daily')};return b}
// a private championship (drivers ask to join) or rally (its code lets a driver in): a lock, its word beside it (0043)
var LOCK='<svg viewBox="0 0 12 14" width="9" height="11" aria-hidden="true"><path d="M3 6.5V4.2a3 3 0 0 1 6 0v2.3" fill="none" stroke="currentColor" stroke-width="1.7"/><rect x="1" y="6" width="10" height="7.5" rx="1.2" fill="currentColor"/></svg>';
function lockBadge(title){var b=el('span','badge private');b.innerHTML=LOCK;add(b,' '+${tq('private')});if(title)b.title=title;return b}
// a list as a server browser (the rallies, the championships, the cups): a row a line, sorted by a column when its
// heading is pressed (again: the other way). cols: [{k, h: its heading, w: its grid width, cls: 'nm' (the name), 'num'
// or 'st' (right), mid: left out on a narrower screen, desc: high first}]; rows: [{href, cls (its kind's colour),
// v: {k: what sorts}, c: {k: a node or text}, x: a button beside it, outside its link}]; act: the buttons' width
function browser(box,cols,rows,empty,act){box.innerHTML='';if(!rows.length){box.appendChild(el('div','empty',empty));return}
  var sb=el('div','sb'),hd=el('div','sbh'),g=el('div','g'),body=el('div'),st={k:null,d:1};
  function w(cs){return cs.map(function(c){return c.w}).join(' ')}
  sb.style.setProperty('--cols',w(cols));sb.style.setProperty('--colsm',w(cols.filter(function(c){return !c.mid})));if(act)sb.style.setProperty('--act',act);
  function cls(c){return 'sbc'+(c.cls?' sb-'+c.cls:'')+(c.mid?' sb-mid':'')}
  cols.forEach(function(c){var b=el('button',cls(c),c.h);b.type='button';b.onclick=function(){st.d=st.k===c.k?-st.d:c.desc?-1:1;st.k=c.k;
    [].forEach.call(g.children,function(x){x.removeAttribute('aria-sort')});b.setAttribute('aria-sort',st.d>0?'ascending':'descending');draw()};g.appendChild(b)});
  add(hd,g,act?el('div','sbx'):null);
  function cmp(x,y){return typeof x==='string'?x.localeCompare(y):x<y?-1:x>y?1:0}
  function draw(){body.innerHTML='';var rs=rows.slice();
    if(st.k)rs.sort(function(a,b){var x=a.v[st.k],y=b.v[st.k];return x==null?(y==null?0:1):y==null?-1:cmp(x,y)*st.d});
    rs.forEach(function(r){var row=el('div','sbr'+(r.cls?' '+r.cls:'')),a=el('a','sbl');a.href=r.href;
      cols.forEach(function(c){var d=el('div',cls(c)),x=r.c[c.k];if(x!=null&&x!=='')add(d,x);if(c.cls==='nm')d.title=r.v[c.k];a.appendChild(d)});
      add(row,a);if(act){var s=el('div','sbx');if(r.x)s.appendChild(r.x);row.appendChild(s)}body.appendChild(row)})}
  draw();add(sb,hd,body);box.appendChild(sb)}
// in a list's column: what it shows under its heading (n), and on a phone, where there are no headings, in words (w)
function cell(n,w){var s=el('span');add(s,add(el('span','sbv'),n),add(el('span','sbw'),w));return s}
// a name in a list, its badges after it
function nameCell(name,badges){var s=el('span');s.style.display='contents';add(s,el('span','sbt',name),badges);return s}
var ME=null;
// who is signed in: ME, and the header's account (src/header.js headerMe); today's bonus claimed (src/bonus.js)
function account(){return api('/api/me').then(function(me){if(!me.signedIn)throw new Error('signed out');ME=me;headerMe(me);
    if(me.credits)claimBonus($('crhost'),me.credits);return me})
  .catch(function(){ME=null;headerMe(null);return null})}
`;

export function shell(title, body, script, env = {}, meta = {}) {
  // meta (src/pagemeta.js describe): the page's own title (a name: plain text), a line and a picture for a shared link
  const own = meta.title ? escMeta(meta.title) + ' · ACR Daily' : title;
  return `<!doctype html>
<html lang="${langTag()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${own}</title>
${metaTags({ ...meta, title: meta.title ? meta.title + ' · ACR Daily' : title.replace(/&amp;/g, '&'), site: env.SITE_URL || '' })}
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>${CSS}${HEADER_CSS}${BONUS_CSS}${LANG_CSS}</style>
</head>
<body>
${siteHeader(env)}
<main class="wrap">${body}</main>
<script>
${JS()}
(function(){
${script}
})();
</script>
</body>
</html>`;
}

// ------------------------------------------------------------------ a page that isn't there (404)
// Any address that isn't a page (it answered {"error":"not found"} in JSON), and an event, championship, cup, driver
// or team that doesn't exist (they answered 200, their sections empty): what it is, and the way back (a UI review,
// Nov 2026). The API's addresses still answer in JSON.
const MISSING = { page: N_('Page not found'), event: N_('No such event'), league: N_('No such championship'), cup: N_('No such cup'),
  driver: N_('No such driver'), team: N_('No such team') };
export function notFoundPage(env, what = 'page') {
  const head = t(MISSING[what] || MISSING.page);
  return shell(head + ' · ACR Daily', `
  <div class="top"><div class="kick">404</div><h1>${head}</h1>
  <p class="note">${t('The link may be wrong, or what it led to was deleted.')}</p>
  <div class="row" style="margin-top:22px"><a class="btn" href="/">${t("Today's stages")}</a>
  <a class="btn ghost" href="/rallies">${t('Rallies')}</a><a class="btn ghost" href="/tt">${t('Time trial')}</a>
  <a class="btn ghost" href="/cups">${t('Cups')}</a></div></div>`, 'account();', env, { title: '', description: '' });
}

// ------------------------------------------------------------------ /leagues
export function leaguesPage(env) {
  // Rallies (0033): the championships (leagues: rounds, seasons; made by Community organizers) and the rallies (one
  // event anyone makes), each kind in its colour; CREATE A RALLY on its own page (/rallies/new)
  // every championship and rally is listed, public or private (0043): a private championship is asked to join on its
  // page, a private rally needs its code (typed in below, or on its page)
  return shell(t('Rallies') + ' · ACR Daily', `
  <div class="top"><div class="kick">ACR Daily</div><h1>${t('Rallies')}</h1>
  <p class="note">${t("Drive a rally anyone made, or the rounds of a championship. One go per driver, the game's times count. Every rally is in everyone's app, under RALLIES: a private one needs its code.")}</p>
  <div class="row" style="margin-top:16px" id="topb"></div>
  <div class="legend"><span class="kindtag champ">${t('Championship')}</span><span class="kindtag rally">${t('Rally')}</span></div></div>
  <h2>${t('Yours')}</h2><div id="mine"></div>
  <h2>${t('Open rallies')}</h2><div id="ral"></div>
  <h2>${t('Championships')}</h2><div id="pub"></div>
  <div class="grid" style="margin-top:22px">
    <div class="card" id="champcard"><h3>${t('Create a championship')}</h3><div id="create"></div></div>
    <div class="card"><h3>${t('Private rally code')}</h3>
      <label><span>${t('Code')}</span><input type="text" id="code" placeholder="ABCD-EFGH" maxlength="12" autocomplete="off"></label>
      <div class="row" style="margin-top:12px"><button class="btn" id="joinb">${t('Enter code')}</button></div><div class="msg" id="joinmsg"></div></div>
  </div>`, `
  // the lists (a UI review): a server browser each, a row a line, without banners or descriptions (on the rally's or
  // championship's own page); a rally's: its rally, car, stages, maker, drivers and time left, sorted soonest to close
  var RCOLS=[{k:'name',h:${tq('Name')},w:'minmax(0,2.4fr)',cls:'nm'},{k:'rally',h:${tq('Rally')},w:'minmax(0,1.1fr)'},
    {k:'car',h:${tq('Car')},w:'minmax(0,1.4fr)'},{k:'stages',h:${tq('Stages')},w:'64px',cls:'num',desc:1},
    {k:'by',h:${tq('Organizer')},w:'minmax(0,1fr)',mid:1},{k:'drivers',h:${tq('Drivers')},w:'70px',cls:'num',desc:1},{k:'when',h:${tq('Status')},w:'184px',cls:'st'}];
  var CCOLS=[{k:'name',h:${tq('Name')},w:'minmax(0,2.4fr)',cls:'nm'},{k:'by',h:${tq('Organizer')},w:'minmax(0,1.2fr)'},
    {k:'events',h:${tq('Events')},w:'70px',cls:'num',desc:1},{k:'drivers',h:${tq('Drivers')},w:'70px',cls:'num',desc:1},{k:'when',h:${tq('Status')},w:'176px',cls:'st'}];
  function rallyRow(x){var car=x.car||x.carClass;
    return {href:'/e/'+x.id,cls:'k-rally',
      v:{name:x.name,rally:TD(x.rally),car:car,stages:x.stages,by:x.owner,drivers:x.drivers,when:x.status==='open'?x.closes:x.status==='upcoming'?1e14+x.opens:2e14},
      c:{name:nameCell(x.name,x.public?null:lockBadge(${tq('Private: drivers need its code')})),rally:TD(x.rally),car:car,
        stages:cell(String(x.stages),P(${tqp('{0} stage', '{0} stages')},x.stages)),by:cell(x.owner,F(${tq('by {0}')},x.owner)),
        drivers:cell(String(x.drivers),P(${tqp('{0} driver', '{0} drivers')},x.drivers)),
        when:x.status==='open'?el('span','badge open',F(${tq('{0} left')},left(x.closes))):x.status==='upcoming'?${tq('Opens')}+' '+when(x.opens):${tq('finished')}}}}
  var ASKED={};   // my requests to join (0043): championship id -> pending / declined
  function champRow(l){var b=[];if(l.official)b.push(officialBadge());if(!l.public)b.push(lockBadge(${tq('Private: drivers ask to join')}));
    if(ASKED[l.id]==='pending')b.push(el('span','badge ask',${tq('asked')}));
    if(l.applications)b.push(el('span','badge open',P(${tqp('{0} request', '{0} requests')},l.applications)));
    return {href:'/l/'+l.id,cls:'k-champ',
      v:{name:l.name,by:l.owner||'',events:l.events,drivers:l.members,when:l.openEvents?-l.openEvents:l.nextOpens||9e15},
      c:{name:nameCell(l.name,b),by:l.owner?cell(l.owner,F(${tq('by {0}')},l.owner)):'',
        events:cell(String(l.events),P(${tqp('{0} event', '{0} events')},l.events)),drivers:cell(String(l.members),P(${tqp('{0} driver', '{0} drivers')},l.members)),
        when:l.openEvents?el('span','badge open',F(${tq('{0} open')},l.openEvents)):l.nextOpens?F(${tq('next: {0}')},when(l.nextOpens)):''}}}
  function rallies(box,xs,empty){browser(box,RCOLS,xs.map(rallyRow),empty)}
  function champs(box,ls,empty){browser(box,CCOLS,ls.map(champRow),empty)}
  function create(me,org){var c=$('create');c.innerHTML='';
    if(!me){add(c,el('p','muted',${tq('Sign in with Steam first.')}));c.appendChild(steamBtn());return}
    if(!org){add(c,el('p','muted',${tq('Championships are run by Community organizers, a rank the admin gives: ask on Discord. Anyone can create a rally.')}));return}
    c.innerHTML='<label><span>${ts('Name')}</span><input type="text" id="ln" maxlength="60" placeholder="${ts('e.g. Friday Night Rally Club')}"></label>'+
      '<label><span>${ts('About (optional)')}</span><textarea id="la" maxlength="600" placeholder="${ts('Who it is for, how often you run events, your Discord...')}"></textarea></label>'+
      '<p class="note">${ts('You can add a banner afterwards.')}</p>'+
      '<label><span>${ts('Who can join')}</span></label><div class="radio"><label><input type="radio" name="lp" value="1" checked><span>${ts('Public: anyone can join')}</span></label>'+
      '<label><input type="radio" name="lp" value="0"><span>${ts('Private: drivers ask to join, you accept them')}</span></label></div>'+
      '<div class="row" style="margin-top:14px"><button class="btn" id="lc">${ts('Create a championship')}</button></div><div class="msg" id="lcmsg"></div>';
    $('lc').onclick=function(){var b=this;b.disabled=true;
      api('/api/leagues',{name:$('ln').value,about:$('la').value,public:document.querySelector('input[name=lp]:checked').value==='1'})
        .then(function(j){location.href='/l/'+j.id},function(e){b.disabled=false;msg('lcmsg',e.message)})}}
  function load(me){api('/api/leagues').then(function(j){
    ASKED={};(j.applied||[]).forEach(function(a){ASKED[a.id]=a.status});
    rallies($('ral'),j.rallies,${tq('No open rallies. Create one: every driver sees it in their app.')});
    // every championship, public and private (0043): ACR Daily's own first, then the most drivers
    var all=j.public.concat(j.private||[]).sort(function(a,b){return (b.official?1:0)-(a.official?1:0)||b.members-a.members});
    champs($('pub'),all,${tq('No championships yet.')});
    // mine: my rallies, then my championships, a list each (their columns differ)
    if(me){var m=$('mine');m.innerHTML='';
      if(!j.myRallies.length&&!j.mine.length)m.appendChild(el('div','empty',${tq('Nothing yet: create a rally, or join a championship below.')}));
      else{if(j.myRallies.length)rallies(m.appendChild(el('div')),j.myRallies);if(j.mine.length)champs(m.appendChild(el('div','sbgap')),j.mine)}}
    var tb=$('topb');tb.innerHTML='';var cr=el('a','btn',${tq('Create a rally')});cr.href='/rallies/new';tb.appendChild(cr);
    if(j.organizer){var cc=el('a','btn ghost',${tq('Create a championship')});cc.href='#champcard';tb.appendChild(cc)}
    create(me,j.organizer)})}
  account().then(function(me){
    if(!me){$('mine').innerHTML='';add($('mine'),el('div','empty',${tq('Sign in with Steam to see your rallies and championships, or create a rally.')}+' '),steamBtn());
      $('joinb').onclick=function(){location.href=signin()};load(null);return}
    // a private rally's code; a championship's old one: its page (where a driver joins or asks to join, 0043)
    $('joinb').onclick=function(){var b=this;b.disabled=true;
      api('/api/leagues/join',{code:$('code').value}).then(function(j){location.href=j.eventId?'/e/'+j.eventId:'/l/'+j.id},function(e){
        if(e.status===410&&e.body&&e.body.id){location.href='/l/'+e.body.id;return}b.disabled=false;msg('joinmsg',e.message)})};
    load(me)});
  `, env);
}

// ------------------------------------------------------------------ /join/:code
// A private rally's invite: its code in the link (a championship's old link opens its page: src/index.js, 0043)
export function joinPage(code, env) {
  return shell(t('Join a rally') + ' · ACR Daily', `
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick">${t('Invitation')}</div><h1 id="name">${t('Rally')}</h1><p class="about" id="about"></p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:22px" id="act"></div><div class="msg" id="m"></div></div>`, `
  var code=${JSON.stringify(code)};
  account().then(function(me){
    api('/api/leagues/code?code='+encodeURIComponent(code)).then(function(l){
      if(l.kind==='league'){location.replace('/l/'+l.id);return}
      $('name').textContent=l.name;$('about').textContent=l.about||'';document.title=l.name+' · ACR Daily';showBanner($('banner'),l.banner);
      if(l.official)add($('kick'),' ',officialBadge());
      $('facts').innerHTML='';var f=el('div');add(f,el('span','k',${tq('Drivers')}),el('b',null,String(l.members)));$('facts').appendChild(f);
      var a=$('act');
      var rk=l.kind==='event',to=rk?'/e/'+l.eventId:'/l/'+l.id;if(rk){$('kick').innerHTML='';add($('kick'),el('span','kindtag rally',${tq('Rally')}))}
      if(l.member){var g=el('a','btn',rk?${tq('Open the rally')}:${tq('Open the championship')});g.href=to;a.appendChild(g);msg('m',rk?${tq('You are in this rally already.')}:${tq('You are in this championship already.')},true);return}
      if(!me){a.appendChild(steamBtn(${tq('Sign in with Steam to join')}));return}
      var b=el('button','btn',F(${tq('Join {0}')},l.name));b.onclick=function(){b.disabled=true;
        api('/api/leagues/join',{code:code}).then(function(){location.href=to},function(e){b.disabled=false;msg('m',e.message)})};
      a.appendChild(b)},
    function(e){$('name').textContent=${tq('Invite link not valid')};msg('m',e.message)})});
  `, env);
}

// ------------------------------------------------------------------ /l/:id
export function leaguePage(id, env, meta = {}) {
  return shell(t('Championship') + ' · ACR Daily', `
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick">${t('Championship')}</div><h1 id="name"></h1><p class="about" id="about"></p>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="am"></div></div>
  <div id="reqbox"></div><div id="ownerbox"></div>
  <style>${EVENT_LIVE_CSS}</style><div id="evlive"></div>
  <h2>${t('Events')}</h2><div id="evs"></div>
  <h2>${t('Championship')}</h2><div id="seasons"></div>
  <div id="teamsec"></div>
  <h2>${t('Drivers')}</h2><div id="members"></div><div class="msg" id="mm"></div><div id="bans"></div>`, `
  var id=${JSON.stringify(id)},q=new URLSearchParams(location.search),L=null,SEL=null,GSEL='',LMS={};
  if(NARROW.addEventListener)NARROW.addEventListener('change',function(){if(L)seasons(L)});
  ${EVENT_LIVE_JS()}
  ${TEAMS_JS()}
  var PRESETS=${JSON.stringify(Object.fromEntries(Object.entries(POINTS_PRESETS).map(([k, v]) => [k, { ...v, label: t(v.label) }])))},POWER=${JSON.stringify(POWER_PRESET)};
  function load(){return api('/api/leagues/'+id).then(render,function(e){
    $('name').textContent=e.status===404?${tq('No such championship')}:${tq('Championship')};msg('am',e.message)})}
  function evById(eid){return L.events.filter(function(e){return e.id===eid})[0]}
  function seasonById(sid){return L.seasons.filter(function(s){return s.id===sid})[0]}
  function render(l){L=l;document.title=l.name+' · ACR Daily';$('name').textContent=l.name;$('about').textContent=l.about||'';showBanner($('banner'),l.banner);
    $('kick').textContent=(l.owner.name?F(l.public?${tq('Public championship · {0} · run by {1}')}:${tq('Private championship · {0} · run by {1}')},P(${tqp('{0} driver', '{0} drivers')},l.members.length),l.owner.name):
      F(l.public?${tq('Public championship · {0}')}:${tq('Private championship · {0}')},P(${tqp('{0} driver', '{0} drivers')},l.members.length)));
    if(l.official)$('kick').insertBefore(officialBadge(),$('kick').firstChild).insertAdjacentText('afterend',' ');
    var a=$('acts');a.innerHTML='';
    if(!l.me.signedIn)a.appendChild(steamBtn(l.public?${tq('Sign in with Steam to join')}:${tq('Sign in with Steam to ask to join')}));
    else if(!l.me.member&&l.public){var j=el('button','btn',${tq('Join this championship')});j.onclick=function(){j.disabled=true;
      api('/api/leagues/'+id+'/join',{}).then(load,function(e){j.disabled=false;msg('am',e.message)})};a.appendChild(j)}
    else if(!l.me.member)askBox(a,l);
    else if(!l.me.owner){var lv=el('button','btn ghost small',${tq('Leave')});lv.onclick=function(){if(!confirm(F(${tq('Leave {0}?')},l.name)))return;
      api('/api/leagues/'+id+'/leave',{}).then(function(){location.href='/rallies'},function(e){msg('am',e.message)})};a.appendChild(lv)}
    if(l.me.staff){var ne=el('a','btn',${tq('New event')});ne.href='/l/'+id+'/new';a.appendChild(ne)}
    if(l.me.staff&&l.events&&l.events.length){var dd=el('span','muted',${tq('Download its events as a spreadsheet:')}+' ');a.appendChild(dd);a.appendChild(sheetLinks('/api/leagues/'+id+'/sheet'))}
    if(l.me.role==='admin')add(a,el('span','badge admin',${tq('you are an admin')}));
    requests(l);manage(l);events(l);liveMaps(l);seasons(l);teamsSec(l);members(l)}
  // a private one (0043): asked to join, with a word to its admins; asked: waiting (or taken back); declined: when again
  function askBox(a,l){var ap=l.me.application;
    if(l.me.banned){add(a,el('span','muted',${tq("You can't join this championship.")}+(l.me.banned.reason?' ('+l.me.banned.reason+')':'')));return}
    if(ap&&ap.status==='pending'){add(a,el('span','badge ask',${tq('asked')}),el('span','muted',F(${tq('You asked to join on {0}. The admins answer in your inbox.')},FDATE(ap.at))));
      var wb=el('button','btn ghost small',${tq('Take it back')});wb.onclick=function(){wb.disabled=true;
        api('/api/leagues/'+id+'/withdraw',{}).then(load,function(e){wb.disabled=false;msg('am',e.message)})};a.appendChild(wb);return}
    if(ap&&ap.status==='declined'&&ap.again>Date.now()){add(a,el('span','muted',F(${tq('Your request was declined. You can ask again from {0}.')},FDATE(ap.again))));return}
    var f=el('div');f.style.width='100%';f.style.maxWidth='560px';
    add(f,el('p','note',${tq('Private: the admins accept drivers. Ask to join, with a word to them if you like.')}));
    var ta=el('textarea');ta.maxLength=200;ta.placeholder=${tq('A word to the admins (optional)')};ta.style.marginTop='10px';ta.style.minHeight='56px';f.appendChild(ta);
    var b=el('button','btn',${tq('Ask to join')});b.style.marginTop='10px';b.onclick=function(){b.disabled=true;
      api('/api/leagues/'+id+'/apply',{message:ta.value}).then(function(){return load()},function(e){b.disabled=false;msg('am',e.message)})};
    f.appendChild(b);a.appendChild(f)}
  // ---- the requests to join, for its owner and admins to accept or decline (0043), and a driver added straight away
  function requests(l){var box=$('reqbox');box.innerHTML='';if(!l.me.staff)return;var A=l.applications||[];
    var c=el('div','card');c.style.marginTop='26px';box.appendChild(c);
    add(c,el('h3',null,${tq('Requests to join')}));
    if(!A.length)add(c,el('p','muted',l.public?${tq('Public: drivers join without asking.')}:${tq('No requests right now.')}));
    A.forEach(function(x){var it=el('div','item'),d=el('div'),tt=el('div','t');tt.style.fontSize='17px';flag(tt,x.country);driverName(tt,x);
      add(d,tt,el('div','s',FDATE(x.at)+(x.message?' · '+x.message:'')));it.appendChild(d);var act=el('div','actions');
      var ok=el('button','btn small',${tq('Accept')});ok.onclick=function(){answer(x,'accept',ok)};
      var no=el('button','btn ghost small',${tq('Decline')});no.onclick=function(){if(confirm(F(${tq('Decline {0}?')},x.name)))answer(x,'decline',no)};
      add(act,ok,no);it.appendChild(act);c.appendChild(it)});
    add(c,el('div','msg'));c.lastChild.id='rqm';
    add(c,el('h3',null,${tq('Add a driver')}));var r=el('div','row'),inp=el('input');inp.type='text';inp.placeholder=${tq('Driver name')};
    inp.style.flex='1';inp.style.width='auto';inp.style.minWidth='200px';add(r,inp);var found=el('div');add(c,r,found);var tmr=null;
    inp.oninput=function(){clearTimeout(tmr);var qv=inp.value.trim();if(qv.length<2){found.innerHTML='';return}
      tmr=setTimeout(function(){api('/api/players?q='+encodeURIComponent(qv)).then(function(j){found.innerHTML='';
        var inL={};l.members.forEach(function(m){inL[m.steamId]=1});
        j.players.forEach(function(p){var it=el('div','item'),d=el('div','t');d.style.fontSize='16px';flag(d,p.country);add(d,p.name);it.appendChild(d);
          if(inL[p.steamId])it.appendChild(el('span','muted',${tq('in it')}));
          else{var ab=el('button','btn small',${tq('Add')});ab.onclick=function(){ab.disabled=true;
            api('/api/leagues/'+id+'/add',{steamId:p.steamId}).then(function(){return load().then(function(){msg('rqm',F(${tq('{0} is in: told in their inbox.')},p.name),true)})},
              function(e){ab.disabled=false;msg('rqm',e.message)})};it.appendChild(ab)}
          found.appendChild(it)});
        if(!j.players.length)found.appendChild(el('p','muted',${tq('No driver of that name.')}))},function(e){msg('rqm',e.message)})},250)}}
  function answer(x,how,b){b.disabled=true;api('/api/leagues/'+id+'/'+how,{steamId:x.steamId}).then(function(){return load().then(function(){
    msg('rqm',how==='accept'?F(${tq('{0} is in: told in their inbox.')},x.name):F(${tq('{0} declined: told in their inbox.')},x.name),true)})},
    function(e){b.disabled=false;msg('rqm',e.message)})}
  // each open round: its drivers on its stages live, as on the dailies; a round hiding its stages, on a map only for
  // who sees them, else who is on which stage (src/eventlive.js)
  function liveMaps(l){l.events.forEach(function(e){if(LMS[e.id]||e.status!=='open')return;
    var d=el('div'),a=el('a',null,e.name);a.href='/e/'+e.id;$('evlive').appendChild(d);
    LMS[e.id]=liveMap(d,{url:'/api/events/'+e.id+'/live',title:[${tq('LIVE')},' · ',a],sat:function(no){return '/lab/map?event='+e.id+'&ss='+no},
      on:function(){var x=L&&evById(e.id);return !!x&&x.status==='open'}})})}

  // ---- its link (the owner and admins), divisions, teams, settings, banner, Discord (the owner). No invite code: every
  // championship is listed, a private one asked to join on this page (0043)
  function manage(l){var box=$('ownerbox');box.innerHTML='';if(!l.me.staff)return;
    var c=el('div','card');c.style.marginTop='26px';box.appendChild(c);
    add(c,el('h3',null,${tq('Share')}));var link=location.origin+'/l/'+id;
    var r=el('div','row');add(r,el('span','muted',link));var cp=el('button','btn ghost small',${tq('Copy link')});
    cp.onclick=function(){navigator.clipboard.writeText(link).then(function(){msg('om',F(${tq('Copied: {0}')},link),true)})};r.appendChild(cp);c.appendChild(r);
    add(c,el('div','msg'));c.lastChild.id='om';
    embedBox(c,l);
    // divisions: each its own standings; drivers are put in one under Drivers
    add(c,el('h3',null,${tq('Divisions')}),el('p','note',${tq('E.g. PRO, AM. Each division gets its own standings. Put drivers in one under Drivers. Leave empty for none.')}));
    var dr=el('div','row'),dv=el('input');dv.type='text';dv.placeholder='PRO, AM';dv.value=l.divisions.join(', ');dv.style.flex='1';dv.style.width='auto';dv.style.minWidth='200px';
    var dsv=el('button','btn small',${tq('Save divisions')});dsv.onclick=function(){var keep=dv.value.split(',').map(function(x){return x.trim().toLowerCase()});
      var gone=l.divisions.filter(function(x){return keep.indexOf(x.toLowerCase())<0&&l.members.some(function(m){return m.division===x})});
      if(gone.length&&!confirm(F(${tq('Drivers in {0} will be in no division. Go on?')},gone.join(', '))))return;
      api('/api/leagues/'+id+'/divisions',{divisions:dv.value}).then(function(){GSEL='';load()},function(e){msg('dvm',e.message)})};
    add(dr,dv,dsv);c.appendChild(dr);add(c,el('div','msg'));c.lastChild.id='dvm';
    teamSettings(c,l);
    if(!l.me.owner)return;
    add(c,el('h3',null,${tq('Championship settings')}));
    var f=el('div','twocol');f.innerHTML='<label><span>${ts('Name')}</span><input type="text" id="en" maxlength="60"></label>'+
      '<label><span>${ts('Who can join')}</span><select id="ep"><option value="1">${ts('Public: anyone can join')}</option><option value="0">${ts('Private: drivers ask to join')}</option></select></label>';
    c.appendChild(f);add(c,el('label'));c.lastChild.innerHTML='<span>${ts('About')}</span><textarea id="ea" maxlength="600"></textarea>';
    $('en').value=l.name;$('ea').value=l.about||'';$('ep').value=l.public?'1':'0';
    var sv=el('button','btn small',${tq('Save')});sv.style.marginTop='12px';sv.onclick=function(){api('/api/leagues/'+id+'/edit',{name:$('en').value,about:$('ea').value,public:$('ep').value==='1'})
      .then(function(){msg('sm',${tq('Saved.')},true);load()},function(e){msg('sm',e.message)})};c.appendChild(sv);add(c,el('div','msg'));c.lastChild.id='sm';
    bannerBox(c,l);discordBox(c,l);
    var dz=el('div','danger-zone');add(dz,el('h3',null,${tq('Delete the championship')}),el('p','note',${tq('Deletes its events, seasons and results for good.')}));
    var del=el('button','btn danger small',${tq('Delete championship')});del.style.marginTop='10px';del.onclick=function(){var t=prompt(F(${tq('Type the championship name to delete it: {0}')},l.name));if(t==null)return;
      api('/api/leagues/'+id+'/delete',{confirm:t}).then(function(){location.href='/rallies'},function(e){msg('dm',e.message)})};
    dz.appendChild(del);add(dz,el('div','msg'));dz.lastChild.id='dm';c.appendChild(dz)}
  // the banner: any wide picture, cut to 3:1 from its middle and made a 1200 x 400 JPEG here (src/leagues.js BANNER)
  function makeBanner(file){return new Promise(function(ok,no){
    if(!/^image\\/(png|jpeg|webp)$/.test(file.type))return no(new Error(${tq('a PNG, JPEG or WebP picture, please')}));
    var u=URL.createObjectURL(file),img=new Image();
    img.onerror=function(){URL.revokeObjectURL(u);no(new Error(${tq('this picture could not be read')}))};
    img.onload=function(){URL.revokeObjectURL(u);var iw=img.naturalWidth,ih=img.naturalHeight,W=1200,H=400,s=Math.max(W/iw,H/ih);
      if(s>2)return no(new Error(F(${tq('the picture is {0} x {1}: it needs to be at least 600 x 200')},iw,ih)));
      var cv=document.createElement('canvas');cv.width=W;cv.height=H;var g=cv.getContext('2d');
      g.fillStyle='#0A0A0B';g.fillRect(0,0,W,H);g.imageSmoothingQuality='high';g.drawImage(img,(W-iw*s)/2,(H-ih*s)/2,iw*s,ih*s);
      var qs=[0.86,0.78,0.7,0.6,0.5];(function next(k){cv.toBlob(function(b){
        if(!b)return no(new Error(${tq('the browser could not make the banner')}));
        if(b.size<=${BANNER.maxBytes})return ok(b);
        if(k===qs.length-1)return no(new Error(${tq('the picture stays too big: try a simpler one')}));
        next(k+1)},'image/jpeg',qs[k])})(0)};
    img.src=u})}
  function bannerBox(c,l){add(c,el('h3',null,${tq('Banner')}));
    var wrap=el('div','bannerset'),pv;
    if(l.banner){pv=el('img','prev');pv.alt='';pv.src=l.banner}else pv=el('div','none',${tq('No banner yet')});
    var side=el('div'),pick=el('span','btn ghost small filebtn',l.banner?${tq('Change picture')}:${tq('Choose a picture')});
    var fi=el('input');fi.type='file';fi.accept='image/png,image/jpeg,image/webp';pick.appendChild(fi);side.appendChild(pick);
    if(l.banner){var rm=el('button','btn ghost small',${tq('Remove')});rm.style.marginLeft='6px';rm.onclick=function(){if(!confirm(${tq('Remove the banner?')}))return;
      api('/api/leagues/'+id+'/banner',{remove:true}).then(load,function(e){msg('bm',e.message)})};side.appendChild(rm)}
    add(side,el('p','note',${tq('A wide picture, cropped to 3:1. Nothing offensive.')}));
    add(wrap,pv,side);c.appendChild(wrap);add(c,el('div','msg'));c.lastChild.id='bm';
    fi.onchange=function(){var f=fi.files&&fi.files[0];if(!f)return;msg('bm',${tq('Making the banner...')},true);
      makeBanner(f).then(function(b){msg('bm',F(${tq('Uploading ({0} KB)...')},Math.round(b.size/1000)),true);
        return fetch('/api/leagues/'+id+'/banner',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'image/jpeg'},body:b})
          .then(function(r){return r.json().catch(function(){return{}}).then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})})
      .then(function(){msg('bm','');load()},function(e){fi.value='';msg('bm',e.message)})}}
  // ---- on the organizers' own site (src/embeds.js, src/publicapi.js): an embed's code to copy, and the same as data
  function embedBox(c,l){add(c,el('h3',null,${tq('On your own site')}));
    add(c,el('p','note',${tq("Put the standings, an event's results or its live timing on your own page: copy the code into it. It keeps itself up to date.")}));
    var f=el('div','row'),what=el('select'),pick=el('select'),th=el('select');
    [['standings',${tq('Standings')}],['results',${tq('Results')}],['live',${tq('Live timing')}]].forEach(function(x){var o=el('option',null,x[1]);o.value=x[0];what.appendChild(o)});
    [['dark',${tq('Dark')}],['light',${tq('Light')}]].forEach(function(x){var o=el('option',null,x[1]);o.value=x[0];th.appendChild(o)});
    [what,pick,th].forEach(function(s){s.style.width='auto';s.style.minWidth='0'});add(f,what,pick,th);c.appendChild(f);
    var code=el('textarea');code.readOnly=true;code.rows=3;code.style.width='100%';code.style.marginTop='8px';code.style.fontFamily='ui-monospace,Consolas,monospace';code.style.fontSize='12px';
    var row=el('div','row'),cp=el('button','btn ghost small',${tq('Copy code')}),data=el('span','muted');add(row,cp,data);add(c,code,row,el('div','msg'));c.lastChild.id='emm';
    function opts(){pick.innerHTML='';var list=what.value==='standings'?(l.seasons||[]).map(function(s){return[s.id,s.name]}):(l.events||[]).map(function(e){return[e.id,e.name]});
      if(what.value==='standings'&&list.length>1)list.unshift(['',${tq('Latest season')}]);
      list.forEach(function(x){var o=el('option',null,x[1]);o.value=x[0];pick.appendChild(o)});pick.style.display=list.length?'':'none';show()}
    function show(){var site=location.origin,p,api;
      if(what.value==='standings'){p='/embed/championship/'+id+(pick.value?'?season='+pick.value:'');api='/api/v1/championships/'+id+'/standings'+(pick.value?'?season='+pick.value:'')}
      else{if(!pick.value){code.value='';data.textContent='';return}p='/embed/event/'+pick.value+(what.value==='live'?'/live':'');api='/api/v1/events/'+pick.value+(what.value==='live'?'/live':'')}
      if(th.value==='light')p+=(p.indexOf('?')<0?'?':'&')+'theme=light';
      code.value='<iframe src="'+site+p+'" width="100%" height="'+(what.value==='live'?640:560)+'" style="border:0;max-width:100%" loading="lazy" title="ACR Daily"></iframe>';
      data.innerHTML='';add(data,document.createTextNode(${tq('As data:')}+' '));var j=el('a',null,'JSON');j.href=api;j.target='_blank';add(data,j);
      if(what.value!=='live'){add(data,document.createTextNode(' · '));var cv=el('a',null,'CSV');cv.href=api+(api.indexOf('?')<0?'?':'&')+'format=csv';add(data,cv)}
      add(data,document.createTextNode(' · '));var dv=el('a',null,${tq('For developers')});dv.href='/developers';add(data,dv)}
    what.onchange=opts;pick.onchange=show;th.onchange=show;
    cp.onclick=function(){if(!code.value)return;navigator.clipboard.writeText(code.value).then(function(){msg('emm',${tq('Copied.')},true)})};
    opts()}
  function discordBox(c,l){add(c,el('h3',null,'Discord'));
    add(c,el('p','note',${tq('Posts to your Discord when an event opens, a day before it closes, and the results. Paste a channel webhook (channel settings › Integrations › Webhooks). Keep it private.')}));
    var r=el('div','row');
    if(l.discord&&l.discord.set){add(r,el('span','muted',F(${tq('Connected (webhook …{0})')},l.discord.hint)));
      var tb=el('button','btn ghost small',${tq('Send a test message')});tb.onclick=function(){tb.disabled=true;
        api('/api/leagues/'+id+'/discord',{test:true}).then(function(){tb.disabled=false;msg('dcm',${tq('Sent: have a look in the channel.')},true)},function(e){tb.disabled=false;msg('dcm',e.message)})};
      var dc=el('button','btn ghost small',${tq('Disconnect')});dc.onclick=function(){if(!confirm(${tq('Stop posting in that Discord channel?')}))return;
        api('/api/leagues/'+id+'/discord',{remove:true}).then(load,function(e){msg('dcm',e.message)})};
      add(r,tb,dc)}
    else{var inp=el('input');inp.type='text';inp.placeholder='https://discord.com/api/webhooks/…';inp.style.flex='1';inp.style.minWidth='240px';inp.style.width='auto';
      var cb=el('button','btn small',${tq('Connect')});cb.onclick=function(){cb.disabled=true;
        api('/api/leagues/'+id+'/discord',{webhook:inp.value}).then(load,function(e){cb.disabled=false;msg('dcm',e.message)})};add(r,inp,cb)}
    c.appendChild(r);add(c,el('div','msg'));c.lastChild.id='dcm'}

  // ---- events
  function evItem(e){var a=el('a','item');a.href='/e/'+e.id;var d=el('div');
    var t=el('div','t',e.name+' ');t.appendChild(el('span','badge '+e.status,e.status==='open'?${tq('open')}:e.status==='upcoming'?${tq('upcoming')}:${tq('finished')}));
    var s=e.seasonId&&seasonById(e.seasonId);
    if(e.hidden)add(t,' ',el('span','badge',${tq('hidden')}));
    add(d,t,el('div','s',(s?s.name:${tq('One-off')})+' · '+TD(e.rally)+' · '+P(${tqp('{0} stage', '{0} stages')},e.stages)+' · '+P(${tqp('{0} day', '{0} days')},e.days)+' · '+(e.lengthM==null?${tq('stages hidden')}:km(e.lengthM))+' · '+
      (e.car||(e.carClasses?e.carClasses.join(', '):F(${tq('{0} class')},e.carClass)))));
    var r=el('div','r');
    if(e.status==='open')add(r,F(${tq('closes {0}')},when(e.closes)),el('br'),F(${tq('{0} started · {1} finished')},e.entries,e.finished));
    else if(e.status==='upcoming')add(r,F(${tq('opens {0}')},when(e.opens)));
    else add(r,e.winner?F(${tq('won by {0}')},e.winner):${tq('no finishers')},el('br'),F(${tq('{0} of {1} finished')},e.finished,e.entries));
    add(a,d,r);return a}
  function events(l){var box=$('evs');box.innerHTML='';
    var groups=[['open',${tq('Open now')}],['upcoming',${tq('Coming up')}],['closed',${tq('Finished')}]],any=false;
    groups.forEach(function(g){var es=l.events.filter(function(e){return e.status===g[0]});if(g[0]==='closed')es.reverse();if(!es.length)return;any=true;
      box.appendChild(el('h3',null,g[1]));es.forEach(function(e){box.appendChild(evItem(e))})});
    if(!any)box.appendChild(el('div','empty',l.me.staff?${tq('No events yet: make the first one with NEW EVENT.')}:${tq('No events yet.')}))}
  // ---- seasons: one tab each, the one under way first shown
  function seasons(l){var box=$('seasons');box.innerHTML='';var ss=l.seasons;var nb=null;
    if(l.me.staff){nb=el('button','btn ghost small',${tq('+ New season')});nb.onclick=function(){seasonForm(null)}}
    if(!ss.length){add(box,el('div','empty',${tq('No season yet.')}+(l.me.staff?' '+${tq('Create one, then pick it when you make an event.')}:'')));
      if(nb){nb.style.marginTop='10px';box.appendChild(nb)}add(box,el('div'));box.lastChild.id='sform';return}
    if(SEL==null||!seasonById(SEL)){var run=ss.filter(function(s){return s.events.some(function(eid){var e=evById(eid);return e&&e.status!=='upcoming'})});
      SEL=(run.length?run[run.length-1]:ss[ss.length-1]).id}
    var tabs=el('div','tabs');ss.forEach(function(s){var t=el('button','tab'+(s.id===SEL?' on':''),s.name);t.onclick=function(){SEL=s.id;seasons(l)};tabs.appendChild(t)});
    if(nb)tabs.appendChild(nb);box.appendChild(tabs);
    var s=seasonById(SEL);var head=el('div','row');head.style.justifyContent='space-between';add(head,el('p','note',seasonAbout(s)+' '+${tq('Open events count as they stand (one with hidden times once it ends). Ties go to most wins.')}));
    if(l.me.staff){var eb=el('button','btn ghost small',${tq('Edit season')});eb.onclick=function(){seasonForm(s)};head.appendChild(eb)}
    box.appendChild(head);add(box,el('div'));box.lastChild.id='sform';
    // its classes (multi-class events) and the league's divisions: each its own championship
    var G=s.groups||[],g=G.filter(function(x){return x.kind+':'+x.name===GSEL})[0],rows=g?g.standings:s.standings;
    if(G.length){var gt=el('div','tabs sub');[{kind:'',name:${tq('Overall')}}].concat(G).forEach(function(x){var k=x.kind?x.kind+':'+x.name:'';
      var b=el('button','tab'+((g?GSEL:'')===k?' on':''),x.name);b.onclick=function(){GSEL=k;seasons(l)};gt.appendChild(b)});box.appendChild(gt)}
    var evs=s.events.map(evById).filter(function(e){return e&&e.status!=='upcoming'});
    var tw=el('div','tablewrap'),t=el('table');tw.appendChild(t);box.appendChild(tw);
    // (a phone: Points and Wins after the name, the rounds sideways after them: as the event's standings)
    var phone=NARROW.matches;t.className=phone?'phone':'';
    function row(tr,c){(phone?[c.pos,c.drv,c.pts,c.wins]:[c.pos,c.drv]).concat(c.rs,phone?[]:[c.wins,c.pts]).forEach(function(x){tr.appendChild(x)})}
    var h=el('tr');row(h,{pos:el('th',null,${tq('Pos')}),drv:el('th',null,${tq('Driver')}),wins:el('th','r',${tq('Wins')}),pts:el('th','r',${tq('Points')}),
      rs:evs.map(function(e,i){var th=el('th','r');var a=el('a',null,F(${tq('R{0}')},i+1));a.href='/e/'+e.id;a.title=e.name;th.appendChild(a);return th})});t.appendChild(h);
    if(!rows.length){var tr=el('tr'),td=el('td','empty',s.events.length?${tq('No results yet.')}:${tq('No events in this season yet.')});td.colSpan=4+evs.length;tr.appendChild(td);t.appendChild(tr)}
    rows.forEach(function(p){var tr=el('tr',p.rank===1?'p1':'');var d=el('td','drv');flag(d,p.country);teamTag(d,p);driverName(d,p);
      var rs=evs.map(function(e){var c=p.cells[e.id],td=el('td','r'+(c&&c.dropped?' dropped':''));
        if(!c||c.absent)td.textContent='·';else if(c.pos){td.textContent=c.pts;if(c.power)td.appendChild(el('small','ps','PS +'+c.power))}
        else if(c.dsq)td.appendChild(el('span','dnf',${tq('DSQ')}));else if(c.dnf)td.appendChild(el('span','dnf',${tq('DNF')}));else td.appendChild(el('span','run','…'));
        td.title=e.name+(c&&c.pos?': P'+c.pos+(c.classified?' ('+${tq('DNF')}+')':'')+(c.power?', '+F(${tq('Power Stage +{0}')},c.power):''):'')+(c&&c.dropped?' '+${tq('(dropped)')}:'');return td});
      row(tr,{pos:el('td','pos',String(p.rank)),drv:d,wins:el('td','r',String(p.wins)),pts:el('td','r tot',String(p.points)),rs:rs});t.appendChild(tr)});
    h.setAttribute('data-nopage','');paginate(t,'season'+s.id+'|'+(g?GSEL:''),tw);   // (30 a page: src/pager.js)
    if(rows.length)scrollHint(tw,${tq('Swipe the table sideways for each round')});if(s.teamChamp&&l.teams)teamTable(box,l,s,evs)}
  function seasonForm(s){var box=$('sform');box.innerHTML='';var f=el('div','card');f.style.margin='14px 0';box.appendChild(f);
    add(f,el('h3',null,s?F(${tq('Edit {0}')},s.name):${tq('New season')}));
    var g=el('div','twocol');g.innerHTML='<label><span>${ts('Name')}</span><input type="text" id="sn" maxlength="60" placeholder="${ts('e.g. 2026 Autumn')}"></label>'+
      '<label><span>${ts('Points')}</span><select id="sp"></select></label>'+
      '<label class="cust"><span>${ts('Points from P1 down')}</span><input type="text" id="st" placeholder="25, 18, 15, 12, 10, 8, 6, 4, 2, 1"></label>'+
      '<label class="cust"><span>${ts('Then, for every other finisher')}</span><input type="text" id="sf" placeholder="0"></label>'+
      '<label><span>${ts("Power Stage bonus (each event's last stage)")}</span><select id="sw"><option value="">${ts('None')}</option><option value="wrc">'+F(${tq('{0} (as in the WRC)')},POWER.join('-'))+'</option><option value="custom">${ts('Your own…')}</option></select></label>'+
      '<label class="custw"><span>${ts('Bonus from P1 down')}</span><input type="text" id="swt" placeholder="5, 4, 3, 2, 1"></label>'+
      '<label><span>${ts('Worst rounds dropped (each driver)')}</span><select id="sd"></select></label>';
    f.appendChild(g);
    Object.keys(PRESETS).forEach(function(k){var o=el('option',null,PRESETS[k].label);o.value=k;$('sp').appendChild(o)});var oc=el('option',null,${tq('Your own…')});oc.value='custom';$('sp').appendChild(oc);
    for(var i=0;i<=5;i++){var od=el('option',null,i?String(i):${tq('None: every round counts')});od.value=String(i);$('sd').appendChild(od)}
    var pts=s?s.points:PRESETS.wrc,pw=s?s.power:[];
    var pk=Object.keys(PRESETS).filter(function(k){return PRESETS[k].table.join()===pts.table.join()&&PRESETS[k].finisher===pts.finisher})[0];
    $('sn').value=s?s.name:F(${tq('Season {0}')},L.seasons.length+1);$('sp').value=pk||'custom';$('st').value=pts.table.join(', ');$('sf').value=String(pts.finisher||0);
    $('sw').value=!pw.length?'':pw.join()===POWER.join()?'wrc':'custom';$('swt').value=pw.join(', ');$('sd').value=String(s?s.drop:0);
    function vis(){[].forEach.call(f.querySelectorAll('.cust'),function(x){x.style.display=$('sp').value==='custom'?'':'none'});
      [].forEach.call(f.querySelectorAll('.custw'),function(x){x.style.display=$('sw').value==='custom'?'':'none'})}
    $('sp').onchange=function(){var p=PRESETS[this.value];if(p){$('st').value=p.table.join(', ');$('sf').value=String(p.finisher)}vis()};$('sw').onchange=vis;vis();
    var tg=champFields(f,s&&s.teamChamp);
    var r=el('div','row');r.style.marginTop='14px';
    var sv=el('button','btn small',s?${tq('Save season')}:${tq('Make season')});sv.onclick=function(){sv.disabled=true;
      var w=$('sw').value,body={name:$('sn').value,points:{table:$('st').value,finisher:$('sf').value},power:w==='wrc'?POWER:w==='custom'?$('swt').value:[],drop:+$('sd').value};
      if(tg)body.teamChamp=tg();
      api(s?'/api/seasons/'+s.id+'/edit':'/api/leagues/'+id+'/seasons',body).then(function(j){if(!s)SEL=j.id;load()},function(e){sv.disabled=false;msg('sfm',e.message)})};
    var cn=el('button','btn ghost small',${tq('Cancel')});cn.onclick=function(){box.innerHTML=''};add(r,sv,cn);
    if(s){var dl=el('button','btn danger small',${tq('Delete season')});dl.onclick=function(){if(!confirm(F(${tq('Delete {0}? Its events stay, as one-offs, with their results.')},s.name)))return;
      api('/api/seasons/'+s.id+'/delete',{}).then(function(){SEL=null;load()},function(e){msg('sfm',e.message)})};r.appendChild(dl)}
    f.appendChild(r);add(f,el('div','msg'));f.lastChild.id='sfm';f.scrollIntoView({behavior:'smooth',block:'nearest'})}

  // ---- drivers: roles (the owner), remove and ban (the owner and admins)
  var ROLE={owner:${tq('owner')},admin:${tq('admin')},member:${tq('member')}};
  function members(l){var box=$('members');box.innerHTML='';msg('mm','');
    l.members.forEach(function(m){var it=el('div','item');var d=el('div');var t=el('div','t');t.style.fontSize='17px';
      flag(t,m.country);teamTag(t,m);add(t,m.name+' ');if(m.role!=='member')t.appendChild(el('span','badge '+m.role,ROLE[m.role]||m.role));
      if(m.division&&!(l.me.staff&&l.divisions.length))add(t,' ',el('span','badge',m.division));
      add(d,t,el('div','s',F(${tq('joined {0}')},FDATE(m.joined))));it.appendChild(d);
      var act=el('div','actions'),me=ME&&ME.steamId===m.steamId;
      if(l.me.staff&&l.divisions.length){var ds=el('select','div');ds.title=${tq('Division')};
        [['',${tq('No division')}]].concat(l.divisions.map(function(x){return[x,x]})).forEach(function(x){var o=el('option',null,x[1]);o.value=x[0];o.selected=x[0]===(m.division||'');ds.appendChild(o)});
        ds.onchange=function(){api('/api/leagues/'+id+'/division',{steamId:m.steamId,division:this.value||null}).then(load,function(e){msg('mm',e.message)})};act.appendChild(ds)}
      if(l.me.staff&&l.teams&&l.teams.source==='league'&&l.teams.list.length){var tsl=el('select','div');tsl.title=${tq('Team')};
        [['',${tq('No team')}]].concat(l.teams.list.map(function(x){return[String(x.id),x.name]})).forEach(function(x){var o=el('option',null,x[1]);o.value=x[0];o.selected=x[0]===String(m.teamId||'');tsl.appendChild(o)});
        tsl.onchange=function(){api('/api/leagues/'+id+'/teamset',{steamId:m.steamId,teamId:this.value?+this.value:null}).then(load,function(e){msg('mm',e.message)})};act.appendChild(tsl)}
      if(l.me.owner&&m.role!=='owner'){var rb=el('button','btn ghost small',m.role==='admin'?${tq('Make member')}:${tq('Make admin')});
        rb.title=m.role==='admin'?${tq('No longer an admin')}:${tq('Admins run events, seasons, members and stewarding')};
        rb.onclick=function(){api('/api/leagues/'+id+'/role',{steamId:m.steamId,role:m.role==='admin'?'member':'admin'}).then(load,function(e){msg('mm',e.message)})};act.appendChild(rb)}
      if(!me&&(l.me.owner&&m.role!=='owner'||l.me.role==='admin'&&m.role==='member')){
        var rm=el('button','btn ghost small',${tq('Remove')});rm.onclick=function(){if(!confirm(F(${tq('Remove {0} from the championship? Their results stay.')},m.name)))return;
          api('/api/leagues/'+id+'/remove',{steamId:m.steamId}).then(load,function(e){msg('mm',e.message)})};
        var bn=el('button','btn danger small',${tq('Ban')});bn.onclick=function(){var why=prompt(F(${tq("Ban {0}: removed, and they can't join again. Why? (they see it if they try to join)")},m.name),'');if(why==null)return;
          api('/api/leagues/'+id+'/remove',{steamId:m.steamId,ban:true,reason:why}).then(load,function(e){msg('mm',e.message)})};
        add(act,rm,bn)}
      it.appendChild(act);box.appendChild(it)});
    paginate(box,'members');   // (30 a page: src/pager.js)
    var bx=$('bans');bx.innerHTML='';if(!l.bans||!l.bans.length)return;
    add(bx,el('h3',null,${tq('Banned')}));l.bans.forEach(function(b){var it=el('div','item');var d=el('div');
      add(d,el('div','t',b.name),el('div','s',(b.reason?b.reason+' · ':'')+F(${tq('since {0}')},FDATE(b.at))));it.appendChild(d);
      var ub=el('button','btn ghost small',${tq('Unban')});ub.onclick=function(){api('/api/leagues/'+id+'/unban',{steamId:b.steamId}).then(load,function(e){msg('mm',e.message)})};
      it.appendChild(ub);bx.appendChild(it)})}
  account().then(load);
  `, env, meta);
}

// ------------------------------------------------------------------ teams (src/leagueteams.js, teamscore.js)
// A season's team championship in words, in the page's language (the API's teamAbout is English)
const CHAMP_JS = () => `
var BYNAME={time:${tq('times added up')},avg:${tq('average time')},places:${tq('places added up, lowest wins')}};
function champAbout(c){if(!c)return '';var who=c.best?F(${tq('the best {0} of each team count')},c.best):${tq('every driver of a team counts')};
  var how=c.method==='drivers'?(c.power?${tq('their championship points')}:${tq('their championship points, without the Power Stage')}):
    c.method==='reranked'?F(${tq('ranked among themselves, team points {0}')},(c.table||[]).join('-')):
    c.method==='result'?F(${tq("the team's place on the event ({0}), team points {1}")},BYNAME[c.by]||c.by,(c.table||[]).join('-')):${tq('their points over the season')};
  var o=who+': '+how;if(c.nominate)o+='; '+F(${tq('each team nominates up to {0} drivers for an event before it opens')},c.nominate)+(c.fallback==='none'?' ('+${tq('none nominated: no points')}+')':'');
  if(c.drop)o+='; '+F(${tq("each team's worst {0} rounds dropped")},c.drop);return o+'. '+${tq('Points stay with the team a driver drove the event for.')}}
function tTag(p,t){if(t&&t.tag)tmInto(p,t.tagFmt,t.tag,t.color,'teamtag');return p}`;

// The league page's teams: the settings (staff), the teams and who is in them, a season's team standings and penalties,
// the team championship's form
const TEAMS_JS = () => `${CHAMP_JS()}
  var TCOLORS=${JSON.stringify(TEAM.colors)},METHODS=${JSON.stringify(Object.fromEntries(Object.entries(CHAMP_METHODS).map(([k, v]) => [k, t(v)])))};
  function nameOf(sid){var m=L.members.filter(function(x){return x.steamId===sid})[0];return m?m.name:${tq('a driver')}}
  function teamSettings(c,l){var T=l.teams||{};
    add(c,el('h3',null,${tq('Teams')}),el('p','note',${tq("Team standings in the championships: the championship's own teams, or the drivers' ACR Daily teams. Each season then says how its team championship scores.")}));
    var g=el('div','twocol');g.innerHTML='<label><span>${ts('Teams')}</span><select id="tsrc"><option value="">${ts('None')}</option><option value="league">${ts("The league's own teams")}</option><option value="site">${ts("ACR Daily's teams (/teams)")}</option></select></label>'+
      '<label class="tlg"><span>${ts('Who puts drivers in teams')}</span><select id="tpick"><option value="admins">${ts('The admins')}</option><option value="drivers">${ts('The drivers themselves')}</option><option value="managers">${ts("Each team's manager")}</option></select></label>'+
      '<label class="tlg"><span>${ts('Drivers in a team at most')}</span><input type="number" id="tmax" min="1" max="50"></label>'+
      '<label class="tlg"><span>${ts('Transfers')}</span><select id="ttr"><option value="open">${ts('Open (points stay with the team driven for)')}</option><option value="admins">${ts('By the admins only, once a driver has driven for a team')}</option></select></label>';
    c.appendChild(g);$('tsrc').value=T.source||'';$('tpick').value=T.pick||'admins';$('tmax').value=String(T.max||10);$('ttr').value=T.transfers||'open';
    function vis(){[].forEach.call(g.querySelectorAll('.tlg'),function(x){x.style.display=$('tsrc').value==='league'?'':'none'})}$('tsrc').onchange=vis;vis();
    var sv=el('button','btn small',${tq('Save teams')});sv.style.marginTop='12px';sv.onclick=function(){var src=$('tsrc').value;
      if(!src&&T.source&&!confirm(${tq('Turn teams off? The team standings go (back when teams are on again).')}))return;
      api('/api/leagues/'+id+'/teams',src?{source:src,pick:$('tpick').value,max:$('tmax').value,transfers:$('ttr').value}:{off:true}).then(load,function(e){msg('tsm',e.message)})};
    c.appendChild(sv);add(c,el('div','msg'));c.lastChild.id='tsm'}
  function teamsSec(l){var box=$('teamsec');box.innerHTML='';var T=l.teams;if(!T)return;
    add(box,el('h2',null,${tq('Teams')}));
    var note=T.source==='site'?${tq('Drivers drive for their ACR Daily team (/teams).')}:T.pick==='drivers'?${tq('Pick your team below.')}:
      T.pick==='managers'?${tq("Each team's manager picks its drivers.")}:${tq('The admins put drivers in teams.')};
    add(box,el('p','note',note+' '+${tq('Points stay with the team a driver drove the event for.')}));
    var mine=ME&&l.members.filter(function(m){return m.steamId===ME.steamId})[0],myTeam=mine?mine.teamId:null;
    // an invite from a team's manager: accept or decline it
    var inv=mine&&mine.teamInvite&&!myTeam?T.list.filter(function(t){return t.id===mine.teamInvite})[0]:null;
    if(inv){var ib=el('div','card');ib.style.marginBottom='14px';var it0=el('div','t');tTag(it0,inv);add(it0,F(${tq('{0} invites you to drive for it.')},inv.name));ib.appendChild(it0);
      var ia=el('div','row');ia.style.marginTop='10px';var ac=el('button','btn small',${tq('Accept')}),dc=el('button','btn ghost small',${tq('Decline')});
      ac.onclick=function(){api('/api/leagues/'+id+'/teamset',{steamId:ME.steamId,teamId:inv.id}).then(load,function(e){msg('tm',e.message)})};
      dc.onclick=function(){api('/api/leagues/'+id+'/teamdecline',{}).then(load,function(e){msg('tm',e.message)})};add(ia,ac,dc);ib.appendChild(ia);box.appendChild(ib)}
    if(!T.list.length)add(box,el('div','empty',T.source==='site'?${tq("None of the championship's drivers is in a team yet.")}:${tq('No teams yet.')}));
    T.list.forEach(function(t){var it=el('div','item');var d=el('div');var h=el('div','t');h.style.fontSize='17px';tTag(h,t);add(h,t.name+' ');
      if(t.id===myTeam)h.appendChild(el('span','badge upcoming',${tq('your team')}));
      var sub=[P(${tqp('{0} driver', '{0} drivers')},t.drivers.length)+(T.source==='league'?' / '+T.max:'')];if(t.manager)sub.push(F(${tq('manager: {0}')},t.manager.name));
      var invited=l.members.filter(function(m){return m.teamInvite===t.id&&!m.teamId});
      add(d,h,el('div','s',sub.join(' · ')),el('div','s',t.drivers.map(nameOf).join(', ')));
      if(invited.length)d.appendChild(el('div','s',F(${tq('invited: {0}')},invited.map(function(m){return m.name}).join(', '))));it.appendChild(d);
      var act=el('div','actions');
      if(T.source==='league'&&l.me.member){
        if(T.pick==='drivers'&&t.id!==myTeam){var jb=el('button','btn ghost small',${tq('Join')});jb.onclick=function(){api('/api/leagues/'+id+'/teamset',{steamId:ME.steamId,teamId:t.id}).then(load,function(e){msg('tm',e.message)})};act.appendChild(jb)}
        if(t.id===myTeam){var lb=el('button','btn ghost small',${tq('Leave')});lb.onclick=function(){if(!confirm(F(${tq('Leave {0}?')},t.name)))return;api('/api/leagues/'+id+'/teamset',{steamId:ME.steamId,teamId:null}).then(load,function(e){msg('tm',e.message)})};act.appendChild(lb)}
        if(T.pick==='managers'&&T.runs.indexOf(t.id)>=0){var free=l.members.filter(function(m){return !m.teamId&&m.teamInvite!==t.id});
          if(free.length){var sel=el('select','div');var o0=el('option',null,${tq('Invite a driver…')});o0.value='';sel.appendChild(o0);
            free.forEach(function(m){var o=el('option',null,m.name);o.value=m.steamId;sel.appendChild(o)});
            sel.onchange=function(){if(this.value)api('/api/leagues/'+id+'/teaminvite',{steamId:this.value,teamId:t.id}).then(function(){msg('tm',${tq('Invited: they accept or decline on this page.')},true);load()},function(e){msg('tm',e.message)})};act.appendChild(sel)}
          invited.forEach(function(m){var cb=el('button','btn ghost small',F(${tq('Take back the invite to {0}')},m.name));cb.onclick=function(){api('/api/leagues/'+id+'/teaminvite',{steamId:m.steamId,teamId:null}).then(load,function(e){msg('tm',e.message)})};act.appendChild(cb)})
          t.drivers.forEach(function(sid){var xb=el('button','btn ghost small',F(${tq('Release {0}')},nameOf(sid)));xb.onclick=function(){api('/api/leagues/'+id+'/teamset',{steamId:sid,teamId:null}).then(load,function(e){msg('tm',e.message)})};act.appendChild(xb)})}}
      if(T.source==='league'&&(l.me.staff||T.runs.indexOf(t.id)>=0)){var eb=el('button','btn ghost small',${tq('Edit')});eb.onclick=function(){teamForm(t)};act.appendChild(eb)}
      if(T.source==='league'&&l.me.staff){var db=el('button','btn danger small',${tq('Delete')});db.onclick=function(){if(!confirm(F(${tq('Delete {0}? Its drivers are in no team; its points leave the team standings.')},t.name)))return;
        api('/api/leagues/'+id+'/teamdelete',{teamId:t.id}).then(load,function(e){msg('tm',e.message)})};act.appendChild(db)}
      it.appendChild(act);box.appendChild(it)});
    add(box,el('div','msg'));box.lastChild.id='tm';
    if(T.source==='league'&&l.me.staff){var nb=el('button','btn ghost small',${tq('+ New team')});nb.style.marginTop='10px';nb.onclick=function(){teamForm(null)};box.appendChild(nb)}
    add(box,el('div'));box.lastChild.id='tform'}
  function teamForm(t){var box=$('tform');box.innerHTML='';var f=el('div','card');f.style.margin='14px 0';box.appendChild(f);
    add(f,el('h3',null,t?F(${tq('Edit {0}')},t.name):${tq('New team')}));
    var g=el('div','twocol');g.innerHTML='<label><span>${ts('Name')}</span><input type="text" id="tn" maxlength="30"></label><label><span>${ts('Tag (2 to 4 letters or digits)')}</span><input type="text" id="tt" maxlength="4"></label>'+
      (L.me.staff?'<label><span>${ts('Manager')}</span><select id="tmg"></select></label>':'')+'<label><span>${ts('Colour')}</span><div class="colors" id="tcol"></div></label>';
    f.appendChild(g);$('tn').value=t?t.name:'';$('tt').value=t&&t.tag||'';
    if(L.me.staff){var o0=el('option',null,${tq('None (the admins)')});o0.value='';$('tmg').appendChild(o0);
      L.members.forEach(function(m){var o=el('option',null,m.name);o.value=m.steamId;$('tmg').appendChild(o)});$('tmg').value=t&&t.manager?t.manager.steamId:''}
    TCOLORS.forEach(function(c,i){var lb=el('label'),r=el('input');r.type='radio';r.name='tcolor';r.value=c;r.checked=t?t.color===c:i===1;var sw=el('span');sw.style.background=c;add(lb,r,sw);$('tcol').appendChild(lb)});
    var r=el('div','row');r.style.marginTop='14px';var sv=el('button','btn small',t?${tq('Save team')}:${tq('Make team')});
    sv.onclick=function(){var body={name:$('tn').value,tag:$('tt').value,color:(f.querySelector('input[name=tcolor]:checked')||{}).value};
      if(L.me.staff)body.manager=$('tmg').value||null;if(t)body.teamId=t.id;
      sv.disabled=true;api('/api/leagues/'+id+(t?'/teamedit':'/teamadd'),body).then(load,function(e){sv.disabled=false;msg('tfm',e.message)})};
    var cn=el('button','btn ghost small',${tq('Cancel')});cn.onclick=function(){box.innerHTML=''};add(r,sv,cn);f.appendChild(r);add(f,el('div','msg'));f.lastChild.id='tfm'}
  // a season's team standings: points per round (who counted in the cell's tooltip), wins, the stewards' points penalties
  function teamTable(box,l,s,evs){add(box,el('h3',null,${tq('Teams')}),el('p','note',champAbout(s.teamChamp)));
    var tw=el('div','tablewrap'),t=el('table');tw.appendChild(t);box.appendChild(tw);var season=s.teamChamp.method==='season';
    var h=el('tr');add(h,el('th',null,${tq('Pos')}),el('th',null,${tq('Team')}));
    evs.forEach(function(e,i){var th=el('th','r');var a=el('a',null,F(${tq('R{0}')},i+1));a.href='/e/'+e.id;a.title=e.name;th.appendChild(a);h.appendChild(th)});
    add(h,el('th','r',${tq('Wins')}),el('th','r',${tq('Points')}));t.appendChild(h);
    var rows=s.teamStandings||[];
    if(!rows.length){var tr0=el('tr'),td0=el('td','empty',${tq('No teams yet.')});td0.colSpan=4+evs.length;tr0.appendChild(td0);t.appendChild(tr0)}
    rows.forEach(function(p){var tr=el('tr',p.rank===1?'p1':'');add(tr,el('td','pos',String(p.rank)));var d=el('td','drv');tTag(d,p);add(d,p.name);
      if(season&&p.best&&p.best.length)d.appendChild(el('small','muted',' · '+p.best.map(function(x){return nameOf(x.steamId)+' '+x.points}).join(', ')));tr.appendChild(d);
      evs.forEach(function(e){var c=p.cells[e.id],td=el('td','r'+(c&&c.dropped?' dropped':''));
        if(!c||c.absent)td.textContent='·';
        else{td.textContent=String(c.pts);td.title=e.name+(c.rank?': '+F(${tq('P{0} among the teams')},c.rank):'')+(c.counted&&c.counted.length?' · '+c.counted.map(nameOf).join(', '):'')+(c.dropped?' '+${tq('(dropped)')}:'')}
        tr.appendChild(td)});
      var pt=el('td','r tot',String(p.points));if(p.penalty)pt.appendChild(el('small','pen',' '+F(${tq('incl. {0} penalty')},-p.penalty)));
      add(tr,el('td','r',String(p.wins)),pt);t.appendChild(tr)});
    h.setAttribute('data-nopage','');paginate(t,'teams'+s.id,tw);   // (30 a page: src/pager.js)
    (s.teamPenalties||[]).forEach(function(x){var it=el('div','decision');var d=el('div');var tm=(l.teams.list.filter(function(y){return y.id===x.teamId})[0]||{}).name||'';
      add(d,el('b',x.points<0?'good':'bad',(x.points>0?'−':'+')+P(${tqp('{0} point', '{0} points')},Math.abs(x.points))),' '+tm+': '+x.reason);add(d,el('div','muted',F(${tq('by {0}')},x.by)+' · '+when(x.at)));it.appendChild(d);
      if(l.me.staff){var rb=el('button','btn ghost small',${tq('Take back')});rb.onclick=function(){api('/api/seasons/'+s.id+'/teampenalty',{remove:x.id}).then(load,function(e){msg('tpm',e.message)})};it.appendChild(rb)}
      box.appendChild(it)});
    if(l.me.staff&&l.teams.list.length){var f=el('div','stewform');f.innerHTML='<label><span>${ts('Team')}</span><select id="tpt"></select></label><label><span>${ts('Points off (negative: given back)')}</span><input type="text" id="tpp" placeholder="5"></label>'+
      '<label><span>${ts('Reason (everyone sees it)')}</span><input type="text" id="tpr" maxlength="200"></label>';
      var b=el('button','btn small',${tq('Team penalty')});var r=el('div','row');r.appendChild(b);f.appendChild(r);box.appendChild(f);
      l.teams.list.forEach(function(y){var o=el('option',null,y.name);o.value=String(y.id);$('tpt').appendChild(o)});
      b.onclick=function(){api('/api/seasons/'+s.id+'/teampenalty',{teamId:+$('tpt').value,points:+$('tpp').value,reason:$('tpr').value}).then(load,function(e){msg('tpm',e.message)})}}
    add(box,el('div','msg'));box.lastChild.id='tpm'}
  // the season form's team championship (a league with teams): -> a function giving its part of the body, or null
  function champFields(f,tc){if(!L.teams)return null;add(f,el('h3',null,${tq('Team championship')}));var tg=el('div','twocol');
    tg.innerHTML='<label><span>${ts('How teams score')}</span><select id="tcm"><option value="">${ts('No team championship')}</option></select></label>'+
      '<label class="tc"><span>${ts('Drivers who count for a team (0: all)')}</span><input type="number" id="tcb" min="0" max="20"></label>'+
      '<label class="tc"><span>${ts('Nominated drivers per team and event (0: no nominations)')}</span><input type="number" id="tcn" min="0" max="20"></label>'+
      '<label class="tcn"><span>${ts('A team that nominated nobody')}</span><select id="tcf"><option value="all">${ts('All its drivers count')}</option><option value="none">${ts('Scores nothing')}</option></select></label>'+
      '<label class="tcr"><span>${ts('Teams ranked by')}</span><select id="tcy"><option value="time">${ts('Times added up')}</option><option value="avg">${ts('Average time')}</option><option value="places">${ts('Places added up (lowest wins)')}</option></select></label>'+
      '<label class="tcr"><span>${ts('A team short of finishers')}</span><select id="tcs"><option value="fewer">${ts('Ranks after the teams with more')}</option><option value="slowest">${ts("Each missing one: the slowest finisher's time + a penalty")}</option></select></label>'+
      '<label class="tcr tcp"><span>${ts('Penalty: seconds')}</span><input type="number" id="tcps" min="0" max="3600"></label>'+
      '<label class="tcr tcp"><span>${ts('Penalty: % of the slowest time')}</span><input type="number" id="tcpp" min="0" max="100"></label>'+
      '<label class="tcr"><span>${ts('At least this many drivers count (the rest: missing)')}</span><input type="number" id="tcmin" min="1" max="8"></label>'+
      '<label class="tct"><span>${ts('Team points from P1 down')}</span><input type="text" id="tctb" placeholder="25, 18, 15, 12, 10, 8, 6, 4, 2, 1"></label>'+
      '<label class="tcd"><span>${ts('The Power Stage bonus counts for teams')}</span><select id="tcw"><option value="1">${ts('Yes')}</option><option value="0">${ts('No')}</option></select></label>'+
      '<label class="tco"><span>${ts('Worst rounds dropped (each team)')}</span><input type="number" id="tcdr" min="0" max="20"></label>';
    f.appendChild(tg);Object.keys(METHODS).forEach(function(k){var o=el('option',null,METHODS[k]);o.value=k;$('tcm').appendChild(o)});
    $('tcm').value=tc?tc.method:'';$('tcb').value=String(tc?tc.best:2);$('tcn').value=String(tc?tc.nominate||0:0);$('tcf').value=tc&&tc.fallback||'all';
    $('tcy').value=tc&&tc.by||'time';$('tcs').value=tc&&tc.short||'fewer';$('tcps').value=String(tc&&tc.plusS||0);$('tcpp').value=String(tc&&tc.plusPct||0);$('tcmin').value=String(tc&&tc.min||1);
    $('tctb').value=(tc&&tc.table||[25,18,15,12,10,8,6,4,2,1]).join(', ');$('tcw').value=tc&&tc.power===false?'0':'1';$('tcdr').value=String(tc&&tc.drop||0);
    function sh(c,on){[].forEach.call(tg.querySelectorAll('.'+c),function(x){x.style.display=on?'':'none'})}
    function tvis(){var m=$('tcm').value;sh('tc',!!m);sh('tcn',!!m&&+$('tcn').value>0);sh('tcr',m==='result');sh('tcp',m==='result'&&$('tcs').value==='slowest');
      sh('tct',m==='reranked'||m==='result');sh('tcd',m==='drivers');sh('tco',!!m&&m!=='season')}
    $('tcm').onchange=tvis;$('tcn').oninput=tvis;$('tcs').onchange=tvis;tvis();
    return function(){var m=$('tcm').value;return m?{method:m,best:$('tcb').value,nominate:$('tcn').value,fallback:$('tcf').value,by:$('tcy').value,short:$('tcs').value,
      plusS:$('tcps').value,plusPct:$('tcpp').value,min:$('tcmin').value,table:$('tctb').value,power:$('tcw').value==='1',drop:$('tcdr').value}:{off:true}}}`;

// The event page's teams: who drove for which, who counted, each team's points, nominations; the staff set the team an
// entry counts for
const EVENT_TEAMS_JS = () => `
  function nm(sid){var T=E.teams||{};return (T.names&&T.names[sid])||(E.standings.filter(function(r){return r.steamId===sid})[0]||{}).name||${tq('a driver')}}
  function teamsEv(e){var box=$('evteams');box.innerHTML='';var T=e.teams;if(!T||(!T.results.length&&!T.champ))return;
    add(box,el('h2',null,${tq('Teams')}));if(T.champ)add(box,el('p','note',champAbout(T.champ)));
    var tw=el('div','tablewrap'),t=el('table');tw.appendChild(t);box.appendChild(tw);
    var h=el('tr');add(h,el('th',null,${tq('Pos')}),el('th',null,${tq('Team')}),el('th',null,${tq('Drivers')}));if(T.nominate)h.appendChild(el('th',null,${tq('Nominated')}));
    h.appendChild(el('th','r',${tq('Points')}));t.appendChild(h);
    if(!T.results.length){var tr0=el('tr'),td0=el('td','empty',${tq('No team has a driver on it yet.')});td0.colSpan=5;tr0.appendChild(td0);t.appendChild(tr0)}
    T.results.forEach(function(x){var tr=el('tr',x.rank===1?'p1':'');add(tr,el('td','pos',x.rank?String(x.rank):''));var d=el('td','drv');tTag(d,x);add(d,x.name);tr.appendChild(d);
      var dd=el('td');x.drove.forEach(function(sid,i){if(i)add(dd,', ');add(dd,x.counted.indexOf(sid)>=0?el('b',null,nm(sid)):nm(sid))});if(!x.drove.length)dd.textContent='–';tr.appendChild(dd);
      if(T.nominate){var nd=el('td');nd.textContent=x.nominated.length?x.nominated.map(nm).join(', '):'–';
        if(T.nominationsOpen&&x.canNominate){var nb=el('button','btn ghost small',${tq('Nominate')});nb.style.marginLeft='8px';nb.onclick=function(){nominateForm(e,x)};nd.appendChild(nb)}tr.appendChild(nd)}
      tr.appendChild(el('td','r tot',x.pts==null?'–':String(x.pts)));t.appendChild(tr)});
    if(T.champ)add(box,el('p','note',${tq('In bold: the drivers who count for their team.')}));
    add(box,el('div'));box.lastChild.id='nform';add(box,el('div','msg'));box.lastChild.id='ntm';
    if(!e.me.staff||!e.standings.length)return;
    var f=el('div','stewform');f.innerHTML='<label><span>${ts('Driver')}</span><select id="etd"></select></label><label><span>${ts('Counts for')}</span><select id="ett"></select></label>';
    var b=el('button','btn ghost small',${tq('Set the team')});var r=el('div','row');r.appendChild(b);f.appendChild(r);box.appendChild(f);
    e.standings.forEach(function(x){var o=el('option',null,x.name);o.value=x.steamId;$('etd').appendChild(o)});
    var o0=el('option',null,${tq('No team')});o0.value='';$('ett').appendChild(o0);T.results.forEach(function(x){var o=el('option',null,x.name);o.value=String(x.id);$('ett').appendChild(o)});
    function cur(){var v=(T.entryTeams||{})[$('etd').value];$('ett').value=v?String(v):''}$('etd').onchange=cur;cur();
    b.onclick=function(){api('/api/events/'+id+'/entryteam',{steamId:$('etd').value,teamId:$('ett').value?+$('ett').value:null}).then(load,function(er){msg('ntm',er.message)})}}
  function nominateForm(e,x){var box=$('nform');box.innerHTML='';var f=el('div','card');f.style.margin='14px 0';box.appendChild(f);
    add(f,el('h3',null,F(${tq('Nominate for {0}')},x.name)),el('p','note',F(${tq('Up to {0} drivers: only they count for the team on this event.')},e.teams.nominate)));
    var tk=el('div','ticks');x.drivers.concat(x.nominated.filter(function(s){return x.drivers.indexOf(s)<0})).forEach(function(sid){var lb=el('label'),c=el('input');c.type='checkbox';c.value=sid;
      c.checked=x.nominated.indexOf(sid)>=0;add(lb,c,nm(sid));tk.appendChild(lb)});f.appendChild(tk);
    var r=el('div','row');r.style.marginTop='14px';var sv=el('button','btn small',${tq('Save nominations')});
    sv.onclick=function(){var ids=[].map.call(tk.querySelectorAll('input:checked'),function(c){return c.value});sv.disabled=true;
      api('/api/events/'+id+'/nominate',{teamId:x.id,steamIds:ids}).then(load,function(er){sv.disabled=false;msg('ntm',er.message)})};
    var cn=el('button','btn ghost small',${tq('Cancel')});cn.onclick=function(){box.innerHTML=''};add(r,sv,cn);f.appendChild(r)}`;

// ------------------------------------------------------------------ /e/:id
export function eventPage(id, env, meta = {}) {
  return shell(t('Event') + ' · ACR Daily', `
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick">${t('Event')}</div><h1 id="name"></h1><p class="about" id="rabout" hidden></p>
    <div class="facts" id="facts"></div><div class="chips" id="rules"></div>
    <p class="note" id="hidn" hidden></p>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="am"></div></div>
  <style>${EVENT_LIVE_CSS}</style><div id="live" hidden></div>
  <div class="grid" style="margin-top:26px"><div class="card"><h3>${t('How to drive it')}</h3><ol class="steps" id="how"></ol></div>
    <div class="card"><h3>${t('The rules')}</h3><ol class="steps" id="rulestext"></ol></div></div>
  <h2>${t('Standings')}</h2><p class="note" id="stnote" hidden></p><div id="gtabs"></div><div class="tablewrap" id="stwrap"><table id="st"></table></div>
  <div id="evteams"></div><div id="evmatch"></div>
  <div id="stewards"></div>
  <div id="comments"></div>
  <h2>${t('Itinerary')}</h2><p class="note" id="itnote" hidden></p><p class="note" id="itdl" hidden></p><div class="tablewrap"><table class="itin" id="itin"></table></div>`, `
  var id=${JSON.stringify(id)},E=null,GSEL='',LM=null;
  if(NARROW.addEventListener)NARROW.addEventListener('change',function(){if(E)standings(E)});
  ${EVENT_LIVE_JS()}
  ${CHAMP_JS()}${EVENT_TEAMS_JS()}${SCORING_JS()}
  // a team match (a team 1V1's, a team cup's): its two teams, their lineups and scores
  function matchSec(e){var box=$('evmatch');box.innerHTML='';var M=e.match;if(!M)return;
    add(box,el('h2',null,${tq('Teams')}),el('p','note',scoringAbout(M.scoring)));matchTable(box,M.teams,M.scoring);
    add(box,el('p','note',${tq('In bold: the drivers who count for their team.')}))}
  var LEVEL={off:${tq('off')},light:${tq('light')},severe:${tq('severe')},realistic:${tq('realistic')}};
  function load(){return api('/api/events/'+id).then(render,function(e){$('name').textContent=e.status===404?${tq('No such event')}:${tq('Event')};msg('am',e.message)})}
  function fact(k,v){var d=el('div');add(d,el('span','k',k),el('b',null,v));$('facts').appendChild(d)}
  // when a hidden event shows what it keeps (the API's revealsAt: its close and the grace for late results; a cup's match:
  // when the cup is over)
  function revealWhen(e){return e.league&&e.league.kind==='cup'?${tq('Everything shows when the cup is over.')}:F(${tq('Everything shows on {0}.')},FDATETIME(e.revealsAt||e.closes))}
  function render(e){E=e;document.title=e.name+' · ACR Daily';$('name').textContent=e.name;showBanner($('banner'),e.league.banner);
    // a 1V1's or a cup's match (its holder league is hidden): back to its own page, no league or season
    // (a team 1V1's: th2h, a team cup's: tcup; their pages: /team1v1, /tcup/<id>)
    var hk=['h2h','cup','th2h','tcup','live'].indexOf(e.league.kind)>=0?e.league.kind:null;if(hk)navOn(hk==='h2h'||hk==='th2h'?'1v1':hk==='live'?'ranked':'cups');
    // a rally (one event, anyone's; 0033): its maker and words, in its pink; a championship's round in the leagues' blue
    var rk=e.league.kind==='event',k=$('kick');k.innerHTML='';k.style.color=rk?'#FF7AC6':hk?'':'#5BA8FF';
    $('rabout').textContent=rk?e.league.about||'':'';$('rabout').hidden=!(rk&&e.league.about);
    if(rk){var ra=el('a',null,${tq('Rally')});ra.href='/rallies';add(k,ra,' · '+F(${tq('by {0}')},e.league.owner)+' · '+TD(e.rally)+' ')}
    else{var la=el('a',null,hk==='h2h'?'1V1':hk==='th2h'?${tq('Team 1V1')}:hk==='live'?${tq('Ranked')}+' · '+e.league.name:e.league.name);la.href=hk==='h2h'?'/1v1':hk==='th2h'?'/team1v1':hk==='cup'?'/cup/'+e.league.id:hk==='tcup'?'/tcup/'+e.league.id:hk==='live'?'/ranked':'/l/'+e.league.id;
    add(k,la,' · '+(hk==='cup'?${tq('cup match')}:hk==='tcup'?${tq('team cup match')}:hk?'':(e.season?e.season.name:${tq('one-off')}))+(hk==='h2h'||hk==='th2h'||hk==='live'?'':' · ')+TD(e.rally)+' ')}
    k.appendChild(el('span','badge '+e.status,e.status==='open'?${tq('open')}:e.status==='upcoming'?${tq('upcoming')}:${tq('finished')}));
    $('facts').innerHTML='';
    fact(e.car?${tq('Car')}:e.carClasses?${tq('Car classes')}:${tq('Car class')},e.car||(e.carClasses?F(${tq('{0} (pick a car of one)')},e.carClasses.join(', ')):F(${tq('{0} (pick one)')},e.carClass)));
    fact(${tq('Stages')},e.stages.length+' · '+P(${tqp('{0} day', '{0} days')},e.days)+' · '+km(e.lengthM));
    fact(e.status==='upcoming'?${tq('Opens')}:${tq('Opened')},when(e.opens));
    fact(e.status==='closed'?${tq('Closed')}:${tq('Closes')},when(e.closes)+(e.status==='open'?' ('+F(${tq('{0} left')},left(e.closes))+')':''));
    var r=$('rules');r.innerHTML='';var R=e.rules;
    [R.damage?F(${tq('Damage {0}')},LEVEL[R.damageIntensity]):${tq('No damage')},F(${tq('Wear {0}')},LEVEL[R.wear]),F(${tq('Failures {0}')},LEVEL[R.failures]),R.respawn?${tq('Respawn on')}:${tq('No respawn')},F(${tq('Penalties {0}')},LEVEL[R.penalty]||R.penalty),${tq('Time stands still')}].concat(R.hardcore?[${tq('Hardcore Mode')}]:[]).concat(R.assists==='off'?[${tq('No driving aids')}]:[]).concat(R.retire?[F(${tq('DNF: slowest + {0} min')},R.retire)]:[]).forEach(function(x){r.appendChild(el('span','chip',x))});
    if(e.season&&e.season.power&&e.season.power.length)r.appendChild(el('span','chip',F(${tq('Power Stage: SS{0}')},e.stages.length)));
    if(e.hidden){var hn=hiddenNote(e.hidden);if(hn)r.appendChild(el('span','chip',${tq('Hidden until it ends')}));
      $('hidn').textContent=hn?hn+' '+(e.revealed?(e.me.staff&&!rk?${tq('You see the set-up: you run the championship.')}:${tq('You see the set-up: you made it, or have pressed DRIVE on it.')}):${tq('Drivers see the set-up when they press DRIVE in the app.')})+' '+revealWhen(e):'';
      $('hidn').hidden=!hn}else $('hidn').hidden=true;
    var a=$('acts');a.innerHTML='';
    if(e.me.staff){var ed=el('a','btn ghost small',${tq('Edit event')});ed.href=rk?'/rallies/new?edit='+id:'/e/'+id+'/edit';
      var cp=el('a','btn ghost small',rk?${tq('Copy as a new rally')}:${tq('Copy as the next round')});cp.href=rk?'/rallies/new?from='+id:'/l/'+e.league.id+'/new?from='+id;cp.title=${tq('A new event like this one, opening when this one closes')};
      var dl=el('button','btn danger small',${tq('Delete event')});dl.onclick=function(){if(!confirm(F(${tq('Delete {0} and its results?')},e.name)))return;
        api('/api/events/'+id+'/delete',{}).then(function(){location.href=rk?'/rallies':'/l/'+e.league.id},function(x){msg('am',x.message)})};add(a,ed,cp,dl)}
    if(rk&&e.league.code){var iv=el('div','row');iv.style.width='100%';var link=location.origin+'/join/'+e.league.code;     // (its maker: a private rally's link)
      add(iv,el('span','code',e.league.code));var cl=el('button','btn ghost small',${tq('Copy invite link')});
      cl.onclick=function(){navigator.clipboard.writeText(link).then(function(){msg('am',F(${tq('Copied: {0}')},link),true)})};iv.appendChild(cl);
      if(!e.league.public)add(iv,el('span','muted',${tq('Private: drivers need this link or code.')}));a.appendChild(iv)}
    if(e.locked)add(a,lockBadge(),el('span','muted',${tq('Private: enter its code to drive it and see the results.')}));
    if(!e.me.signedIn)a.appendChild(steamBtn());
    else if(hk){if(e.me.member)add(a,el('span','badge upcoming',${tq('your match')}))}
    else if(rk&&e.locked)codeBox(a);
    else if(rk){if(e.league.public&&!e.me.entry)add(a,el('span','muted',${tq("Open to every driver: it is in everyone's app, under RALLIES.")}))}
    else if(!e.me.member){var jl=el('a','btn',F(e.league.public?${tq('Join {0} to take part')}:${tq('Ask to join {0} to take part')},e.league.name));jl.href='/l/'+e.league.id;a.appendChild(jl)}
    var how=$('how');how.innerHTML='';
    [${tq('Open the ACR Daily app, signed in with Steam.')},
     F(e.car?${tq('Find the event under {0}.')}:${tq('Find the event under {0} and pick a car.')},'<b>'+(hk==='h2h'||hk==='th2h'?'1V1':hk==='cup'||hk==='tcup'?${tq('CUPS')}:${tq('RALLIES')})+'</b>'),
     ${tq('Press <b>DRIVE</b>. The app sets up the whole rally in the game.')},
     ${tq('In the game: <b>Racing › Rally › Rally Weekend › Start Rally</b>.')},
     ${tq('You can stop between stages and carry on later (Rally Weekend › Resume).')}+' '+${tq('Quit the game from a service park: the game keeps its rally only then. Otherwise it takes the rally back and you drive the stages done again (they count only once).')}].forEach(function(x){var li=el('li');li.innerHTML=x;how.appendChild(li)});
    var rt=$('rulestext');rt.innerHTML='';
    [${tq('One go: your first start counts.')},${tq("The game's stage times plus penalties.")},
     ${tq('Retire, restart or drive without the app: DNF.')}+(R.retire?' '+F(${tq('A DNF stays in the results: each stage not driven counts as its slowest time + {0} min.')},R.retire):''),${tq('Damage carries over between service parks.')},
     ${tq('Finish before the event closes.')},
     hk==='h2h'?${tq('Lower total wins the stakes. No finisher or a tie: stakes back.')}:
     hk==='cup'?${tq('Lower total goes through. No finisher or a tie: the higher seed does.')}:
     hk==='th2h'||hk==='tcup'?${tq('The teams are scored as below: the drivers in their lineups only.')}+(hk==='tcup'?' '+${tq('No team with a finisher or a tie: the higher seed goes through.')}:''):
     ${tq('Stewards can add time penalties or disqualify, with a reason shown below.')}
    ].concat(e.season?[F(${tq('Season: {0}.')},e.season.name)+' '+seasonAbout(e.season)]:[]).forEach(function(x){rt.appendChild(el('li',null,x))});
    standings(e);teamsEv(e);matchSec(e);stewards(e);comments(e);itin(e);
    // open: the drivers on its stages live, as on the dailies; its stages hidden, on a map only for who sees them, else
    // who is on which stage (src/eventlive.js)
    if(!LM&&e.status==='open'&&!e.locked)LM=liveMap($('live'),{url:'/api/events/'+id+'/live',
      sat:function(no){return '/lab/map?event='+id+'&ss='+no},names:e.stages.map(function(s){return s.name}),on:function(){return E&&E.status==='open'}})}
  // a private rally without its code (0043): the code, then it is the driver's to drive in the app (and its results to see)
  function codeBox(a){var r=el('div','row'),inp=el('input');inp.type='text';inp.placeholder='ABCD-EFGH';inp.maxLength=12;inp.autocomplete='off';
    inp.style.width='180px';var b=el('button','btn',${tq('Enter code')});b.onclick=function(){b.disabled=true;
      api('/api/events/'+id+'/join',{code:inp.value}).then(function(){msg('am','');return load()},function(x){b.disabled=false;msg('am',x.message)})};
    inp.onkeydown=function(ev){if(ev.key==='Enter')b.click()};add(r,inp,b);a.appendChild(r)}
  function standings(e){var t=$('st');t.innerHTML='';var n=e.stages.length;
    if(e.locked){$('gtabs').innerHTML='';$('stnote').hidden=false;$('stnote').textContent=F(${tq('Drivers so far: {0}. Enter the code to see the results.')},e.drivers||0);return}
    // times hidden: the standings list who has driven which stage (✓), by name; when the times show, said over them
    var masked=!!(e.hidden&&e.hidden.times&&e.standings.length&&e.standings.every(function(r){return r.rank==null}));
    $('stnote').hidden=!masked;$('stnote').textContent=masked?${tq('The times are hidden until it ends: until then this lists who has driven which stage.')}+' '+revealWhen(e):'';
    // overall, or within a class (a multi-class event) or a division
    var G=e.groups||[],g=G.filter(function(x){return x.kind+':'+x.name===GSEL})[0],rows=g?g.standings:e.standings,gt=$('gtabs');gt.innerHTML='';
    if(G.length){var tb=el('div','tabs sub');[{kind:'',name:${tq('Overall')}}].concat(G).forEach(function(x){var k=x.kind?x.kind+':'+x.name:'';
      var b=el('button','tab'+((g?GSEL:'')===k?' on':''),x.name);b.onclick=function(){GSEL=k;standings(e)};tb.appendChild(b)});gt.appendChild(tb)}
    // a phone: Pos, Driver, Total and Gap first, the stages after them, sideways under the name that stays (Total, Gap
    // and DNF were off a 360 px screen, 760 to 990 px over, nothing saying it scrolled: a UI review, Nov 2026)
    var phone=NARROW.matches;t.className=phone?'phone':'';
    function row(tr,c){(phone?[c.pos,c.drv,c.tot,c.gp,c.car].concat(c.ss):[c.pos,c.drv,c.car].concat(c.ss,[c.tot,c.gp])).forEach(function(x){if(x)tr.appendChild(x)})}
    var h=el('tr');row(h,{pos:el('th',null,${tq('Pos')}),drv:el('th',null,${tq('Driver')}),car:e.car?null:el('th',null,${tq('Car')}),
      ss:e.stages.map(function(s){var th=el('th','r','SS'+s.no);th.title=s.name||'';return th}),tot:el('th','r',${tq('Total')}),gp:el('th','r',${tq('Gap')})});t.appendChild(h);
    if(!rows.length){var tr=el('tr'),td=el('td','empty',e.status==='upcoming'?${tq('The event has not opened yet.')}:e.standings.length?${tq('Nobody in it has started yet.')}:${tq('Nobody has started yet.')});
      td.colSpan=5+n;tr.appendChild(td);t.appendChild(tr);return}
    var meId=e.me.entry&&e.me.entry.steamId;
    rows.forEach(function(r){var tr=el('tr',(r.rank===1?'p1':'')+(r.steamId===meId?' me':''));
      var pos=el('td','pos',r.rank?String(r.rank):'');var d=el('td','drv');flag(d,r.country);teamTag(d,r);driverName(d,r);
      var car=e.car?null:el('td','muted',r.car+(e.carClasses&&!g?' · '+r.cls:''));
      var ss=r.stages.map(function(s){var td=el('td','r t'+(s&&s.pos===1?' w':''));
        if(s&&s.retired){add(td,ms(s.totalMs));td.className='r t muted';td.appendChild(el('small','pen',${tq('DNF')}));td.title=(s.reason?s.reason+' · ':'')+${tq('not driven: the slowest time on the stage + the retirement penalty')}}
        else if(s&&s.totalMs==null){add(td,'✓');td.title=${tq('driven (times hidden until the event ends)')}}
        else if(s){add(td,ms(s.totalMs));var bits=[];if(s.penaltyMs)bits.push(pen(s.penaltyMs));if(s.pos)bits.push('P'+s.pos);
          if(bits.length)td.appendChild(el('small',s.penaltyMs?'pen':null,bits.join(' · ')));
          if(s.stewardMs)td.appendChild(el('small','st'+(s.stewardMs<0?' back':''),F(${tq('{0} stewards')},secs(s.stewardMs))));
          td.title=F(${tq('stage time {0}')},ms(s.timeMs))+(s.penaltyMs?' + '+F(${tq('{0} game penalty')},pen(s.penaltyMs)):'')+(s.stewardMs?' '+F(${tq('{0} from the stewards')},secs(s.stewardMs)):'')+
            (s.pos?' · '+F(${tq('P{0} on the stage, P{1} overall after it')},s.pos,s.cumPos):'')+(s.cumGapMs?' · '+F(${tq('{0} behind the best after it')},gap(s.cumGapMs)):'')}return td});
      var tot=el('td','r tot');var gp=el('td','r muted');
      // (the Gap column: gaps only; why a DNF or a DSQ, a time still hidden or so far: under the total, a UI review)
      function why(x){if(x)tot.appendChild(el('small','why',x))}
      if(r.status==='finished'&&r.totalMs==null){tot.textContent=${tq('Finished')};why(${tq('time hidden')})}
      else if(r.status==='finished'){tot.textContent=ms(r.totalMs);gp.textContent=r.gapMs==null?'':gap(r.gapMs)}
      else if(r.status==='dsq'){tot.appendChild(el('span','dnf',${tq('DSQ')}));why(r.reason)}
      else if(r.status==='dnf'&&r.classified&&r.totalMs!=null){tot.textContent=ms(r.totalMs);tot.appendChild(el('small','dnf',' '+${tq('DNF')}));gp.textContent=r.gapMs==null?'':gap(r.gapMs);why(r.reason)}
      else if(r.status==='dnf'){tot.appendChild(el('span','dnf',${tq('DNF')}));why(r.reason)}
      else{tot.appendChild(el('span','run',F(${tq('SS{0} next')},r.done+1)));if(r.done&&r.totalMs!=null)why(F(${tq('{0} so far')},ms(r.totalMs)))}
      // (not finished: the gap to the best over the stages it has driven, and which: the gaps while the event runs)
      if(r.liveGapMs!=null&&r.status!=='finished'&&r.status!=='dsq'&&!(r.status==='dnf'&&r.classified)){if(r.liveGapMs)gp.textContent=gap(r.liveGapMs);gp.appendChild(el('small',null,F(${tq('after SS{0}')},r.liveGapAfter)))}
      if(r.stewardMs&&r.status!=='dsq')tot.appendChild(el('small',null,' '+F(${tq('incl. {0} stewards')},secs(r.stewardMs))));
      row(tr,{pos:pos,drv:d,car:car,ss:ss,tot:tot,gp:gp});t.appendChild(tr)});
    h.setAttribute('data-nopage','');paginate(t,'event'+(g?GSEL:''),$('stwrap'));   // (30 a page: src/pager.js)
    scrollHint($('stwrap'))}
  // the drivers' comments on their stages, sent from the app (src/comments.js): every one for whoever runs the event (a
  // league's owner and admins, a cup's maker), else the viewer's own
  function comments(e){var box=$('comments');box.innerHTML='';var C=e.comments||[],all=e.me.readsComments;if(!C.length&&!all)return;
    add(box,el('h2',null,all?${tq("Drivers' comments")}:${tq('Your comments')}));
    box.appendChild(el('p','note',all?${tq('Sent from the app after their stages, for whoever runs the event: the other drivers do not see them.')}:${tq('Only you and whoever runs the event see them.')}));
    if(!C.length){box.appendChild(el('div','empty',${tq('No comments yet.')}));return}
    C.forEach(function(c){var it=el('div','decision'),d=el('div'),q=el('div','cmt','“'+c.text+'”');q.style.maxWidth='none';
      add(d,el('b',null,'SS'+(c.no+1)),' '+c.name,q,el('div','muted',when(c.updated)+(c.hidden?' · '+${tq('taken down by ACR Daily')}:'')));
      it.appendChild(d);box.appendChild(it)})}
  // the stewards' decisions, for everyone; the owner and admins add and take them back
  function stewards(e){var box=$('stewards');box.innerHTML='';var D=e.decisions||[];if(!D.length&&!e.me.staff)return;
    add(box,el('h2',null,${tq('Stewards')}));
    if(!D.length)add(box,el('div','empty',${tq('No decisions.')}));
    D.forEach(function(x){var it=el('div','decision');var d=el('div');
      // (an entry's DNF taken back, an entry retired, a stage's time set by the stewards: kept as they were decided)
      var tag=x.kind==='dsq'?el('b','bad',${tq('DSQ')}):x.kind==='reinstate'?el('b','good',${tq('DNF taken back')}):
        x.kind==='replay'?el('b',null,F(${tq('SS{0} replay asked for')},x.stage)):
        x.kind==='retire'?el('b','bad',${tq('Retired by the stewards')}):x.kind==='settime'?el('b',null,F(${tq('SS{0} time set: {1}')},x.stage,ms(x.ms))):
        el('b',x.ms<0?'good':'bad',x.stage?F(${tq('{0} on SS{1}')},secs(x.ms),x.stage):F(${tq('{0} on the total')},secs(x.ms)));
      add(d,tag,' '+x.driver+': '+x.reason);add(d,el('div','muted',F(${tq('by {0}')},x.by)+(x.at?' · '+when(x.at):'')));it.appendChild(d);
      if(e.me.staff&&(x.kind==='dsq'||x.kind==='time')){var rb=el('button','btn ghost small',x.kind==='dsq'?${tq('Reinstate')}:${tq('Take back')});rb.onclick=function(){
        (x.kind==='dsq'?api('/api/events/'+id+'/dsq',{steamId:x.steamId,remove:true}):api('/api/events/'+id+'/penalty',{remove:x.id})).then(load,function(er){msg('swm',er.message)})};it.appendChild(rb)}
      box.appendChild(it)});
    if(!e.me.staff)return;
    if(!e.standings.length){add(box,el('p','note',${tq('Penalties can be given once drivers have started.')}));return}
    var f=el('div','stewform');
    f.innerHTML='<label><span>${ts('Driver')}</span><select id="pd"></select></label><label><span>${ts('Applies to')}</span><select id="ps"></select></label>'+
      '<label><span>${ts('Seconds')}</span><input type="text" id="pt" placeholder="${ts('10 or -5')}"></label><label><span>${ts('Reason (everyone sees it)')}</span><input type="text" id="pr" maxlength="200" placeholder="${ts('e.g. cut at the hairpin after split 2')}"></label>';
    var bt=el('div','row');var ab=el('button','btn small',${tq('Add penalty')});var qb=el('button','btn danger small',${tq('Disqualify')});add(bt,ab,qb);f.appendChild(bt);box.appendChild(f);
    add(box,el('div','msg'));box.lastChild.id='swm';
    e.standings.forEach(function(r){var o=el('option',null,r.name+(r.status==='dsq'?' ('+${tq('DSQ')}+')':''));o.value=r.steamId;$('pd').appendChild(o)});
    var o0=el('option',null,${tq('The total')});o0.value='';$('ps').appendChild(o0);
    e.stages.forEach(function(s){var o=el('option',null,'SS'+s.no+' · '+s.name);o.value=String(s.no);$('ps').appendChild(o)});
    ab.onclick=function(){api('/api/events/'+id+'/penalty',{steamId:$('pd').value,stage:$('ps').value,seconds:$('pt').value.replace(',','.'),reason:$('pr').value})
      .then(load,function(er){msg('swm',er.message)})};
    qb.onclick=function(){var nm=$('pd').options[$('pd').selectedIndex].text;if(!confirm(F(${tq('Disqualify {0} from {1}? The reason is shown to everyone.')},nm,e.name)))return;
      api('/api/events/'+id+'/dsq',{steamId:$('pd').value,reason:$('pr').value}).then(load,function(er){msg('swm',er.message)})};
    // DNFs (24 Nov 2026): take a DNF back (the driver goes on from their next stage, the app with the car as it finished
    // the stage before), retire an entry, or set a stage's time (a finish the game lost: the entry moves on; or a
    // counted time corrected). The same driver, stage and reason fields; the time and its penalty below.
    var f2=el('div','stewform');f2.innerHTML='<label><span>${ts('Stage time (m:ss.sss)')}</span><input type="text" id="pst" placeholder="4:12.345"></label>'+
      '<label><span>${ts('Its penalty (s)')}</span><input type="text" id="psp" placeholder="0"></label>';
    var bt2=el('div','row');var rb2=el('button','btn small',${tq('Take back DNF')}),tb2=el('button','btn small',${tq('Set stage time')}),
      xb2=el('button','btn danger small',${tq('Retire (DNF)')}),yb2=el('button','btn ghost small',${tq('Ask for the replay')});add(bt2,rb2,tb2,xb2,yb2);f2.appendChild(bt2);box.insertBefore(f2,$('swm'));
    // (REPLAYS, src/replays.js: the driver's app sends that stage's replay by itself; the ones sent listed under)
    yb2.onclick=function(){if(!$('ps').value){msg('swm',${tq('Pick the stage the time is for.')});return}
      api('/api/events/'+id+'/steward',{steamId:$('pd').value,reason:$('pr').value||'stewards\\' check',op:'replay',stage:+$('ps').value})
        .then(function(r){if(r&&r.code)location.href='/r/'+r.code;else load()},function(er){msg('swm',er.message)})};
    fetch('/api/replays/event/'+id,{credentials:'same-origin'}).then(function(r){return r.ok?r.json():null}).then(function(j){
      if(!j||!j.replays||!j.replays.length)return;var rl=el('div','decision');add(rl,el('b',null,${tq('Replays sent')}));
      j.replays.forEach(function(x){var a=el('a',null,' '+x.name+' · SS'+(x.stage)+' · '+(x.verdict==='clean'?${tq('clean')}:${tq('wants a look')}));a.href='/r/'+x.code;add(rl,el('div',null,a))});
      box.insertBefore(rl,f2)});
    function stw(body){return api('/api/events/'+id+'/steward',Object.assign({steamId:$('pd').value,reason:$('pr').value},body)).then(load,function(er){msg('swm',er.message)})}
    function parseT(s){var m=/^\\s*(?:(\\d+):)?(\\d+(?:[.,]\\d+)?)\\s*$/.exec(s||'');return m?Math.round(((+(m[1]||0))*60+parseFloat(m[2].replace(',','.')))*1000):NaN}
    rb2.onclick=function(){stw({op:'reinstate'})};
    xb2.onclick=function(){var nm=$('pd').options[$('pd').selectedIndex].text;if(!confirm(F(${tq('Retire {0} from {1} (DNF)? The reason is shown to everyone.')},nm,e.name)))return;stw({op:'retire'})};
    tb2.onclick=function(){if(!$('ps').value){msg('swm',${tq('Pick the stage the time is for.')});return}
      var t=parseT($('pst').value);if(!(t>0)){msg('swm',${tq('Give the stage time as m:ss.sss')});return}
      stw({op:'time',stage:+$('ps').value,timeMs:t,penaltyMs:Math.round((parseFloat(($('psp').value||'0').replace(',','.'))||0)*1000)})};
    e.standings.forEach(function(r,i){if(r.status==='dnf')$('pd').options[i].text+=' ('+${tq('DNF')}+')'})}
  // a hidden event: a column that is hidden for every stage goes, and one line over the table says what and until when
  // (it said Hidden in every cell, six times a stage: a UI review, Nov 2026)
  function itin(e){var t=$('itin');t.innerHTML='';var S=e.stages,none=function(k){return S.length&&S.every(function(s){return s[k]==null})};
    var noName=none('name'),noLen=none('lengthM'),noTime=none('time'),noWx=none('weatherLabel'),gone=[];
    if(noName)gone.push(${tq('stage names')});if(noLen)gone.push(${tq('lengths')});if(noTime)gone.push(${tq('start times')});if(noWx)gone.push(${tq('weather')});
    // (a copy to change: the itinerary and settings in the importer's template; not while it hides them)
    var dlp=$('itdl');dlp.innerHTML='';dlp.hidden=!(e.revealed!==false&&!e.locked&&!gone.length&&S.length);
    if(!dlp.hidden)add(dlp,${tq('Copy this event: download it as a spreadsheet, change what you like, and import it as a new event.')}+' ',sheetLinks('/api/events/'+id+'/sheet'));
    $('itnote').hidden=!gone.length;$('itnote').textContent=gone.length?F(${tq('Hidden for now: {0}.')},gone.join(', '))+' '+revealWhen(e):'';
    var cols=1+(noName?0:1)+(noLen?0:1)+(noTime?0:1)+(noWx?0:1);
    var h=el('tr');h.appendChild(el('th',null,''));if(!noName)h.appendChild(el('th',null,${tq('Stage')}));if(!noLen)h.appendChild(el('th','r',${tq('Length')}));
    if(!noTime)h.appendChild(el('th','r',${tq('Start')}));if(!noWx)h.appendChild(el('th',null,${tq('Weather')}));if(cols>1)t.appendChild(h);
    var day=0;S.forEach(function(s){if(s.day!==day){day=s.day;var tr=el('tr','day'),td=el('td',null,F(${tq('Day {0}')},day));td.colSpan=cols;tr.appendChild(td);t.appendChild(tr)}
      if(s.service){var sp=el('tr','sp'),td2=el('td',null,${tq('Service park')});td2.colSpan=cols;sp.appendChild(td2);t.appendChild(sp)}
      var ps=e.season&&e.season.power&&e.season.power.length&&s.no===S.length?' ('+${tq('Power Stage')}+')':'';
      var tr2=el('tr');tr2.appendChild(el('td','pos','SS'+s.no+(noName?ps:'')));if(!noName)tr2.appendChild(el('td','drv',hid(s.name)+ps));
      if(!noLen)tr2.appendChild(el('td','r',km(s.lengthM)));if(!noTime)tr2.appendChild(el('td','r',hid(s.time)));if(!noWx)tr2.appendChild(el('td',null,hid(TD(s.weatherLabel))));t.appendChild(tr2)})}
  account().then(load);
  `, env, meta);
}

// ------------------------------------------------------------------ the event builder (shared)
// What an event races, as a form: its location, car or class, settings and itinerary (days, stages, service parks,
// weather, start times), and as asked its name, season and opening/closing time. A league's event (below), a
// head-to-head's challenge and a cup's matches (src/socialpages.js) are made with it. In a page's script:
//   var B=eventBuilder(box,{cat (GET /api/catalog), state: S, name: false | {label, placeholder}, seasons: [...] | null,
//     window: true | false, windowNote, limited, multi (several classes offered: a league's event), after: function(box){...}}); B.draw();
// It draws into box and draws again on every change (`after` adds the page's own buttons each time); S holds the
// form ({name, rally, carMode, car, carClass, rules, days: [[{track, time, weather, service}]], opens, closes,
// seasonId, hide: {weather, times, stages}}; what is missing gets the defaults, everything hidden for hide); B.body() is
// the event as the API takes it (checkEvent).
// builderFrom(S, event) fills S from an event of the API.
export const BUILDER_JS = () => `
function pad(n){return String(n).padStart(2,'0')}
function localInput(t){var d=new Date(t);return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes())}
function opt(sel,v,t,cur){var o=el('option',null,t);o.value=v;if(v===cur)o.selected=true;sel.appendChild(o)}
function builderFrom(S,x){S.rally=x.rally;S.carMode=x.car?'car':x.carClasses?'classes':'class';S.car=x.car||'';
  S.carClass=x.carClasses?x.carClasses[0]:x.carClass||'';S.carClasses=(x.carClasses||[]).slice();S.rules=x.rules;
  S.days=[];x.stages.forEach(function(s){while(S.days.length<s.day)S.days.push([]);S.days[s.day-1].push({track:s.track,time:s.time,weather:s.weather,service:s.service})});
  // (what it hides, as its maker set it: a copy came up with all three ticked whatever the source hid, Timo 21 Nov 2026)
  var hs=x.hideSet||x.hidden;if(hs)S.hide={weather:!!hs.weather,times:!!hs.times,stages:!!hs.stages}}
var LEVELS={off:${tq('off')},light:${tq('light')},severe:${tq('severe')},realistic:${tq('realistic')}};
function eventBuilder(box,o){var CAT=o.cat,S=o.state,limited=!!o.limited;
  // (the stages may come from several locations, checkEvent: S.rally is the one new stages are taken from)
  function rally(){return CAT.rallies.filter(function(r){return r.name===S.rally})[0]}
  function placeOf(track){return CAT.rallies.filter(function(r){return r.stages.some(function(s){return s.track===track})})[0]}
  function stageOf(track){var r=placeOf(track);return r?r.stages.filter(function(s){return s.track===track})[0]:null}
  if(!rally()){var f0=(S.days||[]).reduce(function(a,d){return a.concat(d)},[])[0];S.rally=(f0&&placeOf(f0.track)||{}).name||''}
  function newStage(day){var st=rally().stages,used=S.days.reduce(function(a,d){return a.concat(d)},[]).map(function(x){return x.track});
    var free=st.filter(function(s){return used.indexOf(s.track)<0})[0]||st[0];var last=day.length?day[day.length-1].time:'08:00';
    var h=Math.min(22,parseInt(last,10)+(day.length?2:0));return{track:free?free.track:'',time:pad(h)+':'+last.slice(3),weather:'Clear',service:false}}
  function fresh(){S.days=[[newStage([])]];S.days[0][0].service=true}
  if(!S.rally)S.rally='Wales';if(!S.carMode)S.carMode='car';
  if(!S.rules)S.rules=Object.assign({},CAT.rules.defaults);
  if(!S.car)S.car=CAT.cars[0].name;if(!S.carClass)S.carClass=CAT.classes[0].cls;if(!S.carClasses)S.carClasses=[];
  if(S.carMode==='classes'&&!o.multi)S.carMode='class';
  if(!S.hide)S.hide={weather:true,times:true,stages:true};   // (src/hidden.js: the default for every new event)
  if(!S.days||!S.days.some(function(d){return d.length})){S.days=[[]];fresh()}
  function draw(){var b=box;b.innerHTML='';
    var top=el('div','twocol');b.appendChild(top);
    if(o.name!==false){var nm=o.name||{},nl=el('label'),ni=el('input');add(nl,el('span',null,nm.label||${tq('Event name')}));
      ni.type='text';ni.id='fn';ni.maxLength=60;ni.placeholder=nm.placeholder||${tq('e.g. Round 3: Rally Wales')};ni.value=S.name||'';
      ni.oninput=function(){S.name=this.value};nl.appendChild(ni);top.appendChild(nl)}
    var rl=el('label'),rs=el('select');add(rl,el('span',null,${tq('Location')}));rs.id='fr';rl.appendChild(rs);top.appendChild(rl);
    CAT.rallies.forEach(function(r){opt(rs,r.name,TD(r.name)+(r.surface?' ('+TD(r.surface).toLowerCase()+')':''),S.rally)});
    // (where new stages come from; the itinerary kept, unless it is still the one stage a new event starts with)
    rs.onchange=function(){var all=S.days.reduce(function(a,d){return a.concat(d)},[]),only=all.length===1&&!S.touched;
      S.rally=this.value;if(only)fresh();draw()};
    if(limited){rs.disabled=true}
    if(o.seasons){var sl=el('label');sl.innerHTML='<span>${ts('Season (its championship)')}</span>';var ss=el('select');
      o.seasons.forEach(function(s){opt(ss,String(s.id),s.name,S.seasonId)});
      opt(ss,'new',o.seasons.length?${tq('A new season (WRC points; set it on the championship page)')}:${tq('Season 1 (made now, WRC points; set it on the championship page)')},S.seasonId);
      opt(ss,'',${tq('One-off: no championship')},S.seasonId);ss.onchange=function(){S.seasonId=this.value};sl.appendChild(ss);b.appendChild(sl)}
    if(o.window){var w=el('div','twocol');w.innerHTML='<label><span>${ts('Opens (your time)')}</span><input type="datetime-local" id="fo"></label><label><span>${ts('Closes (your time)')}</span><input type="datetime-local" id="fc"></label>';b.appendChild(w);
      $('fo').value=localInput(S.opens);$('fc').value=localInput(S.closes);
      $('fo').onchange=function(){S.opens=new Date(this.value).getTime()};$('fc').onchange=function(){S.closes=new Date(this.value).getTime()};
      if(o.windowNote)add(b,el('p','note',o.windowNote))}
    if(limited){if(o.window)$('fo').disabled=true;add(b,el('p','note',${tq('Drivers have started. Only the name, season, a later close and what it hides can change: it can show more, not hide more.')}));hiding(b,true)}
    if(!limited){
      var cm=el('label');cm.innerHTML='<span>${ts('Car')}</span>';b.appendChild(cm);
      var rd=el('div','radio');rd.innerHTML='<label><input type="radio" name="cm" value="car"><span>${ts('One car for everyone')}</span></label><label><input type="radio" name="cm" value="class"><span>${ts('A class: each driver picks a car of it')}</span></label>'+
        (o.multi?'<label><input type="radio" name="cm" value="classes"><span>${ts('Several classes: each has its own results')}</span></label>':'');b.appendChild(rd);
      [].forEach.call(document.querySelectorAll('input[name=cm]'),function(x){x.checked=x.value===S.carMode;x.onchange=function(){S.carMode=this.value;draw()}});
      var carsOf=function(k){return CAT.cars.filter(function(c){return c.cls===k}).map(function(c){return c.name}).join(', ')};
      if(S.carMode==='classes'){var ck=el('div','classes');b.appendChild(ck);
        CAT.classes.forEach(function(k){var l=el('label','sp'),cb=el('input');cb.type='checkbox';cb.checked=S.carClasses.indexOf(k.cls)>=0;
          cb.onchange=function(){S.carClasses=CAT.classes.map(function(x){return x.cls}).filter(function(c){return c===k.cls?cb.checked:S.carClasses.indexOf(c)>=0})};
          add(l,cb,el('b',null,k.cls),' ('+k.group+'): '+carsOf(k.cls));ck.appendChild(l)})}
      else{var cs=el('select');cs.style.marginTop='8px';b.appendChild(cs);
        if(S.carMode==='car'){CAT.cars.forEach(function(c){opt(cs,c.name,c.name+' · '+c.cls,S.car)});cs.onchange=function(){S.car=this.value}}
        else{CAT.classes.forEach(function(k){opt(cs,k.cls,k.cls+' ('+k.group+'): '+carsOf(k.cls),S.carClass)});cs.onchange=function(){S.carClass=this.value}}}
      rules(b);hiding(b);days(b)}
    if(o.after)o.after(b);summary()}
  // what the drivers don't see until it ends (src/hidden.js), so nobody practises it beforehand
  function hiding(b,showOnly){add(b,el('h3',null,${tq('Hidden until it ends')}));
    add(b,el('p','note',${tq('Kept from the drivers so nobody practises it beforehand. Each driver sees the set-up when they press DRIVE in the app; you see everything.')}));
    var g=el('div','classes');[['stages',${tq('Stage names (and their lengths and maps)')}],['weather',${tq('Weather')}],['times',${tq("Stage times: the start time of day, and the drivers' results")}]].forEach(function(x){
      var l=el('label','sp'),cb=el('input');cb.type='checkbox';cb.checked=!!S.hide[x[0]];cb.onchange=function(){S.hide[x[0]]=this.checked};
      if(showOnly&&!cb.checked)cb.disabled=true;   // (started: it can show more, not hide more)
      add(l,cb,x[1]);g.appendChild(l)});b.appendChild(g)}
  function sel(label,key,values,names){var l=el('label');add(l,el('span',null,label));var s=el('select');values.forEach(function(v,i){opt(s,v,names?names[i]:LEVELS[v]||v,String(S.rules[key]))});
    s.onchange=function(){S.rules[key]=this.value==='true'?true:this.value==='false'?false:this.value;draw()};l.appendChild(s);return l}
  function rules(b){add(b,el('h3',null,${tq('Settings')}));var g=el('div','twocol');
    g.appendChild(sel(${tq("Hardcore Mode (the game's own)")},'hardcore',['false','true'],[${tq('Off')},${tq('On: damage, wear, failures and penalties at Realistic')}]));
    if(S.rules.hardcore)Object.assign(S.rules,{damage:true,damageIntensity:'realistic',wear:'realistic',failures:'realistic',penalty:'realistic'});
    else{g.appendChild(sel(${tq('Damage')},'damage',['true','false'],[${tq('On (repair it in the service parks)')},${tq('Off')}]));
      if(S.rules.damage)g.appendChild(sel(${tq('Damage intensity')},'damageIntensity',['light','severe','realistic']));
      g.appendChild(sel(${tq('Wear')},'wear',CAT.rules.levels));g.appendChild(sel(${tq('Mechanical failures')},'failures',CAT.rules.levels))}
    g.appendChild(sel(${tq('Manual respawn')},'respawn',['true','false'],[${tq('On')},${tq('Off (stuck = retire)')}]));
    if(!S.rules.hardcore)g.appendChild(sel(${tq('Penalties (cuts, respawns, jump starts...)')},'penalty',CAT.rules.penalty));
    g.appendChild(sel(${tq('Driving aids')},'assists',CAT.rules.assists||['any','off'],[${tq("Each driver's choice")},${tq('Off: no ABS, traction control or starting handbrake assist')}]));
    var rl=el('label');add(rl,el('span',null,${tq('A retirement (DNF)')}));var rs=el('select');
    [0,1,2,5,10,15,30].forEach(function(m){opt(rs,String(m),m?F(${tq('Stays in: slowest time + {0} min per stage missed')},m):${tq('Out of the event')},String(S.rules.retire||0))});
    rs.onchange=function(){var m=+this.value;if(m)S.rules.retire=m;else delete S.rules.retire};rl.appendChild(rs);g.appendChild(rl);b.appendChild(g)}
  function days(b){add(b,el('h3',null,${tq('Itinerary')}));var no=0;
    S.days.forEach(function(d,di){var box=el('div','day');var hd=el('div','dayhead');add(hd,el('b',null,F(${tq('Day {0}')},di+1)));
      if(S.days.length>1){var x=el('button','btn ghost small',${tq('Remove day')});x.onclick=function(){S.days.splice(di,1);draw()};hd.appendChild(x)}
      box.appendChild(hd);box.appendChild(el('div','sprow',${tq('Service park (the day starts here)')}));
      d.forEach(function(s,si){no++;if(si>0&&s.service)box.appendChild(el('div','sprow',${tq('Service park')}));
        var r=el('div','st');add(r,el('span','no','SS'+no));
        // (every location's stages, the one new stages come from first: an event may cross several)
        var ss=el('select');[rally()].concat(CAT.rallies.filter(function(x){return x!==rally()})).forEach(function(g){if(!g)return;
          var og=el('optgroup');og.label=TD(g.name);g.stages.forEach(function(x){opt(og,x.track,x.name+' · '+km(x.lengthM),s.track)});ss.appendChild(og)});
        ss.onchange=function(){s.track=this.value;S.touched=true;summary()};r.appendChild(ss);
        var ti=el('input');ti.type='time';ti.value=s.time;ti.onchange=function(){s.time=this.value};r.appendChild(ti);
        var ws=el('select','w');CAT.weathers.forEach(function(w){opt(ws,w.id,TD(w.label),s.weather)});ws.onchange=function(){s.weather=this.value};r.appendChild(ws);
        var spl=el('label','sp');if(si>0){var cb=el('input');cb.type='checkbox';cb.checked=!!s.service;cb.onchange=function(){s.service=this.checked;draw()};add(spl,cb,${tq('service park before')})}r.appendChild(spl);
        var tools=el('span','tools');
        var up=el('button',null,'↑');up.title=${tq('Move up')};up.disabled=si===0;up.onclick=function(){d.splice(si-1,0,d.splice(si,1)[0]);fixSp(d);draw()};
        var dn=el('button',null,'↓');dn.title=${tq('Move down')};dn.disabled=si===d.length-1;dn.onclick=function(){d.splice(si+1,0,d.splice(si,1)[0]);fixSp(d);draw()};
        var rm=el('button',null,'✕');rm.title=${tq('Remove')};rm.onclick=function(){d.splice(si,1);if(!d.length&&S.days.length>1)S.days.splice(di,1);else if(!d.length)d.push(newStage(d));fixSp(d);draw()};
        add(tools,up,dn,rm);r.appendChild(tools);box.appendChild(r)});
      var as=el('button','btn ghost small',${tq('+ Add stage')});as.style.marginTop='10px';as.onclick=function(){d.push(newStage(d));draw()};box.appendChild(as);b.appendChild(box)});
    var ad=el('button','btn ghost small',${tq('+ Add day')});ad.style.marginTop='12px';ad.onclick=function(){var nd=[newStage([])];nd[0].service=true;S.days.push(nd);draw()};
    if(S.days.length>=CAT.limits.days)ad.disabled=true;b.appendChild(ad);add(b,el('div','sum'));b.lastChild.id='sum'}
  function fixSp(d){if(d.length)d[0].service=true}
  function flat(){var out=[];S.days.forEach(function(d,di){d.forEach(function(s,si){out.push({track:s.track,day:di+1,service:si===0?true:!!s.service,weather:s.weather,time:s.time})})});return out}
  function summary(){var s=$('sum');if(!s||limited)return;var st=flat(),m=0;st.forEach(function(x){var g=stageOf(x.track);if(g)m+=g.lengthM});
    s.textContent=F(${tq('{0} · {1} · {2} of stages (limits: {3} stages, {4} days)')},P(${tqp('{0} stage', '{0} stages')},st.length),P(${tqp('{0} day', '{0} days')},S.days.length),km(m),CAT.limits.stages,CAT.limits.days)}
  function body(){var b={rally:S.rally,rules:S.rules,stages:flat(),hide:S.hide};if(o.name!==false)b.name=S.name;if(o.window){b.opens=S.opens;b.closes=S.closes}
    if(S.carMode==='car')b.car=S.car;else if(S.carMode==='classes')b.carClasses=S.carClasses;else b.carClass=S.carClass;return b}
  // an event from a sheet (src/eventsheet.js: the body of an imported event) put in the form; the page sets its name and dates
  function load(x){builderFrom(S,x);var f0=S.days.reduce(function(a,d){return a.concat(d)},[])[0];
    S.rally=(f0&&placeOf(f0.track)||{}).name||S.rally;S.touched=true;draw()}
  return {S:S,draw:draw,body:body,load:load}}
`;

// ------------------------------------------------------------------ events from a spreadsheet (the importer, shared)
// A folded panel above a builder: the template to download, a file (.xlsx or .csv) to choose or drop, and what the server
// found in it (src/eventsheet.js, POST /api/events/import): every problem with its row and column, or the events it
// would make. One event goes straight into the form below; several can be made at once (a league) or loaded one at a time.
//   eventImporter(box,{mode: 'league' | 'rally' | 'cup', leagueId, open, scroll: the node to scroll to,
//     load: function(event) (puts it in the form), create: function(events) -> promise (a league: all of them at once)})
export const IMPORT_JS = () => `
function eventImporter(box,o){var mode=o.mode||'league',tz='',last=null;
  try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||''}catch(e){}
  var d=el('details','imp');if(o.open)d.open=true;d.appendChild(el('summary',null,${tq('Import from Excel or CSV')}));
  var body=el('div','impbody');d.appendChild(body);
  add(body,el('p','note',mode==='league'?${tq('Build many events in a spreadsheet: one row is one stage, and the next event name starts the next event, so a whole season is one file. Download the template, fill it in, then choose the file. Every problem is listed with its row and column; nothing is made until you press the button.')}
    :mode==='rally'?${tq('Build the rally in a spreadsheet: one row is one stage. Download the template, fill it in, then choose the file: it fills the form below, and every problem is listed with its row and column.')}
    :${tq("Build the matches' event in a spreadsheet: one row is one stage. Download the template, fill it in, then choose the file: it fills the form below, and every problem is listed with its row and column.")}));
  var dl=el('div','dl');body.appendChild(dl);
  [[${tq('Excel template (.xlsx, with drop-downs)')},'/api/events/template.xlsx?for='+mode,true],[${tq('CSV template')},'/api/events/template.csv?for='+mode],
   [${tq('CSV template with semicolons (Excel in Europe)')},'/api/events/template.csv?sep=;&for='+mode]].forEach(function(x){
    var a=el('a','btn small'+(x[2]?'':' ghost'),x[0]);a.href=x[1];a.setAttribute('download','');dl.appendChild(a)});
  var drop=el('label','drop'),inp=el('input');inp.type='file';inp.accept='.xlsx,.csv,.tsv,.txt,text/csv';
  add(drop,${tq('Choose the filled-in file (.xlsx or .csv), or drop it here')},inp);body.appendChild(drop);
  var res=el('div');body.appendChild(res);
  drop.ondragover=function(e){e.preventDefault();drop.className='drop over'};drop.ondragleave=function(){drop.className='drop'};
  drop.ondrop=function(e){e.preventDefault();drop.className='drop';if(e.dataTransfer.files[0])run(e.dataTransfer.files[0])};
  inp.onchange=function(){var f=inp.files[0];if(f)run(f);inp.value=''};
  function run(file){res.innerHTML='';add(res,el('p','note',F(${tq('Reading {0}…')},file.name)));
    fetch('/api/events/import?for='+mode+'&tz='+encodeURIComponent(tz)+(o.leagueId?'&league='+encodeURIComponent(o.leagueId):''),
      {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream'},body:file})
      .then(function(r){return r.json().catch(function(){return{}}).then(function(j){if(!r.ok)throw new Error(r.status===401?${tq('Sign in with Steam first.')}:j.error||('error '+r.status));return j})})
      .then(show,function(e){res.innerHTML='';add(res,el('div','msg bad',e.message))})}
  function row(){var r=el('tr');for(var i=0;i<arguments.length;i++){var c=arguments[i],td=el('td',c&&c.cls);
      if(c&&c.nodes)add(td,c.nodes);else td.textContent=c&&c.text!=null?c.text:c==null?'':c;r.appendChild(td)}return r}
  function show(j){res.innerHTML='';last=j;
    if(j.errors.length){
      add(res,el('div','imphead bad',P(${tqp('{0} problem found. Nothing was imported: fix it in your sheet and choose the file again.','{0} problems found. Nothing was imported: fix them in your sheet and choose the file again.')},j.errors.length+j.more)));
      var t=el('table'),h=el('thead');h.appendChild(row({text:${tq('Row')}},{text:${tq('Column')}},{text:${tq('What is wrong')}}));
      for(var i=0;i<h.firstChild.children.length;i++)h.firstChild.children[i].outerHTML=h.firstChild.children[i].outerHTML.replace(/^<td/,'<th').replace(/td>$/,'th>');
      t.appendChild(h);var tb=el('tbody');
      j.errors.forEach(function(x){var m=el('div',null,x.message);if(x.event)m.appendChild(el('small',null,F(${tq('Event: {0}')},x.event)));
        tb.appendChild(row({cls:'rw',text:x.row==null?'–':x.row},{cls:'cl',text:x.column||''},{nodes:m}))});
      t.appendChild(tb);var w=el('div','tablewrap');w.appendChild(t);res.appendChild(w);
      if(j.more)add(res,el('p','note',P(${tqp('…and {0} more problem.','…and {0} more problems.')},j.more)));
      warns(j);return}
    var n=j.events.length;
    if(!n){add(res,el('div','msg bad',${tq('No events in the file.')}));return}
    if(n===1&&mode!=='league'||n===1){var ev=j.events[0];use(ev);
      add(res,el('div','imphead good',F(${tq('Loaded {0} into the form below: check it, change what you like, then save.')},ev.name?'"'+ev.name+'"':${tq('the event')})));warns(j);return}
    add(res,el('div','imphead good',P(${tqp('{0} event found.','{0} events found.')},n)));
    var t2=el('table'),h2=el('thead');h2.appendChild(row({text:${tq('Event')}},{text:${tq('Where')}},{text:${tq('Car')}},{text:${tq('Stages')}},mode==='cup'?'':{text:${tq('Open')}},mode==='league'?{text:${tq('Season')}}:'',''));
    for(var k=0;k<h2.firstChild.children.length;k++)h2.firstChild.children[k].outerHTML=h2.firstChild.children[k].outerHTML.replace(/^<td/,'<th').replace(/td>$/,'th>');
    t2.appendChild(h2);var b2=el('tbody');
    j.events.forEach(function(ev){var s=ev.summary,ld=el('button','btn ghost small',${tq('Load into the form')});
      ld.onclick=function(){use(ev);add(res,'')};
      var sn=ev.season==='new'?${tq('A new season')}:ev.season==null?${tq('One-off')}:((j.seasons||[]).filter(function(x){return x.id===ev.season})[0]||{name:String(ev.season||'')}).name;
      var nm=el('div',null,ev.name||'');nm.appendChild(el('small',null,F(${tq('rows {0}–{1}')},ev.rows[0],ev.rows[1])));
      b2.appendChild(row({nodes:nm},s.places.map(TD).join(' · '),s.car||s.classes.join(', '),F(${tq('{0} · {1} km')},s.stages,s.km),
        mode==='cup'?'':when(s.opens)+' → '+when(s.closes),mode==='league'?sn:'',{nodes:ld}))});
    t2.appendChild(b2);var w2=el('div','tablewrap');w2.appendChild(t2);res.appendChild(w2);
    warns(j);
    if(mode==='league'&&o.create){var a=el('div','acts'),cb=el('button','btn',P(${tqp('Create {0} event','Create {0} events')},n)),mm=el('span','msg');
      cb.onclick=function(){cb.disabled=true;mm.className='msg';mm.textContent='';
        o.create(j.events).catch(function(e){cb.disabled=false;mm.className='msg bad';mm.textContent=e.message})};
      add(a,cb,mm);res.appendChild(a)}}
  function warns(j){if(!j.warnings||!j.warnings.length)return;var u=el('ul','warns');
    j.warnings.forEach(function(x){u.appendChild(el('li',null,(x.row?F(${tq('Row {0}: ')},x.row):'')+x.message))});res.appendChild(u)}
  function use(ev){o.load(ev);var sc=o.scroll;if(sc&&sc.scrollIntoView)sc.scrollIntoView({behavior:'smooth',block:'start'})}
  box.innerHTML='';box.appendChild(d)}
`;

// ------------------------------------------------------------------ /rallies/new: a rally (0033), anyone's
// One event, held by a league of its own (kind 'event'): public (every app lists it) or private (listed with a lock:
// its code, or its invite link with the code in it, lets a driver in; 0043).
// ?edit=<event id>: its maker changes it; ?from=<event id>: a new rally like that event.
export function rallyNewPage(env) {
  return shell(t('New rally') + ' · ACR Daily', `
  <div class="top"><div class="kick"><span class="kindtag rally">${t('Rally')}</span></div><h1 id="h">${t('New rally')}</h1>
  <p class="note">${t("One event, open to every driver: a public one is in everyone's app, under RALLIES. One location or several, a service park at the start of each day, stages in time order. Each driver gets one go.")}</p></div>
  <div id="imp"></div>
  <div class="builder" id="b"><div class="empty">${t('Loading…')}</div></div>`, `${BUILDER_JS()}${IMPORT_JS()}
  var Q=new URLSearchParams(location.search),eventId=+Q.get('edit')||null,FROM=+Q.get('from')||null,CAT=null,EV=null,limited=false,B=null;
  var S={name:'',rally:'Wales',carMode:'car',car:'',carClass:'',carClasses:[],rules:null,opens:null,closes:null,days:[[]],about:'',pub:true};
  navOn('leagues');
  function start(){Promise.all([api('/api/catalog'),eventId?api('/api/events/'+eventId):null,FROM&&!eventId?api('/api/events/'+FROM):null]).then(function(r){
      CAT=r[0];EV=r[1];var src=r[2],now=Date.now();
      if(EV){if(EV.league.kind!=='event'||!EV.me.owner){fail(${tq('Only its maker can change a rally.')});return}
        $('h').textContent=${tq('Edit rally')};limited=EV.standings.length>0;
        S.name=EV.name;S.opens=EV.opens;S.closes=EV.closes;builderFrom(S,EV);S.about=EV.league.about||'';S.pub=EV.league.public;
        var hs=EV.hideSet||EV.hidden;S.hide=hs?{weather:!!hs.weather,times:!!hs.times,stages:!!hs.stages}:{weather:false,times:false,stages:false}}
      else if(src){builderFrom(S,src);S.name=src.name;var len=src.closes-src.opens;S.opens=Math.max(src.closes,Math.ceil(now/3600000)*3600000);S.closes=S.opens+len;
        if(src.league.kind==='event'){S.about=src.league.about||'';S.pub=src.league.public}}
      else{S.opens=Math.ceil(now/3600000)*3600000;S.closes=S.opens+7*86400000}
      B=eventBuilder($('b'),{cat:CAT,state:S,seasons:null,window:true,limited:limited,multi:true,after:function(b){
        var f=el('div');f.style.marginTop='22px';
        f.innerHTML='<label><span>${ts('About (optional)')}</span><textarea id="ra" maxlength="600" placeholder="${ts("What it is, what you would like drivers to keep to, your Discord...")}"></textarea></label>'+
          '<label><span>${ts('Who can drive it')}</span></label><div class="radio"><label><input type="radio" name="rp" value="1"><span>${ts("Public: in every driver's app")}</span></label>'+
          '<label><input type="radio" name="rp" value="0"><span>${ts('Private: listed with a lock, drivers need its code')}</span></label></div>';
        b.appendChild(f);$('ra').value=S.about;$('ra').oninput=function(){S.about=this.value};
        [].forEach.call(f.querySelectorAll('input[name=rp]'),function(x){x.checked=(x.value==='1')===!!S.pub;x.onchange=function(){S.pub=this.value==='1'}});
        var sv=el('button','btn',eventId?${tq('Save changes')}:${tq('Create the rally')});sv.style.marginTop='22px';sv.onclick=save;b.appendChild(sv);add(b,el('div','msg'));b.lastChild.id='fm'}});
      B.draw();
      if(!eventId)eventImporter($('imp'),{mode:'rally',scroll:$('b'),load:function(ev){S.name=ev.name;S.opens=ev.body.opens;S.closes=ev.body.closes;B.load(ev.body)}})}).catch(function(e){fail(e.status===401?${tq('Sign in with Steam first.')}:e.message)})}
  function fail(t){var b=$('b');b.innerHTML='';add(b,el('div','empty',t));if(!ME)b.appendChild(steamBtn())}
  function save(){var b=this;b.disabled=true;
    var body=limited?{name:S.name,closes:S.closes,hide:S.hide}:B.body();body.about=S.about;body.public=!!S.pub;
    api(eventId?'/api/events/'+eventId+'/edit':'/api/rallies',body).then(function(j){location.href='/e/'+(eventId||j.id)},function(e){b.disabled=false;msg('fm',e.message)})}
  account().then(function(me){if(!me){fail(${tq('Sign in with Steam first.')});return}start()});
  `, env);
}

// ------------------------------------------------------------------ /l/:id/new, /e/:id/edit: a league's event
export function eventEditPage({ leagueId = null, eventId = null }, env) {
  return shell((eventId ? t('Edit event') : t('New event')) + ' · ACR Daily', `
  <div class="top"><div class="kick" id="kick">${t('New event')}</div><h1 id="h">${eventId ? t('Edit event') : t('New event')}</h1>
  <p class="note">${t('One location or several, a service park at the start of each day, stages in time order. Each driver gets one go.')}</p></div>
  <div id="imp"></div>
  <div class="builder" id="b"><div class="empty">${t('Loading…')}</div></div>`, `${BUILDER_JS()}${IMPORT_JS()}
  var leagueId=${JSON.stringify(leagueId)},eventId=${JSON.stringify(eventId)},CAT=null,EV=null,LG=null,limited=false,B=null;
  var FROM=new URLSearchParams(location.search).get('from');
  var S={name:'',rally:'Wales',carMode:'car',car:'',carClass:'',carClasses:[],rules:null,opens:null,closes:null,days:[[]],seasonId:''};
  function nextName(n){var m=/^(.*?)(\\d+)(\\D*)$/.exec(n);return m?m[1]+(+m[2]+1)+m[3]:n+' 2'}   // "Round 2" -> "Round 3"
  function start(){Promise.all([api('/api/catalog'),eventId?api('/api/events/'+eventId):null,FROM&&!eventId?api('/api/events/'+FROM):null]).then(function(r){
      CAT=r[0];EV=r[1];var src=r[2];leagueId=EV?EV.league.id:leagueId;
      return api('/api/leagues/'+leagueId).then(function(lg){LG=lg;
        if(!lg.me.staff){fail(EV?${tq("Only the championship's owner and admins can edit its events.")}:${tq("Only the championship's owner and admins can make events.")});return}
        if(EV){$('kick').textContent=F(${tq('{0} · edit')},lg.name);limited=EV.standings.length>0;
          S.name=EV.name;S.opens=EV.opens;S.closes=EV.closes;S.seasonId=EV.seasonId==null?'':String(EV.seasonId);builderFrom(S,EV);
          var hs=EV.hideSet||EV.hidden;S.hide=hs?{weather:!!hs.weather,times:!!hs.times,stages:!!hs.stages}:{weather:false,times:false,stages:false}}
        else{$('kick').textContent=F(${tq('{0} · new event')},lg.name);
          var ss=lg.seasons;S.seasonId=ss.length?String(ss[ss.length-1].id):'new';
          if(src){builderFrom(S,src);S.name=nextName(src.name);var len=src.closes-src.opens;S.opens=Math.max(src.closes,Math.ceil(Date.now()/3600000)*3600000);S.closes=S.opens+len;
            S.seasonId=src.seasonId==null?'':String(src.seasonId);$('h').textContent=${tq('Next round')}}
          else{var now=Date.now();S.opens=Math.ceil(now/3600000)*3600000;S.closes=S.opens+7*86400000}}
        B=eventBuilder($('b'),{cat:CAT,state:S,seasons:LG.seasons,window:true,limited:limited,multi:true,after:function(b){
          var sv=el('button','btn',eventId?${tq('Save changes')}:${tq('Create event')});sv.style.marginTop='22px';sv.onclick=save;b.appendChild(sv);add(b,el('div','msg'));b.lastChild.id='fm'}});
        B.draw();
        // (new events only: a sheet makes events, it does not change one)
        if(!eventId)eventImporter($('imp'),{mode:'league',leagueId:leagueId,open:true,scroll:$('b'),
          load:function(ev){S.name=ev.name;S.opens=ev.body.opens;S.closes=ev.body.closes;S.seasonId=ev.season==='new'?'new':ev.season==null?'':String(ev.season);B.load(ev.body)},
          create:function(evs){return api('/api/leagues/'+leagueId+'/importevents',{events:evs.map(function(e){return Object.assign({},e.body,{seasonId:e.season})})}).then(function(){location.href='/l/'+leagueId})}})})}).catch(function(e){fail(e.status===401?${tq('Sign in with Steam first.')}:e.message)})}
  function fail(t){var b=$('b');b.innerHTML='';add(b,el('div','empty',t));if(!ME)b.appendChild(steamBtn())}
  function save(){var b=this;b.disabled=true;var season=S.seasonId===''?null:S.seasonId;
    var body=B.body();body.seasonId=season;
    if(limited)body={name:S.name,closes:S.closes,seasonId:season,hide:S.hide};
    api(eventId?'/api/events/'+eventId+'/edit':'/api/leagues/'+leagueId+'/events',body).then(function(j){
      location.href='/e/'+(eventId||j.id)},function(e){b.disabled=false;msg('fm',e.message)})}
  account().then(function(me){if(!me){fail(${tq('Sign in with Steam first.')});return}start()});
  `, env);
}
