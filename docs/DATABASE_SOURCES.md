# Database sources and accuracy

Availability audit updated October 30, 2026. Database is specific to **MapleStory Classic World**.
Original MapleStory, Mapleland and private-server balance tables are not fallbacks.

## Items, monsters, maps and skills

[OSMS Data Explorer's public API](https://osmsdataexplorer.com/data/api/v1/README.md)
provides a [manifest](https://osmsdataexplorer.com/data/api/v1/meta.json) with the
world, client build, update date, SHA-256 hashes and record counts. Lupin verifies
all seven used files before replacing the local generation. These include NPCs
and quests alongside items, cash items, monsters, skills and maps. The October 26 generation
contains 5,164 named regular/cash items, 117 monsters and 99 skills, including six
crafting disciplines, 343 quest records and 301 NPCs. Empty client placeholders are omitted from search.

Records retain their original fields and rank descriptions in SQLite. Map links
use exact map IDs; location counts are **spawn points**, not a live monster count
or respawn interval. Item cards show base stats, not a character's scrolled or
randomized equipment. Cash Shop NX costs remain distinct from meso resale prices.
No server drop rate or content availability is inferred from a record's presence.

The dataset is attributed to OSMS Data Explorer / @ohmi, CC BY 4.0; game text and
artwork belong to Nexon. Images come from the published URLs and are cached on
demand, outside the installer. Native animation timing is retained.

## Released-content browsing

Client records and client `on_sale` flags alone do not establish that an item
has ever been obtainable in the live game. The raw records remain cached for
identity validation; both manual item searches, Database groups and related entries require
positive release/circulation evidence.

- The public [Nia item browser](https://meowdb.com/msclassic/item-db) supplies its
  sourced `avail=launch` filter for equipment, use, etc, setup and cash utilities.
  Cosmetics use its curated `unsold=hide` filter. Requests also exclude Ossyria
  and closed-test-only content; explicit `cashShopLastSeenIn` flags and future
  `availableDate` values are independently rejected. An internal provider ID
  alone never establishes identity: canonical icon ID and English name must match.
- Monsters use the public index's canonical ID/name/level/HP. Encounter-specific
  duplicate aliases do not inherit the ordinary monster's status. GM/test
  placeholders and the ten Forgotten Hollow monsters plus Rotten Mushmom are
  excluded. The [roadmap](https://meowdb.com/msclassic/news/classic-world-roadmap-maplestory-fest-2026)
  and [area guide](https://meowdb.com/msclassic/guides/forgotten-hollow-the-new-endgame-area)
  place the area after this build, on November 18. A scheduled date does not
  automatically unlock those records; a verified release update is required.
- The existing validated [MesoWatch](https://meso.watch/) snapshot can additionally
  prove circulation, including formerly available cosmetics. It must match the
  exact game ID/name/world, have a positive observed-sale sample, and contain a
  dated sale since Founder's Access opened on October 6. Catalog rows, undated
  prices and closed-test sales alone do not qualify. No extra market HTTP calls
  are made. The cutoff is documented in the current
  [release timeline](https://meowdb.com/msclassic/guides/maplestory-classic-worlds-release-date).
- Positive evidence is retained when a sale/event ends, so this is not merely
  an "on sale now" filter. Evidence is bound to ID/name; renamed/reused records
  must be confirmed again. Failed source updates retain saved proofs and never
  make the full raw catalog visible.

An additional October 30 scroll audit found that the sourced release filter
omitted **Gloves Attack Scroll: Chaos (`2040803`)**, despite a user reporting its
linked description in a live Classic World super megaphone. Lupin records that
as **user-confirmed availability**, not a captured observation, drop or sale.

`recipes.json` is an optional eighth payload, verified against the current OSMS
manifest's exact byte count, SHA-256, record count and generation before use.
Reachable Arcforge recipes require the already-confirmed base scroll, every
ingredient and the exact [Scroll Crafting Catalyst](https://meowdb.com/msclassic/item-db/2723).
The catalyst description permits Intermediate, Greater and Chaos outcomes of
the same category. The documented current crafting cap is eight; raw skill
levels nine/ten do not establish availability. Exact family, slot, stat, tier
and success/destroy values must agree.

This supports 13 previously hidden Chaos outcomes (Hat Accuracy/HP/MP,
Topwear HP/MP, Bottomwear HP/MP, Shield DEF, Overall Armor DEF, Shoes Jump,
Cape Weapon DEF/Magic DEF and Earring DEX), plus Bottomwear MP Intermediate.
Their provenance is **recipe/catalyst mechanics**, not 14 observed live drops.
In the audited local generation, these plus the user-confirmed glove scroll
raise searchable scrolls from 156 to 171 of 208; the other 37 remain unproven.
These counts describe that snapshot, not a promise of complete live coverage.

Fresh native shop rows and accepted item descriptions can also establish
circulation. The source name, canonical ID and tier must match exactly; current
game/panel/row pixels and timestamps must remain verified. Manual search,
screenshots, covered/retained rows, ambiguous names and OCR aliases cannot add
this evidence. Repeat observations avoid writes; newly confirmed identities
refresh the shared released search catalog once per batch. Missing market
prices remain missing regardless of an item's availability.

The checked source-only generation contains 1,742 eligible items (293 cash items)
and 70 ordinary monsters, with 332 maps and 332 quests. Dated market sales can extend the item collection. This is a conservative
sourced subset, not a complete official release ledger: some legitimate content
can remain hidden until supported. Source filters and name/status changes need
periodic review. No third-party application code is copied or executed; downloaded
index records stay in the per-user cache.

Cash entries retain their release/market Sources, with no generic monster-drop section, empty drop message or drop-report
button. Opening one does not request a drop feed. Client NX retail prices and
rental flags are omitted from cards where they cannot establish the actual released
product's terms. Regular item Sources and monster Drops retain the evidence below.
Crafting disciplines are excluded from skill browsing and search.
Crafting **quests** and Citizenship quests remain available when supported by
the release index; the skill exclusion does not remove those quest categories.
Quest browsing groups towns, job advancement and systems/events. Category
thumbnails prefer a released entry with an image, rather than hiding a category
whose lowest-ID entry has no artwork.

## Quests, maps and images

The public [map index](https://meowdb.com/msclassic/maps/all) and
[quest index](https://meowdb.com/msclassic/quest-tracker/all) confirm exact game
IDs/names. Known chain/step/class decorations are normalized, never guessed by
similarity. Developer maps, unconfirmed records and Forgotten Hollow quests stay
hidden. The cached API quest fields supply requirements, rewards, quest givers
and portraits. Reverse reward links make named quests appear in item Sources.
Random reward weights are divided within their own class/choice group; duplicate
flat export rows are omitted. These client references are not measured server
drop probabilities.

Maps use the published minimap and symbol URLs. Monster counts mean exported
spawn points, not a live population or a respawn timer. Full-render positions
cannot simply be scaled onto every minimap: their crops can differ. The optional
marker path requires two consistent canonical portal anchors, a matching
content-addressed native WebP, and matching minimap palette/terrain projection.
Uncertain maps keep the minimap and monster list without guessed dots. Both
checked real examples (East Entrance to Mushroom Town and Henesys Hunting Ground I)
failed the final projection check, so their markers stay hidden.

Alignment is loaded only for the selected map and cached separately. Images are
not retained by this worker; a plugin that needs native decoding is capped at
eight million pixels (32 MiB of RGBA pixels) for this one-time background check.
Failures are cached and matching last-good geometry is retained on network errors.

## Resolving skill discrepancies

Numeric rank tables were cross-checked against the current
[Bubbling Formula Wiki](https://bubbling.wiki/wiki), with mechanics checked against
[NiaMeowDB's Classic World skill pages](https://meowdb.com/msclassic/skills).
Published client values are references, not measurements of live server damage.

- **Rush, Fighter/Page/Spearman:** the numeric data and Bubbling's
  [Rush table](https://bubbling.wiki/skills/1301005) agree on 69% at rank 11 and
  74% at rank 14. Some English descriptions instead say 70% and 73%. Lupin uses
  the numeric values without interpolating a smoother progression. Rank 10's
  numeric distance is 130; the increase to 150 at rank 11 is independently
  documented in [Nia's notes](https://meowdb.com/msclassic/skills/spearman/rush).
- **Power Knockback:** both numeric tables give 170% at rank 8, while its English
  description says 140%. Lupin retains 170%, as in
  [Bubbling's table](https://bubbling.wiki/skills/3001003). It does not assume that
  the rank must lie between its neighbours or confuse damage with knockback
  distance. The current [Nia page](https://meowdb.com/msclassic/skills/bowman/power-knockback)
  still carries the other English value; this is a source disagreement, not a
  live combat test.
- **Arrow Bomb:** the exported attack fields describe its single-target delivery
  arrow (0%), omitting the linked explosion. The
  [explosion rank table](https://bubbling.wiki/skills/3101004) and
  [Nia's mechanics](https://meowdb.com/msclassic/skills/hunter/arrow-bomb) support
  70% at rank 1 through 130% at rank 30, with up to six targets including the
  initial enemy. The card displays explosion damage, stun chance and duration.

`reference_skills.py` applies only these identified presentation rules with exact
ID/name/rank/value guards. It does not change cached source records. Unexpected
future Arrow Bomb text or numeric fields do not receive an old override. Hover
the affected rank text or value to see the distinction. Recheck these rules after
skill balance patches; do not extend them through guessed progressions.

## Drops and reverse item lookups

[MapleClassic Wiki](https://mapleclassic.wiki/) supplies dated observations through
its public Cargo API (CC BY-NC-SA 4.0). Lupin joins monster/drop/item tables using
their own page relationships, then validates **both game IDs and names** against
the current local generation. Base monster variants only are included. The dated
sample contained 158 matching relationships; this is partial coverage.

An observed percentage stays attached to its sample kills/drops, game version,
date and reported interval. It is not presented as an official server chance.
Unknown rates stay unknown. Currency and no-drop observations are not fake items.
The public report page is linked from the card.

[NiaMeowDB](https://meowdb.com/msclassic/) supplements the selected item or monster
with community drop reports. Its monster identity must independently match
ID/name/level/HP from the public monster table. Its item identity must match the
exact canonical image ID and name; internal provider IDs alone are insufficient.
Unmatched or ambiguous rows are omitted. In the checked sample, Green Mushroom
had 32 combined relationships, and Pan Lid linked back to Green Mushroom.

Community votes are shown as votes in the source tooltip, **never as a percentage**.
Reports with more negative than positive votes are marked disputed. Where sources
overlap, the dated Wiki observation and its provenance are retained rather than
averaging unrelated evidence. Neither source claims a complete authoritative
server drop table.

## Refresh and offline behavior

- Check the bulk manifest asynchronously on launch and daily; download changed
  files only, then replace the complete validated generation atomically.
- Refresh the Wiki observation table daily. Preserve the last-good generation on
  malformed, empty-after-nonempty, failed or cancelled updates.
- Release indexes refresh daily. Positive historical evidence remains after a sale ends.
- Supplementary reports are fetched only for an explicitly selected ordinary item/monster,
  then cached for 24 hours (30 minutes for a failed lookup). Idle or repeated
  selection does not poll. The update check is in Settings; it compares the manifest without forcing unchanged files or still-fresh source indexes to download again.
- Cache images for 30 days, misses for six hours; use at most four downloads,
  eight MiB/128 native decoded images and 64 MiB/1,024 files on disk. Visible rows precede nearby thumbnail prefetch; up to twelve landing icons can warm in the background. Obsolete requests are cancelled without being cached as misses. Only one selected monster animation plays; hidden/minimized or reduced-motion views pause it.
- Market cards read the existing full-market snapshot. Browsing Database never
  starts item-price requests. Its refresh policy remains separate from references.

Prices and Database use the same selected-item card, with compact market/sale
information beside a sliding stats/Sources panel. Ordinary on-screen listings stay compact.
Equipment can sort by name, required level or class; other item lists have relevant
type/value/rate choices. Monsters sort by level or name; skills retain job order.
Monster drops use two columns; opening a drop and going Back restores the same
monster, subpage and list position.

The source has automated validation and public/generated fixtures. Saved private
research copies and live captures are excluded from source, installers and archives.

## NPC shops and reward boxes

Checked October 29, 2026. The public [Nia NPC shop list](https://meowdb.com/msclassic/npc-shops) supplies named shop inventories, locations and published NPC purchase prices. Lupin requires each canonical item icon ID/name and NPC ID/name to match the local database; provider item IDs alone are not used as canonical IDs. The checked page yielded 599 matching item/NPC rows across 31 NPCs. Historical launch-price qualifications remain attached to the source. These prices never replace market references or a player shop asking price.

Selected item pages may also publish player-reported reward boxes, for example [Green Bamboo Hat](https://meowdb.com/msclassic/item-db/790). Both ends require a fresh matching public index binding before a box is linked to a canonical database entry. Box relationships are reports, not drop rates. Shops refresh daily; selected-item source checks cache successful/empty results for a day and errors for 30 minutes. Failures preserve matching last-good relationships.

Known incomplete scroll targets are normalized by exact scroll-family ID plus canonical name. This corrects Hat, Topwear, Bottomwear and Pet equipment targets without changing verified raw files, success rates or effects. An unfamiliar or mismatched name stays unclassified.
