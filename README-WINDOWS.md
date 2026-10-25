# Classic Price Lens for Windows

Extract the whole portable ZIP, then double-click **run-windows.bat**. Python and Qt are included; no Python, Rust or Minerva installation is needed. Keep the `runtime`, `price_lens` and `bin` folders together.

Select the monitor containing MapleStory Classic World in the control panel. Windows captures that monitor with Qt's OS screen-capture backend. The overlay draws item names and meso references in its own transparent, click-through window. It does not attach to the game or access its process, memory, renderer, files, packets, messages or inputs.

Inventory/equipment tooltip prices are enabled by default. Shop-row labels take priority when the pointer is over a shop listing; generic inventory tooltip labels are suppressed there. The checkbox can disable hover pricing, and its state is saved. Equipment is assumed unscrolled.

Prices come from NiaMeowDB's Classic World data, including NX/cash items. They are **meso resale references**, with NX retail costs kept separate. References are cached for 15 minutes by default; the panel shows cache and report ages. A newly encountered item may need an online request. Duplicate names are narrowed using the source's current item IDs; unresolved variants are not guessed.

Minimize the control panel to keep only the labels. Closing it ends capture and the helper processes. Run **selftest-windows.bat** for an offline OCR/package check that does not capture a screen or interact with a game.

Resource use is bounded: capture is capped where Qt supports it, frame queues apply backpressure, OCR skips unchanged shop pixels, known shops use a small read region, and the OCR worker uses two threads. Network requests are independent of the screen-reading rate. No telemetry or screenshot uploads.

This build targets **Windows 10/11 x64**. Real Windows desktop capture, mixed DPI and fullscreen behavior still need a Windows playtest; the verification file distinguishes local Windows-binary tests from native Windows acceptance. See `THIRD_PARTY.md` for component licenses and data attribution.
