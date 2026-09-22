#!/usr/bin/env bash
#
# Bridge the host's Android emulator into a Tart guest.
#
#     scripts/adb-bridge.sh up   [--vm nf]     start both sides
#     scripts/adb-bridge.sh verify [--vm nf]   check every ADB client
#     scripts/adb-bridge.sh down [--vm nf]     tear down
#
# Why this exists: an ARM64 AVD needs Hypervisor.framework and cannot be accelerated
# inside a macOS guest, so the emulator runs on the host (docs/adr/0002).
#
# Why a forwarder on BOTH sides, rather than ADB_SERVER_SOCKET:
#
#   * adb cannot bind one interface -- `adb -L tcp:<ip>:5037 server nodaemon` fails with
#     "listening on specified hostname currently unsupported" -- so exposing it directly
#     would mean `adb -a` on all interfaces plus a root pf rule. A forwarder binds one
#     interface, needs no root, and leaves no firewall state behind.
#   * AGP does NOT honour ADB_SERVER_SOCKET. Gradle installDebug hangs on
#     "[DeviceMonitor]: Cannot reach ADB server, attempting to reconnect" no matter what
#     the environment says. Measured 2026-09-22, AGP 9 / Gradle 9.1.
#
# Forwarding 127.0.0.1:5037 *inside the guest* makes every client's localhost assumption
# true, so nothing needs to honour anything. adb, Gradle and Maestro all then work with
# no environment variables at all.
#
# Port 5554 is the emulator *console*, not adb. It carries the device name and the
# console-only features (GPS, SMS, battery). It needs the auth token from the host, which
# `up` copies in -- no escalation, since the guest already has full adb control.

set -uo pipefail

VM="nf"
ACTION="${1:-}"; shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --vm) VM="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

ADB="${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}"
ADB_PORT=5037
CONSOLE_PORT=5554

die() { echo "error: $*" >&2; exit 1; }

gateway() {
  # `tart exec` has a minimal PATH without /sbin, so `route` is not callable and returns
  # nothing silently. netstat is always available.
  tart exec "$VM" sh -c "netstat -rn -f inet 2>/dev/null | awk '/^default/ {print \$2; exit}'" \
    | tr -d '\r\n'
}

up() {
  command -v socat >/dev/null || die "socat not installed on the host: brew install socat"
  tart exec "$VM" bash -lc 'command -v socat >/dev/null' \
    || die "socat not installed in the guest: tart exec $VM brew install socat"

  "$ADB" start-server >/dev/null 2>&1
  "$ADB" devices | grep -q 'device$' || die "no device attached to the host adb server"

  local gw; gw="$(gateway)"
  [ -n "$gw" ] || die "could not read the guest's default gateway"
  echo "guest gateway: $gw"

  # Host side: expose only on the vmnet interface. adb itself stays on localhost.
  pkill -f "socat.*LISTEN:${ADB_PORT}" 2>/dev/null
  pkill -f "socat.*LISTEN:${CONSOLE_PORT}" 2>/dev/null
  socat TCP-LISTEN:${ADB_PORT},bind="$gw",fork,reuseaddr TCP:127.0.0.1:${ADB_PORT} \
    >/tmp/nf-socat-adb.log 2>&1 &
  socat TCP-LISTEN:${CONSOLE_PORT},bind="$gw",fork,reuseaddr TCP:127.0.0.1:${CONSOLE_PORT} \
    >/tmp/nf-socat-console.log 2>&1 &
  sleep 1

  # Guest side: make localhost mean the host's server.
  tart exec "$VM" bash -lc "
    pkill -f 'socat.*LISTEN:${ADB_PORT}' 2>/dev/null
    pkill -f 'socat.*LISTEN:${CONSOLE_PORT}' 2>/dev/null
    nohup socat TCP-LISTEN:${ADB_PORT},bind=127.0.0.1,fork,reuseaddr TCP:${gw}:${ADB_PORT} \
      >/tmp/socat-adb.log 2>&1 &
    nohup socat TCP-LISTEN:${CONSOLE_PORT},bind=127.0.0.1,fork,reuseaddr TCP:${gw}:${CONSOLE_PORT} \
      >/tmp/socat-console.log 2>&1 &
    sleep 1
  "

  if [ -f "$HOME/.emulator_console_auth_token" ]; then
    local token; token="$(cat "$HOME/.emulator_console_auth_token")"
    tart exec "$VM" bash -lc "printf '%s' '$token' > ~/.emulator_console_auth_token
      chmod 600 ~/.emulator_console_auth_token"
    echo "console auth token installed in the guest"
  fi

  echo "bridge up. The guest needs no ADB_SERVER_SOCKET; localhost:5037 is the host's server."
}

verify() {
  local fails=0
  check() {  # check <name> <command...>
    local name="$1"; shift
    if tart exec "$VM" bash -lc "$*" >/dev/null 2>&1; then
      printf '  \033[32mpass\033[0m  %s\n' "$name"
    else
      printf '  \033[31mFAIL\033[0m  %s\n' "$name"; fails=$((fails + 1))
    fi
  }
  echo "ADB clients, from inside $VM, with no environment variables:"
  check "adb CLI"              'adb devices | grep -q "device$"'
  check "emulator console"     'exec 3<>/dev/tcp/127.0.0.1/5554 && head -c 20 <&3 | grep -q Android'
  check "Gradle (AGP/adblib)"  'cd "/Volumes/My Shared Files/work/spike-compose" 2>/dev/null && ./gradlew installDebug --console=plain -q'
  check "Maestro (dadb)"       'cd "/Volumes/My Shared Files/work/spike-compose" 2>/dev/null && maestro test .maestro/smoke.yaml'
  echo
  [ "$fails" -eq 0 ] && echo "all clients reach the host emulator" || echo "$fails client(s) failed"
  return "$fails"
}

down() {
  pkill -f "socat.*LISTEN:${ADB_PORT}" 2>/dev/null
  pkill -f "socat.*LISTEN:${CONSOLE_PORT}" 2>/dev/null
  tart exec "$VM" bash -lc "pkill -f 'socat.*LISTEN:${ADB_PORT}'; pkill -f 'socat.*LISTEN:${CONSOLE_PORT}'" 2>/dev/null
  echo "bridge down"
}

case "$ACTION" in
  up) up ;;
  verify) verify ;;
  down) down ;;
  *) sed -n '3,8p' "$0"; exit 2 ;;
esac
