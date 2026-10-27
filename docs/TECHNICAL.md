# Technical details

For installation and everyday use, start with the [README](../README.md).

## Boundary: pixels only

The only game observation is an ordinary OS screen capture. This project:

- Does not open, inspect, attach to, or enumerate the MapleStory process.
- Does not read game memory or files, intercept packets, inject a DLL, hook a renderer, or use a game API.
- Does not send input, window messages, or commands to the game.
- Does not parent or attach an overlay window to the game window.
- Creates and controls only its **own** windows and helper processes.
- Sends item names/IDs to the public price source; screenshots and OCR frames stay local. No telemetry.

On KDE Wayland, labels use a separate **XWayland** window because ordinary Wayland windows cannot freely position themselves at desktop coordinates. Qt's input-transparent/no-focus flags apply to that independent window. No game handle or game process is used. The X11 bypass-window-manager flag prevents KDE from shifting the annotation canvas below the top panel. The control panel is a normal movable window; drag it wherever convenient.

## Data and caching

- Catalog: [OSMS Data Explorer](https://osmsdataexplorer.com/), its Classic World `data/current/items.json` **and `cash_shop.json`**, cached separately for one day. The cash catalog adds NX coupons, pet skills, cosmetics and other cash items, including named items currently off sale. This is a reference catalog, not evidence that every item is currently obtainable.
- Individual fallback prices: [NiaMeowDB Classic World](https://meowdb.com/msclassic/free-market), fetched **on demand for visible items or an explicit Search selection**. The provider ID is matched using both the exact name and game item ID (`iconKey`); its database row IDs differ from game IDs. Search filters the local catalog while typing and resolves duplicate names before asking for a price.
- Uses the site's **24-hour median** with at least five samples; otherwise its explicitly labeled longer-window `usual` reference. These are reported prices (asking and sold), not guaranteed completed trades. A daily median with fewer than five samples can be displayed when no longer-window reference exists, clearly marked as thin data. The request asks for clean condition.
- Individual fallback cache lifetime defaults to **15 minutes**, adjustable to 5/30/60. Up to three background requests handle new items, with duplicates coalesced. Fresh quotes and item-name lookups stay in memory during scanning; disk caching survives restarts; failed requests use a cooldown and never reset the age of an existing quote. Successful empty, unsupported-item and old-data responses respect the full cache TTL instead of triggering repeated requests. Cache expiry immediately removes the deal rating. Latest reports older than 24 hours, or missing report times, also prevent a rating.
- Prices show **cache age and report age separately**. Rechecking an old report does not make the market observation new. At most 6,000 cached records are retained; records older than seven days are removed on startup. Empty, old-report and source-unsupported responses retain their HTTP cache TTL; they do not get fetched again on every screen read.
- `Below reference` starts at 20% under, `Above reference` over 20% above, otherwise `Near reference`. These are comparison bands, not profitable-flip guarantees. Potential resale margin uses a **3% sale fee**. Listing quantities are normalized for ordinary items; stars/bullets are priced per set, never per projectile.
- Duplicate item names are resolved against the provider's current Classic catalog. A reference is selected only when one matching candidate ID remains; multiple current matches stay explicitly ambiguous. The source's database ID is still validated against the game ID.
- NX retail costs are shown separately in the panel when supplied by the cash catalog. **Overlay FM values are mesos, not NX.** Retail cost is never substituted for a market reference.

Resource controls: frames use local uncompressed RGBA instead of PNG encode/decode, local frame buffers provide backpressure, unchanged shop pixels skip OCR, known shops are read from a small capture region, and a moved shop triggers a full search immediately. The UI rebuilds item cards only when their content changes or ages tick. Rust/OCR uses at most two worker threads; network requests are deduplicated and time-limited. SQLite connections close after each operation. No full-market polling at the screen-reading rate.

In v0.4.2, a visible-item priority queue submits at most three running jobs and keeps at most 64 queued jobs. Missing/expired hovered items take the next available slot ahead of other visible items; queued requests from earlier shops are discarded. Provider completions return to the owning Qt thread before changing scheduler state. Old references stay visible with their original age and explicit queued/refreshing/retry status, while expired prices have no deal rating. Pausing or losing fresh screen/game-area context discards queued screen-derived work. In v0.6.0, a manual Search selection uses the same queue and TTL while its tab stays open, even without capture. Leaving Search cancels its queued demand.

HTTPS connections are reused within the existing worker pool. [Price lookup timing](PRICE_LOOKUP_LATENCY.md) records the measured source delays and remaining limits.

Visible, well-supported references with recent reports can refresh 7.5–30 seconds before expiry, depending on the selected TTL and an item-specific stagger. Other responses retain the full TTL. A successful request resets only lookup age, never source-report age; repeated screen readings still share one request. Failed early checks may retry at expiry, then normal failures use the existing two-minute backoff. [ARCHITECTURE.md](../ARCHITECTURE.md) explains the complete flow and invariants.

The cache and bounded capture log use Qt's standard per-user cache directory. On Linux, the default is typically `~/.cache/LocalTools/Classic Price Lens/`. `--cache /path/prices.sqlite` selects another price-cache location. Installed files remain separate from settings, logs and prices; normal use does not require administrator access.

## Build / other systems

Source builds require Python 3.11+, Rust 1.90+, Git, and PySide6/Qt Multimedia. No AI account or API key is needed. From a repository checkout on Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./setup.sh
./run.sh
```

The reader uses Minerva's MIT headless core, pinned at `7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`. `setup.sh` clones this revision if missing and builds the OCR helper and headless core. Rust build concurrency is limited to two jobs. The OCR model is bundled by upstream; see [THIRD_PARTY.md](../THIRD_PARTY.md).

For a Windows source build, run `setup-windows.ps1` followed by `run-windows.bat`. To build the native installer/package formats, see [packaging/README.md](../packaging/README.md).

macOS remains untested. The intended capture path uses Qt's OS screen capture through the same local helper (`python -m price_lens --capture`), with screen-recording permission on macOS. KDE/Spectacle and XWayland are Linux-specific adapters.

## Checks

```bash
python -m unittest discover -s tests -v
cargo check --locked --manifest-path reader/Cargo.toml -j 2
```

Tests cover item-ID matching, ambiguous names, narrow y/v glyph correction, scroll tiers, bundle versus set pricing, fee calculations, cache expiry, request counting for parked items, unsupported-item 400 responses, failed refreshes, original import age, wrong-world rejection, and upstream OCR fixtures. Capture diagnostics and calibration images are excluded from source control and release packages.

## Limits

Only visible shop rows and enabled tooltips are read; no automated browsing or purchases. Sold rows are omitted, not counted as a source price. Ambiguous names/tiers stay unknown. Tooltip OCR can fail on particular glyphs/fonts; unmatched names stay unknown. The current price source can lag or contain outliers; equipment comparisons assume unscrolled items and do not distinguish individual stat rolls. Labels cover some adjacent game UI/chat; they are mouse-transparent. With screen capture, covering the listing hides it from OCR, as expected. Multiple simultaneous shops, mixed DPI displays, fullscreen-exclusive games, and other operating systems require further testing.

## Windows runtime and installer details

Updates install over the existing version and ask only this app to close through its own local IPC connection. Settings and price-cache files are kept. A second launch activates the existing panel. Close an older portable copy before switching to the installer.

The portable ZIP remains an alternative: extract it completely, then double-click **run-windows.bat**. Keep the `runtime`, `price_lens` and `bin` folders together.

Choose the display containing MapleStory Classic World using the numbered arrangement or list, then click **Start reading**. Approve OS sharing if a chooser appears. Open a player shop or hover over an inventory/equipment item. Windows captures the selected display with Qt's OS screen-capture backend. The overlay draws item names and meso references in its own transparent, click-through window. It does not attach to the game or access its process, memory, renderer, files, packets, messages or inputs.

The primary button starts disabled until a display is selected, then changes between **Start reading**, **Pause reading** and **Resume reading**. It is disabled while capture starts, with **Cancel setup** available. Pause hides labels and stops reading; Resume keeps the same sharing session. The display selection is remembered, but a normal launch waits for Start reading. Sharing problems offer an explicit reconnect action.

Initial guidance appears inside Prices; the display selector and tab row remain fixed across pages. **Settings** contains overlay toggles, update interval, shortcut, optional always-on-top behavior and troubleshooting. **Connection details / capture preview…** displays the existing captured image and technical messages without starting another share.

**Ctrl+Alt+P** toggles reading/labels globally. Open **Settings → Keyboard shortcut…** to disable it or choose another key or combination, then select **Set hotkey**. The app uses Windows `RegisterHotKey` and its own message queue; it installs no keyboard hook and sends no game input. Reserved or conflicting combinations produce a clear message.

Inventory/equipment tooltip prices are enabled by default. Shop-row labels take priority while any player shop is open; inventory tooltip labels are suppressed throughout that context. The checkbox can disable hover pricing, and its state is saved. Equipment is assumed unscrolled.

Prices use a local MesoWatch Classic World snapshot, refreshed in the background on launch and hourly through an installed Chrome/Edge/Chromium. Saved data appears immediately; a missing browser or item uses NiaMeowDB's Classic World fallback, including NX/cash items. They are **meso resale references**, with NX retail costs kept separate. Fallback references are cached for 15 minutes by default; full-market references have a one-hour publication/check limit. Cards show Store price beside Market reference, the per-item/set unit, when the price was checked, snapshot publication age when applicable, and the latest market report age. **Details** expands source/fee information. Recognised items without coverage say **No market reports**, separately from unreadable names. A newly encountered item may need an online request. Duplicate names are narrowed using the source's current item IDs; unresolved variants are not guessed.

Minimize the control panel to keep only the labels. Closing it ends capture and the helper processes. For an offline package check, run **selftest-windows.bat** in the installation folder, normally `%LOCALAPPDATA%\Programs\Classic Price Lens`. This verifies real OCR and overlay IPC without capturing a screen or interacting with a game. The console prints each result and stays open.

Resource use is bounded: capture is capped where Qt supports it, frame queues apply backpressure, OCR skips unchanged shop pixels, known shops use a small read region, and the OCR worker uses two threads. Network requests are independent of the screen-reading rate. No telemetry or screenshot uploads.

Windows installation, upgrade, uninstall and the bundled binaries are tested under Wine. Native Windows desktop capture, mixed-DPI and fullscreen behavior still require validation. See `THIRD_PARTY.md` for component licenses and data attribution.

## Automatic reading area and tray behavior (0.4.0)

Automatic area detection defaults on. The bottom status bar's static LV label and border establish UI scale, centre and bottom. Visible window-caption pixels establish the window bounds; no window list, process lookup or game handle is used. A moved or hidden minimap does not change windowed bounds. The FPS counter is never an anchor. Borderless full-display bootstrapping can use visible minimap/frame corroboration; if the bounds cannot be established confidently, reading waits for a manual area instead of falling back to the entire monitor.

The OS still captures the selected display (or crops a shared workspace to it). Item OCR is limited to the located game area. Static anchor patches detect movement/coverage before drawing another label. Known status anchors avoid repeated global searches, and geometry is rechecked at a bounded interval even when shop pixels stay unchanged. An unseen/covered game produces no item-price requests. A manually selected area takes priority for that session. Reset it in the area-selection dialog to return to automatic detection.

Minimizing uses QSystemTrayIcon by default. The tray menu shares the panel's Start/Pause/Resume state and label setting, and provides Show panel, Settings and Quit. A minimize transition sends one OS notification; desktop notification preferences still apply. If the desktop reports no tray, the panel stays in the taskbar. Closing the panel and explicit Quit stop capture normally; minimizing preserves it. The app's user-only IPC also supports `--minimize` for a desktop shortcut or diagnostics, without keyboard simulation. Installer shutdown works while the panel is hidden.

Debian/Ubuntu packages depend on `pipewire-bin` to supply `/usr/share/pipewire/client.conf` (see the [Debian file list](https://packages.debian.org/bookworm/amd64/pipewire-bin/filelist)); the common translation package alone does not supply it. Distribution checks verify the file is present.

## Capture startup and overlay motion (0.4.1)

The panel, capture helper, annotation helper and offline self-test restrict Qt's plugin search to the running PySide installation before creating an application object. They override inherited `QT_PLUGIN_PATH` and discard `QT_QPA_PLATFORM_PLUGIN_PATH` in their own process environment only. Desktop-wide plugins compiled against another Qt version can otherwise shadow the bundled Wayland/multimedia plugins. No desktop configuration is changed. The self-test constructs a real media sink and supplies a synthetic local frame; it never starts OS capture. Local-helper connection attempts have a ten-second deadline that stops as soon as IPC connects, so the OS sharing chooser has no artificial consent deadline.

The annotation helper samples the ordinary OS pointer at roughly 60 Hz while an inventory card is visible, with a 100ms idle interval otherwise. It moves an identified card without another OCR result or HTTP lookup and invalidates only old/new card rectangles. Large cursor jumps or leaving the game hide the old reference immediately. Item OCR still uses bounded capture/recognition intervals. Main-panel card identity excludes tooltip position so pointer movement does not rebuild its widgets.

Qt animations provide 110ms fade-in, 90ms fade-out and 95ms shop-position easing. A disappearing card freezes at its last position while fading, and an old item does not crossfade over a newly identified one. Disabling labels or losing capture clears immediately. Shop hover detection uses the game pixels outside the list too; while native item details are open, row annotations are tucked away, and covered rows are omitted. A tooltip's reported area is its name line, not the full panel, so tall/engraved-item tooltips use the upstream 640px search extent. Catalog identity remains conservative; colon spacing is normalized, and a success percentage alone never chooses between Greater and Chaos scrolls.

## v0.7.0 interaction and lookup changes

EXP always starts stopped. Start tracking explicitly enables sampling; F11 starts, pauses or resumes. Stop saves and disables sampling. Percentage rates are the default, with raw or combined units available. Rates and ETA require 30 seconds of valid tracked time and use a five-minute window. Its optional readout is anchored to the game area's bottom-left and appears only for a started running or paused session. Map segments save automatically while the overall timer continues.

Price cards are persistent; tab, section and field transitions are short and interruptible. Reduce motion disables them and pauses the local Lupin sprite. Hidden headers also pause the sprite.

Obsolete direct HTTPS requests can be cancelled before they hold up a new page. A small daily public ID index extends only already-verified mappings, without renewing their provider-check timestamps or relaxing price TTLs. New identities still require source matching. A partially clipped shop crop is immediately retried on the full area. Source delay can still dominate a fully uncached page; no whole-market polling is introduced.

## Controls and desktop identity in v0.9.0

Prices includes local name search; Translation has its own tab. One display dropdown selects the capture display. Wayland screen-sharing consent remains an OS dialog. F10 toggles prices independently of EXP, F11 starts/pauses/resumes EXP, and F12 translates (F9 on Windows, whose RegisterHotKey API reserves F12). The top Hotkeys button and Settings edit the same assignments. Wayland binds all three actions in one GlobalShortcuts session. CLI equivalents are `lupin --prices`, `lupin --exp` and `lupin --translate`; `--toggle` pauses the complete reader.

Linux package metadata is `lupin`, replacing/conflicting with/providing `classic-price-lens`. Legacy install roots, application settings and portal/desktop IDs remain stable. The desktop icon has a new Lupin resource name so existing menu entries and pinned launchers resolve the approved icon after a desktop cache refresh.
