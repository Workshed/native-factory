#!/bin/bash
# Shared shell setup for every provisioning step.
set -euo pipefail

export NF_PREFIX=/opt/native-factory
sudo mkdir -p "$NF_PREFIX"
sudo chown "$(id -u):$(id -g)" "$NF_PREFIX"
mkdir -p "$NF_PREFIX/bin" "$NF_PREFIX/build-logs"

# Every script records the versions it installed here; 99-manifest.sh assembles them.
: > "$NF_PREFIX/build-logs/versions.env"

echo "prepared $NF_PREFIX on $(sw_vers -productVersion) ($(uname -m))"
