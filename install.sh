#!/bin/sh
# Set up northstar.pager on a Debian or Ubuntu machine, as root.
#
#   git clone git@github.com:NorthStar-AppSec/northstar.pager.git
#   cd northstar.pager && sudo ./install.sh
#
# What it changes on this machine, and nothing else:
#   1. packages: curl, ca-certificates; Docker Engine from Docker's apt
#      repository when Docker is missing (its key checked against a pinned
#      SHA-256);
#   2. /opt/northstar-pager: alert.py, Dockerfile and compose.yaml copied
#      from this checkout, .env (mode 600) with the tokens, data/alerts.db;
#   3. the Docker container northstar-pager, restarted unless stopped, so it
#      comes back after a reboot.
# On the way it walks you through each token and checks it works: Better
# Stack, Anthropic (Claude), the Telegram bot (it finds your chat id for
# you) and an optional heartbeat, then sends a test message.
# Rerun it to upgrade (after `git pull`) or to change answers; the current
# ones are the defaults. --uninstall removes 2 and 3.

set -eu

# https://download.docker.com/linux/{debian,ubuntu}/gpg (the same file)
DOCKER_KEY_SHA256=1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570
APP_DIR=/opt/northstar-pager
ENV_FILE=$APP_DIR/.env
PROJECT=northstar-pager

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }
step() { printf '\n== %s\n' "$*"; }
tty() { printf '%s\n' "$*" >/dev/tty; }

usage() {
    cat <<EOF
usage: sudo ./install.sh [--uninstall]

  --uninstall   stop and remove the pager, its image and $APP_DIR (asks
                before deleting the alert history)
  -h, --help    this text
EOF
}

# --- questions, on the terminal ---------------------------------------------

ask_yes() {  # question default(y|n): true for yes
    if [ "$2" = y ]; then hint=Y/n; else hint=y/N; fi
    while :; do
        printf '%s [%s]: ' "$1" "$hint" >/dev/tty
        read -r answer </dev/tty || answer=
        case ${answer:-$2} in
            y | Y | yes) return 0 ;;
            n | N | no) return 1 ;;
            *) tty "  answer y or n" ;;
        esac
    done
}

ask() {  # prompt current: sets ANSWER, Enter keeps current
    printf '%s%s: ' "$1" "${2:+ [$2]}" >/dev/tty
    read -r ANSWER </dev/tty || ANSWER=
    ANSWER=${ANSWER:-$2}
}

ask_secret() {  # prompt current: sets ANSWER, not echoed, Enter keeps current
    if [ -n "$2" ]; then
        printf '%s [Enter keeps the current one]: ' "$1" >/dev/tty
    else
        printf '%s: ' "$1" >/dev/tty
    fi
    stty -echo </dev/tty
    read -r ANSWER </dev/tty || ANSWER=
    stty echo </dev/tty
    printf '\n' >/dev/tty
    ANSWER=${ANSWER:-$2}
}

current() {  # name: its value in an existing ENV_FILE, else empty
    [ -r "$ENV_FILE" ] || return 0
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

# --- HTTP, with the secret in a header file, not on the command line --------

http() {  # out-file curl-args…: prints the HTTP status, 000 when unreachable
    out=$1
    shift
    curl --proto '=https' --tlsv1.2 -s --max-time 20 -o "$out" -w '%{http_code}' "$@" || true
}

header_file() {  # "Name: value": a file only root can read, for curl -H @file
    f=$(mktemp "$TMP/h.XXXXXX")
    printf '%s\n' "$1" >"$f"
    echo "$f"
}

# --- checks ------------------------------------------------------------------

preflight() {
    [ "$(id -u)" = 0 ] || die "run as root: sudo ./install.sh"
    [ "$(uname -s)" = Linux ] || die "this script sets up Linux machines"
    if ! has apt-get || [ ! -r /etc/os-release ]; then
        die "this script is for Debian and Ubuntu; elsewhere: copy .env.example to .env and run docker compose up -d --build"
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        debian | ubuntu) DOCKER_OS=$ID; DOCKER_CODENAME=${VERSION_CODENAME:-} ;;
        *)
            case " ${ID_LIKE:-} " in
                *" ubuntu "*) DOCKER_OS=ubuntu; DOCKER_CODENAME=${UBUNTU_CODENAME:-} ;;
                *" debian "*) DOCKER_OS=debian; DOCKER_CODENAME=${VERSION_CODENAME:-} ;;
                *) die "this script is for Debian and Ubuntu, not ${PRETTY_NAME:-this system}" ;;
            esac ;;
    esac
    ARCH=$(dpkg --print-architecture)
    (: </dev/tty) 2>/dev/null || die "no terminal to ask on: run it from an interactive shell"
    SRC=$(cd "$(dirname "$0")" && pwd)
    for f in alert.py Dockerfile compose.yaml; do
        [ -r "$SRC/$f" ] || die "run it from a checkout of northstar.pager: $SRC/$f is missing"
    done
}

install_packages() {
    missing=
    for p in curl ca-certificates; do
        dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'ok installed' || missing="$missing $p"
    done
    if [ -n "$missing" ]; then
        say "installing$missing"
        apt-get update -qq
        # shellcheck disable=SC2086  # one word per package
        apt-get install -y -qq $missing >/dev/null
    fi
}

install_docker() {
    if has docker && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        say "using $(docker --version)"
        return
    fi
    [ -n "$DOCKER_CODENAME" ] || die "cannot tell this release's codename for Docker's apt repository"
    say "installing Docker Engine from download.docker.com ($DOCKER_OS $DOCKER_CODENAME)"
    curl --proto '=https' --tlsv1.2 -fsSL --retry 3 -o "$TMP/docker.asc" "https://download.docker.com/linux/$DOCKER_OS/gpg"
    got=$(sha256sum "$TMP/docker.asc" | cut -d' ' -f1)
    [ "$got" = "$DOCKER_KEY_SHA256" ] || die "Docker's apt key: expected $DOCKER_KEY_SHA256, got $got"
    install -d -m 0755 /etc/apt/keyrings
    install -m 0644 "$TMP/docker.asc" /etc/apt/keyrings/docker.asc
    echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$DOCKER_OS $DOCKER_CODENAME stable" \
        >/etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
    [ ! -d /run/systemd/system ] || systemctl enable --now docker >/dev/null 2>&1
    say "installed $(docker --version)"
}

# --- the tokens, one at a time, each checked ---------------------------------

setup_betterstack() {
    step "Better Stack"
    tty "The pager reads incidents through the Better Stack Uptime API (free plan is fine)."
    tty "  1. Open https://uptime.betterstack.com -> Settings -> API tokens"
    tty "  2. Under 'Uptime API tokens' (not Telemetry), create or copy a token"
    while :; do
        ask_secret "Better Stack Uptime API token" "$(current BETTERSTACK_TOKEN)"
        BETTERSTACK_TOKEN=$ANSWER
        [ -n "$BETTERSTACK_TOKEN" ] || { tty "  a token is required"; continue; }
        code=$(http "$TMP/bs.json" "https://uptime.betterstack.com/api/v2/incidents?per_page=1" \
            -H "@$(header_file "Authorization: Bearer $BETTERSTACK_TOKEN")")
        case $code in
            200) say "ok: Better Stack accepts the token"; return ;;
            401 | 403) tty "  Better Stack refused that token ($code). Is it an Uptime token?" ;;
            *) tty "  could not check it (HTTP $code)" ;
               ask_yes "  keep it anyway?" n && return ;;
        esac
    done
}

setup_anthropic() {
    step "Claude"
    tty "Claude triages each alert. It needs an Anthropic API key (pay per use;"
    tty "a triage costs well under a cent). A Claude.ai subscription token does not work here."
    tty "  1. Open https://console.anthropic.com/settings/keys"
    tty "  2. Create Key, name it e.g. 'northstar-pager', copy it (starts with sk-ant-)"
    tty "  3. Make sure the organization has credits under Billing"
    while :; do
        ask_secret "Anthropic API key" "$(current ANTHROPIC_API_KEY)"
        ANTHROPIC_API_KEY=$ANSWER
        [ -n "$ANTHROPIC_API_KEY" ] || { tty "  a key is required"; continue; }
        code=$(http "$TMP/an.json" https://api.anthropic.com/v1/models \
            -H "@$(header_file "x-api-key: $ANTHROPIC_API_KEY")" -H "anthropic-version: 2023-06-01")
        case $code in
            200) say "ok: Anthropic accepts the key"; return ;;
            401 | 403) tty "  Anthropic refused that key ($code)" ;;
            *) tty "  could not check it (HTTP $code)" ;
               ask_yes "  keep it anyway?" n && return ;;
        esac
    done
}

setup_telegram() {
    step "Telegram"
    tty "Alerts arrive as messages from your own Telegram bot."
    tty "  1. In Telegram, open a chat with @BotFather (the one with the blue check)"
    tty "  2. Send /newbot, pick a name, then a username ending in 'bot'"
    tty "  3. BotFather replies with a token like 123456789:AA..."
    while :; do
        ask_secret "Telegram bot token" "$(current TELEGRAM_BOT_TOKEN)"
        TELEGRAM_BOT_TOKEN=$ANSWER
        [ -n "$TELEGRAM_BOT_TOKEN" ] || { tty "  a token is required"; continue; }
        # the token is part of Telegram's URL; keep it out of ps by passing the URL through a config file
        printf 'url = "https://api.telegram.org/bot%s/getMe"\n' "$TELEGRAM_BOT_TOKEN" >"$TMP/tg.cfg"
        code=$(http "$TMP/tg.json" -K "$TMP/tg.cfg")
        if [ "$code" = 200 ]; then
            BOT=$(sed -n 's/.*"username":"\([^"]*\)".*/\1/p' "$TMP/tg.json")
            say "ok: this is @$BOT"
            break
        fi
        tty "  Telegram refused that token (HTTP $code)"
    done

    TELEGRAM_CHAT_ID=$(current TELEGRAM_CHAT_ID)
    if [ -n "$TELEGRAM_CHAT_ID" ] && ! ask_yes "Send alerts to a different chat than $TELEGRAM_CHAT_ID?" n; then
        return
    fi
    tty ""
    tty "Now open https://t.me/$BOT and press Start (or send it any message)."
    tty "For a group: add @$BOT to the group and send a message there."
    while :; do
        printf 'Press Enter once you have sent it… ' >/dev/tty
        read -r _ </dev/tty || true
        printf 'url = "https://api.telegram.org/bot%s/getUpdates"\n' "$TELEGRAM_BOT_TOKEN" >"$TMP/tg.cfg"
        http "$TMP/up.json" -K "$TMP/tg.cfg" >/dev/null
        # the most recent chat that wrote to the bot
        id=$(grep -o '"chat":{"id":-\{0,1\}[0-9]*' "$TMP/up.json" | tail -n 1 | sed 's/.*://')
        if [ -n "$id" ]; then
            TELEGRAM_CHAT_ID=$id
            say "ok: found chat $TELEGRAM_CHAT_ID"
            return
        fi
        tty "  no message reached @$BOT yet."
        ask "  Or type the chat id yourself (Enter to try again)" ""
        if [ -n "$ANSWER" ]; then TELEGRAM_CHAT_ID=$ANSWER; return; fi
    done
}

setup_heartbeat() {
    step "Heartbeat (optional)"
    tty "If the pager itself dies you would hear nothing. A Better Stack heartbeat"
    tty "catches that: the pager pings it every minute, and Better Stack emails you"
    tty "when the pings stop."
    tty "  1. Better Stack Uptime -> Heartbeats -> Create heartbeat"
    tty "  2. Expect a heartbeat every 1 minute, grace period 5 minutes"
    tty "  3. Copy its URL (https://uptime.betterstack.com/api/v1/heartbeat/...)"
    ask "Heartbeat URL (Enter to skip)" "$(current HEARTBEAT_URL)"
    HEARTBEAT_URL=$ANSWER
    case $HEARTBEAT_URL in
        "" | https://*) ;;
        *) warn "that is not an https URL; skipping the heartbeat"; HEARTBEAT_URL= ;;
    esac
}

# --- install, start, report ---------------------------------------------------

write_files() {
    step "install"
    install -d -m 0755 "$APP_DIR" "$APP_DIR/data"
    for f in alert.py Dockerfile compose.yaml; do
        install -m 0644 "$SRC/$f" "$APP_DIR/$f"
    done
    POLL_SECONDS=$(current POLL_SECONDS)
    (
        umask 077
        cat >"$ENV_FILE.new" <<EOF
# written by install.sh; rerun it to change these
BETTERSTACK_TOKEN=$BETTERSTACK_TOKEN
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
HEARTBEAT_URL=$HEARTBEAT_URL
POLL_SECONDS=${POLL_SECONDS:-60}
EOF
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    say "files in $APP_DIR, tokens in $ENV_FILE (root only)"
}

start() {
    step "start"
    # the build runs alert.py's self-check, so a broken copy never starts
    (cd "$APP_DIR" && docker compose -p "$PROJECT" up -d --build --remove-orphans)
    sleep 5
    state=$(docker inspect -f '{{.State.Status}}' "$(cd "$APP_DIR" && docker compose -p "$PROJECT" ps -q alert)" 2>/dev/null || echo missing)
    [ "$state" = running ] || die "the container is $state; see: cd $APP_DIR && docker compose -p $PROJECT logs"
    say "running"
}

test_message() {
    printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$TELEGRAM_BOT_TOKEN" >"$TMP/tg.cfg"
    code=$(http "$TMP/send.json" -K "$TMP/tg.cfg" \
        --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
        --data-urlencode "text=✅ northstar.pager is running on $(hostname). Alerts will arrive here.")
    if [ "$code" = 200 ]; then
        say "sent a test message to Telegram: check your phone"
    else
        warn "the test message failed (HTTP $code): $(cat "$TMP/send.json")"
    fi
}

report() {
    say ""
    say "Done. northstar.pager checks Better Stack every ${POLL_SECONDS:-60}s."
    say "  logs:     cd $APP_DIR && docker compose -p $PROJECT logs -f"
    say "  history:  sqlite3 $APP_DIR/data/alerts.db 'SELECT started_at, name, triage FROM alerts ORDER BY started_at DESC LIMIT 10'"
    say "  upgrade:  git pull && sudo ./install.sh   (Enter through the questions)"
    say "  remove:   sudo ./install.sh --uninstall"
}

uninstall() {
    [ -d "$APP_DIR" ] || { say "nothing installed in $APP_DIR"; return; }
    ask_yes "Stop and remove northstar.pager?" n || return 0
    if has docker && [ -r "$APP_DIR/compose.yaml" ]; then
        (cd "$APP_DIR" && docker compose -p "$PROJECT" down --rmi local) || warn "docker compose down failed"
    fi
    if ask_yes "Also delete the alert history ($APP_DIR/data)?" n; then
        rm -rf "$APP_DIR"
        say "removed $APP_DIR"
    else
        find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf {} +
        say "removed northstar.pager; kept $APP_DIR/data"
    fi
    say "Docker itself stays installed. Revoke the tokens if you no longer need them."
}

main() {
    UNINSTALL=0
    for arg in "$@"; do
        case $arg in
            --uninstall) UNINSTALL=1 ;;
            -h | --help) usage; exit 0 ;;
            *) usage >&2; exit 2 ;;
        esac
    done
    export DEBIAN_FRONTEND=noninteractive
    preflight
    if [ "$UNINSTALL" = 1 ]; then
        uninstall
        return
    fi
    TMP=$(mktemp -d)
    chmod 0700 "$TMP"
    trap 'stty echo </dev/tty 2>/dev/null; rm -rf "$TMP"' EXIT
    trap 'exit 130' INT TERM

    step "packages"
    install_packages
    install_docker
    setup_betterstack
    setup_anthropic
    setup_telegram
    setup_heartbeat
    write_files
    start
    test_message
    report
}

main "$@"
