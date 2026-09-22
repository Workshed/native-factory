#!/usr/bin/env bash
#
# Run OpenHands Agent Canvas in the guest and point the host browser at it.
#
#     scripts/agent-canvas.sh up      [--vm nf]
#     scripts/agent-canvas.sh status  [--vm nf]
#     scripts/agent-canvas.sh down    [--vm nf]
#
# The UI runs in your browser on the host; the agent server and the coding agent run in
# the guest. Ingress binds 0.0.0.0:8000 in the guest, so `curl` from the host reaches it
# at the guest's IP directly -- but browsers often will not. Chrome on recent macOS
# blocks or prompts for access to private-network addresses, and the failure looks like
# "unreachable" even while curl gets a 200 in 4ms.
#
# So `up` also forwards 127.0.0.1:8000 on the host to the guest, and tells you to use
# http://localhost:8000. A localhost URL is not a local-network request, so no privacy
# prompt or policy is involved.
#
# Authentication: none is injected. The ACP subprocess inherits the guest's HOME, and
# `acp_isolate_data_dir` defaults to False, so Claude Code uses the interactive `/login`
# stored in ~/.claude. Verified 2026-09-22 with no ANTHROPIC_API_KEY and no
# CLAUDE_CODE_OAUTH_TOKEN set anywhere. HANDOFF 4.3 describes the SDK as isolating
# CLAUDE_CONFIG_DIR, which is true only when that flag is turned on.

set -uo pipefail

VM="nf"
PORT=8000
ACTION="${1:-}"; shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --vm) VM="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Local-only development key. It protects the guest's API from anything else on the
# 192.168.64.0/24 vmnet; it is not a secret worth rotating.
KEY="${LOCAL_BACKEND_API_KEY:-nf-local-dev-key}"

guest_ip() { tart ip "$VM" 2>/dev/null; }

case "$ACTION" in
  up)
    tart exec "$VM" bash -lc "
      mkdir -p ~/oh && cd ~/oh
      pkill -f 'agent-canvas' 2>/dev/null
      export LOCAL_BACKEND_API_KEY='$KEY'
      nohup agent-canvas --public --port $PORT > ~/oh/agent-canvas.log 2>&1 &
      sleep 3
    "
    echo "starting; first run fetches agent-server via uvx and can take a few minutes"
    for _ in $(seq 1 60); do
      if curl -sf -o /dev/null --max-time 3 "http://$(guest_ip):$PORT/"; then
        command -v socat >/dev/null || { echo "socat needed for the browser forward" >&2; exit 1; }
        pkill -f "socat.*LISTEN:$PORT" 2>/dev/null
        socat TCP-LISTEN:$PORT,bind=127.0.0.1,fork,reuseaddr TCP:"$(guest_ip)":$PORT \
          >/tmp/nf-socat-canvas.log 2>&1 &
        sleep 1
        echo
        echo "  Agent Canvas:  http://localhost:$PORT/     <- use this in a browser"
        echo "  (direct:       http://$(guest_ip):$PORT/  works for curl, often not for Chrome)"
        echo "  API key:       $KEY   (paste when the UI asks)"
        exit 0
      fi
      sleep 5
    done
    echo "did not come up; check: tart exec $VM tail -40 ~/oh/agent-canvas.log" >&2
    exit 1
    ;;
  status)
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$(guest_ip):$PORT/" || echo 000)"
    local_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$PORT/" || echo 000)"
    echo "guest ingress    http $code   http://$(guest_ip):$PORT/"
    echo "host forward     http $local_code   http://localhost:$PORT/  <- browser"
    tart exec "$VM" bash -lc "lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | grep -E ':($PORT|18000|18001)' | awk '{print \"  \", \$1, \$9}'"
    ;;
  down)
    pkill -f "socat.*LISTEN:$PORT" 2>/dev/null
    tart exec "$VM" bash -lc "pkill -f agent-canvas; pkill -f agent-server" 2>/dev/null
    echo "stopped"
    ;;
  *) sed -n '3,7p' "$0"; exit 2 ;;
esac
