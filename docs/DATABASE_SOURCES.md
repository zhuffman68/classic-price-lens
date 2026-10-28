# Database sources and accuracy

Checked October 28, 2026. Database is specific to **MapleStory Classic World**.
Original MapleStory, Mapleland and private-server balance tables are not fallbacks.

## Items, monsters, maps and skills

[OSMS Data Explorer's public API](https://osmsdataexplorer.com/data/api/v1/README.md)
provides a [manifest](https://osmsdataexplorer.com/data/api/v1/meta.json) with the
world, client build, update date, SHA-256 hashes and record counts. Lupin verifies
all five files before replacing the local generation. The October 26 generation
contains 5,164 named regular/cash items, 117 monsters and 99 skills, including six
crafting disciplines. Empty client placeholders are omitted from search.

Records retain their original fields and rank descriptions in SQLite. Map links
use exact map IDs; location counts are **spawn points**, not a live monster count
or respawn interval. Item cards show base stats, not a character's scrolled or
randomized equipment. Cash Shop NX costs remain distinct from meso resale prices.
No server drop rate or content availability is inferred from a record's presence.

The dataset is attributed to OSMS Data Explorer / @ohmi, CC BY 4.0; game text and
artwork belong to Nexon. Images come from the published URLs and are cached on
demand, outside the installer. Native animation timing is retained.

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
- Supplementary reports are fetched only for an explicitly selected item/monster,
  then cached for 24 hours (30 minutes for a failed lookup). Idle or repeated
  selection does not poll. Manual Refresh can retry sooner.
- Cache images for 30 days, misses for six hours; use at most two downloads,
  64 memory thumbnails and 64 MiB/1,024 files on disk. Only one visible selected
  monster animation plays. Hidden/minimized/clipped or reduced-motion views pause it.
- Market cards read the existing full-market snapshot. Browsing Database never
  starts item-price requests. Its refresh policy remains separate from references.

The source has automated validation and public/generated fixtures. Saved private
research copies and live captures are excluded from source, installers and archives.
