# Lupin 0.17.2

Local patch; uploads remain on hold.

- Both tracking cards now fit a 66-pixel stack in the empty corner left of the status bar. Narrow windows without enough side space use a position above the HUD. Native identification pixels stay clear.
- Totals sit farther right beside aligned percent/coin symbols. Large values retain their digits and have bounded space; clocks yield space before totals can collide with them. The tiny meso coin appears only with a number.
- The GUI and overlays share one two-second numeric snapshot. Pause freezes the last displayed rates and ETA. Both views use **Level X - ETA …** and explain the averaging basis: up to five tracked minutes for EXP, the active session for mesos. Coverage-gap counts stay off the overlay.
- Paused tracking no longer accepts another character/map as a new run or resets pickups. Tracking cards wait for the original character; Resume becomes available after two fresh matching readings. Prices remain independent.
- The map header gets the unused identity-row width, keeping the current Tree Dungeon name visible beside the character and level.
- Empty NPC tables no longer block inventory-hover pricing. Replaying the captured sell-list case clears the old false context and reads Green Bamboo Hat on the next pass, using the existing reader.
- Recent-item rows stay present on re-sighting. A price change animates only affected rows, rather than replaying old number transitions in every entry. Reader shutdown also ignores queued scans before Qt children are destroyed.

## Validation

The 478-test source suite passes with three platform/offscreen skips. The final 49 focused checks cover the shared cadence, an ETA held through a long pause, A → B → A client changes, actual compact overlay pixels/HUD guards, logical/capture scaling, large totals, full map-header width, history stability and NPC tooltip requests. Private screenshots/replays are excluded from source and packages.

All four installed builds pass the 478-test suite: Windows/Wine, pacman, Debian 12 and Ubuntu 22.04, with eight/four/five/five platform skips. Installation, upgrade/removal where supported, offline OCR/overlay, file checks and cache preservation pass. Both staging trees match the final application sources.

The pinned native reader/vendor and both translation bundles are unchanged. The user deferred live follow-up checks. Native Windows gameplay remains separate from Wine validation. Full evidence is recorded in `VERIFICATION.md`.

## Install locally

Manjaro / Arch:

```sh
sudo pacman -U /home/zach/Projects/maple-market-overlay/dist/lupin-0.17.2-1-x86_64.pkg.tar.zst
```

Debian / Ubuntu:

```sh
sudo apt install ./dist/lupin_0.17.2-1_amd64.deb
```

Windows 10/11 x64: run `dist/Lupin-0.17.2-Windows-x64-Setup.exe`. The portable ZIP is `dist/Lupin-Windows-x64.zip`. Existing settings and caches are preserved. Permanent host installation remains deferred to the user.

## Artifacts

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.2-Windows-x64-Setup.exe | 408,835,645 | `81e7ed06fa322f15ddc7577678a2e510079422f4027dbb49adf6d8be7331cb5b` |
| Lupin-Windows-x64.zip | 425,286,389 | `55aebfb30531bb850cf8c3249cd30379c78ac6c25e643ddc10cea84390cb0297` |
| lupin-0.17.2-1-x86_64.pkg.tar.zst | 463,577,800 | `ae2d1583850aeaca7cf81d2c6119f36188b7692cb7c3de73e93880c8e55dcb2e` |
| lupin_0.17.2-1_amd64.deb | 431,453,164 | `bd66369d17370db09e4105e9ed302ac139a5955289c944ec6c99059e24742330` |

Checksums: `dist/SHA256SUMS-0.17.2.txt`. Completed package evidence: `dist/VERIFICATION-0.17.2.md`. No uploads or source push have occurred.
