#!/usr/bin/env bash
#
# Run one target through the pipeline.
#
#     scripts/factory.sh <target> <stage> [--yes]
#     scripts/factory.sh lloyds-mortgage all
#
# Stages
#   inspect         deterministic crawl            -> output/<t>/reference/
#   explore         agent walks the flow           -> reference/journey.md
#   approve         mark the reference reviewed
#   build-ios       agent builds                   -> output/<t>/ios/
#   build-android   agent builds                   -> output/<t>/android/
#   source          sync supplementary source into sources/<target>/
#   capture         screenshots of the finished apps
#   test            re-run both platforms' Maestro flows
#   status          what has run, from runs.jsonl
#   all             inspect, explore, GATE, build-ios, build-android, test
#
# There is one gate, between explore and build. journey.md takes the agent half an hour
# and a human two minutes to read; a build takes an hour and is hard to redirect. That
# asymmetry is the whole argument for stopping there and nowhere else.
#
# Prompts are composed, not written per target:
#     prompts/<stage>.md  +  targets/<t>/brief.md  +  a platform paragraph
# Roughly 60% of each prompt is the shared half.

set -uo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:?usage: factory.sh <target> <stage> [--yes]}"
STAGE="${2:?usage: factory.sh <target> <stage> [--yes]}"
ASSUME_YES=false
[ "${3:-}" = "--yes" ] && ASSUME_YES=true

VM="${NF_VM:-nf}"

#: Maestro's iOS XCTest driver is slow to start on a loaded machine and its default
#: timeout is not generous enough: under a running VM plus an Android emulator it fails
#: with IOSDriverTimeoutException, and when it does start it can take minutes. HANDOFF
#: 4.9 flagged this driver for exactly this on new macOS/Xcode pairs. Measured here on
#: Xcode 26.5 / macOS 26.6.2 -- an earlier 18-minute run of flows that normally take two
#: had the same cause.
MAESTRO_IOS_TIMEOUT="${MAESTRO_DRIVER_STARTUP_TIMEOUT:-180000}"
CANVAS="${NF_CANVAS:-http://localhost:8000}"
KEY="${LOCAL_BACKEND_API_KEY:-nf-local-dev-key}"
PROVIDER="${NF_PROVIDER:-claude-code}"   # any key from OpenHands' ACP provider registry

DIR="targets/$TARGET"
OUT="output/$TARGET"
GUEST="/Volumes/My Shared Files/work/$TARGET"
RUNS="$OUT/runs.jsonl"

[ -d "$DIR" ] || { echo "no target at $DIR" >&2; exit 1; }
mkdir -p "$OUT"

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }

# Each target's output is its own git repository.
#
# It answers "how do I get at the code" with a tool everyone already has, and three
# other things fall out for free: diffs between runs when a site changes and the target
# is rebuilt, provenance in the commit trail, and no file browser to write. The parent
# repository ignores output/ entirely, so these are independent and stay unpushed.
output_repo_init() {
  [ -d "$OUT/.git" ] && return 0
  git -C "$OUT" init -q
  cat > "$OUT/.gitignore" <<'GITIGNORE'
# Build products, not source.
build/
.gradle/
DerivedData/
*.xcuserdatad/
local.properties
GITIGNORE
  git -C "$OUT" add -A >/dev/null 2>&1
  git -C "$OUT" -c user.email=factory@localhost -c user.name="Native Factory" \
    commit -q -m "Initialise $TARGET output" >/dev/null 2>&1 || true
}

commit_output() {  # commit_output <stage> [conversation]
  output_repo_init
  git -C "$OUT" add -A >/dev/null 2>&1
  git -C "$OUT" diff --cached --quiet 2>/dev/null && return 0

  local msg="$1"
  [ -n "${2:-}" ] && msg="$msg

Conversation: $2"
  git -C "$OUT" -c user.email=factory@localhost -c user.name="Native Factory" \
    commit -q -m "$msg" >/dev/null 2>&1 || true
  local n; n="$(git -C "$OUT" show --stat --oneline HEAD 2>/dev/null | tail -1)"
  echo "  committed: $(git -C "$OUT" rev-parse --short HEAD 2>/dev/null)  ${n:-}"
}
fail() { echo "error: $*" >&2; exit 1; }
cfg()  { sed -n "s/^$1:[[:space:]]*//p" "$DIR/target.yaml" | head -1; }

# `cfg` succeeds and prints nothing for an absent key, so `$(cfg x || echo default)`
# never fires the fallback -- it silently passes an empty string. That reached the
# crawler as `--engine ''` and only surfaced on the first target that set neither engine
# nor a plan mentioning it.
cfg_or() { local v; v="$(cfg "$1")"; printf '%s' "${v:-$2}"; }

record() {  # record <stage> <conversation-id> <prompt-sha> <outcome>
  python3 - "$RUNS" "$1" "$2" "$3" "$4" <<'PY'
import json, sys
from datetime import datetime, timezone
path, stage, conv, sha, outcome = sys.argv[1:6]
with open(path, "a") as fh:
    fh.write(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage, "conversation": conv, "prompt_sha256": sha, "outcome": outcome,
    }) + "\n")
PY
}

# Compose a prompt, POST it as a conversation, wait for it to finish.
# Prints the conversation id; the agent's work lands in the mounted workspace.
converse() {  # converse <stage> <prompt-file> <max-iterations>
  local stage="$1" prompt_file="$2" iters="$3"
  local sha; sha="$(shasum -a 256 "$prompt_file" | cut -c1-16)"

  local payload; payload="$(python3 - "$prompt_file" "$GUEST" "$PROVIDER" "$iters" <<'PY'
import json, sys
prompt, workdir, provider, iters = sys.argv[1:5]
print(json.dumps({
    "workspace": {"kind": "LocalWorkspace", "working_dir": workdir},
    "agent_settings": {"agent_kind": "acp", "acp_server": provider},
    "initial_message": {"role": "user",
                        "content": [{"type": "text", "text": open(prompt).read()}],
                        "run": True},
    "max_iterations": int(iters),
}))
PY
)"

  local conv
  conv="$(curl -s -X POST "$CANVAS/api/conversations" \
      -H "X-Session-API-Key: $KEY" -H 'Content-Type: application/json' \
      -d "$payload" --max-time 60 \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')"
  [ -n "$conv" ] || { record "$stage" "" "$sha" "launch-failed"; fail "could not start a conversation — is agent-canvas up?"; }

  echo "  conversation $conv  (prompt $sha)"
  echo "  watch: $CANVAS"

  local status=""
  while :; do
    status="$(curl -s -H "X-Session-API-Key: $KEY" "$CANVAS/api/conversations/$conv" --max-time 15 \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("execution_status","?"))' 2>/dev/null)"
    case "$status" in
      finished) break ;;
      error|failed|stopped) record "$stage" "$conv" "$sha" "$status"; fail "conversation ended: $status" ;;
    esac
    sleep 30
  done

  record "$stage" "$conv" "$sha" "finished"
  commit_output "$stage" "$conv"
}

compose() {  # compose <shared-prompt> <extra-file-or-empty> -> /tmp/nf-prompt.md
  local out=/tmp/nf-prompt-$$.md
  cat "prompts/$1" > "$out"
  printf '\n\n---\n\n' >> "$out"
  cat "$DIR/brief.md" >> "$out"
  [ -n "${2:-}" ] && { printf '\n' >> "$out"; cat "$2" >> "$out"; }

  # Identities, so they stop being guessed. Two builds previously chose
  # uk.co.otaku-dev.MortgageCalculator and com.example.ourlocations -- one inferred from
  # git config, one from the app name.
  local bid aid
  bid="$(cfg bundle_id)"; aid="$(cfg application_id)"
  if [ -n "$bid$aid" ]; then
    {
      printf '\n## Identifiers\n\nUse exactly these; do not invent or infer one.\n\n'
      [ -n "$bid" ] && printf -- '- iOS bundle identifier: `%s`\n' "$bid"
      [ -n "$aid" ] && printf -- '- Android application id: `%s`\n' "$aid"
    } >> "$out"
  fi

  if [ -d "sources/$TARGET" ]; then
    cat >> "$out" <<SOURCE

## Supplementary source

A checkout of the site's own source is mounted **read-only** at
\`/Volumes/My Shared Files/sources/$TARGET\`.

Read it for API shapes, validation rules and business logic that observing the running
site cannot settle — an exact rounding rule, a full list of error codes, a threshold.

It is reference material, not a translation target. The product is what the site *does*;
its source is a second witness, not the specification. Do not port its structure, its
components or its naming into the native apps, and do not modify it.
SOURCE
  fi

  echo "$out"
}

#: A site on the host's loopback needs a forwarder on each side before the guest can
#: reach it. Idempotent and cheap, so stages bring it up rather than refusing and telling
#: the user to — unlike the emulator, which is a real thing to start.
site_bridge_if_local() {
  local url; url="$(cfg url)"
  case "$url" in
    *://localhost*|*://127.0.0.1*|*://0.0.0.0*|*://\[::1\]*) ;;
    *) return 0 ;;
  esac

  local port
  port="$(printf '%s' "$url" | sed -nE 's#^[a-z]+://[^:/]+:([0-9]+).*#\1#p')"
  [ -n "$port" ] || case "$url" in https://*) port=443 ;; *) port=80 ;; esac

  local extra; extra="$(cfg forward_ports)"
  echo "  local site: forwarding port(s) $port $extra"
  scripts/site-bridge.sh up $port $extra || fail "could not bridge the local site"
  scripts/site-bridge.sh verify "$port" || fail "the guest cannot reach $url — is the dev server running?"
}

#: Supplementary source, for API shapes and business rules. Never translated -- the
#: product is what the site does, not what its code says (the brief, and twice confirmed
#: in practice).
#:
#: Synced into sources/<target>/ rather than mounted per target, because Tart fixes
#: mounts at `tart run` time and a mount per target would mean restarting the VM for
#: every job. One read-only `sources` mount covers all of them.
sync_source() {
  local src_path src_repo dest
  src_path="$(cfg source_path)"
  src_repo="$(cfg source_repo)"
  [ -n "$src_path$src_repo" ] || return 0

  dest="sources/$TARGET"
  mkdir -p sources

  if [ -n "$src_path" ]; then
    [ -d "$src_path" ] || fail "source_path does not exist: $src_path"
    echo "  source: syncing $src_path"
    rsync -a --delete \
      --exclude node_modules --exclude .next --exclude dist --exclude build \
      --exclude target --exclude .venv --exclude __pycache__ \
      "${src_path%/}/" "$dest/" || fail "could not sync $src_path"
  else
    if [ -d "$dest/.git" ]; then
      echo "  source: updating $src_repo"
      git -C "$dest" pull --quiet --ff-only || echo "  warning: could not fast-forward" >&2
    else
      echo "  source: cloning $src_repo"
      # Public repositories only. A token for a private one would sit in a VM whose agent
      # runs with a bypassed shell -- see docs/security.md. Clone it yourself and use
      # source_path instead.
      git clone --quiet --depth 50 "$src_repo" "$dest" || fail "could not clone $src_repo"
    fi
  fi

  local n; n="$(find "$dest" -type f 2>/dev/null | wc -l | tr -d ' ')"
  echo "  source: $n file(s) at /Volumes/My Shared Files/sources/$TARGET (read-only)"
}

require_canvas() {
  curl -sf -o /dev/null --max-time 5 "$CANVAS/" \
    || fail "Agent Canvas is not reachable at $CANVAS — run scripts/agent-canvas.sh up"
}

# ---------------------------------------------------------------- stages

stage_inspect() {
  say "inspect — deterministic crawl"
  local url; url="$(cfg url)"
  [ -n "$url" ] || fail "no url: in $DIR/target.yaml"
  mkdir -p "$OUT/reference"
  site_bridge_if_local
  local _inc; _inc="$(cfg include_path)"
  scripts/run-in-guest.sh scripts/inspect-site.ts "$url" \
    --out "$TARGET/reference" \
    --max-routes "$(cfg_or max_routes 8)" \
    --engine "$(cfg_or engine chromium)" \
    ${_inc:+--include-path "$_inc"}
  record inspect "" "$(shasum -a 256 scripts/inspect-site.ts | cut -c1-16)" "finished"
  commit_output inspect
}

stage_explore() {
  say "explore — the agent walks the flow"
  require_canvas
  site_bridge_if_local   # the agent drives Playwright itself and needs the same route
  local p; p="$(compose explore.md)"
  converse explore "$p" 80
  rm -f "$p"
  [ -f "$OUT/reference/journey.md" ] || echo "  warning: no journey.md was written"
}

stage_gate() {
  [ -f "$OUT/reference/APPROVED" ] && return 0
  $ASSUME_YES && { stage_approve; return 0; }

  say "GATE — review the reference material before building"
  cat <<GATE

  Read:   $OUT/reference/journey.md
  Shots:  $OUT/reference/journey/

  Does it cover the right flow, the right branch, and the rule behind the result?
  Getting this wrong is cheap to fix now and expensive to fix after a build.

  Approve:  scripts/factory.sh $TARGET approve
  Or skip the gate next time with: --yes

GATE
  exit 3
}

stage_approve() {
  date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/reference/APPROVED"
  record approve "" "" "approved"
  echo "approved: $OUT/reference/APPROVED"
}

stage_build() {  # stage_build ios|android
  local platform="$1"
  say "build-$platform"
  require_canvas
  [ -f "$OUT/reference/APPROVED" ] || fail "reference not approved — run: scripts/factory.sh $TARGET approve"
  sync_source
  [ "$platform" = "android" ] && { scripts/adb-bridge.sh verify >/dev/null 2>&1 \
    || fail "no Android device reachable — run scripts/adb-bridge.sh up"; }

  local p; p="$(compose build-native-apps.md "prompts/platform-$platform.md")"
  converse "build-$platform" "$p" 120
  rm -f "$p"
}

booted_udid() {
  tart exec "$VM" bash -lc 'xcrun simctl list devices booted -j 2>/dev/null' \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print(next((x["udid"] for v in d["devices"].values() for x in v),""))' 2>/dev/null
}

stage_capture() {
  say "capture — screenshots of the finished apps"
  local udid; udid="$(booted_udid)"
  local found=0

  for platform in ios android; do
    [ -d "$OUT/$platform" ] || continue
    local device
    if [ "$platform" = ios ]; then device="$udid"; else device="emulator-5554"; fi
    [ -n "$device" ] || { echo "  no $platform device; skipping"; continue; }

    local dest="$GUEST/screenshots/$platform"
    tart exec "$VM" bash -lc "rm -rf '$dest' && mkdir -p '$dest'"

    # Prefer the app's own capture flow: the agent wrote it alongside the app, so it
    # follows the real navigation and stays correct as the app changes. Fall back to a
    # bare launch-and-shoot for builds made before capture.yaml was asked for.
    if [ -f "$OUT/$platform/.maestro/capture.yaml" ]; then
      echo "  $platform: running .maestro/capture.yaml"
      # A failed capture flow writes no screenshots at all -- Maestro does not persist
      # the ones it already took. Silently reporting "0 screenshots" makes a broken flow
      # look like an app with nothing to show, so say which it is.
      if ! tart exec "$VM" bash -lc "cd '$GUEST/$platform' && MAESTRO_DRIVER_STARTUP_TIMEOUT=$MAESTRO_IOS_TIMEOUT maestro --device $device test .maestro/capture.yaml" >/dev/null 2>&1; then
        echo "  $platform: capture.yaml FAILED — no screenshots are written when it does." >&2
        echo "             Run it directly to see where: maestro --device $device test .maestro/capture.yaml" >&2
      fi
      # Maestro writes into ~/.maestro/tests/<timestamp>/; lift the newest run's images out.
      tart exec "$VM" bash -lc "
        latest=\$(ls -td ~/.maestro/tests/*/ 2>/dev/null | head -1)
        [ -n \"\$latest\" ] && find \"\$latest\" -name '*.png' -exec cp {} '$dest/' \;
      " >/dev/null 2>&1
    else
      echo "  $platform: no capture.yaml — launching for a single screenshot"
      if [ "$platform" = ios ]; then
        local bundle
        bundle="$(tart exec "$VM" bash -lc "xcrun simctl listapps $device 2>/dev/null | grep -oE '\"[a-zA-Z0-9.-]+\" =' | tr -d '\" =' | grep -vE '^com.apple' | head -1")"
        [ -n "$bundle" ] && tart exec "$VM" bash -lc "
          xcrun simctl launch $device $bundle >/dev/null 2>&1; sleep 4
          xcrun simctl io $device screenshot '$dest/01-launch.png'" >/dev/null 2>&1
      else
        tart exec "$VM" bash -lc "
          pkg=\$(adb shell pm list packages 2>/dev/null | grep -v android | grep example | head -1 | cut -d: -f2 | tr -d '\r')
          [ -n \"\$pkg\" ] && adb shell monkey -p \"\$pkg\" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
          sleep 4; adb exec-out screencap -p > '$dest/01-launch.png'" >/dev/null 2>&1
      fi
    fi

    local n; n="$(ls "$OUT/screenshots/$platform"/*.png 2>/dev/null | wc -l | tr -d ' ')"
    echo "  $platform: $n screenshot(s) -> output/$TARGET/screenshots/$platform/"
    [ "$n" -gt 0 ] && found=$((found + 1))
  done

  record capture "" "" "$([ "$found" -gt 0 ] && echo captured || echo none)"
  commit_output capture
}

stage_test() {
  say "test — re-run the committed Maestro flows"
  local udid rc=0
  udid="$(booted_udid)"

  # Run the flows individually, skipping capture.yaml: it belongs to the `capture`
  # stage, and running it here makes `test` report a screenshot walk as a passing test.
  # Distinct stages should stay distinct even when the mechanism is shared.
  local flows
  if [ -d "$OUT/ios/.maestro" ] && [ -n "$udid" ]; then
    flows="$(cd "$OUT/ios/.maestro" && ls *.yaml 2>/dev/null | grep -v '^capture\.yaml$' | tr '\n' ' ')"
    [ -n "$flows" ] && { tart exec "$VM" bash -lc "cd '$GUEST/ios/.maestro' && MAESTRO_DRIVER_STARTUP_TIMEOUT=$MAESTRO_IOS_TIMEOUT maestro --device $udid test $flows" || rc=1; }
  fi
  if [ -d "$OUT/android/.maestro" ]; then
    flows="$(cd "$OUT/android/.maestro" && ls *.yaml 2>/dev/null | grep -v '^capture\.yaml$' | tr '\n' ' ')"
    [ -n "$flows" ] && { tart exec "$VM" bash -lc "cd '$GUEST/android/.maestro' && maestro --device emulator-5554 test $flows" || rc=1; }
  fi
  record test "" "" "$([ $rc -eq 0 ] && echo passed || echo failed)"
  return $rc
}

stage_status() {
  [ -f "$RUNS" ] || { echo "nothing has run for $TARGET"; return 0; }
  printf '%-14s %-10s %-38s %s\n' STAGE OUTCOME CONVERSATION WHEN
  python3 - "$RUNS" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    print(f"{r['stage']:<14} {r['outcome']:<10} {r.get('conversation') or '-':<38} {r['ts'][:19]}")
PY
}

case "$STAGE" in
  inspect)       stage_inspect ;;
  explore)       stage_explore ;;
  approve)       stage_approve ;;
  gate)          stage_gate ;;
  build-ios)     stage_build ios ;;
  build-android) stage_build android ;;
  source)        say "source"; sync_source ;;
  capture)       stage_capture ;;
  test)          stage_test ;;
  status)        stage_status ;;
  all)           stage_inspect; stage_explore; stage_gate
                 stage_build ios; stage_build android; stage_test; stage_capture ;;
  *)             fail "unknown stage: $STAGE" ;;
esac
