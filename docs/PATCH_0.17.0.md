# Lupin 0.17.0

Built and tested locally. GitHub and itch.io uploads remain on hold.

## Changes

- Separate EXP and meso cards at the bottom left. Both show session gain, rates and elapsed time; EXP also shows character/level, current progress and level-up ETA. Values update every two seconds, with rolling numbers and immediate pause changes. Percentage, raw EXP and both modes remain available.
- Meso gain now counts visible pickup-log arrivals, independently of EXP. The old wallet reader is removed. Start/Resume seeds existing messages; repeated captures do not add a line twice, equal amounts in distinct arrivals can count, and known occlusion/capture gaps hold or rebaseline the reader. The count excludes purchases, trades and potion costs and is not a profit estimate.
- The tracking page has a compact level badge, an inset identity, a rolling clock that adds hours, aligned columns and inline coin units. Main Pause reading holds the session; the Prices shortcut leaves tracking running.
- Enter in the English-to-Korean popup starts a short fade/slide dismissal and submits the current draft. Its validated Korean result is copied automatically, followed by an expiring game-overlay confirmation. Editing/Escape still cancels pending copy authorization. Nothing is pasted and no game input is sent.
- Price cards ignore geometry-only/irrelevant refreshes. Recent items use cached thumbnails and retain their last complete shop asking price across partial/covered/tooltip readings. History stays bounded to 100 unique items and clears on exit.
- Item Overview/Sources sit higher, with inset facts and closer source subtitles. Named NPC shops and reported reward boxes appear first, with images and database navigation. NPC purchase costs remain distinct from market references. Known incomplete scroll targets normalize through matching IDs/names without changing raw reference payloads or effects.
- Shared buttons, right-aligned translation timing fields and the resume layout are refined. Defaults are 27.0833% of logical screen width and 77.7778% of height: 520 x 840 at 1920 x 1080. Manual sizes persist as fractions; minimum width remains 460.

## Tracking details

EXP pace uses the recent five minutes of valid observations and needs 30 seconds to establish a rate. Pickup rates use the session's active elapsed time and appear after 10 seconds. Pickups still count while no EXP arrives. Main reading pause, loss of the captured game and the tracking pause hold the clock. Resuming starts from a fresh baseline rather than crediting unseen changes.

Only the visible bottom-right log is read, at up to five samples per second in a crop no larger than 640 x 300 pixels. Recognition uses the existing English OCR model, with up to 128 cached line masks and at most 24 visible ledger entries. No additional model or image history is retained. Dense bursts, obscured messages and indistinguishable replacement lines may be missed. Historical wallet-based sessions retain their original accounting basis.

## Verification and limits

All 463 packaged tests pass on pacman, Debian 12, Ubuntu 22.04 and Windows/Wine, with expected platform skips. Package installation/removal and cache preservation pass; native Rust unit checks pass. Production widgets fit 520 x 840 and 460 x 840 without page scrollbars, while long inner lists can scroll. The unchanged sharing helper is reused by the running Linux preview.

Synthetic outlined pickup OCR passes at 12/14/16 pixels, and generic item-description OCR passes on both sides of a synthetic trade-sized panel. Actual in-game pickup/pet bursts and live trades still need gameplay checks. Physical Windows capture and clipboard paste remain separate from Wine validation. Screen-only integration and the pinned vendor/model bundles are unchanged.

## Install

Use the normal package/installer; Python, Qt, OCR and both local translation models are bundled. Linux package managers install OS dependencies. Windows may need internet access for the system WebView2 runtime if it is missing.

```sh
# Arch / Manjaro, from the checkout
sudo pacman -U dist/lupin-0.17.0-1-x86_64.pkg.tar.zst

# Debian 12+ / Ubuntu 22.04+, from the checkout
sudo apt install ./dist/lupin_0.17.0-1_amd64.deb
```

Windows 10/11 x64: run `dist/Lupin-0.17.0-Windows-x64-Setup.exe`. A portable ZIP is also available. Archives are unencrypted. Permanent host installation remains deferred; the source preview is already running.

## Artifacts

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.0-Windows-x64-Setup.exe | 408,829,686 | `42f8740816b972a66347fa3060b0d7b56a249a9393fe5fdd8911eda6c630cad7` |
| Lupin-Windows-x64.zip | 425,274,595 | `fde887772cdbc4fc3fbcf8e66d665397a1b984c8ebb8447e5a9987bed9eea92d` |
| lupin-0.17.0-1-x86_64.pkg.tar.zst | 463,583,507 | `8296ac3f6665d9b3f6dc29678461e911bded67f0aa149c30e57192a56c018641` |
| lupin_0.17.0-1_amd64.deb | 431,448,336 | `cbcbb3dd21457d32441d46e9ff63ed383584c7bb882304cd6d547787bfbc0153` |

Checksums: `dist/SHA256SUMS-0.17.0.txt`. Full evidence: `VERIFICATION.md`; private logs/renders are excluded from packages.
