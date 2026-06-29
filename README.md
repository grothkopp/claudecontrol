# claudecontrol

A small macOS **menubar app** that surfaces what the [Claude desktop app](https://claude.ai/download)
is doing — across its **Chat**, **Cowork**, and **Code** tabs — without an
official API. It reads the app's live UI through the macOS Accessibility tree and
shows the current tab's conversations/tasks, their status, and which one is open.

[![CI](https://github.com/grothkopp/claudecontrol/actions/workflows/test.yml/badge.svg)](https://github.com/grothkopp/claudecontrol/actions/workflows/test.yml)
&nbsp;·&nbsp; macOS · Python 3.10+

> **Unofficial.** This is a third-party tool and is **not affiliated with,
> endorsed by, or supported by Anthropic**. "Claude" is a trademark of Anthropic.

---

## What it shows

The menubar shows one line for the **currently selected tab** in Claude:

| State | Title |
|---|---|
| **Code** — a task is awaiting input | `🟡 <task>` |
| **Code** — a task is running | `▶ <task>` |
| **Code** — otherwise | the open task (no symbol) |
| **Cowork / Chat** | the open conversation, else `Claude: <tab>` |

Click it for a dropdown that reproduces the tab's sidebar — **Pinned** / **Recents**
headers with their items beneath, in sidebar order. Code items show `🟡` / `▶`.
**Click any item to jump to that conversation** (switching tabs if needed).

It keeps a **separate cached snapshot per tab**, so switching tabs in Claude
switches what the menubar shows instantly, and the other tabs stay cached even
though only the selected one is readable.

## Requirements

- **macOS** (tested on Sonoma/Sequoia-era builds).
- The **Claude desktop app**, running, with a window open.
- **Accessibility permission** for whatever launches the app (your terminal, or
  the bundled `.app`): **System Settings → Privacy & Security → Accessibility**.
  Without it, the Accessibility calls fail with error `-1719`.
- [`uv`](https://docs.astral.sh/uv/) (for the from-source / Homebrew run modes).

## Install

### Homebrew (tap)

```sh
brew tap grothkopp/claudecontrol
brew install claudecontrol
claudecontrol            # starts the menubar app
```

> The first run uses `uv` to fetch the small Python dependency (`rumps`); grant
> your terminal Accessibility permission when prompted.

### From source

```sh
git clone https://github.com/grothkopp/claudecontrol
cd claudecontrol
uv run claudebar.py      # uv provisions rumps automatically — no manual venv
```

### As a double-clickable .app

See [Packaging](#packaging) to build a self-contained `ClaudeControl.app` (menubar
-only, no dock icon) with `py2app`.

## How it works

The Claude app is an Electron app. Its web contents are invisible to the
Accessibility API until you set `AXManualAccessibility = true` on the process;
after that the full DOM is an AX tree. From there:

- **Active tab** ← the tab button carrying `AXARIACurrent = "page"`.
- **Tasks** ← sidebar row buttons (CSS class `df-row-font`). Code rows carry a
  status in their `AXTitle` (`Running …` / `Awaiting input …` / `Idle …` /
  `#408 · Draft …`); Cowork rows are `Mark as unread/read …`; Chat rows are bare.
- **Open conversation** ← the web-area document title (`"<name> - Claude"`) on
  Chat/Cowork; the editable header button on Code.
- **Driving the UI** ← `AXPress` on any button (switch tabs, open a conversation).

Reads take a few seconds (the Electron a11y tree is slow to walk), so a
background thread runs them back-to-back and the UI renders a cache. Full
technical write-up — selectors, status vocabulary, performance, limitations — is
in [`docs/osascript.md`](docs/osascript.md).

## Pieces

| File | Role |
|---|---|
| [`claude-state.js`](claude-state.js) | JXA reader — detects the active tab and emits its sidebar list as JSON. |
| [`claude-focus.js`](claude-focus.js) | Focuses Claude and opens a conversation by name (switching tabs if needed). |
| [`claudebar.py`](claudebar.py) | The [`rumps`](https://github.com/jaredks/rumps) menubar app — per-tab caching, renders the current tab. |
| [`test_app.py`](test_app.py) | Unit tests (pure logic) + live-app integration tests. |
| [`docs/osascript.md`](docs/osascript.md) | How the Accessibility approach works. |

## Development & tests

```sh
uv run test_app.py -k unit     # fast pure-logic unit tests (no app needed)
uv run test_app.py             # full suite (drives the live Claude app)
```

The integration tests switch tabs and open conversations, then **restore the
starting tab/conversation** in teardown; they **skip** cleanly if the Claude app
has no readable window. CI runs the unit tests only (a live GUI app isn't
available on the runner).

## Packaging

Build a self-contained, double-clickable, menubar-only app with
[`py2app`](https://py2app.readthedocs.io/):

```sh
./scripts/build-app.sh         # → dist/ClaudeControl.app
```

To publish via Homebrew as a **cask** (the `.app`), zip `dist/ClaudeControl.app`,
attach it to a GitHub release, fill the `sha256` in [`Casks/claudecontrol.rb`](Casks/claudecontrol.rb),
and host it in a `homebrew-claudecontrol` tap. The simpler **formula** route (the
`brew install` above) installs the scripts + a `claudecontrol` launcher and needs
no prebuilt binary — see [`docs/packaging.md`](docs/packaging.md).

## Limitations

- Only the **currently-selected** tab is readable; the other two show their last
  cached snapshot until you switch to them.
- **Cowork/Chat** have no per-task status (they're conversation lists) — no
  `🟡`/`▶` there, just names.
- No token counts or elapsed time (the app exposes neither via Accessibility).
- A read takes a few seconds; that's why reads are backgrounded and cached. The
  low-latency upgrade would be a native `AXObserver` daemon.

## License

[MIT](LICENSE) © Stefan Grothkopp
