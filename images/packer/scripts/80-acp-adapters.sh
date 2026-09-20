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

# Every adapter we might plausibly select is installed now. Pre-installing is what makes
# the image reproducible (ADR-0003), and the cost of that choice is that adding a provider
# later means a 60-90 minute rebuild -- so the list is deliberately generous.
adapters=(
  "@agentclientprotocol/claude-agent-acp"
  "@agentclientprotocol/codex-acp"
  "@google/gemini-cli"
  "@github/copilot"
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

# GitHub Copilot is not a built-in OpenHands provider (HANDOFF 4.1): it is reached through
# the Custom provider, using the CLI's own native ACP server, `copilot --acp --stdio`.
# It needs Node 22+, which 20-node-tools.sh has already asserted.
if command -v copilot >/dev/null 2>&1; then
  echo "copilot CLI present: $(copilot --version 2>&1 | head -1)"
else
  echo "warning: @github/copilot installed but 'copilot' is not on PATH" >&2
fi
