# Lupin 0.17.5

- On-screen item cards have a 500 ms grace period before becoming recent items. A new item can replace the active card directly. Recent-row insertion, movement and container height animate independently of the active card, with bounded visible-row painting and reduced-motion support.
- Shop annotations retain stable identities when another row is temporarily missing. Covered listings retain their last confirmed visual presentation only under the same verified shop context; that presentation never creates a newly verified offer. Short native-tooltip fades no longer repeatedly reset the labels or their deal colors.
- Native title retries separate the decorative marker from the item-name glyphs. Exact catalog identity checks remain required; fuzzy or nearest-name pricing is not included. Initial window detection gains independently corroborated handling for a tall description crossing the footer rim.
- EXP and MESO headings start beyond the plus-sign gutter. The normal EXP overlay no longer repeats the rolling-window age. One tracking-page note reads “Rates based on the last 5 minutes”; warmup, paused and held-reading states remain available.

The screen-only boundary, full-market snapshot schedule, both local translation model bundles and pinned Minerva source remain unchanged. Private captures and diagnostics are excluded from installers. Builds and verification are recorded in VERIFICATION.md; live acceptance and native Windows game capture are separate from fixture/offscreen/package checks.

Uploads remain on hold. Host installation is separate:

```sh
sudo pacman -U /home/zach/Projects/maple-market-overlay/dist/lupin-0.17.5-1-x86_64.pkg.tar.zst
```

Windows: run Lupin-0.17.5-Windows-x64-Setup.exe. Debian/Ubuntu: install lupin_0.17.5-1_amd64.deb with apt.


## Local builds

Built and verified 2026-10-30. All four installed platforms pass the 534-test suite. Ten Rust tests and fourteen native fixture checks per reader pass; Windows execution uses Wine and physical game capture remains separate.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.5-Windows-x64-Setup.exe | 408,871,373 | `65b119aa2e04411a5348044c0856672c129d629771b4e91e5652adc2621b272b` |
| Lupin-Windows-x64.zip | 425,318,883 | `9e40ff10b65eab2dea08d81b070dd5e5f0b28dd7743e8c8003efea425b229815` |
| lupin-0.17.5-1-x86_64.pkg.tar.zst | 463,549,999 | `32f565166560cd0a5a893b526b6ac7752112b73c510b27af6d8fece6b76c6e0a` |
| lupin_0.17.5-1_amd64.deb | 431,455,080 | `36db341e4168916a726cd5e58d00919d7e0977edb58e493e224069e0f8ae7c07` |

All four hashes pass `dist/SHA256SUMS-0.17.5.txt`. Both translation bundles are retained, no dependencies were added, and sizes remain close to v0.17.4. Completed evidence is in `dist/VERIFICATION-0.17.5.md`; packaged documentation records staging-time checks. Host installation and uploads remain deferred.
