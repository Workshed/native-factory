#!/usr/bin/env bash
# Cross-cutting invariant 1 (docs/implementation-plan.md): no provider-specific logic
# outside the provider adapters. The ACP seam is only real if nothing else names a provider.
set -euo pipefail

cd "$(dirname "$0")/.."

PATTERN='claude|anthropic|codex|gemini|copilot'
ALLOWED='packages/native-factory-guest/src/native_factory_guest/providers/'

hits=$(grep -rniE "$PATTERN" \
        --include='*.py' \
        packages/ 2>/dev/null \
      | grep -v "$ALLOWED" \
      || true)

if [ -n "$hits" ]; then
  echo "Provider-specific identifiers found outside $ALLOWED:" >&2
  echo "$hits" >&2
  echo >&2
  echo "Move provider logic into a provider adapter, or add a narrow exception here" >&2
  echo "with a comment explaining why it cannot live behind the ACP seam." >&2
  exit 1
fi

echo "ok: no provider-specific logic outside providers/"
