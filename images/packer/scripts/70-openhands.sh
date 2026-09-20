#!/bin/bash
# The OpenHands stack, in a dedicated virtualenv the factory owns.
#
# Installed at Milestone 1, configured at Milestone 2. The guest doctor reports its absence
# as SKIP rather than FAIL until then, so an image built without it is still usable.
set -euo pipefail
NF_PREFIX=/opt/native-factory
VENV="$NF_PREFIX/venv"

uv venv --python "${NF_PYTHON_VERSION:-3.12}" "$VENV"

uv pip install --python "$VENV/bin/python" \
  openhands-sdk \
  openhands-tools \
  openhands-workspace \
  openhands-agent-server

# Agent Canvas: the UI runs in the HOST browser against this guest's agent server. The
# package is here so `agent-canvas --backend-only` is available as an alternative to the
# bare agent server (HANDOFF 4.1).
npm install -g @openhands/agent-canvas

{
  for pkg in openhands-sdk openhands-tools openhands-workspace openhands-agent-server; do
    printf '%s=%s\n' "$pkg" "$("$VENV/bin/python" -c "
import importlib.metadata as m
try:
    print(m.version('$pkg'))
except Exception:
    print('unknown')
")"
  done
} >> "$NF_PREFIX/build-logs/versions.env"

echo "openhands stack installed into $VENV"
