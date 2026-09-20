#!/usr/bin/env bash
#
# Provision a Tart macOS guest for the Native Factory prototype.
#
# Run this INSIDE the VM (or via `tart exec <vm> ...`) after creating it by hand:
#
#     tart clone ghcr.io/cirruslabs/macos-tahoe-xcode:26.5 nf
#     tart set nf --cpu 8 --memory 16384
#     tart run --no-graphics --dir=work:$PWD/output nf &
#     tart exec -it nf bash -lc 'bash "/Volumes/My Shared Files/work/../scripts/setup-guest.sh"'
#
# This exists instead of a Packer golden image. The prototype does not need reproducible
# images -- but it does need to be able to rebuild the VM after breaking it, and "follow
# the README again, carefully" is not that. Running this on a fresh clone is.
#
# Deliberately NOT installed: the Android emulator. An ARM64 AVD needs
# Hypervisor.framework and fails with HV_UNSUPPORTED inside a macOS guest. It runs on the
# host and the guest reaches it over ADB_SERVER_SOCKET. See docs/adr/0002.

set -euo pipefail

MAESTRO_VERSION="${MAESTRO_VERSION:-2.10.0}"
PLAYWRIGHT_VERSION="${PLAYWRIGHT_VERSION:-1.63.0}"

log() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

log "Preconditions"
sw_vers
node_version="$(node --version | tr -d 'v')"
echo "node $node_version"
case "$node_version" in
  2[2-9].*|[3-9][0-9].*) ;;
  *) echo "node 22.12+ required by Agent Canvas and the Copilot CLI" >&2; exit 1 ;;
esac

log "Playwright + browsers"
npm install -g "playwright@${PLAYWRIGHT_VERSION}"
npx --yes "playwright@${PLAYWRIGHT_VERSION}" install chromium webkit

log "Maestro"
MAESTRO_VERSION="$MAESTRO_VERSION" bash -c 'curl -fsSL https://get.maestro.mobile.dev | bash'
grep -q 'maestro/bin' "$HOME/.zprofile" 2>/dev/null || \
  echo 'export PATH="$HOME/.maestro/bin:$PATH"' >> "$HOME/.zprofile"

log "Coding agents"
# Both are installed; which one runs is chosen in OpenHands, not here.
npm install -g @github/copilot || echo "warning: could not install @github/copilot" >&2
if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code is not installed. Install it per https://code.claude.com/docs if wanted."
fi

log "OpenHands Agent Canvas"
command -v uv >/dev/null 2>&1 || brew install uv
npm install -g @openhands/agent-canvas

log "Android: check the toolchain, and check the emulator is ABSENT"
ANDROID_SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
# The legacy SDK Tools script shares the name of the first-party `android` CLI and exits
# 0, so it shadows it silently.
if [ -x "$ANDROID_SDK/tools/android" ]; then
  echo "removing legacy SDK Tools script at $ANDROID_SDK/tools/android"
  rm -f "$ANDROID_SDK/tools/android"
fi
if command -v emulator >/dev/null 2>&1; then
  echo "error: the Android emulator is installed in this guest." >&2
  echo "  It cannot work here (HV_UNSUPPORTED). It runs on the host. See docs/adr/0002." >&2
  exit 1
fi

log "Done"
echo "Authenticate the agents interactively, then verify:"
echo "  copilot        -> /login"
echo "  claude         -> /login"
echo "  python3 scripts/doctor.py --guest"
