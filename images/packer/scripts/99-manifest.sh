#!/bin/bash
# Write /opt/native-factory/manifest.json.
#
# This file is what makes "reproducible" checkable. Packer + Tart cannot produce
# byte-identical images -- a rebuild re-runs Homebrew and npm, and images differ by
# timestamp alone -- so the property under test is that two builds from the same
# versions.lock.json produce equal manifests apart from built_at and the image digest.
# See docs/implementation-plan.md AT-2.
set -euo pipefail
NF_PREFIX=/opt/native-factory

python3 - "$NF_PREFIX" <<'PY'
import json, os, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

prefix = Path(sys.argv[1])

tools = {}
versions_file = prefix / "build-logs" / "versions.env"
if versions_file.exists():
    for line in versions_file.read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            tools[key.strip()] = value.strip()

def capture(argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        return (out.stdout + out.stderr).strip().splitlines()[0]
    except Exception:
        return None

tools.setdefault("xcode", capture(["xcodebuild", "-version"]))
tools.setdefault("java", capture(["java", "-version"]))
tools.setdefault("git", capture(["git", "--version"]))

manifest = {
    "schema": 1,
    "built_at": datetime.now(timezone.utc).isoformat(),
    "base_image": os.environ.get("NF_BASE_IMAGE", "unknown"),
    "template_sha256": os.environ.get("NF_TEMPLATE_SHA256", "unset"),
    "macos": platform.mac_ver()[0],
    "arch": platform.machine(),
    "tools": {k: v for k, v in sorted(tools.items()) if v},
    "deliberately_absent": {
        "android-emulator": "cannot be accelerated inside a macOS guest (ADR-0002)",
        "android-system-images": "unused without the emulator",
    },
}

target = prefix / "manifest.json"
target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(f"wrote {target} with {len(manifest['tools'])} tool versions")
PY

cat "$NF_PREFIX/manifest.json"
