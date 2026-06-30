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
- **Accessibility permission** for whatever launches the app: **System Settings →
  Privacy & Security → Accessibility**. The app **prompts for this automatically**
  on first launch (via `AXIsProcessTrustedWithOptions`) and shows a `⚠️
  Accessibility` menubar state + an "Open Accessibility Settings…" menu item until
  granted. The grant goes to the **responsible process**: the bundled `.app`
  prompts as **"ClaudeControl"**; the Homebrew CLI prompts as your **terminal**
  (that's normal for CLI tools). You may also see a separate **Automation** prompt
  ("…wants to control System Events") the first time — allow it too.
  - **Verify it prompts:** `tccutil reset Accessibility de.xsg.claudecontrol`
    then re-open the app → the dialog should reappear (the `.app` case).
- [`uv`](https://docs.astral.sh/uv/) (for the from-source / Homebrew run modes).

## Install

### Download the .dmg (no terminal needed)

Grab the latest **`ClaudeControl-*.dmg`** from the
[**Releases**](https://github.com/grothkopp/claudecontrol/releases/latest) page,
open it, and drag **ClaudeControl** into Applications. It runs as a menubar item
(no dock icon). The `.dmg` is built in CI by the
[Build DMG workflow](.github/workflows/release.yml).

> The app is **not code-signed/notarized**, so on first launch macOS Gatekeeper
> will block it. **Right-click the app → Open** (once), or run
> `xattr -dr com.apple.quarantine /Applications/ClaudeControl.app`. Then grant it
> Accessibility permission.

### Homebrew (tap)

```sh
brew tap grothkopp/claudecontrol
brew trust grothkopp/claudecontrol   # newer Homebrew requires trusting third-party taps
brew install claudecontrol
claudecontrol                        # starts the menubar app
```

> The first run uses `uv` to fetch the small Python dependency (`rumps`); grant
> your terminal Accessibility permission when prompted.

### From source

```sh
git clone https://github.com/grothkopp/claudecontrol
cd claudecontrol
uv run claudebar.py      # uv provisions rumps automatically — no manual venv
```

### Build the .app/.dmg yourself

```sh
./scripts/build-app.sh    # → dist/ClaudeControl.app  (py2app, menubar-only)
./scripts/build-dmg.sh 0.1.2   # → dist/ClaudeControl-0.1.2.dmg
```

See [Packaging](#packaging) for details and the release flow.

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

A self-contained, menubar-only `.app` is built with
[`py2app`](https://py2app.readthedocs.io/) and packaged into a `.dmg`:

```sh
./scripts/build-app.sh         # → dist/ClaudeControl.app
./scripts/build-dmg.sh 0.1.2   # → dist/ClaudeControl-0.1.2.dmg
```

On every **version tag** (`v*`), the [Build DMG workflow](.github/workflows/release.yml)
runs these on a macOS runner and **attaches the `.dmg` to the GitHub release**, so
users can just download it. (Manual `workflow_dispatch` runs upload the `.dmg` as a
workflow artifact instead.)

Distribution channels — all coexist:

| Channel | Command / action | Notes |
|---|---|---|
| **.dmg** | download from Releases | drag-to-Applications; unsigned (Gatekeeper) |
| **Homebrew formula** | `brew install claudecontrol` | runs the scripts via `uv`; no binary |
| **Homebrew cask** | (optional) `brew install --cask` | wraps the `.dmg`/`.app` — see [`Casks/claudecontrol.rb`](Casks/claudecontrol.rb) |

Full release flow: [`docs/packaging.md`](docs/packaging.md).

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
