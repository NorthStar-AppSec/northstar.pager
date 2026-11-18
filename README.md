# northstar.pager

Polls Better Stack for incidents, has Claude triage each new one (through Claude Code on a Claude subscription, like the northstar worker), and sends it to Telegram. Alerts and triages are kept in SQLite. A replacement for Better Stack's paid on-call add-on.

## Install (Debian / Ubuntu)

```bash
curl -fsSL https://raw.githubusercontent.com/NorthStar-AppSec/northstar.pager/main/install.sh | sudo sh
```

(From a checkout: `sudo ./install.sh`. `PAGER_REF=<tag or branch>` installs another version.)

The script installs Docker if needed, walks you through each token (Better Stack, a `claude setup-token` token for your Claude subscription, your Telegram bot, an optional heartbeat), checks each one works, finds your Telegram chat id, starts the container and sends a test message. Everything lands in `/opt/northstar-pager`.

- Upgrade: run the same command again (Enter keeps the current answers)
- Remove: `curl -fsSL https://raw.githubusercontent.com/NorthStar-AppSec/northstar.pager/main/install.sh | sudo sh -s -- --uninstall`
- Logs: `cd /opt/northstar-pager && docker compose -p northstar-pager logs -f`

## Elsewhere

```bash
cp .env.example .env   # fill it in
docker compose up -d --build
```

Self-check without any tokens: `python3 alert.py --check`.
