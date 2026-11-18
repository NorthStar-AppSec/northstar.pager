# northstar.pager

**An automated first triage for every incident, on your phone within a minute.**

When Better Stack opens an incident, northstar.pager has Claude read it and sends you a short verdict on Telegram: how bad it is, what is probably going on, and the first thing to check. You can decide from your lock screen whether to get up or go back to sleep.

It replaces Better Stack's paid on-call add-on with one small Python file, a Docker container and the Claude subscription you already have.

```
🚨 69 scripted requests on the API in an hour
🕒 Wed 18 Nov 21:09 (12 min ago)

P2 · 69 scripted curl/python requests hit /api/ in one hour
→ Check API logs since 21:09 for source IPs and endpoints hit by curl/python-requests user agents.

Why: Over double the 30/hour threshold from scripting tools, but no sign the API is down.
Likely cause: A scraper or someone probing the API, or your own script using curl/requests.

Monitor: More than 30 requests in an hour on /api/ … (Better Stack's own description)
```

The first two lines tell you **what** happened and **when** it started. The next two give Claude's verdict (`P1` down or under attack, `P2` degraded or suspicious, `P3` noise) and the first thing to do. The detail comes after. When the incident closes you get a short follow-up:

```
✅ Resolved: 69 scripted requests on the API in an hour
🕒 21:09 → 21:21, 12 min
```

## How it works

```
Better Stack ──poll every 60s──▶ alert.py ──new incident──▶ Claude Code (claude -p)
   Uptime API                       │                          triage in ~10s
                                    ▼                                │
                               SQLite (alerts.db) ◀──────────────────┘
                                    │
                                    └──▶ Telegram bot ──▶ your phone
```

1. **Poll.** Every `POLL_SECONDS`, the pager asks the Better Stack Uptime API for incidents from the last two days.
2. **Triage.** For each new open incident, it runs one headless Claude Code turn. Claude gets the incident data plus the last five incidents from the same monitor, so it can spot repeats and flapping. Claude runs locked down, with the same flags as the northstar worker: no tools, no MCP servers, no settings, no saved session, in an empty directory. The incident text is treated as untrusted.
3. **Store.** The incident and its triage are saved to SQLite before anything is sent.
4. **Notify.** Every stored alert that hasn't been sent yet goes to Telegram. If Telegram is down, it is retried on the next poll without triaging again. If Claude is down or the subscription limit is reached, you still get the alert, marked `(triage failed: …)`.
5. **Resolve.** When Better Stack resolves an incident you were paged about, you get the ✅ message.
6. **Heartbeat** (optional). After each successful poll it pings a Better Stack heartbeat, so if the pager itself dies, Better Stack emails you.

Incidents that were already resolved before the pager first saw them are skipped. When Better Stack can't be reached, it waits longer between polls, up to 10 minutes.

Everything is in [`alert.py`](alert.py): Python's standard library plus the `claude` CLI, with no other packages.

## What you need

| | Where to get it |
|---|---|
| **Better Stack Uptime API token** | Better Stack → Settings → API tokens → *Uptime API tokens*. The free plan works. |
| **Claude Code token** | Run `claude setup-token` on any machine where you're logged in to Claude Code. It prints a token starting with `sk-ant-oat` that is valid for a year. It needs a Claude Pro or Max subscription. An Anthropic API key does **not** work. |
| **Telegram bot token** | In Telegram, message [@BotFather](https://t.me/BotFather) → `/newbot` → pick a name and a username ending in `bot`. |
| **Telegram chat id** | Press **Start** on your new bot and send it a message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the number from `"chat":{"id":…}`. |
| **Heartbeat URL** (optional) | Better Stack → Uptime → Heartbeats → Create, expected every 1 minute with a 5 minute grace period. |

## Install on a server (Debian / Ubuntu)

```bash
curl -fsSL https://raw.githubusercontent.com/NorthStar-AppSec/northstar.pager/main/install.sh | sudo sh
```

The installer:

- installs Docker if it is missing, from Docker's apt repository with a pinned key checksum;
- downloads this repository (set `PAGER_REF=<tag or branch>` for another version, or run `sudo ./install.sh` from a checkout);
- builds the image, which includes a pinned, checksummed Claude Code;
- walks you through each token above and checks that it works. It finds your Telegram chat id for you: you just message the bot when asked;
- writes the tokens to `/opt/northstar-pager/.env`, readable only by root, starts the container and sends a test message to Telegram.

The container restarts on its own after a crash or a reboot.

| | |
|---|---|
| Upgrade | Run the same command again. Pressing Enter keeps the current answers. |
| New Claude token (yearly) | Run the same command again and paste the new token. |
| Logs | `cd /opt/northstar-pager && docker compose -p northstar-pager logs -f` |
| Past alerts | `sqlite3 /opt/northstar-pager/data/alerts.db 'SELECT started_at, name, triage FROM alerts ORDER BY started_at DESC LIMIT 10'` |
| Remove | `curl -fsSL https://raw.githubusercontent.com/NorthStar-AppSec/northstar.pager/main/install.sh \| sudo sh -s -- --uninstall` |

## Run it locally (Docker)

```bash
git clone https://github.com/NorthStar-AppSec/northstar.pager.git && cd northstar.pager
cp .env.example .env        # fill in the tokens
docker compose up --build
```

Alerts are stored in `./data/alerts.db`.

To send a fake alert through Claude and Telegram without waiting for Better Stack:

```bash
docker compose run --rm alert python -c "import alert; a={'name':'TEST api.example.com','url':'https://api.example.com/health','cause':'Status 502','started_at':alert.now()}; alert.telegram(alert.fire_message({**a,'triage':alert.triage(a,'')}))"
```

To test the whole chain, create a Better Stack monitor on a URL that can't work, such as `https://pager-test.invalid`. Wait for the 🚨 message, then pause the monitor to get the ✅.

## Run it without Docker

Requires Python 3.11 or newer and the [`claude`](https://code.claude.com) CLI on your `PATH`.

```bash
set -a; . ./.env; set +a
python3 alert.py
```

## Build and test

```bash
python3 alert.py --check            # offline self-check, needs no tokens or network
docker build -t northstar-pager .   # also runs the self-check; a failing check fails the build
shellcheck install.sh
```

The self-check covers storing, de-duplicating, the retry when Telegram is down, resolved messages, alerts that are still sent when triage fails, and the message layout.

The [Dockerfile](Dockerfile) downloads Claude Code `2.1.308` and checks it against pinned SHA-256s, the same as the northstar worker. Change `CLAUDE_VERSION` and both checksums together.

## Configuration

All settings are environment variables, in `.env`:

| Variable | Required | Default | |
|---|---|---|---|
| `BETTERSTACK_TOKEN` | yes | | Better Stack Uptime API token |
| `CLAUDE_CODE_OAUTH_TOKEN` | yes | | From `claude setup-token` |
| `TELEGRAM_BOT_TOKEN` | yes | | From @BotFather |
| `TELEGRAM_CHAT_ID` | yes | | Your chat, or a group (group ids start with `-`) |
| `HEARTBEAT_URL` | no | | Better Stack heartbeat, pinged after each good poll |
| `POLL_SECONDS` | no | `60` | How often to check Better Stack |
| `CLAUDE_MODEL` | no | `claude-opus-5-5` | Model used for triage, at low effort for speed |
| `ALERT_TZ` | no | `Europe/Amsterdam` | Time zone for times in messages |
| `ALERT_DB` | no | `./alerts.db` (`/data/alerts.db` in Docker) | SQLite file |

## Limits

- **Only Better Stack Uptime incidents.** Telemetry alerts and other sources aren't read.
- **The triage only sees what's in the incident.** Claude doesn't look at your logs or metrics. It reasons from the monitor's description and recent history.
- **One message per incident.** There's no acknowledge button or escalation if you don't respond.
- **It reads the first 50 incidents of the last two days.** That is plenty unless something is very wrong.

## License

[MIT](LICENSE)
