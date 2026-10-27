<p align="center"><img src="price_lens/resources/icon-64.png" width="48" height="48" alt="Lupin icon"> <img src="price_lens/resources/lupin.gif" width="73" height="64" alt="Animated Lupin"> <img src="price_lens/resources/wordmark.svg" width="122" height="45" alt="Lupin"></p>

# Lupin

**Tools for MapleStory Classic World.**

- Market prices beside shop, inventory and equipment items, including cash/NX resale prices.
- Item search with item images, a shared local price cache and clear price ages.
- EXP and meso tracking with live rates, a session timer, level-up ETA and saved history.
- Local Korean translation: read Korean messages in English, or write a Korean reply and copy it to paste yourself.

Lupin reads OS-shared screen pixels and draws separate, click-through labels. It never hooks into the game. Screenshots and translations stay on your device. Equipment prices assume unscrolled items.

## Download and install

Download from **[itch.io](https://zhuffman68.itch.io/lupin)**. Repository collaborators can also use [GitHub Releases](https://github.com/zhuffman68/lupin/releases).

| System | Download | Install |
| --- | --- | --- |
| Windows 10/11 x64 | `Windows-x64-Setup.exe` | Run it, then open Lupin from Start. |
| Arch / Manjaro | `.pkg.tar.zst` | `sudo pacman -U ./lupin-0.12.0-1-x86_64.pkg.tar.zst` |
| Debian 12+ / Ubuntu 22.04+ | `.deb` | `sudo apt install ./lupin_0.12.0-1_amd64.deb` |

Extract itch.io downloads before running an installer or package command. A Windows portable ZIP is also available: extract it fully and open `run-windows.bat`.

Requirements: a supported 64-bit desktop, about **3 GB free space** for installation, and internet for market updates and uncached item images. Python, Qt, OCR and local translation models are included. **Chrome, Edge or Chromium** enables the full-market cache; individual lookups work without it. Linux screen sharing needs PipeWire and a working desktop sharing portal, normally provided by KDE or GNOME.

Updates preserve settings, prices and history. Linux packages are now named `lupin` and replace `classic-price-lens`.

## Get started

1. Choose the display containing Classic World and click **Start reading**. Approve OS screen sharing if prompted.
2. Keep the game's bottom status bar visible. Lupin finds the game area automatically.
3. Open a shop or hover an inventory/equipment item to see market references. Search by name at the top of **Prices**; search works without sharing.
4. Open **EXP/Meso Tracking** and press **Start tracking** when ready. Tracking always begins stopped when the app opens.
5. Open **Translation → Read Korean** to scan the game window, or **Write Korean** to translate an English draft and copy it. Writing needs no screen sharing.

| Shortcut | Action |
| --- | --- |
| **Super/Win + F8** | Open the Korean writer. Enter translates and copies; paste and send yourself. |
| **Super/Win + F9** | Toggle prices. Tracking continues. |
| **Super/Win + F10** | Start EXP/meso tracking, then pause/resume it. |
| **Super/Win + F11** | Scan the game window for Korean text. Press again to restart the scan. |

Change shortcuts with **Hotkeys…** below Settings, or Settings. The active shortcut is also shown at the bottom of each tab. Wayland uses the desktop's shortcut chooser. **Pause reading** pauses the shared reader; **Minimize** sends the panel to the tray by default. Right-click the tray icon for controls. **Close / Quit** ends sharing.

## Prices and tracking

Shop labels show names, market references, colored comparisons and price ages. Inventory cards also work while a shop is open; hovering a shop listing uses its row label. Labels overlapping the game's item-description tooltip become faint and return when it closes.

The full market refreshes in the background on launch and hourly. Missing items use individual lookups, cached for 15 minutes by default. Saved data remains visible during refreshes. Price-check time, market-report age and snapshot age are separate; old or thin data receive no deal rating. References are guides, not guaranteed sales.

EXP gain and the shared session timer appear immediately. Rates and ETA need **30 seconds of valid tracked time** to estimate a pace, then use a recent five-minute average. Pause excludes breaks; Stop saves the run and turns off tracking. Map segments save automatically. **Show tracker in game** controls the bottom-left overlay and is also available in Settings. Percentage is the default; Settings offers raw EXP or both. History stays local and exports to CSV.

Meso tracking reads the **wallet in the item inventory**. Keep it visible for live rates, or reopen it periodically to update net change; hidden readings show their age. New balances need two matching screen reads. Purchases, sales and trades count toward net change. Potions already carried and unsold loot are not valued as profit. Pause excludes wallet changes during the break.

The window remembers its last size; the default and minimum width are both 460 pixels. The first-launch layout fits normal controls on a standard desktop; long results and history can scroll.

## Korean replies

Press **Super/Win + F8**, type an English message, then press **Enter** or **Translate & Copy**. A notification confirms the copy. Open chat and paste with **Ctrl+V** when ready; Lupin never pastes, sends or controls the game. Both translation directions work offline with the included models. Incoming scans last four seconds by default; popups stay while their source is visible, then for another 1.5 seconds. Both timings are adjustable in Translation.

Common trade and party shorthand such as `WTS`, `WTB`, `pmo`, `ea` and `LF1M` is recognized. Known item names stay in English. Explicit prices and percentages are checked before copying: `250` stays `250`, `250k` stays `250k`, and `2.5m` stays `2.5m`. Review the preview, especially for unusual slang or freeform sentences.

## Help

- **Game not found:** uncover the bottom status bar or use **Settings → Limit the reading area…**.
- **Sharing stopped or labels misaligned:** use **Reconnect display** and share the selected display or full workspace.
- **No market reports:** the name was recognized, but the source has no usable price.
- **Translation found nothing:** keep the game text visible and try another scan. The pointer position does not limit scanning. Scan duration and the delay after text disappears are configurable under Translation.

Connection details and capture preview are in Settings. Windows installers are checked under Wine; live native Windows capture and mixed-DPI alignment still need a Windows playtest.

[Windows help](README-WINDOWS.md) · [Translation](docs/KOREAN_CHAT.md) · [Architecture](ARCHITECTURE.md) · [Technical details](docs/TECHNICAL.md) · [Building installers](packaging/README.md) · [Validation](VERIFICATION.md) · [Credits](THIRD_PARTY.md)
