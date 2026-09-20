#!/bin/bash
# XcodeBuildMCP: project discovery, build, test, simulator lifecycle, logs.
#
# Used as a CLI by the pipeline; the MCP server is reserved for interactive Agent Canvas
# sessions where a human is driving (ADR-0003).
set -euo pipefail
NF_PREFIX=/opt/native-factory
version="${NF_XCODEBUILDMCP_VERSION:-2.7.0}"

npm install -g "xcodebuildmcp@${version}"

echo "xcodebuildmcp=${version}" >> "$NF_PREFIX/build-logs/versions.env"
echo "xcodebuildmcp ${version}"
