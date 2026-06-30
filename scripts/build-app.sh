#!/usr/bin/env bash
# Build a self-contained, menubar-only ClaudeControl.app with py2app.
#   ./scripts/build-app.sh   →   dist/ClaudeControl.app
#
# Requires uv (https://docs.astral.sh/uv/). No global Python setup needed.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build dist
uv run --with py2app --with rumps --with pyobjc-framework-Quartz python setup.py py2app

echo
echo "Built: dist/ClaudeControl.app"
echo "Run it:   open dist/ClaudeControl.app"
echo "Zip it:   (cd dist && zip -r -y ClaudeControl-0.1.0.zip ClaudeControl.app)"
echo
echo "Grant the app Accessibility permission on first launch:"
echo "  System Settings → Privacy & Security → Accessibility"
