#!/usr/bin/env osascript -l JavaScript
//
// claude-focus.js — bring the Claude app to the front and open a conversation.
//
//   osascript -l JavaScript claude-focus.js "<name>" ["Code"|"Cowork"|"Chat"]
//
// Presses the sidebar row whose (prefix-stripped) name matches <name>. Works on
// all tabs: Code rows are "Idle/Running/… <name>", Cowork rows are
// "Mark as unread/read <name>", Chat rows are bare "<name>". A real sidebar row
// is identified by its CSS class (df-row-font) so we don't accidentally press
// the main-pane header that shares the same name.
//
// If the row isn't in the current tab, switches to the given tab (default Code)
// and retries. With no <name>, opens the Awaiting-input (else Running) row.
//
// Robustness: waits for the window to be AX-available after activate() (it may
// be backgrounded/minimized) and retries while the tree settles.
//
ObjC.import('Foundation');

const CODE_RE = /^(Running|Awaiting input|Idle|#\d+ · (?:Draft|Open|Merged|Closed)) (.+)$/;

function rowName(t) {
  const m = CODE_RE.exec(t);
  if (m) return m[2];
  return t.replace(/^Mark as (?:unread|read) /, '');
}

function run(argv) {
  const wanted = (argv && argv.length) ? argv[0] : null;
  const wantedTab = (argv && argv.length > 1) ? argv[1] : 'Code';

  const se = Application('System Events');
  const proc = se.processes.byName('Claude');
  if (!proc.exists()) return 'Claude not running';

  Application('Claude').activate();

  const sleep = (s) => $.NSThread.sleepForTimeInterval(s);
  const hasWindow = () => { try { return proc.windows().length > 0; } catch (e) { return false; } };
  const contents = () => { try { return proc.windows()[0].entireContents(); } catch (e) { return []; } };
  const press = (el) => { try { el.actions.byName('AXPress').perform(); return true; } catch (e) { return false; } };
  const isRow = (el) => {
    try { return ((el.attributes.byName('AXDOMClassList').value() || []).join(' ')).indexOf('df-row-font') >= 0; }
    catch (e) { return false; }
  };

  for (let k = 0; k < 10 && !hasWindow(); k++) sleep(0.3);
  if (!hasWindow()) return 'no Claude window (open a window in Claude first)';
  try { proc.attributes.byName('AXManualAccessibility').value = true; } catch (e) {}

  function findRow(all) {
    for (let i = 0; i < all.length; i++) {
      let t; try { t = all[i].title(); } catch (e) { continue; }
      if (!t) continue;
      if (wanted) {
        if (rowName(t) === wanted && isRow(all[i])) return all[i];
      } else if (t.indexOf('Awaiting input ') === 0) {
        return all[i];
      }
    }
    if (!wanted) {  // no-arg second choice: a Running row
      for (let i = 0; i < all.length; i++) {
        let t; try { t = all[i].title(); } catch (e) { continue; }
        if (t && t.indexOf('Running ') === 0) return all[i];
      }
    }
    return null;
  }

  function pressTab(all, label) {
    for (let i = 0; i < all.length; i++) {
      let d; try { d = all[i].description(); } catch (e) { continue; }
      if (d === label) { try { if (all[i].role() === 'AXButton') return press(all[i]); } catch (e) {} }
    }
    return false;
  }

  let switchedTab = false;
  for (let attempt = 0; attempt < 4; attempt++) {
    const all = contents();
    const row = findRow(all);
    if (row) return press(row) ? 'opened' : 'press failed';
    if (!switchedTab && pressTab(all, wantedTab)) { switchedTab = true; sleep(1.2); }
    else sleep(0.4);
  }
  return 'not found (app focused' + (wanted ? ': ' + wanted : '') + ')';
}
