# Lupin architecture

Lupin v0.17.1 provides market references, EXP/meso tracking, local Korean translation and a searchable Classic World database for MapleStory Classic World.

## Observation boundary

Game observations come only from ordinary OS-shared screen pixels. No game-process discovery, handles, memory, files, packets, rendering/input hooks or game input are used. The annotation canvas is an independent input-transparent window. OS cursor coordinates position inventory cards. Windows shortcuts use RegisterHotKey; Wayland uses the GlobalShortcuts portal and X11 uses passive grabs for the chosen chords.

Screenshots, chat and drafts remain local. Market downloads contain public market data; image downloads use exact catalog IDs. The Korean writer copies validated text to the OS clipboard only after an explicit action. It never pastes, sends keys or focuses a game field.

## Processes and data flow

```mermaid
flowchart LR
    OS[OS display capture] --> Stream[Persistent capture helper]
    Stream --> Reader[Frame scheduler and Rust OCR]
    Reader --> Identity[Classic World item catalog]
    Identity --> UI[Prices and independent overlays]
    Snapshot[Full-market download] --> Cache[(Local snapshot)]
    Cache --> UI
    Search[Search and watched items] --> Cache
    Images[Exact-ID item images] --> Search
    Reader --> Tracking[EXP and pickup ledger]
    Tracking --> UI
    Stream --> Translate[Local Korean OCR and translation]
    Translate --> UI
    Draft[English draft] --> Writer[Local Korean writer]
    Writer --> Clipboard[OS clipboard]
```

The main Qt process owns settings, layouts, market state and session accounting. Capture and annotations use separate helpers. The Rust reader accepts only local RGBA/PNG input through its own JSON stdin/stdout. Translation workers communicate over bounded local pipes and load their verified models on demand. All portal callbacks enter the Qt GUI thread through signals.

## Capture and recognition

Linux retains its approved PipeWire/portal sharing session. SIGUSR1 hands the capture helper to a replacement UI without another chooser. Normal Quit ends sharing. The explicit KDE screenshot fallback remains available for troubleshooting.

Windows captures the selected OS display with `QScreen.grabWindow(0)`, using desktop GDI rather than Direct3D desktop duplication. It never obtains a game window handle. The dropdown contains real displays; geometry changes update the selected display. Capture runs at most ten times per second, pauses without demand, and skips work while its local output is busy.

Frame dimensions and local buffers are bounded. The client drains packets promptly and retains one newest completed frame; the display interval applies to delivery, not socket reads. Superseded frames are discarded. Pause, stop and display changes clear pending delivery.

The visible bottom status bar and static frame evidence locate Classic World. FPS and movable minimap placement are not anchors. Shop/tooltip pixel fingerprints avoid repeated OCR and preserve proven identities through modest movement and occlusion. Equipment names include gender/stat/tier evidence; ambiguous IDs remain unresolved.

Only a missing, uncovered shop price triggers a retry. A cropped shop passes through the unchanged strict upstream reader at two resamplings. Recovery requires agreement on exact name, row position, quantity and the complete meso amount. Existing prices are never overwritten. An eight-patch pixel cache also remembers failures. The pinned Minerva revision and OCR model are unchanged; the worker uses two OCR threads.

## One full-market cache

`PriceService` loads the Classic World regular/cash catalog and manages a single `SnapshotStore`/`SnapshotUpdater`. There is no individual-price provider, per-item HTTP queue or provider-ID index.

On every launch, saved data loads immediately and one asynchronous full-market download starts. Later downloads follow the selected 5/15/30/60-minute interval. Changing the interval reschedules from the last successful check. Overlapping refreshes coalesce. Overlay, search and watched-item prices are local snapshot reads; typing, selecting, hovering and watching never initiate individual price requests.

A short-lived native `lupin-market-fetch` helper reads the ordinary public market page using system web views: WebKitGTK on Linux and the shared production WebView2 runtime on Windows. It uses an offscreen/invisible window owned by the helper, never a game window. Linux uses an ephemeral context; Windows uses an app-owned data directory and disables OS-account single sign-on. Website permission requests and new windows are denied. No personal browser, installed browser discovery, DevTools socket or resident service is involved. Well-formed source rows with different listing/catalog IDs are excluded as unverified aliases; they never map prices to either ID. Malformed identities, duplicates, wrong worlds and empty exact generations still reject the update.

`SnapshotFetcher` bounds UTF-8 stdout to 8 MiB, retains only bounded diagnostic stderr, accepts one JSON object after a successful helper exit and enforces a deadline. Stop/cancellation discards pending results; refreshes coalesce while a previous helper shuts down. Only the subprocess created by Lupin is terminated. The Windows helper's private job controls its own descendants so cancellation cannot leave its renderer running. Full generation validation still occurs in `SnapshotStore` before replacement.

A complete generation is validated before an atomic SQLite replacement. Checks require Classic World, live list schema, exact IDs/names, clean equipment and item/set units. Failed/invalid refreshes retain the last-good data and its original ages. A transient startup failure gets one retry after 15 seconds, then uses bounded 5/15/60-minute backoff. Missing runtimes and invalid documents do not trigger the startup retry. Successful refreshes never inherit a failure cooldown. `market-last-error.json` retains only the failure kind, exit code, time and up to twelve fixed helper stage/error-code pairs, never page bodies or user text. Connection details shows the current process's retained failure.

Check time, publication time and latest observed-sale time are distinct. Validity ends at the earlier of check time plus the selected interval and publication time plus one hour. Old/missing observations, thin samples and uncertain units cannot earn deal colors. Rechecking an unchanged publication cannot make its publication or observed sales newer. Missing items stay unpriced.

Overlay annotations show the source's latest observed-sale age rather than repeating the snapshot check age. Stale/refresh warnings remain explicit. The larger item panel shows the source's latest observed-sale time. The full list does not supply a verified individual transaction amount; the market median is never presented as the latest sale price.

## Prices and watched items

Selected shop bands can have a different brightness from normal rows. Inside an independently detected shop, the reader measures the blue and orange palettes, validates a single broad selected band, and adjusts only its background pixels in a copy. It reuses the primary strict OCR engine and merges only complete, noncontradicting reads from that band. An eight-entry cache includes current list pixels and coordinates, so price changes and occluders cannot inherit prior amounts. The original frame still drives tooltips and occlusion.

The locator can retain a proven footer span while an item description covers its white rim, provided the independent LV template and OS caption still verify the same coordinates. Losing those anchors still removes the game area. Shop selection/unreadable names can retain references under verified page guards, without an assumed listing amount. A listing returns without another OCR pass only when the entire previously read row pixels and page guards match exactly. Occlusion alpha uses the recognized current description rectangle only; late OCR replies cannot restore a description absent from the latest frame. The old covered-row opacity fallback is removed.

Paired frame strokes alone do not establish a description: bright shop panes have similar borders. Description geometry also requires a dark native interior, excluding Lupin's own annotation rectangles from both body evidence and name anchors. The same proof validates retained rectangles against current frames. Omitting an occlusion from a new annotation clears the previous value. This prevents our dark labels from manufacturing evidence for the pane behind them and repeatedly dimming themselves.

Clicked item-link descriptions may be located beyond the pointer's usual search area. The Rust reader reuses its existing name/bullet recognizer over bounded analysis regions without changing the real cursor or sending input. The GUI requires a catalog match and a visible anchored native description panel before accepting those results. A structurally verified pair of native frame edges permits a local header-only contrast adjustment when chat shows through the translucent fill or upgraded equipment has colored title ink. The cyan marker and its antialiased fringe stay intact, bright foreign occluders are preserved, and the original frame still drives all shop readings and geometry. The same paired-edge proof keeps adjacent comparison panels separate even when their purple hue is lost. A unique equipment name may drop its visible upgrade count for the existing unscrolled reference; exact catalog names retain priority. Cash descriptions with no cyan marker use a separate bounded header reader. It requires paired vertical frame edges and the horizontal top rim, then reads only centered title lines. Complete descenders are retained; up to eight exact header masks cache successful/failed reads. It never searches arbitrary scene text or substitutes a guessed catalog name. Such cards remain beside the description. Small-font I/l and g/q variants and ellipsis punctuation are accepted only for unique catalog candidates; shorter shared Ink-and-Wash prefixes remain ambiguous.

Search controls sit above one shared content area. Selected-item and on-screen/ready views use the same origin; a short fade through the background swaps content without simultaneous text or height animations. Empty status rows are hidden. New market generations synchronize retained price cards even while capture is paused. Search is part of Prices and takes space priority while active. Clearing it animates shop cards back into view. Shop cards retain their widget instances and layout positions during quote/age updates. Item additions/removals use the shared content transition instead of per-card reveal/removal effects; numeric updates do not restart it. Adding a hovered item does not change shop-card identities. Search, shop and inventory cards share an exact-ID watch star and thumbnails. The removed Details expander has no runtime path.

Watched items start collapsed. Expanding shows a compact list with thumbnails and cached references, capped at three visible rows. Its contents stay at a stable full height while a clipping viewport slides, avoiding repeated list reflow. Header/empty-space clicks toggle the panel; items, stars and the scrollbar retain their actions. Rounded selection covers the full row.

Only an item click opens its larger card and takes space priority. Expanding alone retains the normal item/ready view. Deselecting clears that card while retaining the watched view. Collapsing clears the selection and returns to shop cards. Watching/unwatching changes saved exact IDs, not market demand. In-game watched labels shimmer twice inside a steady border and retain a star. Reduced motion uses a steady marker.

Thumbnail downloads share a two-request queue, bounded memory/disk caches and negative caching. Cached images are used immediately without waiting for a network signal. No fetched thumbnails ship.

## Tracking and translation

Tracking starts stopped. Explicit Start enables EXP sampling once a second and a bounded bottom-right pickup-log crop at up to five samples a second, in the existing OCR process. The old wallet reader is removed. The pickup reader recognizes complete system messages, caches up to 128 line masks and never saves frames or chat. A bounded arrival ledger confirms lines in independent captures, aligns scrolling suffixes/prefixes, distinguishes repeated amounts, seeds existing messages on Start/Resume and after coverage gaps, and holds when known windows cover the log. It records gross visible pickups, not profit or wallet changes. Missed/ambiguous bursts can undercount. Legacy saved runs retain their wallet basis; new history/CSV records use pickups and record coverage gaps.

EXP pace needs 30 seconds; pickup rates need 10 seconds. Percent is the default EXP unit; raw/both remain available. Compact fixed-grid EXP and meso cards always stack at bottom left, above the native HUD. Placement uses the independently verified guard top/height at capture scale and never paints over or exempts those guards from validation. Separate visibility settings synchronize between the tracking page and Settings; the new meso preference initially inherits the old combined overlay preference. Numeric snapshots update every two seconds, with immediate pause/context/settings changes. Reading Pause holds the session clock and rebaselines future samples; the Prices shortcut leaves tracking active. History/CSV stay local.

The detected-map header omits a redundant street prefix and shortens overflowing names at the right edge, with the full value in its hover text. Session data and the Map Label field retain the full detected name; manual labels are not rewritten.

The Korean reader scans the detected full game area for a short configurable window, independent of cursor proximity. New scans supersede old work. Matching source pixels retain cards through modest movement; linger and no-result timers are bounded. The Korean original is retained and unstated price/percentage units are not invented.

The writer uses conservative trade/party shorthand and numeric validation before explicit Translate & Copy. Enter in the popup begins a short fade/slide dismissal while the current validated draft finishes; this intentional dismissal preserves only that explicit copy authorization. Escape/edit revokes it. Successful copying shows an expiring bottom-right notification. Editing/canceling invalidates pending copies. Both verified int8 model bundles remain included. See [Korean notes](docs/KOREAN_CHAT.md).

## Presentation, persistence and packaging

Inter is bundled for consistent interface/price typography. The GUI uses a small coin for currency words, except MESO on the tracking panel and EXP/Meso Tracking on its tab; game-overlay text remains plain. Tracking unit coins appear only alongside available numbers. The larger, left-aligned rolling tracking timer shares a borderless row with the tracking controls above both metric panels. The timer adds hours while retaining seconds; its reserved width prevents the adjacent buttons from shifting. Digit-place animation keeps surrounding text/columns steady. Page slides and section transitions are interruptible and respect Reduce motion.

Maximization and control-panel pinning are disabled. Fresh default geometry is 27.0833% × 77.7778% of logical screen dimensions (520 × 840 at 1920 × 1080), clamped to available space with a 460-pixel minimum width. Resizes persist as screen-relative fractions; OS DPI is applied once. Valid older custom sizes migrate without losing the preference; desktop-sized/maximized geometry cannot replace a compact preference. Long item/history lists can scroll independently. Tabs use plain labels, warm selected text and a filled active background.

Programs install to `/opt/lupin` or `%LOCALAPPDATA%\\Programs\\Lupin`; launchers/readers use Lupin names. Windows upgrades move the old program directory, preserve additional files, remove obsolete shipped modules and support rollback before commit. Shutdown sends Quit through Lupin's own local pipe and waits for that specific server process to finish unloading; synchronization-only access comes from the pipe's server PID, with no process enumeration or termination. Stable settings/socket/portal IDs preserve data and approved sharing. The WebView2 SDK, loader and official setup bootstrapper have pinned download hashes. Windows setup checks/prepares the shared runtime before closing an existing installation; Linux package dependencies provide WebKitGTK. The browser engine is not bundled. Both runtime/model manifests are pinned; install roots stay read-only in normal use. Private evidence, credentials, screenshots and caches are excluded. See [packaging](packaging/README.md) and [verification](VERIFICATION.md).

The Windows Korean writer registers the existing PySide6 DLL directory before loading CTranslate2, retaining its directory handle for the worker lifetime. This reuses the bundled Microsoft C++ runtime without importing Qt or requiring a system Visual C++ installation. Cold writer startup has a 60-second deadline; individual inference requests retain their 12-second deadline.

## Local reference database

Database is the fourth tab, with Items / Monsters / Skills / Maps / Quests and local prefix search. Items start with category tiles, then subcategories and weapon types. Skills start with illustrated job families and job lists. Search stays available at each depth; Back restores category, query, scroll position and the selected entry's subpage/rank. Main and subnavigation tabs are centered and use the shared selected/hover colors. `reference_widgets.py` provides fixed-geometry list/tile rows, nearby-image demand and interruptible forward/back slides. Search uses the same content fade as Prices.

`reference_data.py` stores verified source blobs, entities and FTS5 in per-user SQLite WAL storage. `reference_service.py` checks the OSMS Classic World version/hash manifest on launch and daily. Changed items/cash/monsters/skills/maps files replace one complete generation atomically. Wrong-world, hash, count, shape, duplicate and identity failures keep last-good records. Raw client presence does not make a record browsable.

`reference_availability.py` imports positive evidence from NiaMeowDB's sourced release indexes and its never-sold cosmetic exclusion, with exact canonical ID/name matching, future-date/closed-test rejection and explicit GM/test/unreleased exclusions. Monster identity also matches level/HP; duplicate encounter variants do not inherit the ordinary monster's status. Validated MesoWatch snapshots can confirm circulation only with exact names/IDs/world, a positive observed-sale sample and a sale since Founder's Access. Catalog membership, client on-sale flags and undated prices are not evidence. Positive records remain after a sale/event ends; ID/name changes invalidate their join. Release indexes refresh daily with bounded pagination and normal error backoff; saved proofs work offline. Known scheduled content requires a verified release update rather than automatically unlocking on a calendar date. This is a conservative sourced view, not an authoritative complete release registry.

Wiki Cargo observations refresh daily. Their own monster/drop/item joins must match canonical IDs and names; sampled percentages/counts/version/date/interval remain attached. `reference_community.py` supplements a selected ordinary item/monster, cached for 24 hours with a 30-minute error cache. Cash entries have neither generic drop controls nor generic drop requests. Votes never become rates. Related item/monster rows must also have release evidence. Two single-thread reference workers use cancellable requests and GUI-thread result delivery; idle browsing does not poll.

`reference_details.py` owns one complete entry widget. Navigating away disposes that widget and all nested controls, fixing the orphaned skill slider. Background drop results update retained list rows without reconstructing the header, rank control, sprite or subpage. Identical core data does not rebuild the view. Actual changed core records preserve rank/subpage/scroll state. Initial stats start populated; subsequent numeric changes roll. Monster Overview / Locations / Drops have separate scroll areas; ordinary item Sources are separate from Overview. Cash cards omit irrelevant drop/NPC-price scaffolding and repeated name-only descriptions.

`reference_skills.py` preserves raw records while presenting the documented Arrow Bomb explosion and reconciling identified stale rank descriptions with cross-checked numeric data. Exact ID/name/rank/value guards prevent interpolated progressions. [Database sources](docs/DATABASE_SOURCES.md) records the evidence and limitations.

`reference_media.py` retains original decoded pixels in an eight-MiB/128-image LRU. `reference_widgets.py` renders directly at the requested size/device scale: integer enlargement for pixel art, quality downsampling when needed. At most four image requests run; visible rows precede nearby prefetch and obsolete requests yield without creating false negative-cache entries. Up to twelve static landing-page icons can warm while the main window is visible. Disk caching remains 64 MiB/1,024 files, with 30-day freshness and six-hour misses. PNG/WebP byte/dimension/frame limits bound decoding; disk cleanup avoids rescanning on every thumbnail. One selected monster movie uses source timing without a frame cache and pauses when hidden/minimized or under Reduce motion. Downloads remain outside installers/source.

`ReferenceStore.catalog` builds the same released-item identity collection for both manual searches, preserving exact matching domain objects where available. The raw OCR catalog remains separate for recognition. `EntryDetails` embeds the Prices-style `PriceCard` summary beside a fixed-height sliding stats/Sources panel on both pages; compact on-screen listings remain simple price cards. Prices owns selection demand, while Database coordinates the shared reference-image/report services for whichever page is visible. Quote updates retain the header, watch control and stat widgets; core-data changes preserve the selected subpage. Selected cards omit redundant check ages, per-item captions and generic explanations, retaining sale recency and source links.

Database update checks live in Settings and use the manifest/hash comparison, without a forced full refresh. Equipment sorts by class/name/required level; other categories expose relevant type/value/rate orders, monsters level/name, and skills job order without crafting. Monster drops use fixed two-column tiles and preserve subpage/list position across item navigation. `SearchField` supplies the same field geometry and contrasting 28-pixel clear control on both pages.

Market cards read the existing shared snapshot and watch controls, with updates through normal signals. Database browsing never starts individual price requests. Reference, release, drop and market refresh ages stay separate. Raw map placement counts mean spawn points, not server respawn timing; community samples are not official server probabilities.


## Session history and expanded references

`recent_items.py` keeps at most 100 exact-item sightings in memory, replacing
repeated reads and never retaining frames. Live observations and history share
one identity; inactive entries use native painted rows rather than per-row widget
trees. Only visible history thumbnails enter image demand. Market references are
local snapshot reads, with large rolling prices and muted expired values. History
is cleared on application exit and has no persistent file.

NPC and quest bulk files join the existing validated reference generation. A
cached old manifest that lacks these files triggers only the missing downloads.
`reference_indexes.py` validates map/quest release indexes; developer and known
future content remain unavailable. `reference_relations.py` builds canonical
quest requirements/reward links and reverse item sources, keeping choice/class
pools distinct. Returning from a source restores the previous tab, entry and
subpage. Quests use NPC portraits; Maps use published symbols and minimaps.

`reference_geometry.py` has one cancellable worker for the selected map, positive
and negative caches, content-addressed native-image checks and multiple portal
anchors. A palette/terrain projection check rejects incompatible minimap crops.
No full render is retained; native decoding, if required by the plugin, is capped
at eight million pixels. Markers appear only for verified projections. An API
spawn count is a count of exported placements, not live population or timing.

Reader title contrast now shares colored-ink handling across marker and centered
headers. Exact upgrade-suffix validation also applies to independent second reads;
colored title pixels participate in their cache fingerprint. Frame structure and
exact catalog identity remain required. No hooks, process access or game input
are introduced.

## Named item sources

`reference_sources.py` imports one bounded public NPC-shop page daily. An exact canonical icon ID and name must match the local item, and the NPC ID/name must match its local entry. Published shop prices remain NPC purchase costs, never market references or historical shop asking prices. Selected-item reward-box relationships use separately verified public item-index bindings for both the item and box. Successes/empty results cache for a day, failures for 30 minutes, and failed updates preserve last-good rows. These calls retrieve database relationships, not individual market prices. Sources sort named shops and boxes first, use compact image rows, and navigate to proven NPC/item entries. Raw versioned reference payloads remain hash-verified and unchanged; conservative scroll-family corrections apply only to the local presentation records.
