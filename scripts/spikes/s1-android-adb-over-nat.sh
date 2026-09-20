#!/usr/bin/env bash
#
# Spike S1 -- the Android emulator decision gate (ADR-0002, implementation plan AT-7).
#
# HANDOFF 4.5 schedules this at the start of Milestone 6. It runs here instead: it needs
# only a booted guest, the host emulator and a prebuilt APK, all of which exist at
# Milestone 1, and deferring it would put M2-M5 on top of an unverified assumption whose
# failure reopens the emulator placement, the config schema and the M9 concurrency model.
#
# The question is not "does adb work" but "which ADB CLIENTS honour ADB_SERVER_SOCKET".
# HANDOFF 8.2 asks it only of Maestro's dadb; AGP's adblib path and agent-device's client
# make the same assumption and can fail it independently.
#
# Usage:
#   scripts/spikes/s1-android-adb-over-nat.sh --vm nf-w1 --avd Pixel_9_API_36 [--apk path]
#
# A partial pass is a decision, not a failure. Record which clients worked in
# docs/android.md and choose a rung from the fallback ladder in docs/architecture.md 6.

set -uo pipefail

VM=""
AVD=""
APK=""
PORT=5037
RESULTS=()

usage() { sed -n '2,25p' "$0"; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --vm) VM="$2"; shift 2 ;;
    --avd) AVD="$2"; shift 2 ;;
    --apk) APK="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

[ -n "$VM" ] || { echo "--vm is required" >&2; usage; }
[ -n "$AVD" ] || { echo "--avd is required" >&2; usage; }

record() {  # record <id> <pass|fail|skip> <description>
  RESULTS+=("$1|$2|$3")
  case "$2" in
    pass) printf '  \033[32mpass\033[0m  %s  %s\n' "$1" "$3" ;;
    fail) printf '  \033[31mFAIL\033[0m  %s  %s\n' "$1" "$3" ;;
    *)    printf '  skip  %s  %s\n' "$1" "$3" ;;
  esac
}

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------------------- host side

section "Host preconditions"

ADB="$(command -v adb || true)"
[ -n "$ADB" ] || { echo "adb not found on the host" >&2; exit 1; }

PT_VERSION="$("$ADB" version | awk '/^Version/ {print $2}' | cut -d- -f1)"
PT_MAJOR="${PT_VERSION%%.*}"
if [ "${PT_MAJOR:-0}" -lt 35 ]; then
  # 33.0.1 shipped in 2022 and predates the remote-adb behaviour this design assumes.
  # Running the spike against it would prove nothing either way.
  echo "platform-tools $PT_VERSION is too old; upgrade to 35+ before trusting this spike" >&2
  exit 1
fi
record host-platform-tools pass "platform-tools $PT_VERSION"

# The guest must derive the gateway from its own default route: Tart's vmnet subnet is not
# guaranteed to be 192.168.64.1.
GATEWAY="$(tart exec "$VM" sh -c "route -n get default 2>/dev/null | awk '/gateway/ {print \$2}'" | tr -d '\r\n')"
if [ -z "$GATEWAY" ]; then
  record guest-gateway fail "could not read the guest's default gateway"
  exit 1
fi
record guest-gateway pass "guest sees gateway $GATEWAY"

if ! nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
  cat >&2 <<HINT

No adb server is listening on :$PORT. In another terminal:

    adb -a -P $PORT server nodaemon

and scope the port to the Tart NAT -- 'adb -a' binds 0.0.0.0 and cannot bind a single
interface, so this needs a pf rule, not a flag:

    echo "block in proto tcp from any to any port $PORT
    pass in proto tcp from 192.168.64.0/24 to any port $PORT" | sudo pfctl -a native-factory -f -
    sudo pfctl -e

Then start the emulator:

    emulator -avd $AVD -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect

HINT
  exit 1
fi
record host-adb-server pass "listening on :$PORT"

SERIAL="$("$ADB" devices | awk 'NR>1 && $2=="device" {print $1; exit}')"
[ -n "$SERIAL" ] || { echo "no device attached to the host adb server" >&2; exit 1; }
record host-emulator pass "device $SERIAL"

# --------------------------------------------------------------------------- guest side

GUEST_ENV="ADB_SERVER_SOCKET=tcp:${GATEWAY}:${PORT} ANDROID_SERIAL=${SERIAL}"
in_guest() { tart exec "$VM" /usr/bin/env $GUEST_ENV "$@"; }

section "Guest -> host adb, client by client"

# (a) the adb CLI itself
if in_guest adb devices 2>/dev/null | grep -q "$SERIAL"; then
  record a-adb-cli pass "adb CLI sees $SERIAL over ADB_SERVER_SOCKET"
else
  record a-adb-cli fail "adb CLI cannot reach the host server"
fi

# (b) installing an APK from the guest
if [ -n "$APK" ]; then
  if in_guest adb install -r "$APK" 2>&1 | grep -qi success; then
    record b-adb-install pass "adb install succeeded"
  else
    record b-adb-install fail "adb install failed"
  fi
else
  record b-adb-install skip "no --apk given"
fi

# (c) AGP / adblib -- Gradle's own device path, which HANDOFF 8.2 does not ask about
if in_guest sh -c 'cd "/Volumes/My Shared Files/work/android" 2>/dev/null && ./gradlew installDebug --console=plain' 2>&1 | tail -5 | grep -qi 'BUILD SUCCESSFUL'; then
  record c-agp-installdebug pass "Gradle installDebug reached the host emulator"
else
  record c-agp-installdebug fail "Gradle installDebug did not reach the host emulator"
fi

# (d) Maestro's bundled dadb client -- HANDOFF 8.2's original question
if in_guest sh -c 'maestro test --format junit --output /tmp/s1-maestro.xml /tmp/s1-flow.yaml' >/dev/null 2>&1; then
  record d-maestro-dadb pass "maestro reached the host emulator"
else
  record d-maestro-dadb fail "maestro could not reach the host emulator (dadb ignores the env?)"
fi

# (e) agent-device's ADB client
if in_guest agent-device snapshot --platform android >/dev/null 2>&1; then
  record e-agent-device pass "agent-device snapshot succeeded"
else
  record e-agent-device fail "agent-device could not reach the host emulator"
fi

# ----------------------------------------------------------------------------- verdict

section "Verdict"

failed=0
for row in "${RESULTS[@]}"; do
  [ "${row#*|}" = "${row#*|fail|}" ] || failed=$((failed + 1))
done

printf '\n%d of %d checks failed\n' "$failed" "${#RESULTS[@]}"
cat <<'NEXT'

Record the outcome in docs/android.md and set targets.android.emulator accordingly.

  all pass            -> emulator: host. Proceed as designed.
  some clients fail   -> rung 1: build Android on the host, agent stays in the guest.
  no client reaches   -> rung 2: Android E2E degrades to Robolectric + Roborazzi.

Dropping Tart is rung 4, not rung 2: it is the only isolation layer, and discarding it
for an Android-only problem trades the whole security model for one platform's E2E tests.
NEXT

exit $(( failed > 0 ? 1 : 0 ))
