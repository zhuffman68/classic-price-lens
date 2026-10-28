<p align="center"><img src="price_lens/resources/icon-64.png" width="48" height="48" alt="Lupin icon"> <img src="price_lens/resources/lupin.gif" width="73" height="64" alt="Animated Lupin"> <img src="price_lens/resources/wordmark.svg" width="122" height="45" alt="Lupin"></p>

# Lupin

**Tools for MapleStory Classic World.**

Market prices, EXP and meso tracking, and local Korean translation beside the game.
Lupin reads shared screen pixels and draws independent overlays. It never hooks into MapleStory or sends game input.

[Download and install](#download-and-install) · [Getting started](#getting-started) · [Help](#help)

<!-- HERO MEDIA: docs/media/lupin-overview.png — real game and app side by side. -->

## Market prices

See market references beside player-shop listings, with item names and colors that make lower, similar and higher asking prices easy to compare. Hover inventory or equipped items for their market reference, including while a shop is open.

- Supports equipment, scrolls, materials, consumables and cash/NX resale prices when market reports exist.
- Shows item images beside shop entries in the Prices page.
- Keeps shop references visible when an item description overlaps them.
- Shows when a price was checked and how old its market reports are. The larger item card includes the most recent observed sale time when available. Thin or stale data receive no deal rating.
- Compares equipment as unscrolled. Individual stat rolls are not priced.

<!-- DEMO: docs/media/shop-prices.gif — open a populated shop and hover a listing. -->
<!-- SCREENSHOT: docs/media/inventory-equipment.png — a recognized item and its market card. -->

## Item search

Look up an item without opening a shop or sharing a screen. Type its name, browse matching items with thumbnails, and select one for its market reference. Search gets priority over on-screen results, with those results still available when needed.

Prices share a local cache with the overlay. Saved references appear while updates run; missing market reports are shown separately from an unreadable item name. The full market refreshes on launch and at the interval selected in Settings. The overlay, search and watched items all use this shared snapshot; individual price requests are not used. Items without a reference stay unpriced.

<!-- DEMO: docs/media/item-search.gif — type, select an item, inspect its reference, clear the search. -->

## Watched items

Search for an item and choose its **☆** star. When Lupin recognizes it in a shop or an item tooltip, it highlights the label and keeps a star so it is easy to spot, even while its price is loading. Deal colors still show how its asking price compares.

Expand **Watched items** on Prices for thumbnails and saved market references. Three entries fit before the list scrolls. Click an item for its full price card, or click it again to deselect. Collapsing the list clears that card and returns to on-screen items. Stars remove saved entries. The list survives restarts. Reduced motion uses a steady marker.

<!-- DEMO: docs/media/watched-items.gif — watch a searched item, then find it in a real shop. -->

## EXP and meso tracking

Start a session and watch gain, per-minute and per-hour figures in matching columns.

- **EXP:** percentage progress by default, with raw EXP or both available in Settings.
- **Pace:** a session timer, recent average rates and an estimated time to the next level.
- **Mesos:** wallet balance, net change and live rates while the item inventory's wallet is visible.
- **In-game tracker:** an optional bottom-left overlay for pace, level-up ETA and meso change.
- **Session controls:** Start, Pause and Stop; tracking always begins stopped when Lupin opens.

EXP rates and ETA use 30 seconds of valid tracking to establish a pace. Hidden wallet readings show their age; reopening the inventory updates the balance. Net meso change includes purchases, sales and trades. Carried potions and unsold loot are not valued as farming profit.

### Training history

Add a map label and notes directly on the tracking page. Save sessions, compare runs by character and map, and export history to CSV. Map changes save segments automatically; history stays local.

<!-- DEMO: docs/media/tracking.mp4 — real training, visible wallet and the in-game tracker. -->
<!-- SCREENSHOT: docs/media/training-history.png — labeled runs and CSV export. -->

## Korean translation

### Read Korean

Press the scan shortcut to translate visible Korean text into English. Lupin checks the full detected game window, including speech bubbles and chat, independently of the mouse position.

Results appear as soon as they are ready, with the Korean original kept alongside the translation. Popups follow matching text through modest movement and linger briefly after it disappears. Scan duration and popup delay are adjustable; recent results stay in the Translation tab.

<!-- DEMO: docs/media/read-korean.gif — activate a scan and show English with the original Korean. -->

### Write Korean

Open the writer, type an English message and review the Korean preview. Press **Enter** or **Translate & Copy** to copy it; a notification confirms the copy. Choose where to paste with **Ctrl+V** and when to send.

Common trade and party shorthand is recognized. Known item names stay in English, and explicit numbers, prices and percentages are checked: `250` stays `250`, `250k` stays `250k`, and `2.5m` stays `2.5m`.

Both translation directions run locally with the included models. Writing works without screen sharing. Lupin never pastes or sends a message for you.

<!-- DEMO: docs/media/write-korean.gif — draft, preview, Translate & Copy and copied notification. -->

## Desktop controls

Choose a display and Lupin finds the Classic World area automatically. Windows reads that display directly; Wayland also asks for OS sharing approval. A manual area selection is available in Settings. The window remembers its size, supports resizing and minimizing, and does not maximize. Its default and minimum width are 460 pixels so it can fit beside a 1366-wide game on a 1080p display.

- Configurable shortcuts for prices, tracking, reading Korean and opening the writer.
- The current tool's shortcut shown at the bottom of each tab.
- Minimize to the tray by default, with a notification and right-click controls.
- Reduced motion and independent overlay toggles.

| Default shortcut | Action |
| --- | --- |
| **Super/Win + F8** | Open the Korean writer. |
| **Super/Win + F9** | Pause or resume prices. Tracking continues. |
| **Super/Win + F10** | Start tracking, then pause or resume it. |
| **Super/Win + F11** | Scan Korean text. |

Use **Hotkeys…** below Settings to change assignments. **Pause reading** pauses the shared reader; **Close / Quit** ends sharing.

<!-- DEMO: docs/media/desktop-controls.mp4 — display selection, tabs, hotkeys and tray controls. -->

## Download and install

Download from **[itch.io](https://zhuffman68.itch.io/lupin)**. Repository collaborators can also use [GitHub Releases](https://github.com/zhuffman68/lupin/releases).

| System | Download | Install |
| --- | --- | --- |
| Windows 10/11 x64 | `Windows-x64-Setup.exe` | Run it, then open Lupin from Start. |
| Arch / Manjaro | `.pkg.tar.zst` | `sudo pacman -U ./lupin-0.13.2-1-x86_64.pkg.tar.zst` |
| Debian 12+ / Ubuntu 22.04+ | `.deb` | `sudo apt install ./lupin_0.13.2-1_amd64.deb` |

Extract downloaded ZIPs before running an installer or package command. For the Windows portable build, extract the full folder and open `run-windows.bat`. Updates preserve settings, prices and history; Linux packages replace the former `classic-price-lens` package.

Requirements: a supported 64-bit desktop, about **3 GB free space** for installation, and internet for market updates or uncached item images. Python, Qt, OCR and both translation models are bundled. No Chrome, Edge or Chromium installation is needed. Market updates use a short-lived system web view, which closes after updating. Windows setup prepares the shared WebView2 runtime when needed; Linux packages install WebKitGTK through the package manager. Saved prices remain available offline. Linux sharing needs PipeWire and a working desktop sharing portal, normally supplied by KDE or GNOME.

## Getting started

1. Choose the display containing Classic World, click **Start reading**, and approve OS sharing if prompted.
2. Keep the game's bottom status bar visible for automatic game-area detection.
3. Open a shop, hover an item or use **Prices** to search by name.
4. Open **EXP/Meso Tracking** and press **Start tracking**. Open the item inventory to read the wallet.
5. Use **Translation → Read Korean** for incoming text, or **Write Korean** for a reply to copy.

Screenshots, translations and session history stay on the device. Market requests contain item information, never screenshots. Cached references guide comparisons and do not guarantee a sale.

## Help

- **Game not found:** uncover the bottom status bar, or use **Settings → Limit the reading area…**.
- **Sharing stopped or labels misaligned:** reconnect the display and share that display or the full workspace.
- **No market reports:** the item was recognized, but the source has no usable price.
- **Meso balance is old:** reopen the item inventory while tracking.
- **Translation found nothing:** keep the text visible and scan again. The pointer does not limit the scan.

Connection details and capture preview are in Settings. Windows desktop capture is verified in a Windows VM; game capture and mixed-DPI alignment still need a physical Windows playtest.

[Windows help](README-WINDOWS.md) · [Translation](docs/KOREAN_CHAT.md) · [Architecture](ARCHITECTURE.md) · [Technical details](docs/TECHNICAL.md) · [Validation](VERIFICATION.md) · [Credits](THIRD_PARTY.md)
