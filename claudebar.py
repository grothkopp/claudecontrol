# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "rumps>=0.4.0",
#   "pyobjc-framework-Quartz>=10",
#   "pyobjc-framework-ApplicationServices>=10",
# ]
# ///
"""
claudebar — a menubar app that surfaces the Claude Mac App's sidebar (Chat,
Cowork, and Code tabs), read live from the macOS Accessibility tree.

Run:
    uv run claudebar.py

The accessibility tree only exposes the *currently selected* tab. So the reader
detects which tab is active and the app keeps a separate cached snapshot per tab,
always displaying the one currently shown in Claude. Switching tabs in Claude
switches what the menubar shows (instantly, from cache, refreshing in the
background); the other tabs' lists stay cached.

Menubar (single line):
    Code:  🟡 awaiting → ▶ running → focused → idle  (status from the sidebar)
    Cowork/Chat: the focused (open) conversation, else the tab name
                 (these tabs have no per-task status)

Dropdown: the active tab's sidebar reproduced in order — "Pinned" / "Recents"
section headers (non-clickable) with their items beneath; Code items show 🟡 / ▶.
Click an item to focus Claude and switch to it. The footer shows which tab is
displayed and how fresh it is.

Reads take ~5-7 s (slow Electron a11y tree); a single background thread runs them
back-to-back (never overlapping) and caches per tab — the UI renders the cache
and never blocks.
"""

import json
import os
import subprocess
import threading
import time

import rumps

try:
    import Quartz

    def screen_locked():
        """True when the macOS session is locked (screensaver / lock screen).
        While locked, the window server hides app windows from the Accessibility
        API, so reads would just fail — we pause them instead."""
        d = Quartz.CGSessionCopyCurrentDictionary()
        return bool(d.get("CGSSessionScreenIsLocked", 0)) if d else False
except Exception:  # pragma: no cover - Quartz missing → never treat as locked
    def screen_locked():
        return False

try:
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt)

    def accessibility_trusted(prompt=False):
        """True if this process is trusted for Accessibility (required for the
        osascript/System Events reads). With prompt=True, also surface the system
        permission dialog. The grant is attributed to the *responsible* app —
        ClaudeControl.app for the bundled app, or the terminal/launcher that ran
        `claudecontrol` for the Homebrew CLI."""
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))
except Exception:  # pragma: no cover - framework missing → don't block the UI
    def accessibility_trusted(prompt=False):
        return True


def _is_permission_error(err):
    """osascript errors that mean 'permission not granted'."""
    e = (err or "").lower()
    return ("assistive access" in e or "-1719" in e          # Accessibility
            or "not authorized" in e or "-1743" in e)         # Automation (Apple events)

# When bundled as a .app (py2app), the helper scripts live in the app's
# Resources dir, which py2app exposes via $RESOURCEPATH. As a plain script,
# they sit next to this file.
BASE = os.environ.get("RESOURCEPATH") or os.path.dirname(os.path.abspath(__file__))
STATE_JS = os.path.join(BASE, "claude-state.js")
FOCUS_JS = os.path.join(BASE, "claude-focus.js")

REFRESH_GAP_SECONDS = 2.0
LOCK_POLL_SECONDS = 3.0       # while the screen is locked, just re-check this often
UI_TICK_SECONDS = 1.0
READ_TIMEOUT = 90
TITLE_MAXLEN = 32

SYM_AWAITING = "🟡"
SYM_RUNNING = "▶"


def status_symbol(status):
    if status == "Awaiting input":
        return SYM_AWAITING
    if status == "Running":
        return SYM_RUNNING
    return ""  # Idle / #PR / Cowork / Chat → no symbol


def _read_state():
    try:
        out = subprocess.run(
            ["osascript", "-l", "JavaScript", STATE_JS],
            capture_output=True, text=True, encoding="utf-8", timeout=READ_TIMEOUT,
        )
        if out.returncode != 0:
            return {"ok": False, "error": out.stderr.strip() or "osascript failed"}
        return json.loads(out.stdout.strip() or "{}")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"bad json: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _truncate(s, n=TITLE_MAXLEN):
    return s if len(s) <= n else s[: n - 1] + "…"


def select_menubar_title(items, focused, tab):
    """The single menubar line, by priority: awaiting → running → focused → tab.
    Within the awaiting/running group the focused task wins. Pure (no UI) so it
    can be unit-tested. Code tasks carry statuses; Cowork/Chat items don't, so
    those fall through to the focused conversation (else the tab name)."""
    tasks = [it for it in items if it.get("type") == "task"]
    awaiting = [t for t in tasks if t.get("status") == "Awaiting input"]
    runnings = [t for t in tasks if t.get("status") == "Running"]

    def pick(group):
        return next((t for t in group if t["name"] == focused), group[0])

    if awaiting:
        return f"{SYM_AWAITING} {_truncate(pick(awaiting)['name'])}"
    if runnings:
        return f"{SYM_RUNNING} {_truncate(pick(runnings)['name'])}"
    if focused:
        return _truncate(focused)
    return f"Claude: {tab}"


class ClaudeBar(rumps.App):
    def __init__(self):
        super().__init__("Claude: …", quit_button=None)

        self._lock = threading.Lock()
        self._caches = {}            # tab -> state dict (one snapshot per tab)
        self._cache_at = {}          # tab -> monotonic time
        self._current_tab = None     # tab from the latest successful read
        self._updated_at = None
        self._stale = False
        self._reading = False
        self._locked = False
        self._last_error = None

        # Surface the Accessibility permission dialog on first launch if needed,
        # and track whether we're trusted (osascript reads fail with -1719 if not).
        self._ax_ok = accessibility_trusted(prompt=True)

        self._menu_sig = None

        self.mi_age = rumps.MenuItem("Updated: —")
        self._set_menu([], None)

        self._wake = threading.Event()
        threading.Thread(target=self._reader_loop, daemon=True).start()
        self._ui_timer = rumps.Timer(self._render, UI_TICK_SECONDS)
        self._ui_timer.start()

    # ---- background reader (sequential; never overlaps) ---------------------
    def _reader_loop(self):
        while True:
            # While the screen is locked, app windows are hidden from the
            # Accessibility API — skip the (futile, ~5 s) read entirely and just
            # poll the lock state cheaply until the user is back.
            if screen_locked():
                with self._lock:
                    self._locked = True
                    self._reading = False
                self._wake.wait(timeout=LOCK_POLL_SECONDS)
                self._wake.clear()
                continue
            with self._lock:
                self._locked = False
                self._reading = True
            state = _read_state()
            now = time.monotonic()
            with self._lock:
                self._reading = False
                self._updated_at = now
                tab = state.get("tab") if state.get("ok") else None
                if tab:
                    self._caches[tab] = state
                    self._cache_at[tab] = now
                    self._current_tab = tab
                    self._stale = False
                    self._last_error = None
                    self._ax_ok = True
                else:
                    # No tab (transient/ambiguous) or read failed: keep showing
                    # whatever tab we last had, marked stale.
                    self._stale = True
                    self._last_error = state.get("error") if not state.get("ok") else None
                    if _is_permission_error(self._last_error):
                        self._ax_ok = False
            self._wake.wait(timeout=REFRESH_GAP_SECONDS)
            self._wake.clear()

    # ---- menu construction (sidebar order; headers + items) ----------------
    def _set_menu(self, items, tab):
        self.menu.clear()
        any_item = False
        for it in items:
            if it.get("type") == "header":
                self.menu.add(rumps.MenuItem(it["name"], callback=None))  # disabled
            else:
                sym = status_symbol(it.get("status", ""))
                label = "  " + (f"{sym} " if sym else "") + it["name"]
                self.menu.add(rumps.MenuItem(label, callback=self._make_switch(it["name"], tab)))
                any_item = True
        if not any_item and not items:
            self.menu.add(rumps.MenuItem("Open Claude (Chat / Cowork / Code)", callback=None))
        self.menu.add(None)
        self.menu.add(self.mi_age)
        self.menu.add(rumps.MenuItem("Refresh now", callback=self.refresh_now))
        self.menu.add(rumps.MenuItem("Open Accessibility Settings…", callback=self.open_accessibility))
        self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application))

    def _make_switch(self, name, tab):
        args = ["osascript", "-l", "JavaScript", FOCUS_JS, name] + ([tab] if tab else [])
        def cb(_):
            threading.Thread(
                target=lambda: subprocess.run(
                    args, capture_output=True, text=True, encoding="utf-8", timeout=25),
                daemon=True,
            ).start()
        return cb

    # ---- UI render ---------------------------------------------------------
    def _render(self, _=None):
        with self._lock:
            tab = self._current_tab
            cache = self._caches.get(tab) if tab else None
            cache_at = self._cache_at.get(tab) if tab else None
            updated_at = self._updated_at
            stale = self._stale
            reading = self._reading
            locked = self._locked
            ax_ok = self._ax_ok
            error = self._last_error

        if not ax_ok:
            self.title = "⚠️ Accessibility"
            self.mi_age.title = "Grant access: menu → Open Accessibility Settings…"
            return

        if cache is None:
            if locked:
                self.title = "Claude: ⏸"
                self.mi_age.title = "⏸ screen locked"
            else:
                self.title = "Claude: …" if updated_at is None else "Claude: open a tab"
                self.mi_age.title = f"({error})" if error else "Waiting for Claude…"
            return

        items = cache.get("items", [])
        focused = cache.get("focused")

        sig = (tab, focused, tuple((it.get("type"), it.get("name"), it.get("status")) for it in items))
        if sig != self._menu_sig:
            self._set_menu(items, tab)
            self._menu_sig = sig

        if locked:
            self.mi_age.title = "⏸ screen locked"
        else:
            age = int(time.monotonic() - cache_at) if cache_at else 0
            freshness = "cached" if stale else ("refreshing…" if reading else "updated")
            self.mi_age.title = f"{tab} · {freshness} {age}s ago"

        self.title = select_menubar_title(items, focused, tab)

    # ---- actions -----------------------------------------------------------
    def refresh_now(self, _=None):
        self._wake.set()

    def open_accessibility(self, _=None):
        """Re-surface the permission dialog and open the Accessibility pane."""
        accessibility_trusted(prompt=True)
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
            capture_output=True)
        self._wake.set()  # re-check on the next cycle


if __name__ == "__main__":
    ClaudeBar().run()
