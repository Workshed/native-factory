#!/bin/bash
# The first-party `android` CLI, and two assertions about the Android toolchain.
#
# 1. The legacy SDK Tools script shares the name `android`, exits 0, and does nothing. If
#    $ANDROID_HOME/tools is on PATH it shadows the real CLI (HANDOFF 4.8).
# 2. The emulator must NOT be installed. An ARM64 AVD needs Hypervisor.framework and fails
#    with HV_UNSUPPORTED inside a macOS guest, so its presence is a build error rather than
#    a bonus. It runs on the host instead (ADR-0002).
set -euo pipefail
NF_PREFIX=/opt/native-factory
ANDROID_SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"

# 1. Remove the legacy shadow before installing anything.
if [ -x "$ANDROID_SDK/tools/android" ]; then
  echo "removing legacy SDK Tools script at $ANDROID_SDK/tools/android"
  rm -f "$ANDROID_SDK/tools/android"
fi
if grep -q 'Android/sdk/tools' "$HOME/.zprofile" 2>/dev/null; then
  echo "warning: \$ANDROID_HOME/tools is on PATH in ~/.zprofile and will shadow the CLI" >&2
fi

# The first-party CLI. If the install route changes upstream this is the single place to fix.
if ! command -v android >/dev/null 2>&1; then
  brew install android-cli 2>/dev/null || {
    echo "warning: could not install the first-party android CLI via brew." >&2
    echo "  See https://developer.android.com/tools/agents/android-cli" >&2
  }
fi

if command -v android >/dev/null 2>&1; then
  if android --version 2>&1 | grep -qi 'deprecated'; then
    echo "error: the 'android' on PATH is the deprecated script (it exits 0)" >&2
    exit 1
  fi
  printf 'android-cli=%s\n' "$(android --version 2>&1 | head -1)" \
    >> "$NF_PREFIX/build-logs/versions.env"
fi

# 2. Assert the emulator is absent.
if command -v emulator >/dev/null 2>&1; then
  echo "error: the Android emulator is installed in the guest image." >&2
  echo "  It cannot work here: an ARM64 AVD needs Hypervisor.framework and fails with" >&2
  echo "  HV_UNSUPPORTED when nested. The emulator runs on the host (ADR-0002)." >&2
  exit 1
fi
echo "android-emulator=ABSENT_BY_DESIGN" >> "$NF_PREFIX/build-logs/versions.env"

echo "android toolchain checked: CLI present, emulator absent"
