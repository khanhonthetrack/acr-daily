# ACR Daily

Two daily stages, random cars and one global leaderboard for **Assetto Corsa Rally**.
Players run a small Windows app next to the game. It reads the game's telemetry, judges the run, shows its
own timer over the game's timer, and sends finished runs to the server. The server takes each result as the
app sent it and keeps a board per daily.

**Play:** <https://acrdaily.com> (download the app there).
**Discord:** <https://acrdaily.com/discord> (chat, ideas, bug reports; the live timing bot).
**Run your own server:** [SETUP.md](SETUP.md).

Open source under the [MIT licence](LICENSE). Code: <https://github.com/khanhonthetrack/acr-daily>. Issues and pull requests are welcome.

## The rules

| | |
|---|---|
| Dailies | **Two per day**, new at 00:00 UTC. Each has its own stage (never the same one twice in a day), a **random car** from all 18 in the game (`server/src/cars.js`), **conditions** (weather + time of day, `server/src/conditions.js`) and its own board. Each is a **one-stage Rally Weekend** in the game: the app's **DRIVE** button sets it up in the game's save (a backup is kept; `client/acr_daily/rallyweekend.py`) with the stage, car, weather and time of day (time standing still), penalty level Light, manual respawn on, damage on (light damage, light wear, no mechanical failures), one AI opponent and you first on the road. DRIVE never touches a Rally Weekend the player has in progress. |
| Your time | **The game's own.** After a Rally Weekend stage the game writes its official result into its save: stage time, penalty (respawns, cuts, jump starts) and splits. The game writes it once you go on from its results screen; the app reads it then and sends it, and the board time is *the game's stage time + its penalty*. A finished run waiting for it is kept on disk, so closing the app loses nothing: it is looked for again when the app opens. While it waits the app only looks at the save's time and size, and reads it once the game has written it and left it alone for 10 s (`saveslot.SaveWatch`: the game writes it in bursts a few seconds apart): the game wants its save to itself while it writes it, and a read at that moment can make the game's write fail. A finished run without the game's result (the game closed before saving it, e.g. stuck on its loading screen, or the stage started again from its results screen: the app reads the save as the next run starts) goes in with **the app's own time** (apps 0.1.4 to 0.1.5; from the 0.1.5.x test builds, `app.OFFICIAL_ONLY`, there is none: such a run doesn't count, and isn't a DNF either. A daily's is sent with status `void`, and the server forgets its start, so the next run can count (`server/src/voids.js`, test builds only, no limit, each kept in `voided_runs` for the admin). A time trial run is simply not sent), the last line of support, but only for a run without respawns: its stage clock (the game's penalty without respawns is nearly always none). With any respawn the game's penalty can't be known, so the run is a DNF (`server/src/apptime.js`). Such times look like any other on the boards and in Discord; only the admin sees them, flagged for review, who can take one off (`admin.py reject` / `tt-reject`) if it looks wrong. Either way the driver's report goes to the admin (*Sent by the app* below). A time the game saved for another run is a DNF. A lost result with respawns (whose penalty can't be known) is a DNF; the admin looks at such DNFs case by case (the driver's report carries the game's save as the app last read it, from 0.1.5) and can put one on the board (`admin.py reinstate <id> [penalty s]`: the app's clock + the game's penalty when known, else + 10 s a respawn). If the game wrote its save after the finish yet it holds no Rally Weekend result at all, the stage was most likely driven as a Single Rally Stage, which keeps no time: the app tells the driver to drive the dailies through Rally Weekend (DRIVE sets it up), and the report says so. While a run waits, the app's timer window says in orange what saves it. When the wait ends the app plays a system sound and shows a Windows notification: the official time saved, or lost and why (`client/acr_daily/notify.py`, from 0.1.5; Settings › Drive › **Sound and notification** turns it off). |
| Which run counts | **No button to press** (from tester build 0.1.5.48: `app.COMMIT_REQUIRED` off, the owner's call, 19 Nov 2026): the first run of a daily counts from its start, as up to 0.1.5, and the daily's start line says once what makes it count (the timer's alert, in the game too: *ONLY RALLY WEEKEND COUNTS · other modes don't count · don't change game settings · restart or quit is a DNF, in any mode*; a red banner over the daily cards says the same). The app can't tell the game's mode at the start (the game writes a one-stage Rally Weekend into its save only once the stage is finished: 0.1.5.1's `app.in_rally` took every real run for practice, report #175; `app.PRACTICE_CHECK` off), so a restart or quitting is a DNF whatever the mode; a run finished in another mode has no official time and is ignored (below). From 0.1.5.x test builds up to 0.1.5.47 a daily counted only from a run the driver committed to with **START OFFICIAL RALLY** on a card over the game (still in the code behind `app.COMMIT_REQUIRED`: not pressed, practice, ignored). And only the game's official time counts (`app.OFFICIAL_ONLY`, the same test builds): the game saves one only in the Rally Weekend that DRIVE sets up, so that is the only way to drive a daily or a time trial stage; once the clock starts, a restart or quitting is a DNF, whatever the mode. A run that finishes without the game's time (Practice, Single Rally Stage) is ignored, not a DNF: it wasn't the right mode, and the next run counts. (Rally Weekend mode has no restart anyway: of 278 restarts on Rally Weekend dailies from 9 Oct to 15 Nov 2026, none was followed within 30 s by an official time.) A driver who closes the game before it saves loses a Rally Weekend time without a DNF: the admin sees each such run (the report, and `voided_runs`). The app says both rules as loudly as it can (`app.RULES_LOUD`, the same test builds): a red banner over the daily cards, and on a daily's start line the timer's alert in orange (above). The game's result counts only if the save it comes in still holds the daily (or time trial stage) as DRIVE wrote it, as ACRK's challenges check them (`leagues.daily_changed`, from 0.1.5.6): its weather, start time, track conditions (grip, wetness, snow), time speed and rules; changed in the game's menu before START RALLY, the run is ignored, saying what: a daily's doesn't count and is no DNF (sent as `void`, like a run driven in the wrong mode: the daily stays open, the next run counts), a time trial run isn't counted. Rally events check the same, and their stages and service parks. |
| One shot | **Your first run counts.** Later runs are practice. A run that is started and never finished becomes a DNF after an hour. The first run is the one of the driver's first start (recorded live as it starts), even when it arrives after practice runs: a finished run waits for the game's official result. |
| Flags | Picked on your driver page (any country, or none). Until you pick one, it comes from the in-game driver profile. |
| Steam account | Runs are sent under the Steam account that signed in to the app. |
| App version | Everyone is timed by the same rules: the server takes runs only from apps at or above `MIN_APP_VERSION` (`server/wrangler.toml`, from the daily `MIN_APP_FROM` on). Older apps get their UPDATE button. |
| Conditions | Set by DRIVE in the game's Rally Weekend set-up. The game doesn't report them, so they aren't checked: its air temperature can't stand in for them, as the game draws it anew each time it sets a stage up (the same save, stage, time and weather gave 13.0 °C, then 15.7 °C; the set-up screen's forecast shows that session's figure). |
| New stages | Nobody records routes by hand: the app records every clean run (no resets, by the same rules as the timer). The first one on a stage without a driven route is sent to the server, checked (no jumps, plausible length and speed) and becomes that stage's route, and the stage joins the rotation with a random car. Routes taken from the game's files (`tools/gamefiles`) give way to the first driven one, which is matched to its stage by start and finish even when the game reports another name. |
| Stage names | The website and the app show each stage as the game's menu names it ("Peïra Cava - La Bollène-Vésubie", `server/src/stages.js`); the telemetry only reports a short one ("Monte Carlo Peïra Cava"). |
| Download | The app is served by the server itself: `/download/ACR-Daily.exe`. `client\build.bat` copies it to `server\public`, and a deploy publishes it. |
| Live map | While a run is LIVE the app sends its position every few seconds (5 by default; the server sets it, `LIVE_SEND_S` in `server/wrangler.toml`). The website draws everyone on the stage as moving dots on its map, each driver in their own colour with their flag; the app's stage strip shows them along the stage. |
| Discord | A bot in the Discord server's #live-timing keeps one message up to date with who is on stage and today's two timing sheets, and posts each day's final results (`server/src/discord.js`, a webhook run every 5 minutes). |
| Discord events | Anyone with Manage Events types `/event` in a channel (e.g. #events) and fills in a form: title, start (UTC, an offset or a Discord timestamp), length, where and a description. The bot posts a card with **Attending / Maybe / Not attending** buttons; each click updates the card, which lists who answered what (mentions that ping nobody); the same button again takes the answer back. Times show in each reader's own time zone. It also makes the matching Discord server Event (its countdown and reminder), linked from the card; once the event is over the buttons go. Discord calls `POST /discord/interactions`, signed (`server/src/discordrsvp.js`; tables `discord_events`, `discord_rsvps`). The admin can also queue a card without Discord: a `discord_events` row with `channel_id` `queued` (or `queued:<channel id>`) is posted by the bot in #events within 5 minutes, with its server Event. |
| What's new | Every app version has its changelog (`server/src/changelog.js`, plain words for drivers): on the website's `/changelog`, posted once in Discord's #changelog when the server hands the version out (`LATEST_VERSION`; the bot makes the channel, read-only), as the GitHub Release's notes, and in the app: after each update, a **WHAT'S NEW** screen over the app's window (`client/acr_daily/whatsnew.py`, from 0.1.6; a simpler popup from 0.0.31): the version's photo with its headline, each change tagged NEW / IMPROVED / FIXED / NOTE, and under it every version the driver skipped since the one they saw last (`GET /api/changelog/<version>?since=<last seen>`). Not on a new install. It opens again from SETTINGS › About › WHAT'S NEW and the "UPDATED TO … · WHAT'S NEW" bar; `/changelog` shows the same tags. A version can't be released without its entry: the server's tests and the release workflow stop. A test build (four parts) without an entry of its own shows the release it leads to. |
| Restart / retire / quit / stopping | **DNF**. Stopping means the clock frozen away from the finish (or the game gone) for more than 30 s. |
| Pausing | Fine. A pause (clock frozen and the car not moving at all) can last up to 15 minutes; the run carries on with the clock. |
| Shortcuts | **Invalid**. A run has to pass at least 90 % of the route checkpoints (one every 100 m). |
| Wrong car or stage | The run doesn't start. |
| Joining late | The app has to see the clock start, so a run that was already going doesn't count. |

## Rallies and championships

As on RallySimFans: **rallies** anyone makes, one event each, and **championships** (clubs, as in DiRT Rally and EA WRC:
groups of drivers running their own multi-stage events, a league in the code) run by Community organizers
(`server/src/leagues.js`, `server/src/leaguesapi.js`, `client/acr_daily/leagues.py`).

| | |
|---|---|
| A rally | Made by anyone signed in on the website, on its own page (`/rallies/new`): one event (an event's set-up, below), a name, a description, and who can drive it: **public** (it is in every driver's app; a driver joins it by driving it) or **private** (only with its invite link `/join/<code>`, which its maker sees on its page). Its maker stewards it, edits it, copies it as a new one and can delete it (a driver they remove can't see it any more). The admin takes one down with `admin.py rally-delete <event id>`; a banned driver's public rallies are listed to nobody. A driver has at most 3 rallies open or coming. A league row of kind `event` holds it, as a 1V1's or a cup's matches are held, so driving, timing and standings are a league event's (migration 0033). Apps before 0.1.6 list rallies as a league's events. |
| Community organizers | A rank the admin gives by hand (`admin.py organizer <steam id> [--off]`, or the admin page's Drivers): only they make championships. Shown on their driver page. The drivers who ran a championship when it came (2026-11-15) are organizers from the start. |
| The website | `/leagues` (or `/rallies`) is **Rallies**: yours, the open rallies and the championships, each kind in its colour (a rally pink, a championship the leagues' blue), CREATE A RALLY on top, and creating a championship for organizers. |
| In the app | The **RALLIES** tab (COMPETITIONS, from 0.1.6) is a server browser: the event picked shown in full (DRIVE), and under it every rally and championship round in one list that scrolls, each with a bar in its colour, its championship or maker, location, car, stages, how many have driven it and where you are in it; ALL / CHAMPIONSHIPS / RALLIES; a heading sorts; a click picks one, a double click drives it (`client/acr_daily/browserui.py`). No standings under it: each event's are on its page on the website. The public championships you aren't in are rows too (`GET /api/leagues`, from 0.1.5.13): picked, JOIN over the list (a double click joins, asked first; `POST /api/leagues/<id>/join`), and their rounds then come into the list. Every COMPETITIONS tab is one column: the one picked in full and the rest under it, never beside it (1V1: its other matches, then the challenges; CUPS below). |
| A championship | Made on the website (`/leagues`) by a Community organizer, after signing in there with Steam. A name, a description and who can join: **public** (listed, anyone can join) or **private** (only with its invite link `/join/<code>`: eight letters and digits without look-alikes; a new code makes the old link stop working), and a banner. A driver can run 5 leagues. |
| Roles | The **owner** changes the league's settings, banner and Discord posts, makes members admins (or members again) and can delete it. **Admins** (and the owner) make events and seasons, renew the invite code, remove or ban members (a removed driver's event under way ends as a DNF; their results stay) and steward. |
| An event | A **Rally Weekend** in the game, so it follows the game's rules: one location; 1 to 16 stages over up to 4 days, each day opening with a service park, more service parks between stages if wanted (longer than the game's own Rally Weekend takes, 9 stages over 3 days, the app drives it in **legs**: whole days, at most 9 stages and 3 days each, each its own Rally Weekend in the game from a service park; CONTINUE sets the next leg up once a leg's last stage is done. From the 10th stage of a rally set up whole the game crashes between a stage's end and the service park, RALLY MONTECARLO 2026. An app without legs neither lists such an event nor may start it: 426); each stage's weather and start time; one car for everyone, a class (each driver picks a car of it) or several classes (each class with its own standings and championship); the penalty, respawn, damage, wear and failure settings; when it opens and closes (62 days at most). Once someone has started it, only its name, its season and a later close can change. **Copy as the next round** fills the builder with the event (its next number, opening when it closes) to change its stages and save. |
| Driving it | The app's **RALLIES** tab lists the open and coming events of your championships (and every public rally). DRIVE sets the whole rally up in the game's save, then Racing › Rally › Rally Weekend › Start Rally. The game keeps the rally between stages and sessions (Rally Weekend › Resume), repairs the car in the service parks and carries the damage between them. Each stage is judged like a daily and sent with the game's own stage time + penalty. The game holds one Rally Weekend at a time: a league rally in progress is set aside while a daily is set up, and put back by CONTINUE on the event. CONTINUE also finds it among the player's own rallies set aside (PUT BACK), where the app puts it while the entry is a DNF: so an entry an admin reinstates goes on from its stage. |
| DNF | Retiring or restarting a stage, starting a stage a second time (the server keeps each stage's first start; from app 0.0.28 each start goes with when it was, so the same start sent again is not a second one, and only one copy of the app runs at a time: two copies sent each start twice, a DNF), a stage driven without the app watching or outside the event's rally, or not finishing before the event closes. |
| The game takes its rally back | The game keeps a Rally Weekend under way only when it is quit from a service park; quit anywhere else, or after a crash, it takes the rally back some stages, or drops it. From 0.1.5 that no longer ends the entry (it did for three drivers, 9-14 Nov 2026): DRIVE resumes where the game is (or sets the rally up again), the counted stages are driven again for nothing (the app sends nothing for them and the timer says *SS2 counted already · on to SS3*), and the next new stage counts as usual (`leagues.plan`). After each stage the app says to stop only at a service park. More stages done in the game than counted means stages driven without the app watching: under the event's retirement rule each counts as retired (`POST /api/events/:id/missed`, kept as a `league_stage_times` row with `retired`, migration 0032: the slowest time on it + the rule's minutes) and the entry goes on; without the rule, a DNF as before. |
| Hidden | So nobody practises an event beforehand, its maker can keep its **stage names** (with their lengths and maps), its **weather** and its **stage times** (the time of day, and the drivers' results: times, positions, gaps) from the drivers until it ends: three ticks in the event's form, all on by default for every event, 1V1 and cup made from 2026-11-08 on (events made before stay as they were). The location, car, rules and number of stages stay shown. The league's owner and admins see everything; a 1V1's challenger and a cup's maker see the set-up. A driver gets it when they press **DRIVE** in the app (the server keeps that they asked: `event_reveals`), and from then on sees it, and their own times. Everyone else and the league's Discord posts see "hidden" until it ends; the event's live map (`server/src/eventlive.js`: its page, its championship's page, a cup's page) is drawn only for who sees the stages (the owner and admins, a driver who has pressed DRIVE; a line under it says the others don't see it), and everyone else gets who is on which stage (SS2: their names) without the map, with why. It ends: a league event or a 1V1 once it has closed (or the 1V1 is settled), a cup's matches when the whole cup is over, since every round races the same stages; a hidden event's results count in its season once it ends. The app needs the stages to set the game's save up, so a driver who has pressed DRIVE could find them there: starting the stage commits them (a restart is a DNF). Apps older than `HIDDEN_MIN_APP` (`server/wrangler.toml`) don't list hidden events (`server/src/hidden.js`). |
| Official | ACR Daily's own leagues (`server/src/officialleagues.js`), made by the site's admin from a file (`tools/admin.py league new tools/leagues/<file>.json`), never by a driver: run by "ACR Daily" (no driver owns it; the Steam ids in the file's `admins` run it on the website as its admins), marked **official** on its page and the leagues list (public ones listed first), public or private like any league. Its rounds come from a plan: one event a week from the plan's start (the EXR one: Friday 00:00 UTC to the next), each in the next rally of the plan's list, all in one season; each round's stages are drawn by the server from its rally's own (never the same road twice, or where the rally hasn't the roads, a road again only the other way; the stages earlier rounds raced last), each stage's weather from the rally's odds, and everything hidden until the round ends. `league set <id> <file>` changes it from the file (`"public": true` to list it) and adds the rounds not made yet (more `weeks`: more rounds). The first: the **EXR Rally Championship** (`tools/leagues/exr-rally-championship.json`, with EXR Racing Division): private, from Friday 20 November 2026: 6 stages a week over 2 days, one rally a week, Rally2. |
| Stewards | The owner and admins can add a time penalty (on a stage, which moves its positions, or on the total; a negative one gives time back) or disqualify an entry (DSQ: no position, no points). Each decision shows on the event page with its reason and who made it, and can be taken back. |
| Standings | Per event: the totals (stage times + the game's penalties + the stewards'), stage by stage positions and the position after each stage. |
| Retirement rule | Per event, off by default (`rules.retire`, 1 to 60 minutes; the builder's **A retirement (DNF)**; the league's owner or admins choose it): a stage driven without the app counts as retired and the entry goes on, and a DNF stays classified, after everyone who finished (finishers and classified DNFs by stages driven, then the total), each stage it missed counting as that stage's slowest total + those minutes, and scores season points for its position. Not a DSQ, and not while a stage it missed has no time from anyone yet (`eventStandings`, from 0.1.5). Head-to-heads and cup matches still go by finishers only. |
| Divisions | The owner and admins can name a league's divisions (e.g. PRO, AM) and put each driver in one: every event and championship then has standings within each division too. Leagues and events made before divisions and multi-class events stay as they were. |
| Seasons | A league's championships: each season takes some of its events (an event outside any season is a one-off) and has its own points: a table from P1 then points for every other finisher (WRC 25-18-15-12-10-8-6-4-2-1 + 1 per finisher by default), an optional **Power Stage** bonus for the fastest on each event's last stage (5-4-3-2-1 as in the WRC), and each driver's worst rounds dropped. |
| Teams | The owner and admins can give a league teams (`server/src/leagueteams.js`): **its own** (the admins make them: a name, a tag, a colour, a manager; who puts drivers in them: the admins, the drivers themselves or each team's manager (who invites a driver in no team: they accept or decline on the league page); a team's most drivers; transfers open, or by the admins only once a driver has driven for a team) or **ACR Daily's teams** (`/teams`: each driver drives for their own, run by its captain and managers). Each entry keeps the team its driver drove the event for (`league_entries.team_id`, set as they start it): a driver changing teams takes no points along; an entry from before teams were on counts for the driver's team now, and the staff can set any entry's team. With teams on, a season can have a **team championship**: who counts (every driver of a team, or its best X on each event), how (**drivers' points**: their own championship points added up, the Power Stage in or not; **re-ranked**: the counted drivers ranked among themselves and a team points table, as the WRC's manufacturers; **team result**: the teams ranked on each event by their times added up, their average or their places, with a team points table, a team short of finishers ranking behind or each missing driver counting as the slowest time + a penalty; **season**: each team's best X drivers' season points), **nominations** (each team names up to M drivers for an event before it opens, its manager or the admins; only they count; a team that named nobody: all its drivers, or none), its own dropped rounds, and the stewards' points penalties on a team (with a reason, taken back as a time penalty is). The league page shows the team standings next to the drivers', each event page its teams' points and who counted, the league's Discord results post the top teams; hidden results count once the event ends, as the drivers'. How a team's drivers make its result: `server/src/teamscore.js`. |
| Discord | The owner can paste a webhook of one of the league's Discord channels: the server posts there when an event opens, when it has 24 hours left (events open 30 hours or more), and its results with the season's standings (`server/src/leaguediscord.js`, from the cron every 5 minutes). |
| App version | Driving league events needs an app from `LEAGUES_MIN_APP` on (`server/wrangler.toml`). |

### Credits (from `CREDITS_FROM`: 2026-10-12)

Points drivers earn and stake inside ACR Daily (`server/src/credits.js`, the website's `/credits`, shown with a gold coin, the balance in the website's header). 50 to start, a daily bonus of 50 for coming back (the app claims it when it starts, the website on the first page of the day, with a popup), and 50 for finishing the free daily (SS1), paid as soon as that run is in. The **wager daily** (SS2) is driven with a stake of 100, placed before the first run (DRIVE asks): no stake, no run on it, and the server refuses runs and live positions without one. The house stakes too, so the top half of the drivers (rounded up) get 200 back, the rest lose their stake, and what is left over goes to the fastest; nobody finishing: refunds. The time trial's TT2 entry fee (below) is credits too; TT1 is free. **The shop** (`/shop`, `server/src/shop.js`): looks bought with credits, a colour for your name on the timing sheets and your dot on the live map, a badge by your name, a frame round your picture on the live map; they change nothing on the stage. Leagues are free. Credits are only ever earned: they can't be bought, cashed out or given to another driver.

### Time trial (from `TIME_TRIAL_FROM`: the week of 2026-11-09)

A hotlap mode (`server/src/timetrial.js`, the website's `/tt`, the app's **TIME TRIAL** tab, `client/acr_daily/ttui.py`).

| | |
|---|---|
| The week | Monday 00:00 UTC to the next Monday. **Two stages** (TT1, TT2), new each week, from the dailies' pool: the rotation moves two stages on each week, off that week's dailies and on two rallies when it can, never a daily's stage + car (the app would take one run for both). Each has its own car, conditions (weather + time of day) and board. The cron fixes the week's stages as it starts (`tt_schedule`). |
| Driving it | DRIVE sets the stage up as a one-stage Rally Weekend, as for a daily (the dailies' rules), and the game's own stage time + penalty is the time. **Drive it as often as you like** until the week closes: after a run, go on from the game's results screen (it saves its time), then Rally Weekend › START RALLY again (the set-up stays). Only finished runs are sent; restarts and DNFs stay in the app. A run finished just before the close may arrive up to 30 minutes after it. |
| The board | Each driver's **best** time (ties: who set it first), their number of runs, and the prize their place pays as the pot stands. The best run keeps its trace: the app's live gap, ghosts and split standings are against the leader. Not rated. |
| Live map | As the dailies': while on a stage the app sends its position every `LIVE_SEND_S` (only for entrants, with credits on), and `/tt` draws each stage's map with everyone on it as moving dots (`server/src/stagemap.js`, shared with the home page); the app's stage strip shows the others on mine. A driver hotlapping for an hour sends as many requests as an hour of dailies (see *Free tier* below). |
| Entry and prizes | **TT1 is free** (`TT.freeSlot`): no entry fee, no prizes, every signed-in driver's runs count (fees paid on it before it went free come back when its week settles). With credits on, **TT2 costs 200 credits** (`TT.fee`), paid before the first run on it (DRIVE asks, or Enter on `/tt`); runs from a driver who hasn't entered, or that started before the entry, are refused. An hour after the week closes, the pot (every fee) is paid out: the **top half** of the drivers with a time (rounded up) get their fee back plus a share of the others' fees, the shares rising in equal steps by place (with k places paid, P1 k shares, P2 k − 1 ... the last 1). Entrants without a time get their fee back. Each driver gets a notice in the inbox. No credits are made: the fees only move between the drivers. Credits off: free, no prizes. |
| Moderation | `python admin.py tt-reject <id>` takes a run off its board (the driver's next best counts); a week already paid out keeps its payouts. Banned drivers leave the boards. |

**Private time trials** (`tt_private`, migration 0041; `setTtPrivate` in `server/src/timetrial.js`): stages of their
own beside the week's two, for testing a stage with a few drivers before it goes public.

| | |
|---|---|
| Making one | `python admin.py tt-private "London Marylebone - Whitehall|Peugeot 208 Rally4|Clear|midday" "[MOD] Germany Full|Hyundai i20 N Rally2" --title "..." --days 7 --min-app 0.1.5.42`: each stage the game's telemetry name (it needs its route) and a car, weather and time optional. Open from now for `--days` (7 by default), not Monday to Monday. It prints the page's link. `admin.py tt-private <code> --min-app ... / --ends 2026-11-25T18:00 / --title ...` changes one. |
| Its page | `/tt/p/<code>`: the `/tt` page for its stages (maps with everyone on them live, satellite for a stage lined up with the real roads in `server/src/geofits.js`, the boards), not linked from anywhere, `noindex` and no referrer, so only people with the link find it. A code that isn't one: nothing. |
| In the app | `GET /api/tt` adds the private stages open now as `private`, only to an app from their `min_app` version on (`appVersionOf`: the website and older apps never get them); they are TT3, TT4... (`PRIVATE.firstSlot`: each private stage a slot of its own, never used twice), cards beside TT1 and TT2, two by two, saying when they close; *Best times* opens their page. DRIVE, the judges, the live map, the ghosts and the boards are the weekly ones', with the page's key (`p-<code>`) for the week. |
| Rules | Free, no prizes, nothing settled; runs from an app older than `min_app`, started outside its dates, or arriving more than 30 minutes after its close are refused. A community stage (London, a WRC Generations stage: `requires`) needs its track installed, as for any stage; a WRC Generations stage's Rally Weekend is its `[MOD]` location's own calendar (`rallyweekend.location_preset`, the calendars `stagecalendars.py` makes). |
| A route for a stage nobody drove yet | `admin.py`'s `/api/admin/route` with `source: 'game-files'` (a WRC Generations stage: its export's `route_centerline_1m.csv` + the build's shift, telemetry x, z = UE X, Y): the first clean run a player's app records replaces it. |

### Community: tracks and cars to install

The app's **COMMUNITY** tab (and its tile on HOME; `client/acr_daily/communityui.py`, `community.py`): TRACKS and CARS
made by the community (and LIVERIES), as a server browser from 0.1.5.13: the one picked in full over the list (its card with INSTALL / UPDATE / REMOVE), and every item a row under it, one under another, the page scrolling (name, who made it, what it is, size, status; LIVERIES: livery, car, painter, rating, downloads, status); a click picks one, a double click takes its first step (INSTALL, GET IT, DOWNLOAD; never REMOVE or MANAGE). Before, they were cards two by two. The list is the server's (`GET /api/community`,
`server/src/community.js`); each item's package is a GitHub release (`manifest.json`, the zip or its parts,
`card.jpg`). Installing downloads the package, checks the SHA-256 of the zip and of each file, and copies the
containers into the game's `acr\Content\Paks\~mods` (the game closed; other converted stages there are asked about
first, since only one menu registry works at a time); the app lists what it put there in `~mods\ACRDaily-community.json`
and REMOVE takes exactly that out. A package is made for one game build: after a game update the app takes it out
(its menu registry would hide the game's own rallies) until a package for the new build is up, then offers it again.

The public track: **ACR DAILY London** (Westminster, both ways; release tag `acrdaily-london`). Its stage ids
(`AcrXsLn02r0FullForward`, `AcrXsLn02r1FullForward`) are the game's to the server (routes, the time trial, leagues) but
never drawn for the dailies: not everyone has it. A daily or time trial stage on it says so (`requires`): DRIVE without
it installed offers the COMMUNITY page. In the game it is a location of its own with its own Rally Weekend calendars.
Its package holds only the stage's own files and binary deltas (`.acrd`) against the game's files, put together on the
player's PC with `retoc` (the manifest's `assemble`: `community.assemble`), so the download has none of the game's files.
A new version (a higher `version` in its manifest) shows as UPDATE; a package for a new game build replaces the old one
the same way.

**Everyone is credited on the card.** Each item has an `author` (the card's *by*, the list's BY column) and `credits`
(the card's *Credits:* line): who made the stage, the tools it was made with (ACR Extra Stages for London and Lousã,
Stage Exporter and Sando Rally's Stage Export Tool for WRC Generations' stages, retoc, UAssetAPI, CUE4Parse) and its
data (OpenStreetMap, Copernicus, ESA WorldCover, Portugal's DGT, Poly Haven's texture artists...). The packages carry
the full lists (CREDITS.txt, CREDITS.md, Sando's notices).

**Stages from other tools (the test builds only, `testOnly`: a public app isn't sent them).** Installed their own way
(an item's `install`), never by copying files from here:

| | |
|---|---|
| Hattori Rally's **Lousã** (a package whose manifest has a `kit`; `group: 'lousa'`) | One gravel stage in the Serra da Lousã, Portugal (`AcrXsPtLousaFullForward`, 6.7 km), from Hattori Rally's installer kit (its own stage data and open tools, nothing of the game's). INSTALL downloads the kit (its release `hattori-lousa`: manifest + zip beside it, SHA-256 checked; a manifest's zip can instead name a `page` that only a browser downloads from, which the app opens and then finds the zip in Downloads by its size and SHA-256) and `community.build_kit` builds it on the player's PC: the kit unpacked at the top of the game's drive (`ACRDaily-build\hattori-lousa`: the kit reads the game through hard links, about 15 GB while it builds), its own `install.ps1 -BuildOnly -Yes` run in Windows PowerShell 5.1 in a hidden console of its own (it reads the player's game, its offline checks must pass; all it printed is kept in `logs\kit-<id>.log`), its stage list packed again under its own name (`zz_acrxs_lousa_registry_P`: never London's `zz_acrxs_registry_P`), the six files into `~mods` as any package's and the work folder deleted. Its kit makes no Rally Weekend calendar, so the manifest's `kit.calendars` carries ours (`AcrXsPtWeekendShort/Medium/Long`: the game's `DT_RallyWeekendCalendarPreset` with them added, as ACRD1 deltas against the game's own files): `community.kit_calendars` reads the player's table with the kit's retoc, checks it is that one and puts the result in the stage list before it is packed (another game build: installed without them). The installed record carries the game build it was built for, so `guard` takes it out after a game update and INSTALL builds it again. Its credits name Hattori Rally's Patreon, and its card links the stage's own post there (the catalogue's `support: {name, url}`: any item can carry one, an https address only). Its terms: share the download, never the files it builds. |
| Sando Rally's original stages (`install: 'manager'`) | **Chile BioBio** (0.4.2, two gravel stages, `SandoChlBioFull` and `SandoChlBioRevFull`, Free Practice only), from [sandorally.com](https://sandorally.com/original-stages). Its terms: free for personal play, downloaded only from sandorally.com, not repacked; and only Sando's own Stage Manager installs it (it builds the game's stage list from the player's own game files). So INSTALL downloads the official zip (its address, size and SHA-256 in the item's `download`, as sandorally.com publishes them; a cut download goes on from where it stopped), checks it, unpacks it into the app's folder (`community\<id>-<version>`; the zip then goes) and has `Sando-Rally-Original-Stage-Manager.exe` install it, run for the player (`client/acr_daily/managerdrive.py`): started from the download, it offers to install the stage in it in a small window of its own, whose Install (the left of its two buttons; Tk draws them, so they take no message) gets a real click in its window's middle, the window put in front; its notes (Windows' own message boxes) are read and answered as the player would (OK; Yes only to installing), and anything else it asks is left open for the player; once its state (`%LOCALAPPDATA%\Sando-Rally-Original-Stage-Manager\state.json`) lists the stage at its version, it is closed (about 15 seconds on a PC with the game on an SSD). The app then looks at the game again and keeps the download without asking (the manager needs it to update or remove the stage, or change its pace notes). MANAGE opens the manager for the player (downloading it again first if it went). Free space is checked first (about twice the zip in the app's folder while it unpacks, and the stage again in the game's). A new version of the stage: a new `download` in `server/src/community.js`. |
| WRC Generations' stages (`install: 'export'`, one row each) | 22 stages in 9 countries (`Wrcg...Full`): every stage in Stage Exporter's `allowed_stages.json` but Belgium's three (Sando's tool stops on a road piece turned in their level, `BE_YPRES`), made on the player's PC from their own copy of WRC Generations by **[Stage Exporter](https://github.com/Faviogames/Stage-Exporter)** 1.5 (Albert Palahi's add-on to Sando Rally's Stage Export Tool 0.3.7; crowds, roadside vegetation, replay cameras, ACR-style finishes). **INSTALL does all of it** (`client/acr_daily/stageexport.py`): it finds WRC Generations (a folder the player showed with FIND GAME, else Steam's libraries, else the Epic Games launcher's manifests and `LauncherInstalled.dat`) and Sando's tool (the folder kept in the settings, else the usual places: Downloads, Desktop, Documents, each local drive's top; else the zip it came in, left in Downloads, Desktop or Documents, which INSTALL unpacks into the app's `tools\` folder first), puts Stage Exporter into the tool the first time (GitHub's archive of the commit in the catalogue's `tools`, every file under `payload/` checked against its `payloadSha256`, copied as its `INSTALAR.bat` does, the two games' folders written to `custom\installs.json` so its setup asks nothing, `-m wr_setup` run), then runs `wrcg2acr-worker.exe -m wr export <slug>` (about 40 minutes; the game closed) and reads its log for the progress (the phase, how far, the time left) on the card and the row. When it ends the stage is in the game and the row says INSTALLED. With the game open, INSTALL waits and starts by itself once it is closed. More INSTALLs wait their turn (INSTALL ALL over the list puts them in line with every other track: below); while any is being made, a bar there shows how far all of them are, the one being made (its step, how far) and the time left, and STOP ALL stops them; CANCEL stops one (the pack the game had goes back); REMOVE runs `-m wr remove <slug>`. The worker writes its log straight to `logs\stage-export-<time>.log`, so closing the app doesn't stop it and an app opened again follows it to its end (`stage-export-run.json`). Sando no longer offers his tool ([he took it down](https://sandorally.com/stage-export-tool-discontinued) so as not to be part of people sharing exported stages), so the app never ships it: when neither the tool nor its zip is on the PC, INSTALL downloads the Internet Archive's copy of his own zip (the catalogue's `base.download`, the file as sandorally.com served it, checked against its size and SHA-256: `stageexport.fetch_tool`), unpacks it into `tools\` in the app's folder and deletes the download. With a catalogue that has no copy, the row says so, and FIND TOOL lets a player who has it show it once (`Sando-Rally-Stage-Export-Tool.exe` in its folder, or the zip it came in). Nothing it makes leaves the PC, and no pack of converted WRC Generations stages is offered. **Rally Weekend** (`client/acr_daily/stagecalendars.py`): the pack marks its tracks Free Practice only (`DT_Tracks` RaceEventTypes `[FreePractice]`) and adds no calendar, and the game's Rally Weekend menu lists a location only with calendars of its own. So once a line of runs is done (and when the page opens and the pack isn't the one they were made for), the app makes a small container of its own beside the pack, `pakchunk99-wrcgzcalendars_P` (it sorts after the pack, so its tables win, and the stage switch shows and hides it with the pack): the pack's `DT_Tracks` with its tracks opened to Free Practice and the offline Rally Weekend only (`FreePractice`, `Rally`: never the online or challenge modes), the pack's `DT_TracksLocations` without "Free Practice only", and the game's `DT_RallyWeekendCalendarPreset` with three calendars per `[MOD]` location (`<location>WeekendShort/Medium/Long`, copies of Wales', each day on the location's stages). It is made with Sando's own tools in the player's copy of the Stage Export Tool (`bin\retoc`, `bin\uatool\UaTool.exe dumpjson/fromjson`, `bin\acr_stage.usmap`), the tables edited as JSON (new names go among the ones the data uses, which a packed package keeps), in about 5 seconds; it is taken out before each run (the tool reads the game's tables) and whenever it can't be made again (an old copy would hide new stages). |

**INSTALL ALL** (the strip over the TRACKS list: ALL TRACKS, how many are in the game) puts in every track that isn't,
one after another, after one question (what they are, how much to download, how long WRC Generations' take; their terms
are on their cards): the packages first (downloaded, built on the PC), then Sando Rally's (his manager run for the
player), then WRC Generations' stages (made one after another, the longest). The strip says which one is going in;
STOP ALL lets the one going in finish and takes the rest off; what couldn't go in is said once at the end.

What is in the game is read from the game's packages, whatever they are called (`community.stage_packs`): a stage's
package lists its pace notes in its index (`.utoc`) as `DT_Pacenote<stage id>` (Chile BioBio's: `DT_PacenoteSandoChlBioFull`),
and the catalogue's ids are looked for by name too; the game's own containers are left out.

**Every installed set in the game at once: one stage list** (`client/acr_daily/stagelist.py`). The game lists its
stages in nine tables (`DT_Levels`, `DT_Tracks`, `DT_TracksVariants`, `DT_TracksLocations`, their logos and backgrounds,
`DT_TracksTextures`, `DT_RallyWeekendCalendarPreset`, `DT_LoadingScreen`). Every set carries its own copy of them, the
game's rows with its own added (London's and Lousã's `zz_acrxs_*registry_P`, Stage Exporter's pack and our calendars
for it, Sando's `pakchunk99-SandoRegistry_2_P`), and the game loads one copy of each, so on their own only one set's
stages show. No set changes a row of the game's (checked 18 Nov 2026: each only adds), so with two sets or more in
the game the app makes one more copy, `~mods\zz_acrdaily_stagelist_9_P`: the game's own tables (read from its
`pakchunk1-Windows`) with every set's rows added, their names put among the ones the data uses. The game loads it over
the sets' copies (a container named `_<n>_P` comes after the plain `_P` ones and the lower numbers: Sando's list is
`_2_P`). Which containers carry the tables is read from their index (each table's package id, CityHash64 of its name as
the game has it); each set's copy is read on its own with retoc and turned into JSON with UaTool, so nothing of any set
is changed (Chile's files stay as Sando's manager put them). It is made with Sando's tools (retoc, UaTool and the
mappings, from the Stage Export Tool or Sando's stage download: `stagelist.tools`), in about 30 seconds, only on a game
build those mappings read (`stagelist.BUILDS`); made again when a set is installed, made or taken out (its signature:
the containers' sizes and times), taken out before Stage Exporter runs and when it can't be made. Checked in the game
18 Nov 2026: London, Lousã, Chile BioBio and two WRC Generations stages in RALLY SELECTION together, a stage of each
loaded. Without the tools (or on another build), the switch below shows one set at a time as before, and the TRACKS page
says so, naming the tools (`community.pack_groups`, an item's `group` and `tool`).

**One set of stages shown, switched in a second** (`client/acr_daily/stageswitch.py`; when the one list above can't be
made). Switching between ACR Daily's
London (its `zz_acrxs_*` containers in `~mods`), the WRC Generations stages (Stage Exporter's
`pakchunk99-wrcg*` pack, in `~mods` from its 1.5, in `Paks` before) and Sando Rally's (Chile BioBio: his stage containers, whose index names
`DT_PacenoteSando…`, and the stage list his manager builds, a container of no other set's that carries
`DT_TracksVariants`) never deletes or rebuilds anything: the sets not shown are *parked*, their files renamed to
`<name>.acrdaily-off`, which the game doesn't load, and showing one renames its files back. A stage made once (about 40
minutes) is never made again for a switch; Sando's files are only renamed, never changed, and put back before his
manager is opened. Without the one list, installing London, making a WRC Generations stage or installing Chile with
Sando's manager shows that set and parks the others (with it, every set comes back); a parked set's card and rows say HIDDEN with **SHOW** (WRC Generations' strip too: SHOW
IN GAME); with more than one in the game the banner offers SHOW ONLY for each. The game must be closed. While a WRC
Generations stage is made the other sets are parked (Stage Exporter reads `Paks` as the game's own and wants no other
stage mod there) and come back if it doesn't go through.

**Mods never get in the way of the dailies, time trials or leagues.** The game's save is read whatever stages it holds:
a mod's stage id (`SandoChlBioFull`, `WrcgEsSS1Full`, `AcrXs…`) in the player's own Rally Weekend calendar or in its
results reads like the game's own (`rallyweekend.ANY_STAGE_RE`; before, one result of a mod's stage made the whole
results list unreadable, so a daily's official time next to it was "not found", and a Rally Weekend of one on the
calendar stopped DRIVE). And each set's stage list carries its own copy of the game's stage tables, made for one game
version: after a game update the sets whose list was made for the version before (WRC Generations', Sando Rally's) are
hidden (parked, as for a switch) until rebuilt, since an old copy can hide or break the game's own stages
(`communityui._check_stale`, the builds in the settings' `stageSetBuilds`): WRC Generations' REBUILD runs Stage
Exporter's `-m wr repack` (its stage list again from the stages it made, a couple of minutes), Sando's MANAGE opens his
manager, which makes his for the new version as it starts. London is taken out by `community.guard` until its package
for the new version is up.

**Free space** is looked at while a WRC Generations stage is made, not asked for ahead: every few seconds on the tool's
drive and the game's, and in the tool's log ("not enough space on the disk"). A full drive stops the run (the game's
pack goes back as it was) and says which drive to free.
Their stage ids join the game's on the server (routes) and, like London's, never enter the dailies' pool; dailies and
time trials on them are for later.

### Liveries: the drivers' liveries, downloaded and installed

The website's **/liveries** page and the app's **COMMUNITY › LIVERIES** (`server/src/liveries.js`, `liverypage.js`;
`client/acr_daily/liveries.py`, `communityui.py`). A livery in the game is a folder,
`Documents\My Games\acr\Liveries\<car>\<name>\` (what [ACR Livery Tool](https://github.com/agastal/AcrLiveryTool-Release)
exports), 25 a car at most, read when the game starts.

**From ModsCloud.net** (`server/src/liveryimport.js`, migration 0037): its Assetto Corsa Rally skins are listed too, each
with its author's credit (the post's *Credits:*; "painted by" on the page, *by* in the app) and ModsCloud named as
where it is. Nothing is copied: the link is the post's page and the preview is ModsCloud's own picture (`shot_url`).
**The app installs them in one click**: each post's page has its download button, `<page>?download=<id>&token=<t>` (the
same for everyone, sent on to the file in ModsCloud's storage), read from the page once and kept as `download_url`
(migration 0038; `/go?direct=1` sends on to it). Their files are .rar (RAR5; a few .7z): the app unpacks them with its
own **7-Zip** (7z.exe and 7z.dll, 24.09, which the release build downloads pinned by its SHA-256, checks for RAR5 and
bundles: GNU LGPL with the unRAR restriction, its licence in the app's folder and its credits), else Windows' own
`tar.exe`; every file is checked inside its folder, then zipped and installed as any livery (`client/acr_daily/liveries.py`
`to_zip`). If neither can, the app offers the page to download it by hand. They come from ModsCloud's public WordPress API;
the car is read from the title and the brand tag (each car by the words of its name no other car of its brand has; a
brand with one car in the game is that car; two cars named, or none: left out, e.g. race suits and helmets). The
server takes the newest 20 every hour (minute 45; `POST /api/admin/liveries/sync {page, perPage}` by hand), and
`node tools/modscloud_liveries.mjs` writes all of them as SQL for a first import or a catch-up (`--links`: only the files'
links, as UPDATEs). A post seen again updates
its card but never its stars, downloads or status (one the admin hid stays hidden).

| | |
|---|---|
| The page | Each livery a card: its preview (full size on a click), the car, who painted it, its description, the stars (a click votes, 1 to 5, signed in; not on your own), DOWNLOAD (its link, through `/api/liveries/:id/go`: counted) and *Link not working?*. A car and an order (top rated, newest, most downloaded) picked at the top; `?car=<id>` opens on one car. How to put one in by hand under the cards. |
| Publishing | Signed in with Steam: the car, the livery's name, who painted it, the link (optional: without it the card is shown only), a description and a preview (made a JPEG at most 1600 px wide in the browser, 1 MB at most). The file stays where its author put it: Overtake.gg, Google Drive, Dropbox, MEGA, MediaFire, a GitHub release. It waits for the admin; the sender sees where it stands under the form and is told in the inbox. 5 a day and 5 waiting at most a driver. |
| The app | The same cards with RATE IT. Where the link gives the zip itself (a GitHub release, a Dropbox or Google Drive file, an address ending in `.zip`: the server's `directUrl`), **INSTALL** downloads it (`/go?direct=1`) and unzips each folder of it that holds files into the car's folder (a pack for several cars as `<car>\<name>\` inside the zip goes to each car; files at its top: one livery named after the card); programs in a zip refuse it; `%APPDATA%\ACR Daily\liveries.json` lists what went where, and **REMOVE** takes exactly that out. Any other link (a download page): **DOWNLOAD** opens it in the browser. The game's 25 a car is checked first. *Open the liveries folder* opens it in Explorer. |
| The car's folder | The one already in the Liveries folder, or among the game's `acr\Content\LiveryTemplates`, that names the car (the game's own spelling, matched as `names.same_car`), else the zip's own `<car>` folder, else the car's id in the game (`src/cars.js`). If the game spells a car's folder otherwise, export one livery for it with ACR Livery Tool once: the app uses that folder from then on. |
| Moderation | The `/admin` page's **Liveries** tab (or `python admin.py liveries` / `admin.py livery <id> publish / reject / hide / clear / delete ["note"] [--link https://...]`): publish one or turn it down (the sender sees the note), a published one's *link not working* reports (mend the link, it is fine, take it off). Look at the link before publishing: the app downloads what it gives. |
| From the web | Liveries published elsewhere (Overtake.gg, RallyGamer...) are brought in by the admin: `python admin.py livery-import <list.json> [--pending]`, a list of `{car, title, author, link, description, image}`. The link is the author's own page (the file stays there; the card credits them by name), the preview is made a JPEG of at most 1600 px and 1 MB, and each is published at once (`--pending`: on `/admin` first). Sent by `imported` (`src/liveries.js IMPORTED`): no "sent by", nobody told in the inbox. A link already on the page is left as it is, so the list can be run again as it grows. Respect each author's terms: link to their page, never re-upload their file. |

### A time trial on London (the week of 2026-11-16)

TT1 London, TT2 drawn as usual; London's car is drawn for the week, dry, midday:

1. Put the package up (above) and install it from COMMUNITY in your own app; check it in the game (offline): the
   London card in RALLY SELECTION, the stage loads, the finish.
2. Check that a Rally Weekend runs on it, set up as DRIVE will (the game closed; from `client`):
   `python -c "from acr_daily import rallyweekend as r; print(r.write_daily({'stageId': 'AcrXsLn02r0FullForward', 'carId': 'Peugeot208Rally4', 'startSeconds': 43200, 'weatherGame': 'WT_CLEAR'}))"`
   (the save is backed up first), then in the game Racing › Rally › Rally Weekend › START RALLY: Westminster should
   load; finish it and see its time in the results. If the game refuses London in a Rally Weekend, the time trial
   can't count the game's own result on it: say so before the week starts.
3. Record its route: the app's admin panel, **Record**, drive Westminster cleanly from the start to the finish,
   **Upload**. The panel says the stage's telemetry name (e.g. "London Westminster"): use it below.
4. `python admin.py stageid "<telemetry name>" AcrXsLn02r0FullForward`
5. Before Monday 00:00 UTC: `python admin.py tt-schedule 2026-11-16 1 "<telemetry name>" "*" Clear midday`
   (`--remove` to undo). TT2 is drawn from the pool as the week starts.
6. `python admin.py state` shows the route with its stage id; on Monday the TIME TRIAL tab shows TT1 on London (its
   card with the Trafalgar Square render), and DRIVE offers COMMUNITY to anyone without it.

### Messages, 1V1s and cups

| | |
|---|---|
| Inbox | `/inbox` and the app: notices from ACR Daily (a challenge came in, a cup match is ready, results) and short 1:1 messages between drivers (500 characters, 30 an hour), with block and report (`server/src/social.js`). |
| 1V1 | `/1v1`: a driver challenges another to an event of their own making (stages, car or class, rules, a window of up to 14 days) with a stake each (0: a friendly). The challenged driver accepts or declines within a day; accepted, it is a match both drive from the app's 1V1 tab. The lower total wins both stakes; nobody finishing or a dead heat: stakes back (`server/src/h2h.js`: head-to-heads, `h2h` in the code, the API and the database). A challenge can also be made in the app (its 1V1 tab: who, where, the stages or a few drawn at random, the car or a class, the conditions, the window, the stake; `client/acr_daily/challengeui.py`), and once a 1V1 is over either driver sends a **rematch**: the same again, from now. |
| Cups | `/cups`: a knockout of 1V1s (up to 4, 8, 16, 32, 64 or 128 drivers) anyone can make, with an entry fee and a split of the pot (winner takes all, 70 / 30, 60 / 30 / 5 / 5, or the maker's own: a % for 1st, 2nd, then each of 3rd–4th, 5th–8th... down the bracket, 100 % in all, no place getting more than a better one). At the start the bracket is the smallest that holds who joined (63 drivers in a 128 cup: a Round of 64), seeded by the driver rating (equal ratings at random), byes for the top seeds; each round's matches are open for 12 to 72 hours, the rounds closing at fixed times (the start plus a round's length each, so a weekly cup always closes on the same weekday and hour), with a reminder in the inbox for whoever hasn't driven their match before the round closes; nobody finishing or a dead heat: the higher seed goes through (`server/src/cups.js`). A round opens, is decided and is paid with a few bulk statements whatever its size: the free plan allows 50 database queries a cron run. **Official cups** are ACR Daily's own, made by the admin (`python admin.py cup new tools\cups\<file>.json`, e.g. `tools/cups/inaugural-cup.json` with its banner): "run by ACR Daily" with an OFFICIAL badge, listed first and on the home page, rounds of up to two weeks, a banner, a prize of ACR Daily's credits added to the pot, and (`"draw"` in the file) a new random draw of the rally's stages each round: never two on the same road, the ones not driven yet in the cup first, within a total length if set; with `"rallies": [...]` in the draw, each round goes to another of those rallies, in random order (all of them before one comes back), and where a rally has fewer roads than the round has stages (Alsace and Wales: three), one road comes up twice, the other way. Their sign-ups, rounds (with the stages drawn) and results are posted on Discord (`server/src/cupdiscord.js`). In the app, the CUPS tab lists every cup open for entries or under way in one list that scrolls (`client/acr_daily/cupbrowser.py`, from 0.1.5.1), as RALLIES lists its events: filters (ALL, OPEN, UNDER WAY, MINE), a heading sorts, a click picks one (JOIN or LEAVE, CUP ›), a double click joins an open one with room. One of mine with a match to drive, picked, shows that match over the list (its card, DRIVE; YOU says *Match open*): the matches were cards beside it before 0.1.5.13. |
| Team 1V1 | `/team1v1`: a team's captain or a manager challenges another team (`server/src/teamh2h.js`): the event as a 1V1's, **who drives** (any driver of the team, or the drivers each team names) and **how the teams are scored** (`server/src/teamscore.js`): **Top X** (the best X times added up), **Average** (everyone who drove, at least X), **Named** (the team names X drivers, their times added up), **Cross-country** (the best X places added up, lowest wins) or the maker's own: who counts (everyone or the best X), times added up, the average, places or points by place, and a team short of finishers ranking behind or each missing driver counting as the slowest finisher's time + a penalty (% and seconds). The other team's captain or a manager accepts within 2 days. Then both teams drive one match from the app's 1V1 tab: an open lineup is every driver of both teams then; a named one the drivers each team names on `/team1v1` (until each starts; only they can start it). Settled once the window and its grace are over, or once every named driver is done: the better team wins; nobody with a finisher or a dead heat: no contest. Before it closes (a day before, or a quarter of a short window) the lineup drivers still to drive it, and the captain and managers of a team that hasn't named all its drivers, get a reminder in the inbox. No credits, not rated. A rematch once it is over. |
| Team cups | `/tcups`, `/tcup/<id>`: a knockout of team matches (4 to 64 teams) anyone can make (`server/src/teamcups.js`): the event, the scoring as a team 1V1's, rounds of 1 to 7 days, the drivers a team signs up (its roster: at least, at most) and who drives each match: any driver of the roster, **the roster itself** for the whole cup (each team signs up exactly the lineup's size), or **a lineup named for each match** from the roster by the team's captain or a manager. A team's captain or a manager signs it up with its roster (its own drivers; one roster a driver a cup), changes it or takes the team out until the start; a driver can take themselves off a roster. At the start, teams short of the roster's minimum are out, the rest seeded by **team rating** (the average rating of the roster's best drivers, as many as a match counts; 1500 unrated). A match is decided once its round closes: the scoring's winner goes through; nobody with a finisher or a dead heat: the higher seed. No entry fee, not rated. Notices go to the rosters' drivers (and, lineups per match, the captains and managers), with a reminder before a round closes as a cup's. **Official team cups** are ACR Daily's own, made by the admin (`python admin.py tcup new tools\tcups\<file>.json`, e.g. `tools/tcups/autumn-team-cup.json`; `tcup set <id> <file>`, `tcup off <id>`): run by ACR Daily with an OFFICIAL badge, listed first and on the home page, rounds of up to two weeks, a banner; their sign-ups, rounds and results are posted on Discord as the official cups' (`server/src/cupdiscord.js`). |
| How they are driven | Each 1V1 and cup has a hidden "holder" league (`leagues.kind` h2h / cup) whose events are its matches, each open to its two drivers only (`league_events.only_ids`): DRIVE, the stages, the timing and the standings are the leagues'. The cron settles 1V1s and moves cups on every 5 minutes (a few of each a run). |
| Privacy | Messages are not private: they are kept as written (not end-to-end encrypted, deleted after 180 days) and the site's admins can read them, which is how a report is checked. The inbox says so, on the website and in the app. |

### Community spotlight

The home page shows rally communities that race on ACR Daily under the two dailies (`server/src/communities.js`): each with its picture (a click opens its Discord), its name, a line about it, and links to its Discord and its league here. Its picture is kept in `server/src/communityimages.js` (WebP, base64) and served at `/community/<key>.webp`. Another community: one entry in each file. First: EXR Rally.

### The website's header

One on every page (`server/src/header.js`), the parts of the game as the app names them: **DAILIES**, **TIME TRIAL**,
**COMPETITIONS** (a drop-down: Rallies, 1V1, Cups) and **COMMUNITY** (Ranking, Teams, Liveries, Discord). Each is
grey; the part a page is in is underlined in its colour (the modes' colours, as in the app), and each item of a
drop-down has its colour as a bar and a line saying what it is. On the right: how to play (in words signed out, a ?
signed in), the inbox and the credits (signed in), the language and SIGN IN, or the driver's menu (their picture:
driver page, credits and shop, language, sign out), then *Get the app* (not on a phone). A window of 860 px or less,
or a row too wide for its language (`HEADER_FIT`, `src/i18n.js`): one shorter row, the parts in a menu under ☰.
On a touch screen everything in it is 44 px to tap at least (SIGN IN, ☰, the menus' rows), as are the stage chips
of a live map, the day's arrows, tabs and small buttons (WCAG's target size).

### Phones, shared links, missing pages

From a UI review (Nov 2026). A page of one thing (an event, a championship, a cup, a driver, a team) reads its row
first (`src/pagemeta.js`, one query): none, a 404 page saying so (it answered 200 with empty sections); else its own
`<title>` and Open Graph / Twitter tags, so a link shared on Discord shows its name, a line (a rally's location, car,
stages and when it closes) and its banner. A private championship's (and its events') stay plain, as the API keeps
them. Any other address that isn't a page answers 404 with a page (the API's still answer JSON). On a phone (760 px or
less) an event's standings put Total and Gap after the name, the stages scrolling sideways under it, with a shade and
a line saying so (the table was 760 to 990 px wide, Total off the screen); a season's put Points and Wins first; a
cup's bracket shows one round at a time, the one being driven first, its byes in one line; a list's rows put the name
across the width. /liveries shows 24 at a time (*Show 24 more*). A live map folds away while nobody is on a stage
(*Show the map*) and says LIVE only when someone is. A hidden event says when it shows everything (`revealsAt`: its
close and the grace for late results), its itinerary drops the columns it hides instead of *Hidden* in every cell,
and the Gap column holds gaps only (a DNF's reason goes under the total). The list of rallies is at /rallies (/leagues
goes on to it) and the pages say championship, not league; dates are written one way (`FDATE`, `FDATETIME`:
src/i18n.js); names in a championship's and an event's standings link to the driver pages. Grey text is #85858E and
red as text #FF4655 (`--acct`), 4.5:1 or more on every panel (WCAG AA); ACR red stays for fills and borders.

### The app: small windows, offline, the keyboard

From the same review (the 0.1.5.x test builds on). The driver's panel and the view scroll once they are taller than the
window (`tiles.ScrollArea` with `fill`: DRIVE is reachable at 560 x 640; one wheel handler for every scrolling part,
Page Up / Down too), and the cards and HOME's tiles are sized from the room on screen. Without a connection the daily
cards say *Can't reach ACR Daily* with RETRY, tried again every 15 s (the system's error goes to the app's notes, not
the footer). Wrap widths follow the screen's scale or their box (lines broke after two words at 150 %). Buttons,
links, tabs and icons work from the keyboard (Tab, then Enter or Space; `app.keyable`). Lists drop their least needed
columns on a narrow window, never the name and the status. A run that won't count says NOT COUNTING on the timer, not
LIVE. The first start's steps say the rule (your first run counts), and the rules are said once on a first DRIVE: the
banner over the cards, the timer's alert (no commit card since 0.1.5.48). The rule texts name the buttons as they read in each language. The phone's is
the website (the app's narrowest window is for a second screen, and its notifications are Windows').

### Comments on runs

| | |
|---|---|
| What | A line on how a run went, as on RallySimFans: "lost the rear in the hairpin before the split", "the game froze at the finish" (`server/src/comments.js`, `client/acr_daily/commentui.py`, from app 0.1.6). One per driver and daily, time trial stage (for the week) or league stage, 200 characters, one line. Sent again it changes; sent empty it is taken back. |
| Writing one | In the app, once the run's result is on the server, a card pops up under the timer, over the game, after every stage driven once (a daily's counted run, a time or a DNF; a stage of a rally, championship, cup or ranked rally, or the stage a DNF ended on; not a time trial run, those are driven again and again): the comment box, SEND (Enter), **DRIVE** on the other daily when there is one to drive, CLOSE (Escape). It closes by itself after 30 s unless the box is clicked or typed in: then it stays until a button is pressed. What was sent before fills it. Only on a stage the driver has a result on: a daily until the end of the next day (UTC), a time trial stage until a day after its week, a league stage until a week after the event closes. |
| Who sees it | A daily's and a time trial's: everyone once the day (UTC) or the week is over (no hints for the drivers still to drive it; until then the website shows a driver their own, `commentsAt` on the boards), with the time on the website's timing sheets and, for a daily, in Discord's results of the day (the first 8); the app has no timing sheet from 0.1.5.1 (each card links to its standings on the website). A league event's (rallies, cup and 1V1 matches too): only whoever runs it: a championship's owner and admins, a rally's or a cup's maker, each told in their inbox (once per comment, a link to the event's **Drivers' comments**); the drivers see their own there. Official leagues and cups and 1V1s: the site's admin. |
| Moderation | Swearing and slurs are refused when sent (`server/src/wordfilter.js`: English and the site's 9 languages, matched where a word starts, with the usual disguises; ordinary words of any of them let through). `python admin.py comments [days]` lists them all, `python admin.py comment-hide <id> [--show]` takes one down (off every board and page; its driver still sees it). A banned driver's are not shown. Shown as text, never HTML. |

### Bug reports

| | |
|---|---|
| The form | `/report` (linked from the home page and the guide), signed in with Steam: where it happened (a daily, the time trial, a league event, a 1V1, a cup match, the app, the website), the app version (`?v=` fills it in), what happened, the event or page, when, the PC. Up to 6 files: screenshots (picked, dropped or pasted with Ctrl+V), the game's log and save, the app's files; the page says where each one is, with the folders to copy into Win+R. |
| Storage | D1, as R2 is off (`server/src/reports.js`, tables `bug_reports` and `bug_files`): the browser packs each file first (a picture as JPEG unless it is smaller as it came, the rest gzipped, a long log keeping its end), 1.9 MB a file at most once packed (D1's rows are 2 MB), 150 MB for all files together, deleted after 90 days (the text stays). 5 reports a driver a day, 200 for everyone. |
| Sent by the app | When the game loses a finished run's official result (a daily, a time trial or league stage: "the game closed before saving its official result", or none after 30 minutes), the app files a report for the driver itself (`client/acr_daily/gamelog.py`): what it saw (its notes on the run in `official.log`) and the game's own log of that session (`acr.log`, or the `acr-backup-...log` the game keeps of it once started again), its start (the game's version, the PC) and its last 448 KB, gzipped, with the Windows user's and the PC's names taken out. One copy of a session's log; it counts toward the driver's 5 a day. The app tells the driver, who sees it on `/report`. Players' games keep no such log as a rule (the first reports, 13 Nov 2026, found none), so every report also has `acr-daily-diagnostics.txt` attached and summed up in its body: what the app saw of the game from the finish on (`client/acr_daily/gamewatch.py`: whether it left the stage, its window "Not Responding", how its process ended: its exit code tells a normal quit, an end from outside such as the Task Manager, and a crash apart), Windows' own records of the game (its Application log's errors and hangs, which name the module that failed) and any crash report the game left (`Saved\Crashes`, under `%LOCALAPPDATA%` and next to the game). |
| Send diagnostics | From 0.1.5 the app's Settings (Game save) has **Send diagnostics**: the driver types a line on what happened and the app files a report the same way (title *Sent from the app*), with the app's notes, the diagnostics and the game's save attached, and shows its number to quote (`gamelog.send_manual`). |
| Who sees them | The driver their own (status and notes on `/report`, a notice in the inbox when the status changes); the admin all of them: `GET /api/admin/reports`, a file at `/api/admin/reports/<id>/files/<fileId>`, `POST /api/admin/reports/<id> {status, note, prUrl}` with `ADMIN_KEY`, or with `REPORTS_KEY` (header `X-Reports-Key`), which opens those and nothing else. Statuses: new, seen, needs-info, pr, fixed, closed. |

### Drivers, teams and the rating

| | |
|---|---|
| Driver page | `/d/<steamId>` (`/me`: your own), linked from every name on the timing sheets: the rating and world rank with its history, career numbers (dailies, wins, podiums, best place, km driven, runs, favourite car and rally, 1V1 record), the last 20 dailies with place, time and rating change, public leagues, cups (`server/src/drivers.js`, `driverpages.js`). |
| Your own name, picture and flag | On your page: a name of your own (3 to 20 characters; unique, compared without case, spaces or `. _ - '`, so nobody can pose as someone else; not another driver's name; one change a week) shown everywhere instead of your Steam name, which is kept apart; a picture (cut to 256 x 256 in the browser, 60 KB at most) instead of Steam's; and a flag (`src/countries.js`, or none), which the app's in-game country no longer changes once picked. The Steam id stays the identity; `admin.py`'s `/api/admin/driver` puts a name or picture back. |
| Teams | `/teams`, `/t/<id>`: a name and a coloured 2 to 4 character tag shown by its drivers' names on the timing sheets and the live map (as in Trackmania). One team per driver, up to 20; the captain hands out and renews the invite code, removes drivers, edits the team, hands the captaincy on and names up to 3 **managers** (`team_members.role`), who run the team in competitions with the captain: they send and answer team 1V1s, sign it up for team cups and name its lineups, and run it in the leagues that use ACR Daily's teams; a captain leaving passes it to the longest member, the last one out closes the team. |
| Results | Once a day is over (the cron, from 01:05 UTC, every 10 minutes, a few dailies a run, catching up on the days before it was there) each daily's board is kept in `daily_results`: what the driver pages read (`server/src/rating.js`). |
| The rating | Like iRacing's iRating, from `RATING_FROM` (`server/wrangler.toml`: a fresh start, everyone at 1500): both dailies and cup matches count, not 1V1s or league events (easy to farm). A daily is a race of everyone on its board, the finishers by place, every DNF last. The maths is iRacing's as the community reconstructed it: each pair of drivers gives the chance one finishes ahead from both ratings, a driver's change (drivers beaten − expected − fudge) × 200 / field (`server/src/rating.js`). A cup match is a race of two; a no contest or a bye is not rated. Each daily and match is rated once. Cups seed by it. |
| World ranking | `/ranking`: everyone with a rating, best first, by country too. |

## In the game: the timer overlay

A small always-on-top window that sits over the game's own timer (drag it there once, then **Lock timer**
so clicks go through to the game):

```
▌ 2:14.31                       stage clock (the game's penalties come with its official time)
  vs Kalle R.  +3.42            live gap to today's #1 (their full run, matched by distance)
  ──────────────────────
  SPLIT 2 / 3         P3 / 12   at each split (25 / 50 / 75 % of the stage), for 8 s:
  1   Kalle R.                  where you stand against every driver's best run today,
  2   Sami P.          +0.88    RallySimFans style: the leader, the driver ahead,
  3   YOU              +1.24    you, the driver behind
  4   Ott T.           +2.10
  vs your best today  −0.35
```

At the finish the same panel shows your provisional position, then your official one once the game has saved its
result. Split times are stage clock. The app and the server time splits the same way, interpolated between
readings, and agree within ~50 ms.

### The timer and the game's FPS

Two drivers lost half their FPS with the app running (Nov 2026). One (full screen, V-Sync with FreeSync on an AMD
card, ghost cars never on): 115 to 160 FPS without it, mostly in the 60s with it, rarely above 70, at times under 40.
The other: 120-140, then 50-60.

What does it: the timer, the displays, the ghost cars' names and the next-daily card are windows of their own,
always on top, over the game. Windows shows a full-screen game's frames straight on the screen ("independent flip")
while no other window is over it; with one there, Windows' compositor (DWM) draws the game's picture together with
that window instead (some graphics cards and drivers can keep the game apart on a hardware overlay plane; not all),
and FreeSync / G-SYNC usually stop: the screen goes back to its fixed refresh rate. With V-Sync on, a frame that misses
a refresh then waits for the next one, so the game runs at half the refresh rate (72 FPS on a 144 Hz screen, 60 on
120 Hz) or a third (48, 40), which fits the drivers' figures (their screens' refresh rates are not known). A window is
over the game or it isn't: how big it is, how often it is redrawn, or how little the app does, changes nothing there.
Overlays drawn inside the game's own picture (Steam's, RivaTuner's, AMD's) don't have this problem.

What the app's own work costs, measured (after 0.1.5.1: a run of a daily played through `App._tick` with real routes,
the timer's and the main window's redraws included; Python 3.12 under Linux, no game, so Windows' text drawing may
differ a little): **about half a millisecond a tick, around 1 % of one CPU core** at 20 ticks a second. Too little to
take frames from the game.

- **Not moved over and over** (0.1.5.1): the timer set itself always-on-top on every tick, and Tk moves a window to
  the top of Windows' order of windows each time (`SetWindowPos`): 20 times a second, and 10 for the next-daily
  card. Now an overlay goes back on top only when a window of another program has come over it, looked at twice a
  second (`widgets.keep_on_top`). The footer's count of runs waiting to be sent no longer reads `pending.json` from
  disk on every tick.
- **Hide while driving, on by default** (after 0.1.5.1; 0.1.5.1 had it off by default, for every window and every
  game): while a run's stage clock runs (a daily, a time trial or a league stage), nothing of the app on the screen a
  full-screen game fills (the game's window as big as its screen: full screen, or borderless at the screen's size):
  the timer, the displays and the ghost cars' names (the mod's cars still drive in the game); they come back when the
  game is paused and at the finish. A window on another screen stays (it costs the game nothing), and so does
  everything over a game in a smaller window (Windows composes that anyway). Which screen the game fills is looked at
  once a second, in the screens' own pixels (`widgets.GameScreen`; when it can't be told, everything goes, as before).
  A next-daily card still up when a run starts closes. Settings › Timer › Hide while driving turns it off
  (`hideOverGame`; 0.1.5.1's `hideDriving` is dropped, so everyone starts with it on). (`App._hidden_screen`,
  `_apply_visibility`.)
- **No program started to look for the game** (after 0.1.5.1): "is the game running?" ran `tasklist` each time (a
  `cmd.exe`, a console host and a `tasklist.exe` started, and virus-checked), every 2 s while a finished run waited
  for its official time (twice for a league stage) and at the start line's look at the save, with the app's window
  standing still until it answered. Now the game is found in Windows' list of processes and held by a handle once
  found: each later look is one call (`saveslot.game_running`).
- **Pads** (ghost cars, after 0.1.5.1): the camera key's poll asked all four XInput pad slots on every frame (60 a
  second); an empty slot is slow to ask (Microsoft says not to every frame), so one found empty is asked again every
  3 s (`ghostui.PAD_LOOK_S`).
- **Measured on the drivers' PCs** (after 0.1.5.1): while a run's clock runs, the app counts how often the game writes
  its telemetry's graphics page (its packet id), apart for while a window of the app was over the full-screen game and
  while nothing was, and says it in `official.log` after the run: `the game's graphics packets while the clock ran:
  131/s with nothing of the app over the full-screen game (3:10); 64/s with a window of the app over the full-screen
  game (0:40)` (`telemetry.PacketRate`, `App._measure`). Send diagnostics carries it. If the game writes that page once
  a frame, these are its FPS: check once against the game's own FPS counter (or a recorded `shm-dump.jsonl`) before
  reading them so.
- What a driver can do with any version: turn the timer off (Settings › Timer › Show the timer; the displays under
  In-game displays) and compare; put the timer on a second screen, where it costs the game nothing; or turn V-Sync off
  in the game (no halving, but no FreeSync while the timer is over the game). On NVIDIA, "Enable G-SYNC for windowed
  and full screen mode" (Control Panel › Set up G-SYNC) is meant to keep G-SYNC on for a game Windows composes: worth
  a try.
- To see it on a PC: PresentMon's `PresentMode` for `acr.exe` reads `Hardware: Independent Flip` with nothing over the
  game and `Composed: Flip` with the timer there.
- The way to keep a timer over the game while driving at no cost is to draw it inside the game's own picture: through
  RivaTuner's on-screen display (its shared memory, `RTSSSharedMemoryV2`, takes text from other programs; for drivers
  who run RivaTuner), or the way the ghost cars' mod puts cars in the game (`mod/`). Not done.

## How it works

```
 Player PC                                          Cloudflare
┌──────────────────────────────────────┐           ┌───────────────────────────────────┐
│ ACR-Daily.exe (client/)              │  Steam    │ Worker (server/src/index.js)      │
│  telemetry.py  reads shared memory   │  sign-in  │  /auth/steam/*   OpenID sign-in   │
│  judge.py      start/reset/DNF/finish│ ────────► │  /api/challenge  today's stage    │
│  app.py        main window + timer   │  runs     │  /api/runs       stores runs      │
│                window over the game  │ ────────► │  /api/leaderboard                 │
│  api.py        server + offline queue│ ◄──────── │  /               website          │
└──────────────────────────────────────┘           │ D1 database (server/schema.sql)   │
                                                   │ (R2 bucket for the traces: option)│
                                                   └───────────────────────────────────┘
```

**What the game provides** (checked on real runs; same layout as Assetto Corsa Competizione):

| Field | Where |
|---|---|
| Stage clock | `"MM:SS.mmm"` at graphics +12. Reads 0 on the start line, runs from the line, freezes at the finish. |
| Car position | graphics +256 |
| Speed | physics +28 |
| Car and stage names | static +68 / +134 |

Penalties, the final time, assists and settings are **not** provided. (A Rally Weekend stage's official time and
penalty are, afterwards: the game writes them into its save, which `rallyweekend.py` reads.)

**Judging a run.** The app is the only judge (`client/acr_daily/judge.py`). It reads the telemetry 20 times a second and decides:

| | |
|---|---|
| Start | The run starts when the stage clock does, on the daily's stage and car. The car has to be within 60 m of the route's start (further away = **INVALID**). A clock that was already running doesn't count. |
| Resets | Counted for the record (the game's own respawn penalty is in its official time). A reset is either the car jumping further than it could drive between two readings (15 m, or 3 m when nearly stopped, plus 1.5 × the distance its speed covers), or the car going from 30 km/h or more in gear to standing still in neutral within 0.6 s. The game puts a reset car down stopped in neutral, sometimes only a few metres from where it left the road. A reset counts once the run is still going 1.5 s later, and never twice within 3 s. |
| DNF | The clock goes back (a restart), the stage or car changes, the clock stays frozen away from the finish with the car moving (or the game is gone) for more than 30 s, or a pause lasts more than 15 minutes. |
| Pause | The clock frozen and the car not moved more than 2 m since (the game's pause menu freezes the car) = paused: no DNF, and never taken for the finish. |
| Finish | The clock stops near the end of the route while the car rolls on. The run has to pass within 40 m of at least 90 % of the route's checkpoints (one every 100 m), or it is **INVALID**. |

It then sends its result (status and reason, stage clock, resets, splits, jumps) and the whole run trace,
4 samples a second:

- stage clock, PC clock and the game's physics step counter;
- position and speed;
- throttle, brake, steering, gear and rpm;
- air temperature;
- resets so far.

**The server takes the result as sent** (`server/src/validate.js`, `submitRun` in `server/src/index.js`):

| | |
|---|---|
| Time | The game's own stage time + penalty, as the app read them from the game's save (a finished run without them is refused). Not checked against the trace. |
| App version | Apps older than `MIN_APP_VERSION` can't send runs, live positions or new routes (HTTP 426, for the dailies from `MIN_APP_FROM` on; both in `server/wrangler.toml`). So every run on a board was judged by the same rules. |
| First run counts | A driver's first run of a daily goes on its board; later ones are practice. A start that never sends a result is a DNF once a later run arrives, or after an hour. |
| Sanity checks | A run needs a signed-in Steam account that isn't banned, today's daily (yesterday's until 00:30 UTC) with its stage and car, a known status, 0–99 resets and a clock under 4 h. A driver can send 300 runs a day. |
| The trace | Kept for the counted run only, gzipped (`server/src/traces.js`), not judged. It feeds the run viewer, the split standings, section times, the stats page and the live gap to #1. After 14 days only each daily's top 3 keep theirs; the others keep their times, splits and sections. |

**Reports.** Every counted run has a public viewer page (`/run/<id>`) showing:

- the map against the day's #1;
- speed, gap, throttle, brake and steering charts with a shared crosshair;
- section times;
- a **Report this run** button.

A report (signed-in drivers who finished a daily, one each) is a note for the admin and changes nothing by itself.
An admin decides with `tools/admin.py` ([SETUP.md](SETUP.md#5-looking-after-it)): `state` lists every reported
run, `run <id>` shows one, `reject <id>` takes it off the board, and `ban <steamId>` blocks a player (their runs leave
the boards and new ones are refused). For the dailies before 2026-10-09, which the app timed itself: for a reset the
app missed, `resets <id>` finds the resets in the run's trace and `fix-run <id> <resets> [stage clock of each]`
corrects its resets, total and splits (`--dry-run` first).

**No longer checked.** The server used to re-run the app's rules on the trace and test whether it behaved like a car
in the game (`server/src/realism.js`). Those checks refused or flagged real runs, so they were removed. The server no
longer checks:

- that the trace starts at the start, reaches the finish at the reported time and passes the checkpoints;
- that the clock only goes forwards, with no gaps;
- that every jump in the trace was counted as a reset;
- the stage clock against the PC clock and the game's physics steps;
- speed, acceleration, braking, cornering, throttle, rpm and steering against what a car can do;
- section times against the other drivers' and the driver's own best;
- the air temperature against the other drivers' (the game draws it anew each session, so the same set-up differs);
- that the game ran under the Steam account that signed in.

What this catches: restarts, resets, shortcuts, the wrong car or stage and joining late, judged by the same rules
for everyone. What it can't catch: a modified app or a made-up upload, because the server takes the app's word for
it. The viewer and the reports exist so people can spot those.

## Folders

```
client/              the Windows app (Python 3.13 + tkinter, built with PyInstaller)
  acr_daily/         telemetry, judge, route, recorder, saveslot (game save), gamelog (the game's log, sent when it loses a run's result), rallyweekend (the game's Rally Weekend
                     set-up and results in its save), leagues (league events in the save), autodrive, ghosts,
                     widgets, api, app (UI: a 16:9 window in panels, laid out like RaceRoom's; a fixed size from 0.1.5.13, Settings › Window size: 1280 × 720 up to 1920 × 1080 at Windows' scale, and vertical ones (720 × 1280 up to 1080 × 1920) for a screen stood on its end, the ones that fit any of the PC's screens; one picked that doesn't fit the screen the window is on puts it on a screen it fits, e.g. the vertical one (`app.work_areas`, `area_for`); or Resizable as before, `app.WINDOW_SIZES`, `fixed_size`), signinui (Steam first: the
                     sign-in screen), homeui (HOME, where it opens: a photo tile for each part), tabsui (the header's nav and icons, the driver's card, 1V1
                     challenges, cups), challengeui (a new 1V1), leagueui (COMPETITIONS: leagues, 1V1s, cups), ttui (the
                     time trial tab), settingsui (the settings
                     tab), profileui (the driver page: profile, achievements, shop, customize, as on the website), tiles
                     (the stage and event cards), photos (the photos behind them: Wikimedia Commons, credited in
                     photos/photos.json and photos/CREDITS.md; a league's or a cup's own banner, from the website, on
                     its cards), icons (Lucide's, ISC: icons/)
  acr_daily/i18n.py  the app's languages (locales/: the catalogs)
  tests/             unit tests (judge, standings, names, save slot, route recorder, languages)
  build.bat          builds dist/ACR-Daily.exe with the server URL baked in
  make_icon.py       draws the app icon (acr_daily/icon.ico) and the header logo (acr_daily/logo-*.png)
  make_icons.py      draws the UI's icons (acr_daily/icons/*.png) from Lucide's SVGs and the Discord mark
server/              Cloudflare Worker + D1 + R2
  src/               index.js (API + auth), validate.js (stores runs), realism.js (splits, sections,
                     temperatures), cars.js, conditions.js, stages.js (menu names), steam.js,
                     traces.js (run traces), cache.js (kept boards, stats), discord.js (the Discord bot),
                     leagues.js (leagues: rules, standings, seasons), leaguesapi.js (their API), leaguediscord.js (their Discord posts),
                     social.js (the inbox), h2h.js (1V1s), cups.js (cups), timetrial.js (the weekly time trial);
                     teamscore.js (how a team's drivers make its result), leagueteams.js (a league's teams and team
                     championships), teammatch.js (team matches), teamh2h.js (team 1V1s), teamcups.js (team cups);
                     pages: site.js, viewer.js, statspage.js, leaguepages.js, socialpages.js, timetrialpage.js, teampages.js;
                     header.js (every page's header: DAILIES, TIME TRIAL, COMPETITIONS ▾, COMMUNITY ▾, as the app);
                     logo.js (logo + favicon); i18n.js (the languages; locales/: the catalogs)
  test/              *.test.mjs (node --test), e2e*.py (against `wrangler dev`), fixtures/ (real runs)
  schema.sql         full schema; migrations/ upgrade older databases
tools/admin.py       routes, pool, schedule, reject runs, ban players, pack old traces
tools/i18n/          extract.py: the strings to translate, the API's messages, the catalogs checked
routes/              reference routes (Alsace Obersteigen, Alsace Forêt, Wales Afon Bidno)
brand/               the logo and app icon as SVG
CATALOG.md           every stage, car, weather and time the game offers
```

## Languages

The app and the website speak **English, Polski, Magyar, 日本語, Deutsch, Français, Español, Italiano, Português
(Brasil) and 简体中文**. A new language: its catalogs (below), and an entry in `LANGS` in `client/acr_daily/i18n.py`
(and `_WIN_LANG`, Windows' language id) and in `server/src/i18n.js` (with its import and `CATALOGS` entry); a plural
rule in `plural_index` / `pluralIndex` if it counts differently, and `NFORMS` in `tools/i18n/extract.py`.

- **The app** starts in Windows' display language the first time (English if it isn't one of these), and the Settings
  tab or the sign-in screen switch it (the app starts again in the new language).
  `ACR_DAILY_LANG=de` runs it in one language while developing.
- **The website** follows `?lang=`, then the `lang` cookie the picker in the header sets (in the driver's menu once
  signed in), then the browser's
  Accept-Language. The API answers in the request's language too: its error messages and a driver's achievements
  (the app sends its own language; it says the weather, rallies and the like in its own catalog).
- **The words** are the English text itself, marked in the code: `_('...')` / `n_(one, other, n)` in the app (Python
  `%` formats; `%2$s` in a translation puts the values in another order), `t('...')` / `tn(...)` on the server and
  `${tq('...')}` / `F(...)` / `P(...)` in a page's script (`{0}` values). The API's messages are collected from
  `err('...')` and the like.
- **The catalogs**: `client/acr_daily/locales/<code>.json` (the app) and `server/src/locales/<code>.js` (the website
  and the API): English -> translation; a plural is a list of the language's CLDR forms (Polish 3, Hungarian, Japanese
  and Chinese 1, the others 2).
- **After changing the words**: `python tools/i18n/extract.py api` (the API's message list), then
  `python tools/i18n/extract.py check` lists what each language is missing, no longer uses, or gets wrong (values,
  plural forms, markup); `check --all` also takes in a language translated but not offered (`PAUSED`).
  `python tools/i18n/extract.py list app|web`
  prints every English string. `node server/test/pages_i18n_check.mjs [code|pseudo]` builds every page in every
  language (`pseudo`: every word with quotes and `<` in it) and compiles its scripts.
- **The changelog** (`server/src/changelog.js`): each entry's headline and lines are in `N_()`, so `check` lists them
  for every language. The website's /changelog and the app's WHAT'S NEW screen say them in the reader's language
  (English until translated); the #changelog post on Discord and the GitHub Release say English.
- **Not translated**: the game's own menu names (Racing › Rally › Rally Weekend...), stage and car names, the admin
  page, Discord posts, and what drivers and admins write (messages, league notes, stewards' reasons).

## Development

```bat
:: client tests (judge tests on raw recordings run when ACR_DAILY_RECORDINGS points at them)
cd client && python -m unittest discover -s tests

:: run the app from source; a JSONL telemetry dump can stand in for the game:
set ACR_DAILY_REPLAY=<path to dump.jsonl>
set ACR_DAILY_REPLAY_FROM=55
python run.py

:: server tests
cd server && npm install && npm test

:: local server with a local database (--local-upstream: without it the Worker sees every request as one to acrdaily.com,
:: the route in wrangler.toml, and a Steam sign-in comes back to the real site: "Sign-in expired")
copy .dev.vars.example .dev.vars
npx wrangler d1 execute acr-daily --local --file=schema.sql
npx wrangler dev --port 8790 --ip 127.0.0.1 --local-upstream 127.0.0.1:8790
python test\e2e.py http://127.0.0.1:8790 local-test-admin-key-0123456789abcdef
```

**Admin mode in the app.** In `%APPDATA%\ACR Daily\settings.json`, set `"admin": true` and `"adminKey": "<ADMIN_KEY>"`.
This adds two buttons:

- **Record route:** drive a stage once, cleanly. The route is saved to `%APPDATA%\ACR Daily\routes`.
- **Upload route:** sends the recorded route to the server.

## Limits worth knowing

- The timer window can only sit over the game in **borderless or windowed** mode, not exclusive fullscreen.
- **Game updates.** A patch could move telemetry fields. If that happens, `telemetry.py` is the only file to fix.
- **Assists and settings.** The game doesn't report assists, gearbox or difficulty, so they can't be enforced. Put a note on the website asking people to drive fairly.
- **Free tier.** ACR Daily is built to stay on Cloudflare's free plan with about 100 drivers a day:
  - *100,000 requests a day.* While driving the app sends its position every 5 s (the other drivers come back in the
    same answer); otherwise it asks for the boards every 2 minutes with the game running, 5 without, and the rest every
    10–60 minutes. That is roughly 400 requests per driver per day. The pace is set on the server (`LIVE_SEND_S` ...
    in `server/wrangler.toml`): if the daily count gets close to the limit (dashboard > Workers > acr-daily > Metrics),
    raise them and deploy; the apps follow within 10 minutes.
  - *100,000 rows written, 5 million read a day.* Boards and the stage stats are built once and kept
    (`server/src/cache.js`), live positions are deleted 2 minutes after their last update, and the stats page uses
    each run's small profile instead of its trace.
  - *10 ms of CPU a request.* Nothing reads more than two traces at once.
  - *500 MB of database.* Only counted runs keep a trace, gzipped (~50 KB a run); after 14 days only each daily's
    top 3 do (`TRACE_DAYS`, `TRACE_TOP` in `server/src/traces.js`). With 100 counted runs a day the database is about
    300 MB after a year.
  The paid plan ($5 a month) lifts all of these; with it an R2 bucket can hold the traces (`server/wrangler.toml`).

## Licence and disclaimer

ACR Daily is released under the [MIT licence](LICENSE).

It is a fan-made community project and is not affiliated with, endorsed by or connected to Supernova Games
Studios, Kunos Simulazioni, 505 Games or Valve. *Assetto Corsa Rally* and all car, stage and brand names are
trademarks of their respective owners. The app only reads the telemetry the game publishes, edits the
player's own single-stage and Rally Weekend set-ups in their save file (with a backup) and reads the game's own
results from it; it does not modify the game.
