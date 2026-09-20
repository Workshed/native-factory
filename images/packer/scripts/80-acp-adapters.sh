#!/bin/bash
# ACP adapters, pre-installed at resolved versions.
#
# HANDOFF 4.1 writes these as `npx -y @agentclientprotocol/claude-agent-acp`. npx resolves
# and downloads at invocation, which would make a "reproducible" image depend on npm
# reachability and on whatever version is latest at run time. Installing them globally and
# recording the resolved version keeps the architecture and removes the drift (ADR-0003).
#
# No credentials are baked in here. Authentication is injected per conversation at run time
# (docs/architecture.md section 9).
set -euo pipefail
NF_PREFIX=/opt/native-factory

adapters=(
  "@agentclientprotocol/claude-agent-acp"
  "@agentclientprotocol/codex-acp"
  "@google/gemini-cli"
)

for adapter in "${adapters[@]}"; do
  if ! npm install -g "$adapter"; then
    echo "warning: could not install $adapter; that provider will be unavailable" >&2
    continue
  fi
  resolved="$(npm list -g --depth=0 --json "$adapter" | python3 -c "
import json,sys
d = json.load(sys.stdin).get('dependencies', {})
print(next(iter(d.values()), {}).get('version', 'unknown'))
")"
  printf '%s=%s\n' "$adapter" "$resolved" >> "$NF_PREFIX/build-logs/versions.env"
  echo "$adapter $resolved"
done

# GitHub Copilot is not a built-in OpenHands provider; it is reached through the Custom
# provider with `copilot --acp` and is not installed here (HANDOFF 4.1).
