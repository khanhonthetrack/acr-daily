# The bug bot

Discord **#bug-reports** → GitHub issue → AI fix (draft PR) → tests + AI review → you merge → "Fixed" in the Discord thread.

| Step | When | What | Workflow |
|---|---|---|---|
| Intake | every 4 hours (or Run workflow by hand) | Claude reads each new forum post (10 min after the last message in it) and its screenshots/logs. A clear report becomes an issue (`from-discord`, `bug`, `area:*`) and the thread gets "Logged as #N". A known bug is added to its issue. Missing details: up to 2 rounds of questions, then logged with `needs-info`. Not a bug: a short reply, no issue. Later messages in a logged thread are copied to the issue. | `bugbot-intake.yml` |
| Fix | you add the label **`ai-fix`** | Claude (Windows runner) finds the cause, edits, adds a test, runs the tests. The workflow opens a **draft PR** "Fixes #N" on `bugbot/issue-N`, or comments why it made no fix. | `bugbot-fix.yml` |
| Test + review | right after | App + server unit tests on Windows; Claude reviews the diff and the test log. The review goes on the PR with labels `tests-passed`/`tests-failed` and `needs-in-game-test` (a checklist). PR marked ready only when both are good. | `bugbot-fix.yml` |
| You | | Check it (in the game when asked), merge. Merging closes the issue. **The bot never merges or deploys.** | |
| Released | the `release` workflow succeeds | Every Discord issue closed as done before that release gets "Fixed: … It's in ACR Daily vX: click UPDATE" in its threads, then `notified`. | `bugbot-notify.yml` |
| Server-only fix | you deploy, then add the label **`live`** | "Fixed: … It's live now, no update needed." | `bugbot-notify.yml` |

## Setup (once)

1. **Discord bot** (the one ACR Daily already uses for #faq and Events): in the [Developer Portal](https://discord.com/developers/applications) › the bot › *Bot*, turn on **Message Content Intent** (without it the posts read empty). In the server, give the bot on **#bug-reports**: View Channel, Read Message History, Send Messages in Threads (and Manage Channels for step 5, once).
2. **Claude login**: in a terminal run `claude setup-token` and copy the token it prints.
3. **GitHub** › repo › Settings › Secrets and variables › Actions:
   - secret `CLAUDE_CODE_OAUTH_TOKEN` = the token from step 2
   - secret `DISCORD_BOT_TOKEN` = the bot token (same value as the Worker's `DISCORD_BOT_TOKEN`)
   - optional variables: `DISCORD_GUILD_ID` (default: the ACR Daily server), `BUGBOT_FORUM_ID` (default: the forum called `bug-reports`), `BUGBOT_TRIAGE_MODEL` (default Sonnet), `BUGBOT_MODEL` (fix + review; default: Claude Code's)
4. **GitHub** › Settings › Actions › General › Workflow permissions: tick **Allow GitHub Actions to create and approve pull requests** (for the draft PRs).
5. Actions › **bugbot-intake** › Run workflow › mode `setup-forum`: writes the forum's post guidelines (the questions every report should answer) and adds tags. Then `dry` once: it reads the open posts and lists what it would do, without writing anything.

## Safety

Anyone can post on Discord, and a post can try to steer an AI. So:
- Intake Claude has only Read/Grep/Glob, and no Discord or GitHub token in its environment (`claude_env()`). Its questions are posted with mentions off.
- Fixing starts only from your `ai-fix` label (labels need write access). The fixing job's GitHub token is read-only and not in the checkout; the bot's edits are a patch that another job (no Claude) turns into the PR. Patches touching `.github/` or `tools/bugbot/` are refused.
- Left over: the fixing Claude can run the unit tests, so in theory code it writes runs with its own Claude login in the environment. Read the issue before you add `ai-fix`.
- Issues are public: they copy the report text and link the thread, never Discord names.

## Local

```
python -m unittest tools/bugbot/test_bugbot.py
DISCORD_BOT_TOKEN=... GITHUB_TOKEN=... GITHUB_REPOSITORY=khanhonthetrack/acr-daily python tools/bugbot/bugbot.py intake --dry
```
