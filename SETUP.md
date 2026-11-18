# Running your own ACR Daily server

Everything runs on Cloudflare: one Worker (API + website + app download), one D1 database and one R2 bucket (the run
traces). The free plan is enough to try it and for a few dozen drivers a day; for more, the Workers Paid plan
($5 a month). Commands are for a Windows Command Prompt, from the repository folder.

## 1. Tools

- **Node.js LTS** from <https://nodejs.org> (for `wrangler`, Cloudflare's CLI).
- **Python 3.13** from <https://python.org> (for the app and `tools\admin.py`).
- A free **Cloudflare account**: <https://dash.cloudflare.com/sign-up>.

## 2. Deploy the server

```bat
cd server
npm install
npx wrangler login
npx wrangler d1 create acr-daily
```
`d1 create` prints a `database_id`. Put it in `server\wrangler.toml` in place of the one there.

```bat
npx wrangler d1 execute acr-daily --remote --file=schema.sql
```
`schema.sql` is the full current schema. `migrations\` is only for servers created before a change.

The run traces go to an R2 bucket (R2 has to be switched on once in the Cloudflare dashboard, *R2 Object Storage*;
10 GB are free):
```bat
npx wrangler r2 bucket create acr-daily-traces
```
then remove the `#` in front of the `[[r2_buckets]]` lines in `wrangler.toml`. Without the bucket the traces stay in
the database, as before; a server that ran without it moves them with `python admin.py move-traces` once it has one.

Make an admin key (treat it like a password) and store it as a secret:
```bat
python -c "import secrets; print(secrets.token_urlsafe(32))"
npx wrangler secret put ADMIN_KEY
```
Optional, for names and avatars: a Steam Web API key from <https://steamcommunity.com/dev/apikey>,
stored with `npx wrangler secret put STEAM_API_KEY`.

Optional, the Discord bot (a live board of who is on stage and today's timing sheets, then each day's results):
in your Discord server, open the channel it should post in (e.g. a read-only #live-timing), *Edit Channel ›
Integrations › Webhooks › New Webhook*, name it, give it the icon from `brand\`, *Copy Webhook URL*, then
`npx wrangler secret put DISCORD_WEBHOOK_URL` and paste it. It runs every 5 minutes from the cron trigger;
`SITE_URL` in `wrangler.toml` is the address its links point to.

Optional, the Discord bot account (the FAQ, #changelog, `/event` below, and the two dailies as Discord server Events
every day, created at 00:00 UTC, live all day, ended at midnight, only with `DISCORD_DAILY_EVENTS = "1"` in
`wrangler.toml`: off by default; `src/discordevents.js`): a webhook cannot do these, so this needs a bot account. At
<https://discord.com/developers/applications> *New Application* (e.g. "ACR Daily"), give it the icon from `brand\`;
*Bot › Reset Token* and copy it; then add the bot to your server with
`https://discord.com/oauth2/authorize?client_id=<Application ID>&scope=bot&permissions=17600775979008`
(Create Events + Manage Events, nothing else). Store the token with `npx wrangler secret put DISCORD_BOT_TOKEN` and set
`DISCORD_GUILD_ID` (your server's id) in `wrangler.toml`. `python admin.py discord` shows what it did.

Optional, event sign-ups on Discord (`src/discordrsvp.js`): anyone with **Manage Events** types `/event` in a channel
(e.g. #events), fills in the form (title, start, length, where, description) and the bot posts a card with
**Attending / Maybe / Not attending** buttons that lists who answered what; it also makes the matching server Event.
Nothing to set up beyond the bot above and a deploy: within 10 minutes (or at once with `python admin.py discord`, its
`commands`) the server makes its tables, reads the application's Public Key from Discord, registers `/event` and sets
the application's **Interactions Endpoint URL** to `SITE_URL/discord/interactions`. Its `commands` says what went wrong
otherwise, e.g. a 403 registering `/event` for a bot added without the commands scope: open
`https://discord.com/oauth2/authorize?client_id=<Application ID>&scope=bot+applications.commands&permissions=17600775979008`
once (the same permissions). Who may use `/event`: Server Settings › Integrations › (the bot) › `/event` (Manage Events
by default).
To post a card as the bot instead (no one typing `/event`): insert a `discord_events` row with `channel_id = 'queued'`
(`npx wrangler d1 execute acr-daily --remote --command "INSERT INTO discord_events (guild_id, channel_id, title, description,
location, starts, ends, created_by_name, created) VALUES (...)"`, times in ms); the cron posts it in #events (the bot
needs Send Messages and Embed Links there) and makes its server Event. `python admin.py discord` shows `queued`.

```bat
npx wrangler deploy
```
It prints your address, e.g. `https://acr-daily.YOURNAME.workers.dev`.

## 3. Release the app

The exe people download is built by **GitHub Actions** from a tagged commit (`.github\workflows\release.yml`),
with a signed build attestation, so anyone can check that it's the public code
(`gh attestation verify ACR-Daily.exe --repo <owner>/acr-daily`). In your fork, set `SERVER_URL` in the workflow
and `DOWNLOAD_URL` / `SOURCE_URL` in `server\wrangler.toml` to your own addresses.

For each version:
1. Bump `__version__` in `client\acr_daily\__init__.py` and, in the same commit, add the version's entry at the top
   of `server\src\changelog.js`: what drivers will notice, one short plain line each. From 0.0.31 on it also needs
   a `title` (the headline), a `photo` (a key of `client\acr_daily\photos\photos.json`; a new photo goes there with
   its author and licence) and 2 to 12 short lines, and from 0.1.6 on each line's kind: `NEW(N_("..."))`,
   `BETTER(...)`, `FIX(...)` or `NOTE(...)` (its tag: NEW, IMPROVED, FIXED, NOTE). The app shows them on its WHAT'S NEW
   screen after the update, with every version the driver skipped under them.
   It is published as the release's notes, on the website's `/changelog`, in Discord's #changelog and on that screen. **No entry, no release**: the tests
   (`server\test\changelog.test.mjs`) and the workflow stop without one. Commit and push.
2. `git tag v<version>` and `git push origin v<version>`. The workflow tests, builds and publishes the GitHub Release
   (exe + `.sha256` + attestation, with the changelog entry as its notes). Or, without a tag: GitHub › Actions › release › Run workflow on `main`; it releases
   the version in `__init__.py` and the release makes its tag.
   **Test builds** for the testers, automatic: each change of the app merged into `main` (`client/`, `mod/`, the release
   workflow) runs `.github/workflows/dev.yml`, which builds it as a prerelease numbered after the release out now
   (`LATEST_VERSION` 0.1.5: 0.1.5.4, 0.1.5.5...; the number is written for that build only, `main` keeps the next version, 0.1.6).
   Its what's new is the release it leads to (`changelog.js` `entryForBuild`: no entry needed for each), shown under
   the test build's own number ("What's new in 0.1.5.42 (test build)": testers never read of a release that isn't
   out), once per entry: a later test build under the same entry opens nothing by itself (SETTINGS › About › WHAT'S
   NEW shows it). A tester
   installs one test build once from its release page; from then on their app finds the newest test build on GitHub
   and offers it on its UPDATE bar, and the release itself when `LATEST_VERSION` passes them. Nobody else is offered
   one: the website's download and everyone else's UPDATE follow `LATEST_VERSION`. By hand: Actions › release › Run
   workflow with *test* ticked (any branch), or Actions › dev build. The builds use the live server: deploy it (with its
   migrations) when a change needs the server too.
3. When the release is up, set `LATEST_VERSION` in `server\wrangler.toml` and `npx wrangler deploy`. The website's
   download points at the new release and every app shows its UPDATE button. Within 10 minutes the bot posts the
   version's changelog in Discord's #changelog (it makes that channel, read-only, like #faq; it needs
   `DISCORD_BOT_TOKEN`; it needs Send Messages and Embed Links in #changelog), and `/changelog` shows it. After the update an
   app shows its WHAT'S NEW screen on its first start (`GET /api/changelog/<version>?since=<last seen>`: so deploy the
   server before people update).
4. If older apps must stop sending runs (they judge differently), also set `MIN_APP_VERSION` to the new version and
   `MIN_APP_FROM` to the first daily it applies to (usually tomorrow, so a day under way keeps its apps). From then on
   the server refuses their runs, live positions and new routes (HTTP 426), and they show their UPDATE button.
5. **Rally Weekend dailies** (the game's own time and penalties count, see README): release an app that does them
   first, then set `OFFICIAL_FROM`, `MIN_APP_VERSION` (that app) and `MIN_APP_FROM` to the same day, usually tomorrow,
   and deploy. Dailies before that day keep their Single Rally Stage rules; the website, the guide and the Discord FAQ
   switch their rules text on the day.
6. **Leagues** (README): on a server made before them, first add their tables
   (`npx wrangler d1 execute acr-daily --remote --file=migrations/0014_leagues.sql`). That comes before the deploy:
   the Steam sign-in reads the new `logins.next` column. Then `npx wrangler deploy`: the website's league pages work
   at once. Then release the app with the LEAGUES view; `LEAGUES_MIN_APP` in `wrangler.toml` is that version.
7. **Credits, messages, 1V1s and cups** (README): add their tables before deploying a server that has them,
   credits on or not (the timing sheets read the looks table, every league query `leagues.kind`):
   `migrations/0015_credits.sql`, then `migrations/0016_shop.sql`, then `migrations/0017_social.sql`, the same way as
   step 6. Messages, 1V1s and cups work at once; their stakes and entry fees only with credits on.
   To switch credits on, release the app that stakes at DRIVE and set
   `CREDITS_MIN_APP` in `wrangler.toml` to that version (older apps are told to update before they can drive SS2,
   which needs a stake from then on), set `CREDITS_FROM` = the first day they count, and deploy.
   Credits are only ever earned: never let them be bought or cashed out, which would make the wager daily gambling.
8. **Driver pages, teams and the rating** (README): `migrations/0018_drivers.sql` (after 0017, the same way), then
   deploy. Driver pages, names, pictures, teams and the ranking page work at once; the cron keeps each finished day's
   results from then on, catching up on the days before (a few dailies every 10 minutes). The rating starts with
   `RATING_FROM` in `wrangler.toml`: the first daily it counts (usually tomorrow; everyone starts at 1500), and deploy.
9. **Official cups** (README): `migrations/0019_official_cups.sql` (after 0017, the same way), then deploy. Make one with
   `python admin.py cup new cups\inaugural-cup.json` from `tools` (its settings, its match and its banner from the file).
   The coming 30 days' dailies are fixed ahead by the cron every hour; after changing the pool, `python admin.py ahead --repick`.
   An official cup's sign-ups, rounds and results are posted on Discord (`src/cupdiscord.js`): in the channel of
   `DISCORD_CUPS_WEBHOOK_URL` (a webhook made as for the bot above, e.g. in a #cups channel:
   `npx wrangler secret put DISCORD_CUPS_WEBHOOK_URL`), else in the bot's own channel.
10. **Cup reminders** (round times fixed to the start, a reminder in the inbox before a round closes):
   `migrations/0020_marks.sql` (the same way), then deploy.
11. **The weekly time trial** (README): `migrations/0027_time_trial.sql` (after 0026, the same way), then deploy. It
   starts with the week `TIME_TRIAL_FROM` in `wrangler.toml` is in (empty: off); the app's TIME TRIAL tab comes with app
   0.0.23. The cron fixes each week's two stages as it starts and pays out the week before an hour after it closes.
12. **Bug reports** (README, `/report`): `migrations/0028_bug_reports.sql` (the same way), then deploy. The admin reads
   them with `ADMIN_KEY`. For someone (or an agent) who should read and answer the reports and nothing else, set a key
   of their own: `npx wrangler secret put REPORTS_KEY` (24 characters or more), sent as the header `X-Reports-Key`.
13. **Hidden events** (README, Leagues › Hidden): `migrations/0029_hidden_events.sql` (the same way), then deploy. Events
   made before it keep everything shown; new ones hide their stage names, weather and times by default. Apps older than
   `HIDDEN_MIN_APP` in `wrangler.toml` (0.0.25) don't list hidden events, so release that app soon after.
14. **Official leagues** (README, Leagues › Official): `migrations/0030_official_leagues.sql` (the same way), then deploy.
   Make one from a file with `python admin.py league new leagues\exr-rally-championship.json` (`tools/leagues/`); it
   prints the league's page and its invite link. Change it, or add rounds, with `python admin.py league set <id> <file>`.
15. **League stage starts sent twice** (README, Leagues › DNF): `migrations/0031_stage_start_stamp.sql` (the same way),
   then deploy, then release app 0.0.28 (it sends each start's time; older apps work as before).
16. **A league stage retired** (README, Leagues › Retirement rule): `migrations/0032_stage_retired.sql` (the same way), then
   deploy (the league standings read its column).
17. **Rallies and Community organizers** (README, Rallies and championships): `migrations/0033_rallies.sql` (the same
   way) before the deploy (the server reads `players.organizer`), then deploy, then release app 0.1.6 (the RALLIES tab;
   older apps list rallies as league events). The migration makes the drivers who run a championship
   organizers; more with `python admin.py organizer <steam id>` (`--off` takes it back) or the admin page.
18. **Comments on runs** (README): `migrations/0034_comments.sql` (the same way), then deploy (the boards and event pages
   read the table; without it they show no comments), then release the app that offers them (0.1.5.1 / 0.1.6; older apps
   just don't). Or migration and deploy at once from GitHub: Actions › deploy › Run workflow, one migration a run.
19. **Liveries** (README, Liveries): `migrations/0035_liveries.sql` (the same way), then deploy. Drivers send theirs
   on `/liveries`; publish them on the `/admin` page's Liveries tab (or `python admin.py liveries`). The app's
   COMMUNITY › LIVERIES comes with 0.1.5.1 / 0.1.6; older apps simply don't show it.
20. **Event sign-ups on Discord** (`/event`, section 2's last Discord paragraph): just deploy. The server makes its
   tables itself (`migrations/0037_discord_events.sql` is the same, if you'd rather run it first).
21. **Team competitions** (README: Leagues › Teams, Team 1V1, Team cups; teams' managers): `migrations/0042_team_competitions.sql`
   (the same way), then deploy. Everything works at once: team matches come to every app in its 1V1 and CUPS tabs; the
   next app release links them to their team pages and shows a team match's scores on its timing sheet.

To try a build on your own PC first: `client\build.bat https://acr-daily.YOURNAME.workers.dev` (output in `client\dist`).

To try the app from source against a local server without touching your real sign-in:
`set ACR_DAILY_HOME=%TEMP%\acr-daily-test` and `set ACR_DAILY_SERVER=http://127.0.0.1:8790` before `python run.py`
(a local server with Rally Weekend days: `npx wrangler dev --port 8790 --ip 127.0.0.1 --local-upstream 127.0.0.1:8790 --var OFFICIAL_FROM:2000-01-01`).

## 4. Stages

Stages join the rotation by themselves: the first clean run (no resets) on a stage without a route is sent by
the app, checked by the server and becomes that stage's route. To seed some right away:

```bat
cd tools
set ACR_DAILY_SERVER=https://acr-daily.YOURNAME.workers.dev
set ACR_DAILY_ADMIN_KEY=<your admin key>
python admin.py routes ..\routes
python admin.py state
```

## 5. Looking after it

- **The admin page, `/admin`** on the website (it asks for the admin key, kept in that browser tab only): runs with
  warnings or reports (clear or reject), reported private messages (dismiss, delete, ban the sender), drivers (put a
  name or picture back to Steam's, ban, unban), teams (close one), banned drivers, a league's banner to take down.
- The server doesn't check runs: it keeps each result as the app sent it ([README](README.md#how-it-works)).
  Drivers can report a run (a note for the admin; it changes nothing by itself). `python admin.py state` lists every
  reported run and any run the old server checks flagged. `admin.py run <id>` shows one, `admin.py reject <id>`
  removes it, `admin.py ban <steamId>` blocks a player.
- The Discord bot: `python admin.py discord` runs it now and says what it did (or why it can't post).
- A run with resets the app missed: `python admin.py resets <id>` lists the resets its trace shows, then
  `python admin.py fix-run <id> <resets> <stage clock of each, e.g. 2:57.670> --dry-run` shows the new total, splits
  and place; run it again without `--dry-run` to write it (`fix-run <id> 0` undoes it).
- `python admin.py schedule <date> <slot> "<stage>" "<car>" [weather] [time]` fixes a future daily.
  A day's dailies never change once the day has started.
- The app is the only judge (`client\acr_daily\judge.py`). When a new version judges runs differently, raise
  `MIN_APP_VERSION` and `MIN_APP_FROM` (step 3) so one board never mixes the two.
- The exe isn't code-signed, so Windows SmartScreen warns on first start (*More info → Run anyway*).
