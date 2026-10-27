# Lupin for Windows

**Tools for MapleStory Classic World.** Market prices, item search, EXP tracking and local Korean speech-bubble translation.

1. Download the Windows installer from [itch.io](https://zhuffman68.itch.io/lupin) and extract it if wrapped in a ZIP.
2. Run **Lupin-0.9.0-Windows-x64-Setup.exe**, then open Lupin from Start. Administrator access is not required.
3. Choose the game's display and click **Start reading**. Keep its bottom status bar visible.

Requires Windows 10/11 x64, about **2 GB free space**, and internet for market updates. Python, Qt, OCR and translation models are included. Edge, Chrome or Chromium enables the launch/hourly full-market cache; individual lookups work without a compatible browser.

**F10** toggles prices. **F11** starts EXP tracking, then pauses/resumes it. **F9** translates Korean bubbles: Windows reserves F12, so it cannot be a global shortcut. Use **Hotkeys…** to change assignments.

EXP starts stopped. Press **Start tracking** on EXP Tracking; rates and ETA appear after 30 seconds of valid tracking. The bottom-left tracker has its own visible checkbox. Search is at the top of Prices and needs no screen sharing. Translation has a separate page and works offline after enabling it.

Minimize sends the panel to the tray by default. Click its icon to restore, or right-click for controls. Close or Quit ends reading and sharing.

For the portable version, extract the ZIP fully and open **run-windows.bat**. Close an older portable copy before switching to the installer. Updates preserve settings, prices and history. Uninstall through **Settings → Apps**. The installation folder includes **selftest-windows.bat** for an offline check.

Windows installer checks run under Wine. Live native Windows capture and mixed-DPI alignment still need a Windows playtest.

[Everyday use and troubleshooting](README.md) · [Technical details](docs/TECHNICAL.md) · [Credits](THIRD_PARTY.md)
