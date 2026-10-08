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

Optional, the Discord bot (a live board of who is on stage and today's timing sheets, then each day's results and
the hall of fame): in your Discord server, open the channel it should post in (e.g. a read-only #live-timing), *Edit Channel ›
Integrations › Webhooks › New Webhook*, name it, give it the icon from `brand\`, *Copy Webhook URL*, then
`npx wrangler secret put DISCORD_WEBHOOK_URL` and paste it. It runs every minute from the cron trigger;
`SITE_URL` in `wrangler.toml` is the address its links point to.

Optional, the two dailies as Discord server Events every day (created at 00:00 UTC, live all day, ended at midnight;
`src/discordevents.js`): a webhook cannot make events, so this needs a bot account. At
<https://discord.com/developers/applications> *New Application* (e.g. "ACR Daily"), give it the icon from `brand\`;
*Bot › Reset Token* and copy it; then add the bot to your server with
`https://discord.com/oauth2/authorize?client_id=<Application ID>&scope=bot&permissions=17600775979008`
(Create Events + Manage Events, nothing else). Store the token with `npx wrangler secret put DISCORD_BOT_TOKEN` and set
`DISCORD_GUILD_ID` (your server's id) in `wrangler.toml`. `python admin.py discord` shows what it did.

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
1. Bump `__version__` in `client\acr_daily\__init__.py`, commit and push.
2. `git tag v<version>` and `git push origin v<version>`. The workflow tests, builds and publishes the GitHub Release
   (exe + `.sha256` + attestation).
3. When the release is up, set `LATEST_VERSION` in `server\wrangler.toml` and `npx wrangler deploy`. The website's
   download points at the new release and every app shows its UPDATE button.
4. If older apps must stop sending runs (they judge differently), also set `MIN_APP_VERSION` to the new version and
   `MIN_APP_FROM` to the first daily it applies to (usually tomorrow, so a day under way keeps its apps). From then on
   the server refuses their runs, live positions and new routes (HTTP 426), and they show their UPDATE button.
5. **Rally Weekend dailies** (the game's own time and penalties count, see README): release an app that does them
   first, then set `OFFICIAL_FROM`, `MIN_APP_VERSION` (that app) and `MIN_APP_FROM` to the same day, usually tomorrow,
   and deploy. Dailies before that day keep their Single Rally Stage rules; the website, the guide and the Discord FAQ
   switch their rules text on the day.

To try a build on your own PC first: `client\build.bat https://acr-daily.YOURNAME.workers.dev` (output in `client\dist`).

To try the app from source against a local server without touching your real sign-in:
`set ACR_DAILY_HOME=%TEMP%\acr-daily-test` and `set ACR_DAILY_SERVER=http://127.0.0.1:8790` before `python run.py`
(a local server with Rally Weekend days: `npx wrangler dev --port 8790 --var OFFICIAL_FROM:2000-01-01`).

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

- The server doesn't check runs: it keeps each result as the app sent it ([README](README.md#how-it-works)).
  Viewers can report a run. `python admin.py state` lists every reported run (three reports mark it UNDER REVIEW
  on the board) and any run the old server checks flagged. `admin.py run <id>` shows one, `admin.py reject <id>`
  removes it, `admin.py ban <steamId>` blocks a player.
- The Discord bot: `python admin.py discord` runs its minute now and says what it did (or why it can't post).
- A run with resets the app missed: `python admin.py resets <id>` lists the resets its trace shows, then
  `python admin.py fix-run <id> <resets> <stage clock of each, e.g. 2:57.670> --dry-run` shows the new total, splits
  and place; run it again without `--dry-run` to write it (`fix-run <id> 0` undoes it).
- `python admin.py schedule <date> <slot> "<stage>" "<car>" [weather] [time]` fixes a future daily.
  A day's dailies never change once the day has started.
- The app is the only judge (`client\acr_daily\judge.py`). When a new version judges runs differently, raise
  `MIN_APP_VERSION` and `MIN_APP_FROM` (step 3) so one board never mixes the two.
- The exe isn't code-signed, so Windows SmartScreen warns on first start (*More info → Run anyway*).
