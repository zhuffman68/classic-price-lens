# Classic Price Lens

A screen-only market-price companion for **MapleStory Classic World**.

It reads visible player-shop listings from OS screenshots, looks up a market reference, and draws a small item name and price beside each row in an independent, transparent, click-through window. A separate control panel shows the details. You open shops and scroll yourself.

## Install

Download an unencrypted installer/package from [GitHub Releases](https://github.com/zhuffman68/classic-price-lens/releases). **Python, Qt and the OCR reader are included.** Python, Rust, Minerva, an AI account and API keys are not prerequisites for installed builds.

| System | Download | Installation |
| --- | --- | --- |
| Windows 10/11 x64 | `ClassicPriceLens-0.2.0-Windows-x64-Setup.exe` | Run the installer, then open **Classic Price Lens** from Start. Installs for the current user without administrator access. |
| Arch / Manjaro x86_64 | `classic-price-lens-0.2.0-1-x86_64.pkg.tar.zst` | `sudo pacman -U ./classic-price-lens-0.2.0-1-x86_64.pkg.tar.zst` |
| Debian 12+ / Ubuntu 22.04+ amd64 | `classic-price-lens_0.2.0-1_amd64.deb` | `sudo apt install ./classic-price-lens_0.2.0-1_amd64.deb` |

Prerequisites: a supported 64-bit desktop system, about **1 GB free space** including the download, and internet for market-price updates. Linux package managers install the OS library dependencies. Wayland requires PipeWire, XWayland, and a working screen-sharing portal backend matching the desktop, such as `xdg-desktop-portal-kde` or `xdg-desktop-portal-gnome`. KDE Plasma and GNOME desktop installations normally provide one. No service, driver or login startup task is added.

On Linux, open **Classic Price Lens** from the application menu or run `classic-price-lens`. On Windows, use the Start-menu shortcut. Select the monitor containing Classic World and approve the OS screen-sharing picker when shown. Inventory/equipment tooltip prices start enabled. [Windows details and portable alternative](README-WINDOWS.md).

The single capture button changes between **Start**, **Pause** and **Resume**. It stays gray until a valid monitor is selected, and shows **Starting…** until frames arrive. The selected monitor is remembered. Pause hides the overlay and stops OCR/price refreshes; Resume reuses the same sharing session, avoiding another sharing picker. Supported capture backends reduce their frame rate while paused.

Use **Hotkey…** to enable/disable the global shortcut and choose a key or key combination. Windows and X11 default to **Ctrl+Alt+P**. Wayland uses the desktop's shortcut chooser, requested through that button; after the desktop confirms a binding it is remembered. On older Wayland desktops without the GlobalShortcuts portal, create a system keyboard shortcut running `classic-price-lens --toggle`. Hotkeys use OS registration, never a keyboard hook or game attachment.

For an offline installation check on Linux:

```bash
classic-price-lens --self-test
```

This reads a bundled test image and checks the separate overlay process, without capturing a desktop. Installed builds support `--version`, `--toggle` and `--quit`; a second normal launch activates the existing panel. Windows installation/upgrade/removal controls only the app's own local IPC connection. Close an older portable copy before switching to the installed version. User settings and cached prices are kept during upgrades and removal.

Uninstall through **Settings → Apps** on Windows, `sudo pacman -R classic-price-lens` on Arch/Manjaro, or `sudo apt remove classic-price-lens` on Debian/Ubuntu.

Linux packages are checked in isolated Debian 12 and Ubuntu 22.04 filesystems and with pacman. Windows install, upgrade, uninstall and offline checks run under Wine; live native Windows capture, alignment and mixed-DPI behavior still need a Windows playtest. See [VERIFICATION.md](VERIFICATION.md) for the exact validation boundary.

## Use

In KDE's screen-sharing picker, share the selected monitor or the full workspace; full-workspace frames are cropped locally to the selected monitor. Only one OS sharing session stays open, and the control panel can reuse it across UI handoffs. Closing the panel normally ends sharing and its helpers. Minimize the panel to leave just the labels.

The streaming path reads new frames immediately, with bounded buffers and no queue of old screenshots. Prices already in the cache appear without network access. A first lookup for an unseen item still depends on the provider's response time. The panel displays the measured reading delay separately from price age.

**Inventory / equipment tooltip prices** is a persistent checkbox, **on by default**. It shows the matched name and meso reference above the game's visible tooltip, including items in inventory and equipment. Shop-row labels take priority while the pointer is on a shop listing; a duplicate inventory label is suppressed there. It reads tooltip pixels and the OS pointer position, with no mouse hook or input injection. Tooltip OCR stops when the checkbox is off. Equipment is assumed unscrolled.

**KDE capture** is a slower fallback using ordinary Spectacle screenshots, one at a time, with uncompressed temporary BMPs instead of PNG compression. **Crop** selects pixels in the capture preview. **Open screenshot** is a clearly marked offline mode and draws no labels over the live game.

Labels contain the matched item name in small type, the reference price, percentage versus that reference, and cache age. Equipment is assumed **unscrolled** and receives the same comparisons as other items. Actual stats, upgrades and remaining slots are not read. The assumption is stated once in the panel instead of repeated on each label. For items with fewer than five reference samples, it says `thin data`. The panel gives the source, window, sample count, latest report time, and exact cache expiration.

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
- Default prices: [NiaMeowDB Classic World](https://meowdb.com/msclassic/free-market), fetched **on demand for visible, uniquely identified items**. The provider ID is matched using both the exact name and game item ID (`iconKey`); its database row IDs differ from game IDs.
- Uses the site's **24-hour median** with at least five samples; otherwise its explicitly labeled longer-window `usual` reference. These are reported prices (asking and sold), not guaranteed completed trades. A daily median with fewer than five samples can be displayed when no longer-window reference exists, clearly marked as thin data. The request asks for clean condition.
- Cache lifetime defaults to **15 minutes**, adjustable to 5/30/60. Up to three background requests handle new items, with duplicates coalesced. Fresh quotes and item-name lookups stay in memory during scanning; disk caching survives restarts; failed requests use a cooldown and never reset the age of an existing quote. Successful empty, unsupported-item and old-data responses respect the full cache TTL instead of triggering repeated requests. Cache expiry immediately removes the deal rating. Latest reports older than 24 hours, or missing report times, also prevent a rating.
- Prices show **cache age and report age separately**. Rechecking an old report does not make the market observation new. At most 6,000 cached records are retained; records older than seven days are removed on startup. Empty, old-report and source-unsupported responses retain their HTTP cache TTL; they do not get fetched again on every screen read.
- `Below reference` starts at 20% under, `Above reference` over 20% above, otherwise `Near reference`. These are comparison bands, not profitable-flip guarantees. Potential resale margin uses a **3% sale fee**. Listing quantities are normalized for ordinary items; stars/bullets are priced per set, never per projectile.
- Duplicate item names are resolved against the provider's current Classic catalog. A reference is selected only when one matching candidate ID remains; multiple current matches stay explicitly ambiguous. The source's database ID is still validated against the game ID.
- NX retail costs are shown separately in the panel when supplied by the cash catalog. **Overlay FM values are mesos, not NX.** Retail cost is never substituted for a market reference.

Resource controls: frames use local uncompressed RGBA instead of PNG encode/decode, local frame buffers provide backpressure, unchanged shop pixels skip OCR, known shops are read from a small capture region, and a moved shop triggers a full search immediately. The UI rebuilds item cards only when their content changes or ages tick. Rust/OCR uses at most two worker threads; network requests are deduplicated and time-limited. SQLite connections close after each operation. No full-market polling at the screen-reading rate.

The cache and bounded capture log use Qt's standard per-user cache directory. On Linux, the default is typically `~/.cache/LocalTools/Classic Price Lens/`. `--cache /path/prices.sqlite` selects another price-cache location. Installed files remain separate from settings, logs and prices; normal use does not require administrator access.

## Build / other systems

Source builds require Python 3.11+, Rust 1.90+, Git, and PySide6/Qt Multimedia. No AI account or API key is needed. From a repository checkout on Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./setup.sh
./run.sh --capture
```

The reader uses Minerva's MIT headless core, pinned at `7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`. `setup.sh` clones this revision if missing and builds the OCR helper and headless core. Rust build concurrency is limited to two jobs. The OCR model is bundled by upstream; see [THIRD_PARTY.md](THIRD_PARTY.md).

For a Windows source build, run `setup-windows.ps1` followed by `run-windows.bat`. To build the native installer/package formats, see [packaging/README.md](packaging/README.md).

macOS remains untested. The intended capture path uses Qt's OS screen capture through the same local helper (`python -m price_lens --capture`), with screen-recording permission on macOS. KDE/Spectacle and XWayland are Linux-specific adapters.

## Checks

```bash
python -m unittest discover -s tests -v
cargo check --locked --manifest-path reader/Cargo.toml -j 2
```

Tests cover item-ID matching, ambiguous names, narrow y/v glyph correction, scroll tiers, bundle versus set pricing, fee calculations, cache expiry, request counting for parked items, unsupported-item 400 responses, failed refreshes, original import age, wrong-world rejection, and upstream OCR fixtures. Capture diagnostics and calibration images are excluded from source control and release packages.

## Limits

Only visible shop rows and enabled tooltips are read; no automated browsing or purchases. Sold rows are omitted, not counted as a source price. Ambiguous names/tiers stay unknown. Tooltip OCR can fail on particular glyphs/fonts; unmatched names stay unknown. The current price source can lag or contain outliers; equipment comparisons assume unscrolled items and do not distinguish individual stat rolls. Labels cover some adjacent game UI/chat; they are mouse-transparent. With screen capture, covering the listing hides it from OCR, as expected. Multiple simultaneous shops, mixed DPI displays, fullscreen-exclusive games, and other operating systems require further testing.
