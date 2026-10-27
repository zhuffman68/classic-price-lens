# Lupin for Windows

**Tools for MapleStory Classic World.** Market prices, item search with images, EXP tracking and local Korean translation in both directions.

1. Download the Windows installer from [itch.io](https://zhuffman68.itch.io/lupin) and extract it if wrapped in a ZIP.
2. Run **Lupin-0.10.0-Windows-x64-Setup.exe**, then open Lupin from Start. Administrator access is not required.
3. Choose the game's display and click **Start reading**. Keep its bottom status bar visible.

Requires Windows 10/11 x64, about **3 GB free space** for installation, and internet for market updates and uncached item images. Python, Qt, OCR and both translation models are included. Edge, Chrome or Chromium enables the launch/hourly full-market cache; individual lookups work without a compatible browser.

**F8** opens the Korean writer. **F10** toggles prices. **F11** starts EXP tracking, then pauses/resumes it. **F9** translates Korean bubbles: Windows reserves F12, so it cannot be a global shortcut. Use **Hotkeys…** to change assignments.

EXP starts stopped. Press **Start tracking** on EXP Tracking; rates and ETA appear after 30 seconds of valid tracking. The bottom-left tracker has its own visible checkbox. Search is at the top of Prices and needs no screen sharing.

Translation has **Read Korean** and **Write Korean** pages. F8 opens a compact writer without screen sharing: type English and press Enter to translate and copy. A notification confirms the copy; paste with Ctrl+V and send yourself. Nothing sends input to the game. Common trade/party shorthand is expanded, known item names are retained, and numeric values/percentages are checked. Review freeform translations before pasting. Both models run locally, without a cloud account or API key.

Minimize sends the panel to the tray by default. Click its icon to restore, or right-click for controls. Close or Quit ends reading and sharing.

For the portable version, extract the ZIP fully and open **run-windows.bat**. Close an older portable copy before switching to the installer. Updates preserve settings, prices and history. Uninstall through **Settings → Apps**. The installation folder includes **selftest-windows.bat** for an offline check.

Windows installer checks run under Wine. Live native Windows capture, mixed-DPI alignment and Korean paste in the game still need a Windows playtest.

[Everyday use and troubleshooting](README.md) · [Technical details](docs/TECHNICAL.md) · [Credits](THIRD_PARTY.md)
