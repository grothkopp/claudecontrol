#!/usr/bin/env osascript -l JavaScript
//
// claude-state.js — read live state of the Claude Mac App via the macOS
// Accessibility tree. Emits JSON on stdout. Works on all three tabs.
//
//   osascript -l JavaScript claude-state.js
//
// The accessibility tree only exposes the SELECTED tab's sidebar. The selected
// tab's buttons give no "selected" flag, so we identify the tab from the top
// nav button — "New session" (Code) / "New task" (Cowork) / "New chat" (Chat) —
// and parse the rows accordingly:
//   Code:   "Running …" / "Awaiting input …" / "Idle …" / "#408 · Draft …"
//   Cowork: "Mark as unread …" / "Mark as read …" (status not in the title)
//   Chat:   bare "<name>"
// All three share "Pinned"/"Recents" section headers and an account pop-up
// footer (an AXPopUpButton), which marks the end of the sidebar list.
//
// Output:
//   { "ok": true,
//     "tab": "Code" | "Cowork" | "Chat" | null,
//     "items": [ {"type":"header","name":"Pinned"},
//                {"type":"task","name":"…","status":"Idle"} ],   // status: Code only
//     "focused": "…" | null,        // open conversation (main-pane header title)
//     "scanned": 232 }
//

const CODE_RE = /^(Running|Awaiting input|Idle) (.+)$/;
const PR_RE = /^(#\d+ · (?:Draft|Open|Merged|Closed)) (.+)$/;
const NEW_RE = /^New (session|task|chat)$/;
const TAB_OF = { session: 'Code', task: 'Cowork', chat: 'Chat' };
const HEADERS = new Set(['Pinned', 'Recents']);
const SKIP = new Set(['View all']);
const GAP_AFTER_ROWS = 60;   // stop this many non-row elements past the last row
const HARD_CAP = 400;

function parseRow(title, tab) {
  if (tab === 'Code') {
    const m = CODE_RE.exec(title) || PR_RE.exec(title);
    if (m) return { name: m[2], status: m[1] };
    return { name: title, status: '' };
  }
  if (tab === 'Cowork') {
    return { name: title.replace(/^Mark as (?:unread|read) /, ''), status: '' };
  }
  return { name: title, status: '' };  // Chat / unknown
}

function run() {
  const se = Application('System Events');
  const proc = se.processes.byName('Claude');
  if (!proc.exists()) return JSON.stringify({ ok: false, error: 'Claude app not running' });
  try { proc.attributes.byName('AXManualAccessibility').value = true; } catch (e) {}

  let all;
  try { all = proc.windows[0].entireContents(); } catch (e) {
    return JSON.stringify({ ok: false, error: 'no window: ' + e });
  }

  // Active tab: the Chat/Cowork/Code button carries aria-current="page" when
  // selected (AXARIACurrent === "page"); the inactive ones have it absent. This
  // is the canonical "highlighted tab" signal — AXSelected and the class list
  // are identical across tabs and useless here. The buttons sit near the top of
  // the tree (~index 27-29). Fallback below: the top "New session/task/chat".
  let tab = null;
  for (let i = 0; i < Math.min(all.length, 60); i++) {
    let d; try { d = all[i].description(); } catch (x) { continue; }
    if (d === 'Chat' || d === 'Cowork' || d === 'Code') {
      let cur = ''; try { cur = all[i].attributes.byName('AXARIACurrent').value(); } catch (x) {}
      if (cur === 'page') { tab = d; break; }
    }
  }

  // The open ("focused") conversation: Chat/Cowork expose it as the web-area
  // (document) title "<name> - Claude" — robust even when it's not in the
  // visible Pinned/Recents list. Code keeps the name OUT of the doc title (it's
  // just "Claude"); Code's open conversation is matched from its header below.
  let focused = null;
  for (let i = 0; i < Math.min(all.length, 16); i++) {
    let r; try { r = all[i].role(); } catch (x) { continue; }
    if (r !== 'AXWebArea') continue;
    let wt; try { wt = all[i].title(); } catch (x) { continue; }
    const m = wt && /^(.+) - Claude$/.exec(wt);
    if (m) focused = m[1];
  }

  const items = [];
  const rowNames = new Set();
  let foundList = false;   // seen the first section header (sidebar list started)
  let gap = 0;
  let scanned = 0;
  const limit = Math.min(all.length, HARD_CAP);

  for (let i = 0; i < limit; i++) {
    scanned++;
    let title; try { title = all[i].title(); } catch (x) { title = null; }
    if (!title) { if (foundList && ++gap > GAP_AFTER_ROWS) break; continue; }

    const nm = NEW_RE.exec(title);
    if (nm) { if (!tab) tab = TAB_OF[nm[1]]; continue; }   // fallback if aria-current missing

    if (HEADERS.has(title)) { items.push({ type: 'header', name: title }); foundList = true; gap = 0; continue; }
    if (!foundList) continue;                                   // top nav: skip
    if (SKIP.has(title) || title.indexOf('Relaunch to update') === 0) continue;

    // A real sidebar row is a button with the row CSS class; main-pane buttons
    // (tool/file/message actions, the account selector, the focused header) lack
    // it, which both excludes them and self-terminates the scan via the gap.
    let cls = ''; try { cls = (all[i].attributes.byName('AXDOMClassList').value() || []).join(' '); } catch (x) {}
    if (cls.indexOf('df-row-font') >= 0) {
      const row = parseRow(title, tab);
      items.push({ type: 'task', name: row.name, status: row.status });
      rowNames.add(row.name);
      gap = 0;
      continue;
    }

    // Not a row → main-pane content. The focused conversation's header title is a
    // bare name matching a sidebar row.
    const fname = parseRow(title, tab).name;
    if (!focused && rowNames.has(fname)) focused = fname;
    if (++gap > GAP_AFTER_ROWS) break;
  }

  return JSON.stringify({ ok: true, tab, items, focused, scanned });
}
