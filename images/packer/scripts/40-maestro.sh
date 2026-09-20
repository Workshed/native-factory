#!/bin/bash
# Maestro, pinned. Requires Java 17+, already in the base image.
#
# The iOS XCTest driver has recurring hang issues on new macOS/Xcode combinations
# (HANDOFF 4.9), so this version and the image's Xcode are a tested pair, not independent
# choices. Milestone 5 smoke-tests them together.
set -euo pipefail
NF_PREFIX=/opt/native-factory
version="${NF_MAESTRO_VERSION:-2.10.0}"

export MAESTRO_VERSION="$version"
curl -fsSL "https://get.maestro.mobile.dev" | bash

# The installer drops into ~/.maestro/bin; put it on PATH for every shell and for tart exec.
grep -q 'maestro/bin' "$HOME/.zprofile" 2>/dev/null || \
  echo 'export PATH="$HOME/.maestro/bin:$PATH"' >> "$HOME/.zprofile"
ln -sf "$HOME/.maestro/bin/maestro" "$NF_PREFIX/bin/maestro"

echo "maestro=${version}" >> "$NF_PREFIX/build-logs/versions.env"
"$HOME/.maestro/bin/maestro" --version
