<p align="center"><img src="price_lens/resources/icon-64.png" width="48" height="48" alt="Lupin icon"> <img src="price_lens/resources/lupin.gif" width="73" height="64" alt="Animated Lupin"> <img src="price_lens/resources/wordmark.svg" width="122" height="45" alt="Lupin"></p>

# Lupin

**Tools for MapleStory Classic World.**

- Market prices beside shop, inventory and equipment items, including cash/NX resale prices.
- Item search with a shared local price cache and clear price ages.
- EXP tracking with percentage per minute/hour, a session timer, level-up ETA and saved history.
- Local Korean speech-bubble translation with the original text alongside English.

Lupin reads OS-shared screen pixels and draws separate, click-through labels. It never hooks into the game. Screenshots and translations stay on your device. Equipment prices assume unscrolled items.

## Download and install

Download from **[itch.io](https://zhuffman68.itch.io/lupin)**. Repository collaborators can also use [GitHub Releases](https://github.com/zhuffman68/lupin/releases).

| System | Download | Install |
| --- | --- | --- |
| Windows 10/11 x64 | `Windows-x64-Setup.exe` | Run it, then open Lupin from Start. |
| Arch / Manjaro | `.pkg.tar.zst` | `sudo pacman -U ./lupin-0.9.0-1-x86_64.pkg.tar.zst` |
| Debian 12+ / Ubuntu 22.04+ | `.deb` | `sudo apt install ./lupin_0.9.0-1_amd64.deb` |

Extract itch.io downloads before running an installer or package command. A Windows portable ZIP is also available: extract it fully and open `run-windows.bat`.

Requirements: a supported 64-bit desktop, about **2 GB free space**, and internet for market updates. Python, Qt, OCR and local translation models are included. **Chrome, Edge or Chromium** enables the full-market cache; individual lookups work without it. Linux screen sharing needs PipeWire and a working desktop sharing portal, normally provided by KDE or GNOME.

Updates preserve settings, prices and history. Linux packages are now named `lupin` and replace `classic-price-lens`.

## Get started

1. Choose the display containing Classic World and click **Start reading**. Approve OS screen sharing if prompted.
2. Keep the game's bottom status bar visible. Lupin finds the game area automatically.
3. Open a shop or hover an inventory/equipment item to see market references. Search by name at the top of **Prices**; search works without sharing.
4. Open **EXP Tracking** and press **Start tracking** when ready. Tracking always begins stopped when the app opens.
5. Open **Translation** to enable local Korean translation, then press its shortcut near a speech bubble.

| Shortcut | Action |
| --- | --- |
| **F10** | Toggle prices. EXP tracking continues. |
| **F11** | Start EXP tracking, then pause/resume it. |
| **F12** | Translate visible Korean speech bubbles. **F9 on Windows**, where F12 is reserved. |

Change shortcuts with **Hotkeys…** beside Pause/Resume or in Settings. Wayland uses the desktop's shortcut chooser. **Pause reading** pauses the shared reader; **Minimize** sends the panel to the tray by default. Right-click the tray icon for controls. **Close / Quit** ends sharing.

## Prices and EXP

Shop labels show names, market references, colored comparisons and price ages. Shop listings take precedence over inventory hover cards. Labels overlapping the game's item-description tooltip become faint and return when it closes.

The full market refreshes in the background on launch and hourly. Missing items use individual lookups, cached for 15 minutes by default. Saved data remains visible during refreshes. Price-check time, market-report age and snapshot age are separate; old or thin data receive no deal rating. References are guides, not guaranteed sales.

EXP gain and elapsed time appear immediately. Rates and ETA need **30 seconds of valid tracked time** to estimate a pace, then use a recent five-minute average. Pause excludes breaks; Stop saves the run and turns off EXP reading. Map segments save automatically. **Show tracker in game** controls the bottom-left overlay and is also available in Settings. Percentage is the default; Settings offers raw EXP or both. History stays local and exports to CSV.

## Help

- **Game not found:** uncover the bottom status bar or use **Settings → Limit the reading area…**.
- **Sharing stopped or labels misaligned:** use **Reconnect display** and share the selected display or full workspace.
- **No market reports:** the name was recognized, but the source has no usable price.
- **Translation found nothing:** keep the bubble visible and press its shortcut nearby. Moving bubbles and expanded chat history are not supported yet.

Connection details and capture preview are in Settings. Windows installers are checked under Wine; live native Windows capture and mixed-DPI alignment still need a Windows playtest.

[Windows help](README-WINDOWS.md) · [Translation](docs/KOREAN_CHAT.md) · [Architecture](ARCHITECTURE.md) · [Technical details](docs/TECHNICAL.md) · [Building installers](packaging/README.md) · [Validation](VERIFICATION.md) · [Credits](THIRD_PARTY.md)
