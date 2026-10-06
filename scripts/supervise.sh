#!/usr/bin/env bash
#
# Drive a target through its stages, halting at the gate.
#
#     scripts/supervise.sh <target>             run, or resume where it stopped
#     scripts/supervise.sh <target> approve     approve the gate (then run again)
#     scripts/supervise.sh <target> reject "…"  stop, with a reason
#     scripts/supervise.sh <target> state       print state.json
#     scripts/supervise.sh <target> reset       forget progress; keeps output
#
# **This exits at the gate rather than sleeping in it.** A supervisor that waits is a
# process to supervise in turn — a pid to track, something to restart after a reboot,
# something to leak. Exiting means the state is entirely in `state.json`, resuming is
# just running the command again, and completed stages are skipped because they are
# recorded. The console's Approve button therefore writes a file and re-invokes this;
# it does not signal anything.
#
# `factory.sh` still decides how a stage runs. This decides which stage runs next.

set -uo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:?usage: supervise.sh <target> [approve|reject <reason>|state|reset]}"
ACTION="${2:-run}"

DIR="targets/$TARGET"
OUT="output/$TARGET"
STATE="$OUT/state.json"

[ -d "$DIR" ] || { echo "no target at $DIR" >&2; exit 1; }
mkdir -p "$OUT"

cfg() { sed -n "s/^$1:[[:space:]]*//p" "$DIR/target.yaml" | head -1; }

#: Stages in order. `gate` is a checkpoint rather than work, and is in the list so that
#: moving it is a matter of editing a plan rather than editing this script.
#: `explore` is omitted for targets whose flow is links rather than buttons — the
#: deterministic crawl already reaches everything. Override with `plan:` in target.yaml.
DEFAULT_PLAN="inspect explore gate build-ios build-android capture test"

#: A codebase target starts from a survey of what exists rather than a crawl of a site,
#: and the gate reviews that survey. The later stages differ too and are not built yet.
DEFAULT_PLAN_CODEBASE="survey gate baseline task verify"

plan() {
  local p; p="$(cfg plan)"
  [ -n "$p" ] && { echo "$p"; return; }
  case "$(cfg kind)" in
    codebase) echo "$DEFAULT_PLAN_CODEBASE" ;;
    *)        echo "$DEFAULT_PLAN" ;;
  esac
}

write_state() {  # write_state <status> <stage> [message]
  python3 - "$STATE" "$TARGET" "$1" "$2" "${3:-}" "$(plan)" <<'PY'
import json, os, sys
from datetime import datetime, timezone
path, target, status, stage, message, plan = sys.argv[1:7]
prev = {}
if os.path.exists(path):
    try:
        prev = json.load(open(path))
    except ValueError:
        pass
json.dump({
    "target": target,
    "status": status,                       # running | awaiting-approval | done | failed | rejected
    "stage": stage,
    "since": datetime.now(timezone.utc).isoformat(),
    "plan": plan.split(),
    "completed": prev.get("completed", []),
    "message": message or None,
}, open(path, "w"), indent=2)
PY
}

mark_done() {  # mark_done <stage>
  python3 - "$STATE" "$1" <<'PY'
import json, sys
path, stage = sys.argv[1:3]
s = json.load(open(path))
if stage not in s["completed"]:
    s["completed"].append(stage)
json.dump(s, open(path, "w"), indent=2)
PY
}

completed() {  # completed <stage> -> 0 if already done
  [ -f "$STATE" ] || return 1
  python3 - "$STATE" "$1" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
raise SystemExit(0 if sys.argv[2] in s.get("completed", []) else 1)
PY
}

case "$ACTION" in
  state)
    [ -f "$STATE" ] && cat "$STATE" || echo "{\"target\": \"$TARGET\", \"status\": \"new\"}"
    exit 0 ;;
  reset)
    rm -f "$STATE" "$OUT/reference/APPROVED"
    echo "reset $TARGET (output kept)"; exit 0 ;;
  approve)
    scripts/factory.sh "$TARGET" approve || exit 1
    echo "approved — run scripts/supervise.sh $TARGET to continue"; exit 0 ;;
  reject)
    reason="${3:?usage: supervise.sh <target> reject \"<reason>\"}"
    write_state rejected gate "$reason"
    python3 - "$OUT/runs.jsonl" "$reason" <<'PY'
import json, sys
from datetime import datetime, timezone
open(sys.argv[1], "a").write(json.dumps({
    "ts": datetime.now(timezone.utc).isoformat(), "stage": "gate",
    "conversation": "", "prompt_sha256": "", "outcome": "rejected", "reason": sys.argv[2],
}) + "\n")
PY
    cat <<REJECTED

Rejected: $reason

  The fix is the brief, not a re-run: edit targets/$TARGET/brief.md, then

      scripts/supervise.sh $TARGET reset
      scripts/supervise.sh $TARGET

  Re-running against an unchanged brief would mostly reproduce what was rejected.

REJECTED
    exit 0 ;;
  run) ;;
  *) echo "unknown action: $ACTION" >&2; exit 2 ;;
esac

# ------------------------------------------------------------------ run the plan

for stage in $(plan); do
  if completed "$stage"; then
    printf '  \033[2m✓ %s (done)\033[0m\n' "$stage"
    continue
  fi

  if [ "$stage" = gate ]; then
    if [ -f "$OUT/reference/APPROVED" ]; then
      write_state running gate; mark_done gate
      printf '  \033[32m✓ gate (approved)\033[0m\n'
      continue
    fi
    # Point at what this target actually produced. A target whose plan skips `explore`
    # has no journey.md, and offering a path that does not exist is how a gate teaches
    # people to click past it.
    doc="$OUT/reference/site.md"; shots="$OUT/reference/screenshots/"
    [ -f "$OUT/reference/journey.md" ] && { doc="$OUT/reference/journey.md"; shots="$OUT/reference/journey/"; }
    # A codebase target's gate reviews the survey, which lives in the clone.
    for s in repos/"$TARGET"-ios/SURVEY.md repos/"$TARGET"-android/SURVEY.md; do
      [ -f "$s" ] && { doc="$s"; shots="repos/"; break; }
    done

    write_state awaiting-approval gate "review $doc"
    cat <<GATE

  Waiting for approval.

    Read:     $doc
    Shots:    $shots
    Approve:  scripts/supervise.sh $TARGET approve
    Reject:   scripts/supervise.sh $TARGET reject "why"

GATE
    exit 0
  fi

  write_state running "$stage"
  if scripts/factory.sh "$TARGET" "$stage"; then
    mark_done "$stage"
  else
    write_state failed "$stage" "stage $stage failed"
    echo "stopped: $stage failed" >&2
    exit 1
  fi
done

# A codebase target does one task per run. Clearing the per-task stages means the next
# invocation picks up the next unchecked item, while survey, gate and baseline stay done.
if [ "$(cfg kind)" = codebase ]; then
  python3 - "$STATE" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
s["completed"] = [c for c in s["completed"] if c not in ("task", "verify", "capture")]
json.dump(s, open(sys.argv[1], "w"), indent=2)
PY
fi

write_state done ""
echo
echo "$TARGET complete."
[ "$(cfg kind)" = codebase ] && echo "Run again for the next task."
