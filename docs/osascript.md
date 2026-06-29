# Controlling the Claude Mac App via macOS Accessibility (osascript / AX)

Read live state from the Claude Mac App — task lists, running/idle state, and
permission prompts — and drive its UI (click Allow/Deny, switch modes) through
the macOS Accessibility (AX) API. No private API, no app cooperation required.

Tested against Claude Mac App **v1.15962.0** (Electron/Chromium), bundle id
`com.anthropic.claudefordesktop`, on macOS (Darwin 25.x).

> The companion script [`claude-state.js`](../claude-state.js) implements the
> read path described here and emits JSON.

---

## TL;DR

- The app is Electron. Its web contents are **invisible to AX until you opt in**
  by setting `AXManualAccessibility = true` on the process. This is the whole
  ballgame — before it, the window has 4 elements; after, ~1200.
- Once enabled, the full DOM is exposed as an AX tree: buttons, static text, and
  status icons all carry useful `AXDescription` / `AXValue` / DOM attributes.
- **The single most useful signal is each sidebar row's `AXTitle`**, which is
  `"<status> <task name>"` — e.g. `"Running Claude Mac App task control"`,
  `"Awaiting input AI consulting landing page"`, `"Idle aicx-nanoclaw"`. This
  gives you every task's name *and* live status in one read, works regardless of
  which conversation is open, and needs no fragile icon/text pairing. See
  [Reading tasks & status via `AXTitle`](#reading-tasks--status-via-axtitle).
- Every actionable element supports the **`AXPress`** action, so you can click
  Allow/Deny and switch Chat/Cowork/Code programmatically.
- **AX only ever shows the currently-selected mode** (Chat *or* Cowork *or*
  Code). Inactive modes are unmounted from the DOM, not merely hidden. Reading
  all three requires cycling tabs (disruptive). For always-on cross-mode
  monitoring, use the session/process layer instead (see
  [Limitations](#limitations--what-ax-cannot-do)).
- **The open ("focused") conversation IS detectable** — not from the sidebar
  (`AXSelected`/`AXFocused` are `false` on every row), but from the **main-pane
  header**: a title `AXButton` whose bare `AXTitle` equals a sidebar task name.
  See [Detecting the focused conversation](#detecting-the-focused-conversation).
- **Not available via AX:** token counts and elapsed time — the app renders no
  accessible text for them. Track elapsed time yourself.

---

## Prerequisites

1. **Accessibility permission.** Whatever process sends the AppleScript
   (`osascript`, your terminal, your daemon) must be granted access under
   **System Settings → Privacy & Security → Accessibility**. Without it every
   call fails with:

   ```
   System Events got an error: osascript is not allowed assistive access. (-1719)
   ```

   This grant cannot be set programmatically — the user must toggle it once.

2. **The Claude app must be running.** Bringing it forward is not required (AX
   reads work in the background), but the process must exist.

---

## Step 1 — Enable the Chromium accessibility tree

Chromium only builds its accessibility tree when an assistive client requests
it. Setting the `AXManualAccessibility` attribute on the process is the
documented Chromium opt-in. It is **idempotent and cheap** — set it defensively
on every run.

```applescript
tell application "System Events" to tell process "Claude"
  set value of attribute "AXManualAccessibility" to true
end tell
```

Verification — element count before vs. after:

```applescript
tell application "System Events" to tell process "Claude"
  count of (entire contents of window 1)   -- 4 before, ~1201 after
end tell
```

Before opt-in, `window 1` contains only the native title-bar chrome:

```
AXGroup
AXButton  "close button"
AXButton  "full screen button"
AXButton  "minimize button"
```

---

## Step 2 — The element model

After opt-in, the meaningful content falls into these AX roles:

| Role           | Carries state in        | Used for |
|----------------|-------------------------|----------|
| `AXButton` (sidebar row) | **`AXTitle`** = `"<status> <name>"` | **Primary signal** — every task's name + live status. See below. |
| `AXButton` (control)     | `AXDescription`         | Mode tabs (`Chat`/`Cowork`/`Code`), `Stop`, permission `Allow`/`Deny`, message actions |
| `AXStaticText` | `AXValue`               | Message text, exit codes; a row's bare title (no status) |
| `AXImage`      | `AXDescription`         | Per-row status icon — **unreliable to pair** (see note); prefer the row's `AXTitle` |

> **Why `AXTitle`, not the status icon?** Each sidebar row also has a leading
> status `AXImage` whose `AXDescription` echoes the state (`Idle`, etc.), but
> pairing icons to titles by tree order is fragile — a trailing PR badge image
> can bind to the wrong row. The row `AXButton`'s `AXTitle` already concatenates
> the status and the name (`"Running Claude Mac App task control"`), so read that
> and parse it. One attribute, no pairing, no ambiguity.

### Useful attributes (available on every node)

Pulled from `name of every attribute of <element>`:

```
AXRole              AXSubrole            AXRoleDescription
AXDescription       AXValue              AXTitle              AXHelp
AXDOMIdentifier     AXDOMClassList       AXURL                AXEnabled
AXFocused           AXSelected           AXParent             AXChildren
AXSize              AXPosition           AXFrame              AXSelectedText
```

### Available actions

```
AXPress            AXShowMenu           AXScrollToVisible
```

`AXPress` is the one that matters — it activates buttons/links.

---

## Step 3 — Selectors (what to match on, and how robust each is)

Ranked most-robust to least:

1. **`AXTitle` on sidebar row buttons** — *the primary task signal*. Format is
   `"<status> <name>"`; parse the status prefix (closed vocabulary, below) and
   take the rest as the name. Works across all tabs and needs no pairing.
2. **`AXDescription` on control buttons/images** — stable, human-readable
   labels for non-row controls: `"Chat"`, `"Cowork"`, `"Code"`, `"Stop"`,
   `"Allow"`, `"Reject"`.
3. **`AXDOMClassList`** — real CSS classes, e.g. `df-pill`, `df-row-font`.
   Stable across renders, but **not always discriminating**: the three mode
   tabs share an *identical* class list, and so do all sidebar rows. Useful to
   *recognize* a row (`contains "df-row-font"`), not to single one out.
4. **`AXValue` on static text** — visible text; fine for reading message bodies,
   fragile as a selector because copy changes.
5. **`AXDOMIdentifier`** — e.g. `base-ui-_r_e_`. **Avoid.** React-generated;
   churns between renders.

### Observed concrete selectors

| Element | Role | Selector | Notes |
|---|---|---|---|
| **Task (name + status)** | `AXButton` | `AXTitle` matches `/^(Running\|Awaiting input\|Idle) (.+)$/` (or PR form) | **the main read**; see vocabulary below |
| Mode tab — Chat/Cowork/Code | `AXButton` | `AXDescription == "Chat"` etc. | `AXPress` to switch |
| Generation in progress | `AXButton` | `AXDescription == "Stop"` | present ⇒ focused convo is generating |
| Permission prompt (inline) | `AXButton` | `AXDescription` matches `/Allow\|Deny\|Reject\|Approve/` | `AXPress` to respond |

### Which tab am I on? (Chat / Cowork / Code)

The active tab button carries **`AXARIACurrent = "page"`** (the DOM
`aria-current="page"`); the inactive ones have the attribute absent. That's the
canonical "highlighted tab" signal. (Don't bother with `AXSelected` or the class
list — both are identical across the three tab buttons. `AXARIACurrent` is the
one that differs.) The buttons sit near the top of the tree (~index 27-29):

```
[27] AXButton AXDescription="Chat"   AXARIACurrent=<absent>
[28] AXButton AXDescription="Cowork" AXARIACurrent=<absent>
[29] AXButton AXDescription="Code"   AXARIACurrent="page"   ← active
```

As a fallback (e.g. if `aria-current` is ever missing), the **top nav button**
is also unique per tab:

| Tab | Top nav `AXTitle` | Row `AXTitle` format |
|---|---|---|
| **Code** | `New session` | `"<status> <name>"` (status vocabulary below) |
| **Cowork** | `New task` | `"Mark as unread <name>"` / `"Mark as read <name>"` (some pinned items are bare) |
| **Chat** | `New chat` | bare `"<name>"` |

All three share `Pinned`/`Recents` headers and an account `AXPopUpButton` footer.
Since Chat rows are bare names (indistinguishable from nav/footer by title), the
robust way to pick out a **sidebar row** on any tab is its CSS class: a row's
`AXDOMClassList` contains `df-row-font`. Main-pane buttons (tool/file/message
actions, the account selector, the focused-conversation header) lack it — which
both excludes them and lets a "gap of non-rows" terminate the scan.

The AX tree still only exposes the **selected** tab; to show all three, read
whichever is active and **cache per tab** (the menubar app keeps one snapshot
each and displays the current tab).

### Status vocabulary (the `AXTitle` prefix) — Code tab

Observed prefixes on **Code** sidebar row `AXTitle`s (the rest of the string is
the task name). Cowork/Chat rows carry no status here. This is a **closed set**:

| Prefix | Meaning |
|---|---|
| `Running ` | Actively generating right now. |
| `Awaiting input ` | Yielded to the user — needs a reply or an **allow/deny** decision. This is the cross-tab "needs attention" signal; you do **not** need the conversation open to see it. |
| `Idle ` | Not running, nothing pending. |
| `#<n> · Draft `, `#<n> · Open `, `#<n> · Merged `, `#<n> · Closed ` | Code task with an associated PR; effectively idle. (Other git states likely follow the same `#<n> · <state>` shape.) |

Rows **without** one of these prefixes are navigation, not tasks, and should be
skipped: `New session`, `Routines`, `Dispatch Beta`, `Customize`.

**Section headers** are also buttons with a bare `AXTitle`: `Pinned` and
`Recents` (a `Recent` variant may appear). They delimit the sidebar's pinned vs.
recent groups; treat them as group labels, not tasks. In tree order they appear
exactly where they sit in the sidebar (`Pinned` … its tasks … `Recents` … its
tasks), so a single ordered pass reproduces the sidebar layout.

**Mode detection (cheap):** the reader is Code-oriented. On the Chat/Cowork tabs
these status prefixes don't appear (Cowork rows read `Mark as unread`, Chat is
~empty), so finding **zero** status-prefixed tasks is a reliable "not on the Code
tab" signal — `claude-state.js` reports it as `code: false`, and the menubar app
keeps showing its last cached Code snapshot instead of an empty list.

> **Caveat — `Awaiting input` is broader than "permission prompt".** It covers
> any turn-yield (finished-and-waiting *or* a true allow/deny gate). To tell
> them apart, additionally check for inline `Allow`/`Deny` buttons (requires the
> task to be the open conversation). For a menubar "needs you" indicator,
> `Awaiting input` alone is the right, robust trigger.

> **The status icon `AXImage` is mode-dependent and noisier:** in Cowork its
> description is `Mark as unread` (a hover-action label, not a run-state); in
> Chat the sidebar is essentially empty. The row `AXTitle` is consistent across
> modes — prefer it.

---

## Step 4 — Reading the task list

Walk the tree, keep `AXButton`s whose `AXTitle` starts with a known status
prefix, and split prefix from name:

```applescript
tell application "System Events" to tell process "Claude"
  set value of attribute "AXManualAccessibility" to true
  set out to ""
  repeat with e in (entire contents of window 1)
    try
      if role of e is "AXButton" then
        set t to (value of attribute "AXTitle" of e)
        if t is not missing value and t is not "" then
          -- task rows start with a status word; nav items don't
          if t starts with "Running " or t starts with "Awaiting input " ¬
             or t starts with "Idle " or t starts with "#" then
            set out to out & t & linefeed
          end if
        end if
      end if
    end try
  end repeat
  return out
end tell
```

The JXA version in [`claude-state.js`](../claude-state.js) parses the prefix and
emits JSON, already picking the single task the UI should surface (`active` =
`Awaiting input` first, else `Running`):

```json
{
  "ok": true,
  "active": { "name": "AI consulting landing page", "status": "Awaiting input" },
  "decisionNeeded": true,
  "running": true,
  "tasks": [
    { "name": "aicx-nanoclaw", "status": "Idle" },
    { "name": "Claude Mac App task control", "status": "Running" },
    { "name": "Teams app package generation and deployment", "status": "#408 · Draft" }
  ]
}
```

Run it:

```sh
osascript -l JavaScript claude-state.js
```

---

## Step 5 — Detecting running vs. finished

- **Any task running / needs you** ⇒ read the row `AXTitle` prefixes: a
  `Running ` row is generating; an `Awaiting input ` row has yielded to the
  user. This is the robust, cross-tab signal and is what `claude-state.js` uses.
- **Focused conversation running (secondary)** ⇒ a top-level `AXButton` with
  `AXDescription == "Stop"` exists. When generation finishes the `Stop` button
  disappears (replaced by the send control). Use this only when you specifically
  care about the *open* conversation; the `AXTitle` prefixes are otherwise
  sufficient and don't depend on which tab is selected.
- **Per-task (Code mode)** ⇒ the row's status icon reads `Idle` when not
  running. Poll and diff: `Idle → working` = started, `working → Idle` =
  finished.

Polling cadence of 1–2 s is fine. For lower latency / event-driven detection,
see [Production path](#production-path-axobserver).

---

## Detecting the focused conversation

The sidebar gives no "this row is open" flag (rows have no `aria-current` /
`AXSelected`). Detection differs by tab:

### Chat & Cowork — the web-area (document) title

The root **`AXWebArea`** (near tree index ~10) carries the open conversation as
its title: **`"<name> - Claude"`** (a list/home view with nothing open is just
`"Claude"`). This is the `document.title`. It's the most robust signal — it
works even when the open conversation isn't in the visible Pinned/Recents list:

```
[10] AXWebArea  AXTitle = "Book - Claude"     → focused = "Book"   (Cowork)
[10] AXWebArea  AXTitle = "Kündigung - Claude" → focused = "Kündigung" (Chat)
[10] AXWebArea  AXTitle = "Claude"            → nothing open
```

Note the **window**'s `AXTitle` stays `"Claude"` — it's the *web area*'s title
that holds the conversation name. (Don't confuse the two; that mismatch cost a
debugging detour.)

### Code — the main-pane header button

Code keeps the name *out* of the document title (its web-area title is just
`"Claude"`). Instead its **main content pane has a header showing the open
conversation's title**, an `AXButton` (the editable/rename control) whose **bare
`AXTitle` equals the task's sidebar name** (no status prefix). Find it and you
know which task is focused.

Concretely, the header title button looks like:

```
[170] AXButton @1398,50  AXTitle = "Claude Mac App task control"
      class = truncate text-left text-body-medium text-t9 … cursor-text
```

Distinguishing it cheaply (without reading positions or classes per element):

- Sidebar **row** buttons have a *status-prefixed* `AXTitle` (`"Running …"`).
- Sidebar inner labels are `AXStaticText` — their `AXTitle` is **empty** (text
  lives in `AXValue`), so a title-only scan skips them.
- Tool/file buttons in the transcript have titles like `"Ran …"` / `"foo.py"`
  that don't match any task name.
- The header title button is therefore **the first `AXTitle` that (a) has no
  status prefix and (b) exactly equals a known sidebar task name.**

So in one title-only pass (the same one that reads the task list): collect task
names from the status-prefixed rows, and the first later bare title that matches
one of those names is the focused conversation.

[`claude-state.js`](../claude-state.js) tries the web-area title first (Chat /
Cowork) and falls back to the header match (Code), returning either as
`"focused"`. Verified live on all three tabs: switching conversations updates it.

Caveats: a conversation must be open (a list/home view → `focused` is `null`);
and for Code, duplicate task names can't be told apart.

---

## Step 6 — Reacting to permission events (Allow / Deny)

Permission prompts render as ordinary buttons. Detect and respond with the same
two primitives — enumerate by `AXDescription`, then `AXPress`:

```applescript
-- Respond to a permission prompt. Pass "Allow" or "Reject"/"Deny".
on respondToPermission(choice)
  tell application "System Events" to tell process "Claude"
    repeat with e in (entire contents of window 1)
      try
        if role of e is "AXButton" and description of e is choice then
          perform action "AXPress" of e
          return "pressed " & choice
        end if
      end try
    end repeat
  end tell
  return "no button: " & choice
end respondToPermission
```

Detection query (what the script reports as `permission.visible`): any
`AXButton` whose description matches `/Allow|Deny|Reject|Approve/`.

> Exact button labels vary by prompt (e.g. `Allow`, `Allow always`, `Reject`).
> Enumerate first, match loosely, decide, then `AXPress` the chosen one.

---

## Step 7 — Switching modes

```applescript
tell application "System Events" to tell process "Claude"
  repeat with e in (entire contents of window 1)
    try
      if role of e is "AXButton" and description of e is "Code" then
        perform action "AXPress" of e
        exit repeat
      end if
    end try
  end repeat
end tell
```

After pressing, wait ~1.2 s for the view to re-render before reading.

---

## Limitations — what AX *cannot* do

- **Only the selected mode is visible.** Chat/Cowork/Code are mutually exclusive
  in the DOM; the inactive two are unmounted. Empirically confirmed — switching
  tabs replaces the sidebar wholesale:

  | Mode | Sidebar (same instant) |
  |---|---|
  | Code | aicx-nanoclaw, *Claude Mac App task control · #408 Draft*, … (15) |
  | Cowork | Bewerbungen, Book, Wärmepumpe, JobFriend, … (28) |
  | Chat | empty (account row only) |

  Reading all three at once is **not possible** without cycling tabs, which
  moves the user's UI and is racy.

- **Selected-tab detection:** `AXSelected` and `AXDOMClassList` are identical
  across the three tab buttons (a red herring) — but the active one carries
  **`AXARIACurrent = "page"`**. Use that. See
  [Which tab am I on?](#which-tab-am-i-on-chat--cowork--code).

- **The sidebar doesn't flag the open row** — `AXSelected`/`AXFocused` are
  `false` even on the open one (`data-selected="open"` isn't surfaced). But you
  can still identify the open conversation from the **main-pane header** instead;
  see [Detecting the focused conversation](#detecting-the-focused-conversation).

- **Tokens and elapsed time are not exposed.** The app renders no accessible
  text for token counts or run duration anywhere in the tree (confirmed by
  dumping every node around the `Stop` button — only the input box and queued
  message are there). Track elapsed time yourself from when a row first turns
  `Running`; tokens are simply unavailable via AX.

- **Cowork status icons aren't run-states** (`Mark as unread` is a hover label).
  This is another reason to read the row `AXTitle`, not the status `AXImage`.

- **Performance — the dominant cost is per-element attribute reads, not the
  walk.** Measured on this tree (~1070 nodes):
  - `entireContents()` itself is **cheap** (returns refs, sub-second).
  - Reading **one attribute per node is the killer.** JXA `.title()` ≈ **15–30 ms**
    each; AppleScript `value of attribute "AXTitle"` is far worse (~**167 ms**
    each → a full-tree loop measured **179 s**). Reading every node's title in
    JXA was ~**41 s**.
  - **Vectorized reads do NOT work** here: `title of (entire contents of window
    1)` and `value of attribute "AXTitle" of (entire contents …)` both raise
    `-1700` ("can't make … into type specifier"). Property vectorization only
    works over *direct-children* collections (`every button of <group>`), and
    the sidebar has no shallow semantic container (it's generic nested
    `AXGroup`s ~29 levels deep), so there's no cheap scope handle.
  - **What works:** `entireContents()` is depth-first and the **sidebar renders
    first**, so read `.title()` only until you've walked past it — stop after a
    run of non-task titles (and a hard cap). [`claude-state.js`](../claude-state.js)
    does this and drops from ~41 s to **~5 s** (scans ~200 of ~1070 nodes). It
    also reads *only* `AXTitle` (not role) and filters by the status-prefix
    regex, halving the per-node work.
  - Even at ~5 s this is too slow for the UI thread. Run the reader on a
    **background thread, cache the result, and render the cache** (the menubar
    app does exactly this; poll every ~30 s). The genuinely fast fix is a
    native `AXObserver` daemon — see [Production path](#production-path-axobserver).

---

## Recommended architecture (layered)

Don't use AX tab-cycling for the cross-mode picture. Layer it:

- **AX — for the in-view mode:** within the selected tab, the row `AXTitle`
  prefixes give every task's `Running` / `Awaiting input` / `Idle` state in one
  read, plus inline **permission prompts** (Allow/Deny). This is where AX is
  uniquely good — `Awaiting input` and prompts are pure UI with no file-system
  signal. (It still can't see the *other two* tabs' lists — that's the mode
  limitation above, not a per-task one.)
- **Session/process layer — for always-on Code monitoring:** Code tasks are
  local Claude Code sessions. Watch
  `~/Library/Application Support/Claude/local-agent-mode-sessions/` (lock files
  per active session) or use the `list_sessions` MCP tool. This sees every Code
  task regardless of which tab is on screen, with zero UI disruption.
- **Cowork / Chat** are server-side conversations fetched on demand; they have
  no local run-state to poll and their lists exist in the AX tree only while
  their tab is selected.

---

## Production path: AXObserver

For real-time, low-latency reaction (instead of polling), port the read path to
a small **Swift or PyObjC** helper using `ApplicationServices`:

- Hold the `AXUIElement` for the Claude process (don't re-walk from scratch).
- Register an **`AXObserver`** for notifications:
  - `kAXValueChangedNotification` — status/text changes (task started/finished).
  - `kAXCreatedNotification` / `kAXUIElementDestroyedNotification` — a permission
    prompt appearing/dismissing, the `Stop` button coming and going.
- On notification, read the relevant subtree and fire your callback
  (webhook / local socket / exec).

This converts the polling design above into an event-driven one and removes the
~1–2 s `osascript` spawn cost. The JXA script is the proof-of-concept; the
`AXObserver` daemon is the robust, fast version.

---

## Quick reference

```sh
# One-shot JSON state dump
osascript -l JavaScript claude-state.js

# Enable AX tree (run once per app launch; script does it defensively)
osascript -e 'tell application "System Events" to tell process "Claude" \
  to set value of attribute "AXManualAccessibility" to true'

# Count exposed elements (sanity check: ~1200 means tree is live)
osascript -e 'tell application "System Events" to tell process "Claude" \
  to count of (entire contents of window 1)'
```

| Goal | Primitive |
|---|---|
| Enable tree | `set AXManualAccessibility = true` on process |
| List tasks | keep `AXButton`s whose `AXTitle` starts with a status prefix; split prefix/name |
| Active task | row `AXTitle` starting `Awaiting input ` (needs you), else `Running ` |
| Is running? | any `AXTitle` starts `Running ` (or focused-only: a `Stop` button exists) |
| Decision needed? | any `AXTitle` starts `Awaiting input ` (or inline `Allow`/`Deny` buttons) |
| Respond / switch / open | `perform action "AXPress" of <button>` |
| Tokens / elapsed | **not available** — track elapsed yourself |

---

## Consumers in this repo

- [`claude-state.js`](../claude-state.js) — JXA reader; detects the active `tab`
  (Code/Cowork/Chat) and emits its ordered `items` (section headers + rows) plus
  `focused`, identifying rows by the `df-row-font` class and stopping after a gap
  past the last row (~5–7 s).
- [`claude-focus.js`](../claude-focus.js) — activates the Claude app and
  `AXPress`es a row to open it. Pass a name (and optionally the tab) to switch to
  that conversation; it matches the row by prefix-stripped name + `df-row-font`
  class, and switches to the given tab first if the row isn't in the current one.
  Waits for the window to be AX-ready after `activate()`.
- [`claudebar.py`](../claudebar.py) — a [`rumps`](https://github.com/jaredks/rumps)
  menubar app (run with `uv run claudebar.py`). A background thread runs
  `claude-state.js` back-to-back (never overlapping, ~2 s gap) and keeps **one
  cached snapshot per tab**; a 1 s UI timer renders the current tab's cache, so
  the menu opens instantly and never blocks. The menubar shows, for Code,
  `🟡 awaiting → ▶ running → focused → idle`; for Cowork/Chat, the focused
  conversation (else the tab name). The dropdown reproduces the current tab's
  sidebar — `Pinned`/`Recents` headers (disabled) with items beneath, in sidebar
  order (no re-sort), each clickable to switch via `claude-focus.js`.
  See [`README.md`](../README.md).
