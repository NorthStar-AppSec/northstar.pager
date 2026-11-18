FROM python:3.13-slim

# Claude Code, pinned and checked like the northstar worker's (worker-setup.sh)
ARG CLAUDE_VERSION=2.1.308
ARG TARGETARCH
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) plat=linux-x64;   sum=356733f185fa988e6bf3aa9a555269fdd167982a2e2a80d3c8a78037bb92ad58 ;; \
      arm64) plat=linux-arm64; sum=fdd22e6cbb734d580f5664c48df4294eeec850218ff07f186f9af30426396ee1 ;; \
      *) echo "unsupported arch $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/usr/local/bin/claude')" \
      "https://downloads.claude.ai/claude-code-releases/$CLAUDE_VERSION/$plat/claude"; \
    echo "$sum  /usr/local/bin/claude" | sha256sum -c -; \
    chmod 755 /usr/local/bin/claude; \
    claude --version

WORKDIR /app
COPY alert.py .
ENV ALERT_DB=/data/alerts.db PYTHONUNBUFFERED=1 DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
RUN python alert.py --check
CMD ["python", "alert.py"]
