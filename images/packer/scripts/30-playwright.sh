#!/bin/bash
# Playwright plus the browsers, baked in so a discovery run needs no network for them.
#
# WebKit as well as Chromium: the iOS implementation is judged against what Safari renders,
# so the reference crawl should be able to see that too (docs/architecture.md section 14).
set -euo pipefail
NF_PREFIX=/opt/native-factory
version="${NF_PLAYWRIGHT_VERSION:-1.63.0}"

npm install -g "playwright@${version}"
npx --yes "playwright@${version}" install chromium webkit

echo "playwright=${version}" >> "$NF_PREFIX/build-logs/versions.env"
echo "playwright ${version} with chromium, webkit"
