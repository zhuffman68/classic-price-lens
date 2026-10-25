# Classic Price Lens

This is a screen-only companion for **MapleStory Classic World**.

- Never attach to, inspect or enumerate the game process, read game memory/files/packets, hook a renderer, send game input/messages, or parent an overlay to the game window.
- Observe through ordinary OS capture. OS pointer coordinates are allowed; input/event hooks are not. Draw only in independent, click-through windows. Tests may drive our own UI or fixtures; game actions must remain user-driven.
- Shop-row labels take priority over generic inventory tooltips when the pointer is over a shop listing. Inventory hover pricing defaults on, with a persistent toggle.
- Equipment is assumed unscrolled. Validate exact item IDs, handle duplicate names conservatively, and never substitute NX retail costs for meso market prices.
- Cache successful, empty, unsupported and old-report responses for the selected TTL. Market-data validity and HTTP-cache validity are separate. Never fetch on every frame.
- Preserve the user's active sharing session during a Linux UI update: SIGUSR1 to our main process performs a handoff; normal close stops sharing. Do not restart the capture helper for routine UI changes.
- `python -m unittest discover -s tests -q` checks prices, real OCR fixtures, local frame IPC and UI context. Use offscreen Qt for automated UI tests. Native Windows game capture is not proven by Wine/offscreen tests.
- Windows packaging: `scripts/package_windows.py` stages verified runtime downloads and the compiled Windows reader; `scripts/make_windows_zip.py` creates the ZIP and checksums. `setup-windows.ps1` supports a native source build. See README and VERIFICATION for current evidence and platform limits.

Keep vendor Minerva at its pinned revision; read its own AGENTS.md before changing it. Do not include private `evidence/`, live screenshots, caches or database files in a package.
