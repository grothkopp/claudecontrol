#!/usr/bin/env bash
# Package dist/ClaudeControl.app into a compressed .dmg with a drag-to-Applications
# layout.  Build the app first:  ./scripts/build-app.sh
#
#   ./scripts/build-dmg.sh [version]   →   dist/ClaudeControl-<version>.dmg
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:-0.0.0}"
APP="dist/ClaudeControl.app"
DMG="dist/ClaudeControl-${VERSION}.dmg"

[ -d "$APP" ] || { echo "error: $APP not found — run ./scripts/build-app.sh first"; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # drag-to-install target

rm -f "$DMG"
hdiutil create -volname "ClaudeControl ${VERSION}" \
  -srcfolder "$STAGE" -ov -format UDZO "$DMG"

echo
echo "Built: $DMG"
