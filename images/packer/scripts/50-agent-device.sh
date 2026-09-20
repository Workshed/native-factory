#!/bin/bash
# agent-device: interaction and evidence on both platforms (HANDOFF 4.9).
#
# Installed as a plain CLI rather than wired in as an MCP server, so it works for any ACP
# provider without provider-native MCP configuration (ADR-0003).
set -euo pipefail
NF_PREFIX=/opt/native-factory

npm install -g agent-device
resolved="$(npm list -g --depth=0 --json agent-device | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["dependencies"]["agent-device"]["version"])')"

echo "agent-device=${resolved}" >> "$NF_PREFIX/build-logs/versions.env"
echo "agent-device ${resolved}"
