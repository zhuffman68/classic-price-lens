# Technical details

For installation and everyday use, start with the [README](../README.md).
For source setup, tests and build tools, see [Developing Lupin](DEVELOPING.md).
The [architecture](../ARCHITECTURE.md) explains the component boundaries;
[VERIFICATION.md](../VERIFICATION.md) records evidence and remaining platform checks.

## Screen capture and game boundaries

The only game observation is ordinary OS screen capture. Lupin does not open,
inspect or enumerate the game process; read its memory, files or packets; hook a
renderer; send game input or window messages; or parent a window to the game.
It creates and controls only its own windows and helper processes.

One display dropdown selects the capture display. Click **Start reading** and
approve the desktop sharing chooser if one appears. On Windows, Qt captures the
selected display without a portal chooser. Linux Wayland uses the desktop's
screen-sharing portal. A normal launch waits for Start reading, even when the
previous display is remembered.

The primary control changes between Start, Pause and Resume reading. Pause holds
screen reading and tracking; Resume reuses the sharing session. Connection
problems offer an explicit reconnect action. **Settings → Connection details**
shows the existing captured image and diagnostics without starting another share.

Automatic game-area detection uses visible status-bar LV/border pixels, UI scale
and window-caption pixels. The FPS counter and movable minimap are not required
windowed anchors. A borderless full-display view needs corroborating frame
pixels. If bounds are uncertain, reading waits rather than treating the whole
monitor as the game. A manual area selection takes priority until reset.

The OS captures the chosen display; item OCR is restricted to the identified
game area. Static pixel guards detect movement and coverage before drawing new
labels. Capture queues apply backpressure, unchanged shop pixels skip OCR, known
shops use small read regions, and the reader uses two worker threads.

On KDE Wayland, the independent annotation helper uses XWayland for desktop
positioning. Its canvas is transparent to input and cannot accept focus. The
X11 bypass-window-manager flag applies only to Lupin's canvas, keeping it clear
of desktop-panel repositioning. No game window handle or ownership is involved.

Qt plugin lookup is limited to the running PySide installation in Lupin's own
processes. Existing desktop-wide Qt plugins cannot shadow the bundled capture
plugins. Capture helpers communicate through bounded local IPC; connecting to
the sharing helper has a deadline, while the OS consent dialog itself has no
artificial consent timeout.

## Market prices and item cards

The Classic World regular/cash catalog comes from OSMS Data Explorer. Prices use
one validated MesoWatch full-market snapshot, refreshed asynchronously on launch
and before the earlier of the selected 5/15/30/60-minute interval and the source
publication's one-hour expiry. An old publication uses bounded retries rather
than a rapid refetch loop. Item views, searches, watches and
OCR frames do not make individual price requests.

A short-lived native helper loads the public market page through WebKitGTK on
Linux or the shared production WebView2 runtime on Windows, then exits. No browser
application, personal browser profile or DevTools connection is needed. Screen
images, OCR text and searched names stay local; there is no telemetry.

A complete generation replaces the previous snapshot atomically. Failed updates
preserve last-good prices and their original ages. Source publication, fetch/check
time and latest observed sale are distinct. Validity respects the chosen interval
and the publication-age limit. Missing, thin, uncertain or old observations do not
receive deal colors.

Prices require exact verified game IDs, names, clean condition and item/set units.
Well-formed listing/catalog ID mismatches are omitted, not guessed. Malformed IDs,
duplicates, wrong worlds and generations without exact rows are rejected.
Equipment comparisons assume unscrolled items and do not value individual stat
rolls. NX retail prices never substitute for resale prices. Stars and bullets use
set units. A median is not presented as the amount of a particular sale.

Shop labels remain in place. Labels overlapped by a verified native description
fade to 25% opacity instead of disappearing. Only that recognized panel can cause
dimming; scenery and bright shop panes cannot. Inventory/equipped-item references
can coexist with a shop where supported. Hover pricing has a persistent setting.

The Prices page combines search, compact on-screen listings, watched items and
shared selected-item cards. Search and Database use the same item identity and
market snapshot. Watches use exact IDs. A selected watched item takes precedence;
collapsing the watched panel returns to the on-screen context.

Active GUI cards have a two-second grace period before retirement to recent
items, separate from the current observations required to draw overlays. Recent
items keep up to 100 unique session entries, thumbnails and the last confirmed
asking price; they clear on exit. Quote/age refreshes do not restart structural
animation. Thumbnail downloads have their own bounded cache and never renew
price validity. Private caches and fetched images are not packaged.

## Tracking

EXP/meso tracking starts stopped on every launch. Start explicitly enables it;
Pause holds the session and its displayed pace; Stop and save ends it. Starting a
new session resets its totals and initial rate measurement. Moving maps preserves
totals and rate windows while saving map-history segments.

EXP warmup needs 30 seconds of accepted readings, not wall-clock time. Both rate
windows cover up to five active minutes; meso rates have a separate ten-second
minimum. Timers tick each second, while gains, rates and ETA use two-second
snapshots. Pause and context changes appear immediately. A paused session does not
switch to another visible character. Identity must be reconfirmed before Resume.

Losing visual recognition automatically holds the session, independently of
manual Pause. Timers stop at the last verified frame; the original character
must be confirmed before automatic resumption. A manually selected rectangle
also needs game anchors. Switching desktop focus alone does not pause a readable
game, and unreadable EXP digits alone do not interrupt meso reading.

Meso tracking counts confirmed visible pickup-log arrivals. It does not read the
wallet, subtract potion costs, count trades or estimate profit. Start/Resume and
coverage gaps seed existing messages so an old line is not counted again. Equal
amounts in distinct arrivals can count separately. Fast or hidden arrivals may be
missed; missing coverage is not treated as zero gain.

A separate lightweight worker reads only the pickup crop, so shop OCR cannot
hold up its queue. Per-line position and visual evidence follow scrolling and
fading; EXP, party and item receipts provide non-currency anchors. Unknown or
partly faded text does not clear the log or create a guessed amount. Both the
work queue and arrival history are bounded, and Stop releases the worker.

EXP and MESO have separate visibility checkboxes. Their compact overlays stack
beside the bottom-left HUD, narrowing before using the above-HUD fallback. Native
locator pixels stay clear. The page states the five-minute rate basis once;
paused, warmup, checking and hidden states remain distinct from accepted values.

## Translation, shortcuts and motion

Both Korean directions run locally with the verified model bundles included in
releases. See the [translation guide](KOREAN_CHAT.md) for supported contexts,
slang, numeric safeguards and limitations. English-to-Korean writing copies only
a current validated draft after explicit Enter or Translate & Copy. Editing or
canceling revokes pending copies. It never pastes, sends keys or focuses game chat.

With a freshly identified game, the writing shortcut opens a compact independent
editor at bottom right, beside the status bar or above it on narrower layouts.
The preview expands upward, Enter submits and closes it, and feedback appears
above it. If the desktop denies focus, click the message field or choose Open in
Lupin. Without capture or safe placement, the ordinary writer window is used.
The Translation tab retains its full inline writer. The helper only mirrors the
draft; translation, validation and explicit clipboard authorization remain shared.

Defaults on both platforms are Super/Win+F9 for prices, +F10 for tracking, +F11
for reading Korean and +F8 for writing Korean. Customized bindings are preserved.
Shortcut buttons share one configuration flow. Registration uses Windows
RegisterHotKey, the Wayland GlobalShortcuts portal or an X11 passive grab, never
keyboard hooks, key-state polling or synthesized game input. Wayland activation
tokens may focus only Lupin's own surfaces.

Panel, card and overlay transitions are short and interruptible. Reduce motion
disables decorative motion and pauses the header sprite. Hidden/minimized headers
also stop their animation. Pointer-following price labels reuse the current
identified item rather than issuing another market request for each movement.

## Installation, updates and desktop behavior

Normal downloads are Windows Setup, Arch/Manjaro and Debian/Ubuntu native packages.
Portable Windows downloads are retired; existing portable users should close
their old copy and install Setup manually. The supported offline Windows check
is **selftest-windows.bat**, which runs the packaged application self-test without
capturing a screen or interacting with a game.

Windows installs per user to Programs/Lupin. Upgrade/removal asks only Lupin to
close through its local control endpoint. Linux uses the native package manager.
Settings, histories, prices and logs live under per-user paths, not the program
folder. Legacy internal settings/socket/desktop/portal identities remain stable
so upgrades retain data and approved sharing.

GitHub update checks use signed metadata and exact artifact hashes. Launch and
scheduled checks do not install automatically; the user chooses **Download &
install**. Linux authentication goes through the fixed polkit helper and native
package manager. Source checkouts do not automatically check/install updates.
See [update details](UPDATES.md).

Minimize-to-tray is enabled by default with an OS notification. The tray provides
panel, reading, settings and quit controls. If no tray is available, the panel
stays in the taskbar. Closing the panel or Quit stops capture normally; minimizing
preserves it. `--minimize` controls only Lupin through its own IPC.

## Validation limits

Fixture tests, isolated installed checks and Wine transactions are separate from
live acceptance. Native Windows VM desktop/shop capture has been exercised;
physical multi-monitor, mixed-DPI, fullscreen-exclusive and additional-platform
behavior still require validation. macOS is not a supported release target.
No automated browsing, purchases or game control is performed. OCR can remain
unreadable or ambiguous, and upstream market/database information can be delayed
or incomplete. Current source changes are not evidence of a tested installer;
consult [VERIFICATION.md](../VERIFICATION.md) for the exact tested state.
