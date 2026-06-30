# /// script
# requires-python = ">=3.10"
# dependencies = ["pytest>=8", "rumps>=0.4.0"]
# ///
"""
Tests for claudebar.

    uv run test_app.py            # all tests
    uv run test_app.py -k unit    # just the pure-logic unit tests

Two groups:
  - Unit tests: pure logic in claudebar (status_symbol, select_menubar_title) —
    no Claude app needed.
  - Integration tests: drive the LIVE Claude app via claude-state.js /
    claude-focus.js — switch tabs and open conversations, asserting the reader
    tracks them. NON-DESTRUCTIVE: a session fixture records the starting tab +
    open conversation and restores it in teardown (runs even if a test fails).

Integration tests skip themselves if the Claude app has no readable window.
"""

import json
import os
import subprocess
import sys
import time

import pytest

import claudebar  # the app under test (importing does not start the UI)

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_JS = os.path.join(HERE, "claude-state.js")
FOCUS_JS = os.path.join(HERE, "claude-focus.js")

SWITCH_SETTLE = 2.5   # seconds to let the sidebar re-render after a tab switch
OPEN_SETTLE = 2.5     # seconds to let a conversation open


# ----------------------------------------------------------------------------
# osascript helpers (integration)
# ----------------------------------------------------------------------------
def read_state():
    out = subprocess.run(["osascript", "-l", "JavaScript", STATE_JS],
                         capture_output=True, text=True, encoding="utf-8", timeout=90)
    return json.loads(out.stdout.strip() or "{}")


def open_conversation(name, tab):
    subprocess.run(["osascript", "-l", "JavaScript", FOCUS_JS, name, tab],
                   capture_output=True, text=True, timeout=40)
    time.sleep(OPEN_SETTLE)


def press_tab(tab):
    assert tab in ("Chat", "Cowork", "Code")
    js = (
        "function run(){var p=Application('System Events').processes.byName('Claude');"
        "try{p.attributes.byName('AXManualAccessibility').value=true;}catch(e){}"
        "var a=p.windows[0].entireContents();"
        "for(var i=0;i<a.length;i++){var d='';try{d=a[i].description();}catch(e){continue;}"
        "if(d==='%s'){try{a[i].actions.byName('AXPress').perform();}catch(e){}return;}}}" % tab
    )
    subprocess.run(["osascript", "-l", "JavaScript", "-e", js],
                   capture_output=True, text=True, timeout=30)
    time.sleep(SWITCH_SETTLE)


def ensure_tab(tab, tries=3):
    """Press a tab and confirm via the reader; retry through the known flakiness."""
    st = {}
    for _ in range(tries):
        press_tab(tab)
        st = read_state()
        if st.get("tab") == tab:
            return st
    return st


def same_conversation(a, b):
    """Equal, or one a prefix of the other (sidebar names can be truncated while
    the web-area document title is full)."""
    if not a or not b:
        return False
    if a == b:
        return True
    n = min(len(a), len(b), 18)
    return a[:n] == b[:n]


# ----------------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def restore_starting_state():
    """Record where the user started and put it back when the suite ends."""
    try:
        base = read_state()
    except Exception:
        base = {}
    base = base if base.get("ok") and base.get("tab") else None
    yield base
    if base:  # best-effort restore — runs even if tests failed
        try:
            if base.get("focused"):
                open_conversation(base["focused"], base["tab"])
            else:
                press_tab(base["tab"])
        except Exception:
            pass


@pytest.fixture
def app(restore_starting_state):
    if restore_starting_state is None:
        pytest.skip("Claude app has no readable window")
    return restore_starting_state


# ----------------------------------------------------------------------------
# unit tests — pure logic, no app
# ----------------------------------------------------------------------------
def test_unit_status_symbol():
    assert claudebar.status_symbol("Awaiting input") == claudebar.SYM_AWAITING
    assert claudebar.status_symbol("Running") == claudebar.SYM_RUNNING
    assert claudebar.status_symbol("Idle") == ""
    assert claudebar.status_symbol("#408 · Draft") == ""
    assert claudebar.status_symbol("") == ""


def _tasks(*pairs):
    return [{"type": "task", "name": n, "status": s} for n, s in pairs]


def test_unit_title_awaiting_beats_running():
    items = _tasks(("A", "Running"), ("B", "Awaiting input"))
    assert claudebar.select_menubar_title(items, None, "Code") == f"{claudebar.SYM_AWAITING} B"


def test_unit_title_running():
    items = _tasks(("A", "Idle"), ("B", "Running"))
    assert claudebar.select_menubar_title(items, None, "Code") == f"{claudebar.SYM_RUNNING} B"


def test_unit_title_focused_wins_within_group():
    items = _tasks(("A", "Running"), ("B", "Running"))
    # focused task B should be the one shown even though A comes first
    assert claudebar.select_menubar_title(items, "B", "Code") == f"{claudebar.SYM_RUNNING} B"


def test_unit_title_focused_no_status():
    # Cowork/Chat: no statuses → show the focused conversation, no symbol
    items = _tasks(("Bewerbungen", ""), ("Book", ""))
    assert claudebar.select_menubar_title(items, "Book", "Cowork") == "Book"


def test_unit_title_tab_fallback():
    items = _tasks(("Bewerbungen", ""), ("Book", ""))
    assert claudebar.select_menubar_title(items, None, "Chat") == "Claude: Chat"


def test_unit_title_truncates():
    long = "x" * 80
    out = claudebar.select_menubar_title(_tasks((long, "Running")), None, "Code")
    assert out.startswith(claudebar.SYM_RUNNING + " ")
    assert "…" in out and len(out) < len(long)


# ----------------------------------------------------------------------------
# integration tests — live Claude app
# ----------------------------------------------------------------------------
def test_reader_shape(app):
    st = read_state()
    assert st["ok"] is True
    assert st["tab"] in ("Code", "Cowork", "Chat")
    assert isinstance(st["items"], list)
    for it in st["items"]:
        assert it["type"] in ("header", "task")
        assert it["name"]
        if it["type"] == "task":
            assert "status" in it
    assert st["focused"] is None or isinstance(st["focused"], str)


@pytest.mark.parametrize("tab", ["Chat", "Cowork", "Code"])
def test_tab_detection(app, tab):
    """Switching to a tab is reflected by the reader (via AXARIACurrent)."""
    st = ensure_tab(tab)
    assert st.get("tab") == tab


def test_sections_and_status(app):
    """Code shows Pinned/Recents headers and status-bearing rows."""
    st = ensure_tab("Code")
    headers = [i["name"] for i in st["items"] if i["type"] == "header"]
    statuses = {i["status"] for i in st["items"] if i["type"] == "task"}
    assert any(h in ("Pinned", "Recents") for h in headers)
    # Code rows carry a status vocabulary (Idle / Running / Awaiting input / #PR)
    assert statuses and statuses != {""}


@pytest.mark.parametrize("tab", ["Code", "Cowork", "Chat"])
def test_focused_roundtrip(app, tab):
    """Open a conversation on a tab; the reader reports it as focused."""
    st = ensure_tab(tab)
    if st.get("tab") != tab:
        pytest.skip(f"could not switch to {tab}")
    tasks = [i for i in st["items"] if i["type"] == "task"]
    if not tasks:
        pytest.skip(f"{tab} has no conversations")
    target = tasks[0]["name"]
    open_conversation(target, tab)
    st2 = read_state()
    assert st2.get("tab") == tab
    assert same_conversation(st2.get("focused"), target), \
        f"focused={st2.get('focused')!r} != target={target!r}"


def test_cross_tab_open(app):
    """Opening a Cowork conversation while on Code switches tabs and focuses it."""
    cw = ensure_tab("Cowork")
    tasks = [i for i in cw["items"] if i["type"] == "task"]
    if not tasks:
        pytest.skip("no Cowork conversations")
    target = tasks[0]["name"]
    moved = ensure_tab("Code")
    if moved.get("tab") != "Code":
        pytest.skip("could not park on Code")
    open_conversation(target, "Cowork")
    st = read_state()
    assert st.get("tab") == "Cowork"
    assert same_conversation(st.get("focused"), target)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", *sys.argv[1:]]))
