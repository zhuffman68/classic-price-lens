# Classic Price Lens for Windows

Download **ClassicPriceLens-0.3.0-Windows-x64-Setup.exe** from [GitHub Releases](https://github.com/zhuffman68/classic-price-lens/releases). Run it, then launch **Classic Price Lens** from Start. The installer adds an optional desktop shortcut and an entry in **Settings → Apps** for uninstalling. It installs for the current user and does not need administrator access. It adds no background service, driver or login startup task.

Prerequisites: **Windows 10/11 x64**, about **1 GB free space** including the installer, and internet for price refreshes. Python, Qt and the OCR executable are included; no separate Python, Rust, Minerva or API key is needed. Live native Windows capture remains a preview until tested on Windows hardware.

Updates install over the existing version and ask only this app to close through its own local IPC connection. Settings and price-cache files are kept. A second launch activates the existing panel. Close an older portable copy before switching to the installer.

The portable ZIP remains an alternative: extract it completely, then double-click **run-windows.bat**. Keep the `runtime`, `price_lens` and `bin` folders together.

Choose the display containing MapleStory Classic World using the numbered arrangement or list, then click **Start reading**. Approve OS sharing if a chooser appears. Open a player shop or hover over an inventory/equipment item. Windows captures the selected display with Qt's OS screen-capture backend. The overlay draws item names and meso references in its own transparent, click-through window. It does not attach to the game or access its process, memory, renderer, files, packets, messages or inputs.

The primary button starts disabled until a display is selected, then changes between **Start reading**, **Pause reading** and **Resume reading**. It is disabled while capture starts, with **Cancel setup** available. Pause hides labels and stops reading; Resume keeps the same sharing session. The display selection is remembered, but a normal launch waits for Start reading. Sharing problems offer an explicit reconnect action.

**Preview with examples** shows clearly marked, made-up values without sharing a screen or requesting item prices. **Setup help** repeats the three steps. **Settings** contains overlay toggles, update interval, shortcut, optional always-on-top behavior and troubleshooting. **Connection details / capture preview…** displays the existing captured image and technical messages without starting another share.

**Ctrl+Alt+P** toggles reading/labels globally. Open **Settings → Keyboard shortcut…** to disable it or choose another key or combination, then select **Set hotkey**. The app uses Windows `RegisterHotKey` and its own message queue; it installs no keyboard hook and sends no game input. Reserved or conflicting combinations produce a clear message.

Inventory/equipment tooltip prices are enabled by default. Shop-row labels take priority when the pointer is over a shop listing; generic inventory tooltip labels are suppressed there. The checkbox can disable hover pricing, and its state is saved. Equipment is assumed unscrolled.

Prices come from NiaMeowDB's Classic World data, including NX/cash items. They are **meso resale references**, with NX retail costs kept separate. References are cached for 15 minutes by default. Cards show Store price beside Market reference, the per-item/set unit, when the price was checked and the latest market report age. **Details** expands source/fee information. Recognised items without coverage say **No market reports**, separately from unreadable names. A newly encountered item may need an online request. Duplicate names are narrowed using the source's current item IDs; unresolved variants are not guessed.

Minimize the control panel to keep only the labels. Closing it ends capture and the helper processes. For an offline package check, run **selftest-windows.bat** in the installation folder, normally `%LOCALAPPDATA%\Programs\Classic Price Lens`. This verifies real OCR and overlay IPC without capturing a screen or interacting with a game. The console prints each result and stays open.

Resource use is bounded: capture is capped where Qt supports it, frame queues apply backpressure, OCR skips unchanged shop pixels, known shops use a small read region, and the OCR worker uses two threads. Network requests are independent of the screen-reading rate. No telemetry or screenshot uploads.

Windows installation, upgrade, uninstall and the bundled binaries are tested under Wine. Native Windows desktop capture, mixed-DPI and fullscreen behavior still require validation. See `THIRD_PARTY.md` for component licenses and data attribution.
