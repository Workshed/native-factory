#!/bin/bash
# The factory's own guest runtime, installed into the venv created by 70-openhands.sh.
set -euo pipefail
NF_PREFIX=/opt/native-factory
VENV="$NF_PREFIX/venv"
SRC=/tmp/native-factory-packages

[ -d "$VENV" ] || uv venv --python "${NF_PYTHON_VERSION:-3.12}" "$VENV"

uv pip install --python "$VENV/bin/python" \
  "$SRC/native-factory-core" \
  "$SRC/native-factory-guest"

# `native-factory vm doctor` invokes this path over tart exec.
"$VENV/bin/native-factory-guest" --help >/dev/null

printf 'native-factory-guest=%s\n' \
  "$("$VENV/bin/python" -c "import importlib.metadata as m; print(m.version('native-factory-guest'))")" \
  >> "$NF_PREFIX/build-logs/versions.env"

rm -rf "$SRC"
echo "guest runtime installed at $VENV/bin/native-factory-guest"
