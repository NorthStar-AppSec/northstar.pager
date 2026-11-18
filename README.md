# northstar.pager

**An automated first triage for every incident, on your phone within a minute.**

When Better Stack opens an incident, northstar.pager has Claude read it and sends you a short verdict on Telegram: how bad it is, what is probably going on, and the first thing to check. You can decide from your lock screen whether to get up or go back to sleep.

It replaces Better Stack's paid on-call add-on with one small Python file, a Docker container and the Claude subscription you already have.

```
🚨 Security overview › API 4xx burst from one IP (50+ in 10 min)
🕒 Wed 18 Nov 21:34 (11 min ago)

P3 · Scanner hit backoffice login and guessed API paths, finished
→ Nothing to do now; third scanner this week, add a Bunny rate limit on /api/ and /backoffice/.

Why: 418 requests, none logged in; the 200s and 302s are the public login page. Stopped at 21:45.

🔎 Logs for IP 152.32.213.37
⚪ Stopped · last request 21:45
418 requests since 21:42 · 0 logged in · 114 public pages, no credential
Responses: 304× 404; 57× 200; 57× 302
Most hit: GET /backoffice/login/ (57); GET /backoffice/ (57); GET /api/ (12)
Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/ (36); …
```

The first two lines tell you **what** happened and **when** it started. The next three give Claude's verdict (`P1` down or got through, `P2` degraded or still active, `P3` noise) and the one thing to do. With log access set up, the 🔎 block shows what the culprit did, looked up just before the alert was sent: whether it is still going, whether anyone logged in (a public login page doesn't count), what it targeted, and the other side of the same requests (which users, IPs, API keys and organizations were involved, and whether a staff override was used). The culprit is whoever the alert names: an IP, a user (`user 1838`), an API key (`los_…`), or an organization, partner or leadbot it was aimed at. A security alert that names nobody, such as "tenant-boundary probing", gets the top two failing actors from the logs. (The 🔎 block is real output from 18 Nov; the verdict above it is illustrative.) When the incident closes you get a short follow-up:

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

Python's standard library plus the `claude` CLI, with no other packages:

| File | Does |
|---|---|
| [`alert.py`](alert.py) | Entry point: checks the env, polls in a loop, heartbeat, back-off |
| [`pager/poll.py`](pager/poll.py) | One poll: store new incidents, investigate, triage, send what is unsent |
| [`pager/investigate.py`](pager/investigate.py) | Finds who the alert is about and summarizes their `auth_audit` lines |
| [`pager/triage.py`](pager/triage.py) | The prompt and the locked-down `claude -p` call |
| [`pager/messages.py`](pager/messages.py) | The 🚨 and ✅ texts |
| [`pager/betterstack.py`](pager/betterstack.py), [`telegram.py`](pager/telegram.py), [`net.py`](pager/net.py) | The API clients |
| [`pager/store.py`](pager/store.py), [`clock.py`](pager/clock.py) | SQLite and time formatting |
| [`tests/`](tests) | `python3 -m unittest`, offline |

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
docker compose run --rm alert python -c "from pager import clock, messages, telegram, triage; a={'name':'TEST api.example.com','url':'https://api.example.com/health','cause':'Status 502','started_at':clock.now()}; telegram.send(messages.fire_message({**a,'triage':triage.triage(a,'')}))"
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
python3 -m unittest                 # offline tests, need no tokens or network
docker build -t northstar-pager .   # also runs the tests; a failing test fails the build
shellcheck install.sh
```

The tests cover storing, de-duplicating, the retry when Telegram is down, resolved messages, alerts that are still sent when triage fails, the log summary, and the message layout.

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
| `BETTERSTACK_LOGS_URL`, `_USER`, `_PASSWORD` | no | | Better Stack → your log source → *Connect remotely*. Enables the 🔎 log lookup |
| `BETTERSTACK_LOGS_TABLE` | no | | That source's table without suffix, e.g. `t123456_production` |
| `ALERT_DB` | no | `./alerts.db` (`/data/alerts.db` in Docker) | SQLite file |

## Limits

- **Only Better Stack Uptime incidents.** Telemetry alerts and other sources aren't read.
- **The log lookup reads only the `auth_audit` trail** (the LeadBot backend's audit log), from 15 minutes before the incident until now, for at most two subjects. It runs only for security alerts, recognized by keyword in the incident text (auth, denied, privilege, tenant, 4xx…), so a plain outage never triggers it. Subjects are found by pattern in that same text. The lookup stays off until all four `BETTERSTACK_LOGS_*` settings are filled in, and the pager logs a warning at startup when only some are. Claude itself has no tools: it reasons from the incident, recent history and that summary.
- **One message per incident.** There's no acknowledge button or escalation if you don't respond.
- **It reads the first 50 incidents of the last two days.** That is plenty unless something is very wrong.

## License

[MIT](LICENSE)
