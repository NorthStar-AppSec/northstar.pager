# northstar.pager

Polls Better Stack for incidents, has Claude triage each new one, and sends it to Telegram. Alerts and triages are kept in SQLite. A replacement for Better Stack's paid on-call add-on.

## Install (Debian / Ubuntu)

```bash
git clone git@github.com:NorthStar-AppSec/northstar.pager.git
cd northstar.pager && sudo ./install.sh
```

The script installs Docker if needed, walks you through each token (Better Stack, Anthropic, your Telegram bot, an optional heartbeat), checks each one works, finds your Telegram chat id, starts the container and sends a test message. Everything lands in `/opt/northstar-pager`.

- Upgrade: `git pull && sudo ./install.sh` (Enter keeps the current answers)
- Remove: `sudo ./install.sh --uninstall`
- Logs: `cd /opt/northstar-pager && docker compose -p northstar-pager logs -f`

## Elsewhere

```bash
cp .env.example .env   # fill it in
docker compose up -d --build
```

Self-check without any tokens: `python3 alert.py --check`.
