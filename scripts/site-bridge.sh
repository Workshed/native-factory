#!/usr/bin/env bash
#
# Make a dev server on the host's loopback reachable from the guest — at the same URL.
#
#     scripts/site-bridge.sh up   3000 [3001 …]
#     scripts/site-bridge.sh verify 3000
#     scripts/site-bridge.sh down
#
# A site at http://localhost:3000 is unreachable from the guest: `localhost` there is the
# guest. The obvious fix is to expose the dev server on 0.0.0.0 and point the guest at
# the host's IP — but that publishes your work to the network to solve a VM problem, and
# it changes the URL, which breaks the thing below.
#
# **Forward on BOTH sides, and the URL never changes.**
#
#     host   socat <gateway>:3000 -> 127.0.0.1:3000     (expose to the vmnet only)
#     guest  socat 127.0.0.1:3000 -> <gateway>:3000     (make localhost mean the host)
#
# The guest-side half is the important one, and it is the same insight as the adb bridge
# (docs/adr/0002): rather than asking every client to honour a rewritten address, make
# the client's assumption true. Two consequences follow, both of which matter:
#
#   * `http://localhost:3000` works verbatim in the guest, so nothing rewrites URLs and
#     the reference material records the URL you actually gave;
#   * the HTTP **Host header stays `localhost:3000`**. Dev servers that check it — Vite
#     and webpack-dev-server reject unknown hosts by default — see exactly what they
#     expect, so no allowedHosts configuration is needed.

set -uo pipefail

VM="${NF_VM:-nf}"
ACTION="${1:-}"; shift || true

die() { echo "error: $*" >&2; exit 1; }

gateway() {
  # `tart exec` has a minimal PATH without /sbin, so `route` is not callable there.
  tart exec "$VM" sh -c "netstat -rn -f inet 2>/dev/null | awk '/^default/ {print \$2; exit}'" \
    | tr -d '\r\n'
}

up() {
  [ $# -gt 0 ] || die "usage: site-bridge.sh up <port> [port …]"
  command -v socat >/dev/null || die "socat not installed on the host: brew install socat"
  tart exec "$VM" bash -lc 'command -v socat >/dev/null' \
    || die "socat not installed in the guest: tart exec $VM brew install socat"

  local gw; gw="$(gateway)"
  [ -n "$gw" ] || die "could not read the guest's default gateway"

  for port in "$@"; do
    if ! nc -z 127.0.0.1 "$port" 2>/dev/null; then
      echo "  warning: nothing is listening on 127.0.0.1:$port yet" >&2
    fi

    pkill -f "socat.*LISTEN:$port,bind=$gw" 2>/dev/null
    socat TCP-LISTEN:"$port",bind="$gw",fork,reuseaddr TCP:127.0.0.1:"$port" \
      >"/tmp/nf-site-$port.log" 2>&1 &

    tart exec "$VM" bash -lc "
      pkill -f 'socat.*LISTEN:$port,bind=127.0.0.1' 2>/dev/null
      nohup socat TCP-LISTEN:$port,bind=127.0.0.1,fork,reuseaddr TCP:$gw:$port \
        >/tmp/socat-site-$port.log 2>&1 &
      sleep 1
    "
    echo "  localhost:$port reachable in the guest (via $gw)"
  done
}

verify() {
  local port="${1:?usage: site-bridge.sh verify <port>}"
  local code
  code="$(tart exec "$VM" bash -lc "curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://localhost:$port/ || echo 000")"
  if [ "$code" = "000" ]; then
    printf '  \033[31mFAIL\033[0m  guest cannot reach http://localhost:%s/\n' "$port"
    return 1
  fi
  printf '  \033[32mpass\033[0m  guest reaches http://localhost:%s/ (http %s)\n' "$port" "$code"
}

down() {
  pkill -f 'socat.*TCP:127.0.0.1:[0-9]*$' 2>/dev/null
  tart exec "$VM" bash -lc "pkill -f 'socat-site' ; pkill -f 'socat.*LISTEN:[0-9]*,bind=127.0.0.1'" 2>/dev/null
  echo "site bridge down"
}

case "$ACTION" in
  up)     up "$@" ;;
  verify) verify "$@" ;;
  down)   down ;;
  *)      sed -n '3,8p' "$0"; exit 2 ;;
esac
