#!/usr/bin/env bash
#
# Push a script into the guest and run it there.
#
#     scripts/run-in-guest.sh scripts/inspect-site.ts https://example.com --out reference
#
# Why not just run it from the read-only mount? Because the guest's view of the shared
# mount goes stale. Measured 2026-09-22:
#
#   * a NEW file on the host is read correctly in the guest;
#   * a MODIFIED file keeps returning the old content, indefinitely;
#   * if the new content is longer, the tail is NUL-filled to the new length, which
#     surfaces as `SyntaxError: Unexpected character '\0'` pointing at a line past the
#     end of the file;
#   * deleting and recreating the file on the host does not clear it.
#
# So editing a script on the host and running it from the mount silently executes the
# previous version. `tart exec -i` with the file on stdin bypasses the mount entirely.
#
# The rw work mount is not affected in the same way for the case that matters: the guest
# writes there and reads its own writes.

set -euo pipefail

VM="${NF_VM:-nf}"
SCRIPT="${1:?usage: run-in-guest.sh <script> [args...]}"
shift

[ -f "$SCRIPT" ] || { echo "no such script: $SCRIPT" >&2; exit 1; }

NAME="$(basename "$SCRIPT")"
REMOTE="\$HOME/nf/$NAME"

tart exec -i "$VM" bash -l -c "mkdir -p \$HOME/nf && cat > $REMOTE" < "$SCRIPT"

case "$NAME" in
  *.ts|*.js|*.mjs)
    # NODE_PATH so createRequire can resolve the global Playwright install.
    tart exec "$VM" bash -l -c "cd '/Volumes/My Shared Files/work' && NODE_PATH=\$(npm root -g) node $REMOTE $*"
    ;;
  *.sh)
    tart exec "$VM" bash -l -c "chmod +x $REMOTE && cd '/Volumes/My Shared Files/work' && $REMOTE $*"
    ;;
  *.py)
    tart exec "$VM" bash -l -c "cd '/Volumes/My Shared Files/work' && python3 $REMOTE $*"
    ;;
  *)
    echo "don't know how to run $NAME" >&2; exit 2 ;;
esac
