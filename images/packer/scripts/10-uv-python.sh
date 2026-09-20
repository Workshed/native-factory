#!/bin/bash
# uv and a managed Python. The base image's system Python is too old and is not ours to own.
set -euo pipefail
NF_PREFIX=/opt/native-factory

if ! command -v uv >/dev/null 2>&1; then
  brew install uv
fi

uv python install "${NF_PYTHON_VERSION:-3.12}"

{
  echo "uv=$(uv --version | awk '{print $2}')"
  echo "python=$(uv python find "${NF_PYTHON_VERSION:-3.12}" | xargs -I{} {} --version | awk '{print $2}')"
} >> "$NF_PREFIX/build-logs/versions.env"

echo "uv $(uv --version)"
