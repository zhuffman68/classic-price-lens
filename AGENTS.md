# Lupin (formerly Classic Price Lens)

This is a screen-only companion for **MapleStory Classic World**.

- Never attach to, inspect or enumerate the game process, read game memory/files/packets, hook a renderer, send game input/messages, or parent an overlay to the game window.
- Observe through ordinary OS capture. OS pointer coordinates are allowed; input/event hooks are not. Draw only in independent, click-through windows. Tests may drive our own UI or fixtures; game actions must remain user-driven.
- Configurable hotkeys must use OS shortcut registration only: Windows RegisterHotKey, the Wayland GlobalShortcuts portal or an X11 passive grab for the chosen chord. Never use keyboard hooks/listeners, poll keyboard state or synthesize game input. Test hotkeys through our own messages or an isolated X server, without sending game input.
- Shop-row labels take priority over generic inventory tooltips whenever a player shop is visibly open, wherever the pointer is. Inventory hover pricing defaults on, with a persistent toggle.
- Equipment is assumed unscrolled. Validate exact item IDs, handle duplicate names conservatively, and never substitute NX retail costs for meso market prices.
- Cache successful, empty, unsupported and old-report responses for the selected TTL. Market-data validity and HTTP-cache validity are separate. Never fetch on every frame.
- Full-market snapshots refresh asynchronously on launch and hourly. Keep them local, preserve last-good data on failures, validate Classic World/exact IDs/names/units, and keep publication/check/report ages distinct. The optional headless browser uses only its own profile/process and exits after each update; never touch the user's browser or game.
- Preserve the user's active sharing session during a Linux UI update: SIGUSR1 to our main process performs a handoff; normal close stops sharing. Do not restart the capture helper for routine UI changes.
- `python -m unittest discover -s tests -q` checks prices, real OCR fixtures, local frame IPC and UI context. Use offscreen Qt for automated UI tests. Native Windows game capture is not proven by Wine/offscreen tests.
- Windows packaging: `scripts/package_windows.py` stages verified runtime downloads and the compiled Windows reader; `scripts/make_windows_zip.py` creates the ZIP and checksums. `setup-windows.ps1` supports a native source build. See README and VERIFICATION for current evidence and platform limits.
- Installer/package builds: see `packaging/README.md`. Keep install roots read-only during normal use; write logs, settings and price caches only to per-user paths. Windows upgrade/removal may close only our app via its local control socket. Never use a generic process killer or global Wine prefix. Validate package transactions in isolated roots, preserving active host sharing.

Keep vendor Minerva at its pinned revision; read its own AGENTS.md before changing it. Do not include private `evidence/`, live screenshots, caches or database files in a package.

Lupin keeps legacy internal application/package/settings/socket IDs for upgrade compatibility. Price Search is explicit manual demand, works without capture, and must share the existing scheduler, cache and limits. Typing or browsing suggestions must not issue price requests.

EXP watching starts automatically from reliable, connected readings; percentage rates are the default, with raw/both settings. Keep header/display/tabs fixed between pages. Respect Reduce motion and stop the header movie while hidden. Provider identity proof may be extended only by a fresh, matching public index; hints never establish an unverified identity.
