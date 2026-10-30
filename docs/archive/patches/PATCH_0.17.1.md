# Lupin 0.17.1

Local patch; uploads remain on hold.

- Compact EXP and meso overlays always stack vertically above the bottom-left status bar. Placement preserves the pixels used to identify Classic World, fixing the overlays' own detection/disappearance feedback.
- Separate **Show EXP overlay** and **Show meso overlay** checkboxes on the tracking page and in Settings. Existing visibility preferences are retained during migration.
- Leaving Both display mode removes its extra raw-EXP line from the reused compact card.
- Long detected map names shorten at the right edge instead of losing their first letters. Hover for the full name; session labels retain the original value.
- Shop panes with similar borders no longer count as item descriptions. Occlusion requires a dark native interior and ignores Lupin's own labels as evidence. Stale occlusion is cleared when the description is gone.

## Validation

The final 471-test source suite passes with three platform/offscreen skips. Real annotation pixels preserve native HUD detection across four window/UI-scale combinations. A private 18-second shop recording reproduces the prior dimming cycle; nine sampled frames reject the false pane after the fix. Real public tooltip and warm/comparison-panel checks still pass. UI handoffs reused the approved sharing helper. The user subsequently closed Lupin; it was left closed.

The final Windows/Wine, pacman, Debian 12 and Ubuntu 22.04 packages each pass all 471 installed application tests, with eight/four/five/five platform skips. Installation, offline OCR/overlay, upgrade/removal where supported, file checks and cache preservation pass. Windows initially exceeded a test-harness deadline; the final verbose suite passes in 98.844 seconds. Physical Windows gameplay is not established by Wine.

The user deferred live gameplay checks. In-game pickup/pet bursts, live trades and physical Windows capture remain separate acceptance checks. Private recordings, settings and image/database caches are excluded from source and packages. The pinned reader/vendor/model bundles are unchanged.

## Install locally

Manjaro / Arch:

```sh
sudo pacman -U /home/zach/Projects/maple-market-overlay/dist/lupin-0.17.1-1-x86_64.pkg.tar.zst
```

Debian / Ubuntu:

```sh
sudo apt install ./dist/lupin_0.17.1-1_amd64.deb
```

Windows 10/11 x64: run `dist/Lupin-0.17.1-Windows-x64-Setup.exe`. A portable ZIP is also built. Existing settings and cached data are preserved; no archive encryption is used.

## Artifacts

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.1-Windows-x64-Setup.exe | 408,829,051 | `fafaa91e1ca2f82bb13ef2f0cd67d9f9e5cc99c7a7226d73698d5e38b7ef4999` |
| Lupin-Windows-x64.zip | 425,280,647 | `d038160952998b522dcb3d6f83438f559bff17fae75428f66698b0704807b789` |
| lupin-0.17.1-1-x86_64.pkg.tar.zst | 463,513,160 | `36904f2ee214820f5a6f9a8c0b32ae11e0d3ffcebadcc06edf565ddae4e8ffc3` |
| lupin_0.17.1-1_amd64.deb | 431,463,008 | `b1de54239e72c7cedb46b7004186a4b90b80519f53439abd02721323f9b5441d` |

Checksums and package evidence are recorded in `VERIFICATION.md` and `dist/SHA256SUMS-0.17.1.txt`. Permanent host installation remains deferred to the user.
