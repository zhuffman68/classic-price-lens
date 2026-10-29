<p align="center"><img src="price_lens/resources/icon-64.png" width="48" height="48" alt="Lupin icon"> <img src="price_lens/resources/lupin.gif" width="73" height="64" alt="Animated Lupin"> <img src="price_lens/resources/wordmark.svg" width="122" height="45" alt="Lupin"></p>

# Lupin

**Tools for MapleStory Classic World.**

Market prices, EXP and meso tracking, local Korean translation, and a searchable Classic World database beside the game.
Lupin reads shared screen pixels and draws independent overlays. It never hooks into MapleStory or sends game input.

[Download and install](#download-and-install) · [Getting started](#getting-started) · [Help](#help)

<!-- HERO MEDIA: docs/media/lupin-overview.png — real game and app side by side. -->

## Market prices

See market references beside player-shop listings, with item names and colors that make lower, similar and higher asking prices easy to compare. Hover inventory or equipped items for their market reference, including while a player shop or NPC vendor is open. Standard item descriptions from trades use the same reader.

- Supports equipment, scrolls, materials, consumables and cash/NX resale prices when market reports exist.
- Shows item images beside shop entries in the Prices page.
- Keeps shop references visible when an item description overlaps them.
- Prices recognized item-description popups opened from item links, including away from the cursor.
- Shows the age of the latest observed sale beside each market reference, with refresh warnings when needed. Thin or stale data receive no deal rating.
- Compares equipment as unscrolled. Individual stat rolls are not priced.

<!-- DEMO: docs/media/shop-prices.gif — open a populated shop and hover a listing. -->
<!-- SCREENSHOT: docs/media/inventory-equipment.png — a recognized item and its market card. -->

## Item search

Look up an item without opening a shop or sharing a screen. Prices and Database search the same released-item collection. Select an item for its market reference, base stats and Sources in one card. Search gets priority over on-screen results, with those compact listings still available when needed. Both search fields have a clearly visible clear button.

Prices share a local cache with the overlay. Saved references appear while updates run; missing market reports are shown separately from an unreadable item name. The full market refreshes on launch and at the interval selected in Settings. The overlay, search and watched items all use this shared snapshot; individual price requests are not used. Items without a reference stay unpriced.

Recently seen items stay in a compact list after their screen labels disappear. Each row has a thumbnail, a large market reference and its last-seen/listing information. Seeing a history item again updates that same row. The list keeps one entry per item, up to 100, and clears when Lupin closes.

<!-- DEMO: docs/media/item-search.gif — type, select an item, inspect its reference, clear the search. -->

## Watched items

Choose the **☆** star on a search, shop or inventory card to watch that exact item. When Lupin recognizes it in a shop or an item tooltip, it highlights the label and keeps a star so it is easy to spot, even while its price is loading. Deal colors still show how its asking price compares.

Expand **Watched items** on Prices for thumbnails and saved market references. Three entries fit before the list scrolls. Click an item for its full price card, or click it again to deselect. Collapsing the list clears that card and returns to on-screen items. Stars remove saved entries. The list survives restarts. Reduced motion uses a steady marker.

<!-- DEMO: docs/media/watched-items.gif — watch a searched item, then find it in a real shop. -->

## EXP and meso tracking

Start a session and watch gain, per-minute and per-hour figures in matching columns.

- **EXP:** percentage progress by default, with raw EXP or both available in Settings.
- **Pace:** a session timer, recent average rates and an estimated time to the next level.
- **Mesos:** meso pickups, with per-minute and per-hour rates from the visible pickup log.
- **In-game trackers:** compact EXP and meso cards in the empty corner beside the status bar, with independent visibility switches, gain, rates, time and level-up ETA.
- **Session controls:** Start, Pause and Stop; tracking always begins stopped when Lupin opens.

EXP rates and ETA need 30 seconds of clear EXP readings to establish a pace; covered or rejected readings can extend the wait. Both EXP and meso rates then average the last five active minutes, using the available time while starting. Gain totals cover the whole session. Elapsed clocks tick every second; gains, rates and ETA update every two seconds. Pause freezes the current pace and ETA, and Resume continues the retained window. Moving maps preserves gains and pace while saving history segments. **Stop and save** ends the session; a new Start begins a fresh warmup. A paused session stays with its original character when another client becomes visible. Pausing screen reading holds tracking; the Prices shortcut can pause prices independently.

The meso overlay includes the last confirmed pickup. Cards narrow to fit the empty HUD corner before moving above the status bar. Reading held means the displayed EXP values are retained while Lupin waits for a clear reading.

Meso gain counts readable pickup messages, including while EXP is unchanged. Fast bursts or covered text can be missed. Purchases, trades, potion costs and unsold loot are excluded; this is a pickup total, not farming profit.

### Training history

Add a map label and notes directly on the tracking page. Save sessions, compare runs by character and map, and export history to CSV. Map changes save segments automatically; history stays local.

<!-- DEMO: docs/media/tracking.mp4 — real training, visible pickup log and the in-game trackers. -->
<!-- SCREENSHOT: docs/media/training-history.png — labeled runs and CSV export. -->

## Korean translation

### Read Korean

Press the scan shortcut to translate visible Korean text into English. Lupin checks the full detected game window, including speech bubbles and chat, independently of the mouse position.

Results appear as soon as they are ready, with the Korean original kept alongside the translation. Popups follow matching text through modest movement and linger briefly after it disappears. Scan duration and popup delay are adjustable; recent results stay in the Translation tab.

<!-- DEMO: docs/media/read-korean.gif — activate a scan and show English with the original Korean. -->

### Write Korean

Open the writer, type an English message and review the Korean preview. Press **Enter** or **Translate & Copy** to submit it. The popup closes smoothly while translation finishes, then copies the Korean text and confirms it in the game overlay. The writer inside the Translation tab stays open. Choose where to paste with **Ctrl+V** and when to send.

Common trade and party shorthand is recognized. Known item names stay in English, and explicit numbers, prices and percentages are checked: `250` stays `250`, `250k` stays `250k`, and `2.5m` stays `2.5m`.

Both translation directions run locally with the included models. Writing works without screen sharing. Lupin never pastes or sends a message for you.

<!-- DEMO: docs/media/write-korean.gif — draft, preview, Translate & Copy and copied notification. -->

## Database

Browse **Items**, **Monsters**, **Skills**, **Maps** and **Quests** without sharing a screen. Items open with illustrated categories and subcategories; skills are organized by job. Search remains available throughout, with Back and breadcrumbs to retrace your steps.

- **Items:** images, stats, requirements, potion/scroll effects, Sources and saved market references with watch controls. Sort equipment by name, level or class, with relevant sorting for other categories.
- **Monsters:** stats, locations, two-column clickable drops and animated sprites where available. Sort by level or name; Back restores the monster after inspecting a drop.
- **Skills:** job navigation, prerequisites and a rank slider for costs and effects. Crafting skills are omitted.
- **Maps:** minimaps, map symbols, linked monsters, published spawn-point counts and connections. Spawn markers appear only when image-coordinate alignment verifies.
- **Quests:** quest-giver portraits, level and location, illustrated requirements and rewards, and linked prerequisite/next quests where recorded. Item Sources link back to named reward quests.

Selected item cards share a compact price column and sliding Overview/Sources panel. Equipment separates stats from requirements; scrolls show success rate and effects. Sources put named NPC shops and reported reward boxes first, followed by monster and quest sources, with images and links to database entries. NPC shop costs are kept separate from player-market references. Quest reward totals keep their units beside their values.

Browsing includes content supported by release or observed-market evidence, including previously available items. GM/test and unconfirmed code-only entries are excluded. Cash pages show relevant information without generic drop-report sections.

Check for database updates in **Settings**. Only changed reference files are downloaded; saved data works offline.

The database updates in the background and remains available offline after its first download. Images are cached as you browse. Drop percentages describe dated community samples; other community reports show no invented rate. Source links and dataset dates are included. [Data sources and accuracy](docs/DATABASE_SOURCES.md).

<!-- DEMO: docs/media/database.gif — search a monster, preview its sprite and maps, follow a drop to its item card, then browse skill ranks. -->

## Desktop controls

Choose a display and Lupin finds the Classic World area automatically. Windows reads that display directly; Wayland also asks for OS sharing approval. A manual area selection is available in Settings. The compact window follows the display's size and remembers manual resizing. It supports minimizing and does not maximize. Its minimum width is 460 pixels.

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
| Arch / Manjaro | `.pkg.tar.zst` | `sudo pacman -U ./lupin-0.16.0-1-x86_64.pkg.tar.zst` |
| Debian 12+ / Ubuntu 22.04+ | `.deb` | `sudo apt install ./lupin_0.16.0-1_amd64.deb` |

Extract downloaded ZIPs before running an installer or package command. For the Windows portable build, extract the full folder and open `run-windows.bat`. Updates preserve settings, prices and history; Linux packages replace the former `classic-price-lens` package.

Requirements: a supported 64-bit desktop, about **3 GB free space** for installation, and internet for market/database updates or uncached images. Python, Qt, OCR and both translation models are bundled. No Chrome, Edge or Chromium installation is needed. Market updates use a short-lived system web view, which closes after updating. Windows setup prepares the shared WebView2 runtime when needed; Linux packages install WebKitGTK through the package manager. Saved prices remain available offline. Linux sharing needs PipeWire and a working desktop sharing portal, normally supplied by KDE or GNOME.

## Getting started

1. Choose the display containing Classic World, click **Start reading**, and approve OS sharing if prompted.
2. Keep the game's bottom status bar visible for automatic game-area detection.
3. Open a shop, hover an item or use **Prices** to search by name.
4. Open **EXP/Meso Tracking** and press **Start tracking**. Keep the pickup log visible to count meso gains.
5. Use **Translation → Read Korean** for incoming text, or **Write Korean** for a reply to copy.
6. Open **Database** to browse items, monsters, locations, drops and skills. Screen sharing is optional for this tab.

Screenshots, translations and session history stay on the device. Market requests contain item information, never screenshots. Cached references guide comparisons and do not guarantee a sale.

## Help

- **Game not found:** uncover the bottom status bar, or use **Settings → Limit the reading area…**.
- **Sharing stopped or labels misaligned:** reconnect the display and share that display or the full workspace.
- **No market reports:** the item was recognized, but the source has no usable price.
- **Meso pickups are missing:** keep the bottom-right pickup log visible; covered or fast-moving messages can be missed.
- **Translation found nothing:** keep the text visible and scan again. The pointer does not limit the scan.

Connection details and capture preview are in Settings. Windows desktop capture is verified in a Windows VM; game capture and mixed-DPI alignment still need a physical Windows playtest.

[Windows help](README-WINDOWS.md) · [Translation](docs/KOREAN_CHAT.md) · [Architecture](ARCHITECTURE.md) · [Technical details](docs/TECHNICAL.md) · [Validation](VERIFICATION.md) · [Credits](THIRD_PARTY.md)
