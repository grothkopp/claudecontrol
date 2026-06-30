"""
py2app build config for a self-contained, menubar-only ClaudeControl.app.

    uv run --with py2app --with rumps python setup.py py2app
    # → dist/ClaudeControl.app

`LSUIElement` makes it a menubar agent (no dock icon). The JXA helper scripts
are bundled into the app's Resources dir; claudebar.py finds them via the
$RESOURCEPATH env var that py2app sets.
"""

from setuptools import setup

APP = ["claudebar.py"]
DATA_FILES = ["claude-state.js", "claude-focus.js"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "ClaudeControl",
        "CFBundleDisplayName": "Claude Control",
        "CFBundleIdentifier": "de.xsg.claudecontrol",
        "CFBundleVersion": "0.1.2",
        "CFBundleShortVersionString": "0.1.2",
        "NSHumanReadableCopyright": "© 2026 Stefan Grothkopp. MIT License. "
        "Unofficial — not affiliated with Anthropic.",
    },
    "packages": ["rumps"],
    "includes": ["objc", "Foundation", "AppKit", "Quartz"],
}

setup(
    name="ClaudeControl",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
