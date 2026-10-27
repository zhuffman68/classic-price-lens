<p align="center"><img src="price_lens/resources/lupin.webp" width="67" height="55" alt="Animated Lupin"> <img src="price_lens/resources/wordmark.svg" width="159" height="84" alt="Lupin"></p>

# Lupin

Market prices beside your **MapleStory Classic World** items.

Previously named Classic Price Lens. Updates keep your settings and saved history.

Open a player shop or hover over an inventory/equipment item to see its name and a market-price reference. Prices include cash/NX items and are shown in **mesos**. Equipment is treated as unscrolled.

Watch EXP gain, percentage per minute/hour, and estimated time to level automatically. Switch to raw EXP or both in Settings. Training history stays on your device and can be exported to CSV.

The app reads shared screen pixels and draws separate, click-through labels. It never hooks into the game. Screenshots stay on your device.

## Download and install

Get the latest files from **[itch.io](https://zhuffman68.itch.io/lupin)**. Repository collaborators can also use [GitHub Releases](https://github.com/zhuffman68/lupin/releases).

| System | Choose | Install |
| --- | --- | --- |
| Windows 10/11 x64 | `Windows-x64-Setup.exe` | Run it, then open Lupin from Start. |
| Arch / Manjaro | `.pkg.tar.zst` | `sudo pacman -U ./lupin-0.7.0-1-x86_64.pkg.tar.zst` |
| Debian 12+ / Ubuntu 22.04+ | `.deb` | `sudo apt install ./lupin_0.7.0-1_amd64.deb` |

You'll need a supported 64-bit desktop, about **1 GB free space**, and internet for price updates. Python, Qt and the reader are included. **Chrome, Edge or Chromium** enables the full-market cache; otherwise prices use individual lookups. Linux screen sharing needs PipeWire and a working desktop sharing portal; KDE and GNOME normally provide them.

A portable Windows ZIP is also available: extract it fully and open `run-windows.bat`.

## Get started

1. Open Lupin and choose the display containing the game.
2. Click **Start reading** and approve screen sharing if prompted.
3. Keep the bottom status bar visible. The app finds the game area automatically and follows it when it moves. Moving or closing the minimap is fine.
4. Open a shop or hover an item. Minimize the panel when you're ready.

Use **Search** to look up an item by name, including NX items. Select a result to check its meso price. Search works without screen sharing and shares the overlay's saved price cache.

**EXP watching starts automatically** once the character and EXP bar are readable. The page shows elapsed tracking time, gain, rates per minute/hour and time to next level. Rates settle after 30 seconds and use a recent smoothed average. **Pause watching** excludes a break; **Reset session** saves the current run and starts fresh. Map changes save history segments and watching continues. Optional labels and notes are in **Session options**.

The EXP overlay sits inside the game's bottom-left corner. **Settings → EXP rate display** chooses percentage (default), raw EXP, or both with percentage first. Its overlay can be disabled separately. Paused or unreadable stretches are excluded; standing still counts. Progress carries across level-ups; inferred raw EXP totals can be approximate.

## Everyday controls

- Shop labels show item names, market references, colored comparisons and price ages. While a player shop is open, its listing prices take precedence over inventory hover cards.
- **Pause / Resume:** hides or restores labels. Resume reuses the sharing session.
- **Minimize:** puts the panel in the system tray by default and sends a notification. Click the tray icon to restore it. Right-click for reading controls, labels, Settings and Quit. If no tray is available, the panel minimizes to the taskbar.
- **Close or Quit:** ends reading and screen sharing.
- **Settings:** change the hotkey, hover prices, price update interval, automatic area detection or tray behavior.

The **full market refreshes in the background on launch, then hourly**. Saved prices appear immediately. A compatible browser runs briefly for each update, then exits. This can be disabled in Settings. Missing items use individual lookups, cached for **15 minutes** by default.

**Price checked**, snapshot age and **latest market report** show separate ages. Expand **Details** for the source and more information. Failed updates keep the saved copy, and stale or thin data receive no deal rating. References are a guide, not guaranteed sale prices.

Individual lookups can refresh shortly before expiry. During a refresh, the previous value stays visible with its age and progress. Cached shop items do not need separate price requests.

## If something isn't working

- **Can't find the game:** uncover the bottom status bar and the game window. For a cropped, covered or unusual layout, use **Settings → Limit the reading area…** to select it yourself. Multiple visible game windows also need a manual area.
- **Sharing stopped or labels don't line up:** use **Reconnect display** and share the selected display or full workspace.
- **No market reports:** the item name was recognised, but the source has no price for it.
- **Need more help:** open **Settings → Connection details / capture preview…**.

Upgrades keep settings, cached prices and EXP history. **Reduce motion** pauses the header animation and removes transitions. Windows installation is checked under Wine; live native Windows capture and mixed-DPI alignment still need a Windows playtest.

[Windows help](README-WINDOWS.md) · [Architecture](ARCHITECTURE.md) · [Technical details and source builds](docs/TECHNICAL.md) · [Building installers](packaging/README.md) · [Validation](VERIFICATION.md) · [Credits and licenses](THIRD_PARTY.md)
