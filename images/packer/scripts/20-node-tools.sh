#!/bin/bash
# Node is already in the base image (node@24). Agent Canvas needs 22.12+; assert rather
# than assume, because a base image change here would fail much later and less clearly.
set -euo pipefail
NF_PREFIX=/opt/native-factory

node_version="$(node --version | tr -d 'v')"
major="${node_version%%.*}"
minor="$(echo "$node_version" | cut -d. -f2)"
if [ "$major" -lt 22 ] || { [ "$major" -eq 22 ] && [ "$minor" -lt 12 ]; }; then
  echo "node $node_version is older than 22.12, which Agent Canvas and agent-device require" >&2
  exit 1
fi

echo "node=$node_version" >> "$NF_PREFIX/build-logs/versions.env"
echo "npm=$(npm --version)" >> "$NF_PREFIX/build-logs/versions.env"
echo "node $node_version, npm $(npm --version)"
