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
fail() { echo "error: $*" >&2; exit 1; }
cfg()  { sed -n "s/^$1:[[:space:]]*//p" "$DIR/target.yaml" | head -1; }

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
}

compose() {  # compose <shared-prompt> <extra-file-or-empty> -> /tmp/nf-prompt.md
  local out=/tmp/nf-prompt-$$.md
  cat "prompts/$1" > "$out"
  printf '\n\n---\n\n' >> "$out"
  cat "$DIR/brief.md" >> "$out"
  [ -n "${2:-}" ] && { printf '\n' >> "$out"; cat "$2" >> "$out"; }
  echo "$out"
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
  local _inc; _inc="$(cfg include_path)"
  scripts/run-in-guest.sh scripts/inspect-site.ts "$url" \
    --out "$TARGET/reference" \
    --max-routes "$(cfg max_routes || echo 8)" \
    --engine "$(cfg engine || echo chromium)" \
    ${_inc:+--include-path "$_inc"}
  record inspect "" "$(shasum -a 256 scripts/inspect-site.ts | cut -c1-16)" "finished"
}

stage_explore() {
  say "explore — the agent walks the flow"
  require_canvas
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
  [ "$platform" = "android" ] && { scripts/adb-bridge.sh verify >/dev/null 2>&1 \
    || fail "no Android device reachable — run scripts/adb-bridge.sh up"; }

  local p; p="$(compose build-native-apps.md "prompts/platform-$platform.md")"
  converse "build-$platform" "$p" 120
  rm -f "$p"
}

stage_test() {
  say "test — re-run the committed Maestro flows"
  local udid rc=0
  udid="$(tart exec "$VM" bash -lc 'xcrun simctl list devices booted -j 2>/dev/null' \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print(next((x["udid"] for v in d["devices"].values() for x in v),""))' 2>/dev/null)"

  if [ -d "$OUT/ios/.maestro" ] && [ -n "$udid" ]; then
    tart exec "$VM" bash -lc "cd '$GUEST/ios' && maestro --device $udid test .maestro/" || rc=1
  fi
  if [ -d "$OUT/android/.maestro" ]; then
    tart exec "$VM" bash -lc "cd '$GUEST/android' && maestro --device emulator-5554 test .maestro/" || rc=1
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
  test)          stage_test ;;
  status)        stage_status ;;
  all)           stage_inspect; stage_explore; stage_gate
                 stage_build ios; stage_build android; stage_test ;;
  *)             fail "unknown stage: $STAGE" ;;
esac
