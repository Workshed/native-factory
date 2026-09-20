#!/usr/bin/env bash
#
# Provision a Tart macOS guest for the Native Factory prototype.
#
# Run this INSIDE the VM (or via `tart exec <vm> ...`) after creating it by hand:
#
#     tart clone ghcr.io/cirruslabs/macos-tahoe-xcode:26.5 nf
#     tart set nf --cpu 8 --memory 16384
#     tart run --no-graphics \
#       --dir=work:$PWD/output \
#       --dir=scripts:$PWD/scripts:ro nf &
#     tart exec nf bash -l "/Volumes/My Shared Files/scripts/setup-guest.sh"
#
# scripts/ is mounted read-only and separately from output/: the agent must write
# the generated projects, and has no reason to be able to rewrite the provisioning.
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

log "JDK 17"
# The base image installs openjdk@17 via Homebrew, which is **keg-only**: present but
# unlinked, invisible to /usr/libexec/java_home, and `java` resolves to the macOS stub
# that tells you to visit java.com. Maestro and Gradle both need a real JDK.
# HANDOFF 4.4 lists openjdk@17 as part of the image, which is true but not usable.
#
# Symlinking into /Library/Java/JavaVirtualMachines rather than exporting JAVA_HOME:
# `tart exec` starts a shell with a minimal PATH and does not read ~/.zprofile, so an
# env-var fix works interactively and then fails under automation. The symlink makes
# /usr/bin/java work everywhere, for every shell.
JDK_PREFIX="$(brew --prefix openjdk@17 2>/dev/null || true)"
if [ -z "$JDK_PREFIX" ] || [ ! -d "$JDK_PREFIX/libexec/openjdk.jdk" ]; then
  brew install openjdk@17
  JDK_PREFIX="$(brew --prefix openjdk@17)"
fi
sudo ln -sfn "$JDK_PREFIX/libexec/openjdk.jdk" /Library/Java/JavaVirtualMachines/openjdk-17.jdk
java -version

log "Playwright + browsers"
npm install -g "playwright@${PLAYWRIGHT_VERSION}"
npx --yes "playwright@${PLAYWRIGHT_VERSION}" install chromium webkit

log "Maestro"
MAESTRO_VERSION="$MAESTRO_VERSION" bash -c 'curl -fsSL https://get.maestro.mobile.dev | bash'

log "Coding agents"
# Both are installed; which one runs is chosen in OpenHands, not here.
npm install -g @github/copilot || echo "warning: could not install @github/copilot" >&2
if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code is not installed. Install it per https://code.claude.com/docs if wanted."
fi

log "OpenHands Agent Canvas"
command -v uv >/dev/null 2>&1 || brew install uv
npm install -g @openhands/agent-canvas

log "Android toolchain"
# macos-tahoe-xcode:26.5 puts the SDK at ~/android-sdk. ANDROID_HOME is exported for
# interactive shells but is empty under `tart exec`, so derive the path, do not trust it.
ANDROID_SDK="$HOME/android-sdk"
[ -d "$ANDROID_SDK" ] || ANDROID_SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
[ -d "$ANDROID_SDK" ] || { echo "no Android SDK found" >&2; exit 1; }

# The legacy SDK Tools script shares the name of the first-party `android` CLI and exits
# 0, so it shadows the real one silently.
if [ -x "$ANDROID_SDK/tools/android" ]; then
  echo "removing legacy SDK Tools script at $ANDROID_SDK/tools/android"
  rm -f "$ANDROID_SDK/tools/android"
fi

# android-cli is a **cask**, not a formula. Errors are deliberately not suppressed: an
# earlier version of this script hid them with 2>/dev/null and the install failed
# silently, which cost more time than the noise ever would.
if ! command -v android >/dev/null 2>&1; then
  brew install --cask android-cli
fi
android --version 2>&1 | head -1

# PATH for every shell, including the minimal one `tart exec` provides. path_helper reads
# /etc/paths.d at login, so this works without touching any per-shell rc file.
printf '%s\n%s\n%s\n' \
  "$ANDROID_SDK/platform-tools" \
  "$ANDROID_SDK/cmdline-tools/latest/bin" \
  "$HOME/.maestro/bin" \
  | sudo tee /etc/paths.d/native-factory >/dev/null

# The emulator must NOT be here. An ARM64 AVD needs Hypervisor.framework and fails with
# HV_UNSUPPORTED inside a macOS guest; it runs on the host (docs/adr/0002).
if command -v emulator >/dev/null 2>&1; then
  echo "error: the Android emulator is installed in this guest." >&2
  echo "  It cannot work here. Remove it; the host runs it. See docs/adr/0002." >&2
  exit 1
fi

log "Done"
echo "Authenticate the agents interactively, then verify:"
echo "  copilot        -> /login"
echo "  claude         -> /login"
echo "  python3 \"/Volumes/My Shared Files/scripts/doctor.py\" --guest"
