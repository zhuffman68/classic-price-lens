# Lupin for Windows

**Tools for MapleStory Classic World.** Market prices, item search with images, EXP/meso tracking and local Korean translation in both directions.

1. Download the Windows installer from [itch.io](https://zhuffman68.itch.io/lupin) and extract it if wrapped in a ZIP.
2. Run **Lupin-0.16.0-Windows-x64-Setup.exe**, then open Lupin from Start. Administrator access is not required.
3. Choose the game's display and click **Start reading**. A real display is preselected. Keep the game's bottom status bar visible.

Requires Windows 10/11 x64, about **3 GB free space** for installation, and internet for market updates and uncached item images. Python, Qt, OCR and both translation models are included. A browser installation is not required. Setup prepares the shared WebView2 runtime when needed; the first installation may need an internet connection. The full market refreshes on launch and at the interval selected in Settings. No individual price lookups are made.

**Win + F8** opens the Korean writer. **Win + F9** toggles prices. **Win + F10** starts EXP/meso tracking, then pauses/resumes it. **Win + F11** scans the game window for Korean text. Use **Hotkeys…** to change assignments.

EXP starts stopped. Press **Start tracking** on EXP/Meso Tracking; rates need 30 seconds of clear EXP readings, and a positive pace also produces a level-up ETA. Covered/rejected readings can extend the warmup. The overlay's **Last 5 min** label means its rolling pace window; the timer shows session time. EXP and meso cards stack beside the status bar, with large gain totals and separate visibility checkboxes on the tracking page and in Settings. Numbers update together every two seconds. Meso rates average the active session. Pausing freezes the displayed ETA and retains the original character when another client is visible. Meso gain counts readable pickup messages; purchases, trades and potion costs are excluded. Keep the bottom-right pickup log visible. Pausing screen reading holds tracking, while the Prices shortcut remains independent. Inventory hover pricing also works with an NPC vendor open. Search is at the top of Prices and needs no screen sharing. The main window remembers its size.

Translation has **Read Korean** and **Write Korean** pages. Win + F8 opens a compact writer without screen sharing: type English and press Enter to translate and copy. A notification confirms the copy; paste with Ctrl+V and send yourself. Nothing sends input to the game. Common trade/party shorthand is expanded, known item names are retained, and numeric values/percentages are checked. Review freeform translations before pasting. Both models run locally, without a cloud account or API key.

Choose an item’s **☆** star to watch it. **Watched items** on Prices shows thumbnails and cached references, with three rows before scrolling. Click a row for its price card, click it again to deselect, or collapse the list to return to shop prices. Recognized watched items are highlighted in the game and retain a star. Reduced motion keeps the marker steady.

The panel resizes and remembers its size; maximizing is disabled. Minimize sends it to the tray by default. Click its icon to restore, or right-click for controls. Close or Quit ends reading and sharing.

For the portable version, extract the ZIP fully and open **run-windows.bat**. Its launcher also prepares WebView2 when needed. Close an older portable copy before switching to the installer. Updates preserve settings, prices and history. Uninstall through **Settings → Apps**. The installation folder includes **selftest-windows.bat** for an offline check.

Windows uses its native certificate trust for market connections. A temporary connection failure gets one automatic catalog retry; persistent failures show their cause. Certificate checking remains enabled.

Display capture and a running Classic World shop are verified in a Windows VM. Physical-PC capture, mixed-DPI alignment and Korean paste still need a physical Windows playtest.

[Everyday use and troubleshooting](README.md) · [Technical details](docs/TECHNICAL.md) · [Credits](THIRD_PARTY.md)
