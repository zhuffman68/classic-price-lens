# Lupin for Windows

1. Download the **Windows installer** from [itch.io](https://zhuffman68.itch.io/lupin). Extract the download ZIP and run **Lupin-0.7.0-Windows-x64-Setup.exe**. Repository collaborators can also download the Setup file directly from [GitHub Releases](https://github.com/zhuffman68/lupin/releases).
2. Run it, then open **Lupin** from Start. Administrator access is not needed.
3. Choose the display containing Classic World and click **Start reading**. Approve sharing if prompted.
4. Keep the bottom status bar visible. The app finds the game area automatically. Open a shop or hover an inventory/equipment item to see meso references.

You'll need **Windows 10/11 x64**, about **1 GB free space**, and internet for price updates. Python, Qt and OCR are included. Edge, Chrome or Chromium enables the launch/hourly full-market cache; without a compatible browser, individual price lookups remain available.

EXP watching starts automatically. Settings can switch its bottom-left overlay between percentage (default), raw EXP, or both. Player shops always take precedence over inventory hover prices.

Minimize the panel to put it in the system tray. A notification confirms it; click the icon to restore the panel, or right-click for controls. Closing the panel or choosing **Quit** ends reading and sharing. Tray behavior and automatic detection can be changed in **Settings**.

**Ctrl+Alt+P** pauses/resumes reading. Change it under **Settings → Keyboard shortcut…**.

For the portable version, extract the ZIP fully and open **run-windows.bat**. Close an older portable copy before switching to the installer. Updates keep settings and cached prices.

Uninstall through **Settings → Apps**. For an offline installation check, run **selftest-windows.bat** from the installation folder.

Windows installer checks run under Wine. Live native Windows capture and mixed-DPI alignment still need a Windows playtest.

[Everyday use and troubleshooting](README.md) · [Technical details](docs/TECHNICAL.md) · [Credits](THIRD_PARTY.md)
