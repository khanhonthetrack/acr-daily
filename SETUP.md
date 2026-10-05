# Running your own ACR Daily server

Everything runs on Cloudflare's free plan: one Worker (API + website + app download) and one D1 database.
Commands are for a Windows Command Prompt, from the repository folder.

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

Make an admin key (treat it like a password) and store it as a secret:
```bat
python -c "import secrets; print(secrets.token_urlsafe(32))"
npx wrangler secret put ADMIN_KEY
```
Optional, for names and avatars: a Steam Web API key from <https://steamcommunity.com/dev/apikey>,
stored with `npx wrangler secret put STEAM_API_KEY`.

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

To try a build on your own PC first: `client\build.bat https://acr-daily.YOURNAME.workers.dev` (output in `client\dist`).

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

- `python admin.py state` lists runs flagged by the realism checks or reported by viewers.
  `admin.py run <id>` shows one, `admin.py reject <id>` removes it, `admin.py ban <steamId>` blocks a player.
- `python admin.py schedule <date> <slot> "<stage>" "<car>" [weather] [time]` fixes a future daily.
  A day's dailies never change once the day has started.
- The realism limits are in `server\src\realism.js` (`LIMITS`). Loosen a flag value there if real runs get flagged.
- The exe isn't code-signed, so Windows SmartScreen warns on first start (*More info → Run anyway*).
