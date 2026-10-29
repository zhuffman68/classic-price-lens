# Lupin 0.17.4

- Both EXP and meso per-minute/per-hour figures use a recent five-minute window; gain totals cover the whole session. Meso rates retain their ten-second minimum, separate from EXP's thirty-second initial warmup.
- Pause freezes the current pace and ETA. Resume rebaselines new readings while preserving both windows. Map changes save history segments without clearing pace or cumulative gains. Stop and save ends the session; a new Start resets totals, clocks and rate history.
- Captured name shapes stabilize character identity when OCR alternates characters such as Z and 2. Proofs use the same submitted frame as the EXP reading, with bounded normalized word/glyph templates. Verified scale variants retain the identity key. Genuine visual changes still require confirmation; missing evidence holds known data. No game integration or name-specific alias was added.
- Elapsed clocks tick each second, independently of two-second gains/rates/ETA updates. Held/reacquiring states explain retained EXP values.
- The percent unit is larger. Meso figures gain plus signs and the GUI uses the overlay's green. The normal MESO heading omits Session pace while Paused and Log hidden remain. Its footer shows the last confirmed pickup, retaining it across maps and pauses.
- Cards can narrow to 200 pixels in the empty HUD corner before moving above the status bar. Large values retain aligned units and scale to their available space. The level badge removes excess automatic indentation. Both ETA labels use a middle dot.
- Shop price-change chips sit higher in the item-name row, with more space before the market/last-sale line.

The 503-test source suite passes with three platform/offscreen skips. New checks cover captured-name spelling changes and public UI-scale variants, map continuity, pause/resume and Stop/Start boundaries, recent meso bucket trimming, last-pickup persistence, independent clock cadence, narrow-corner placement and real reader IPC proofs. Source and installed-package evidence are recorded in VERIFICATION.md.

The existing sharing helper is retained. A live Linux preview reads the currently visible character, reaches an EXP pace after its initial warmup, freezes values/clock during a brief pause and resumes without another warmup. The open shop obscures the pickup log, so real meso arrivals remain a separate live check; counting/window behavior is verified with controlled replays. Private captures and diagnostics are excluded from packages.

Windows/Wine, pacman, Debian 12 and Ubuntu 22.04 each pass the 503-test installed suite. Package transactions, offline OCR/overlay checks and cache preservation pass, including running-app upgrade/removal on Windows. These checks do not establish native Windows gameplay capture. The final normal source preview retains the approved share and starts tracking stopped; permanent installation remains separate.

Uploads remain on hold. Permanent host installation is separate:

```sh
sudo pacman -U /home/zach/Projects/maple-market-overlay/dist/lupin-0.17.4-1-x86_64.pkg.tar.zst
```

Windows: run Lupin-0.17.4-Windows-x64-Setup.exe. Debian/Ubuntu: install lupin_0.17.4-1_amd64.deb with apt. Final artifact hashes and completed post-build verification are supplied beside the builds.

## Local builds

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.4-Windows-x64-Setup.exe | 408,845,113 | `b8e431549972b4e88963e672dbd742a63a9017e640f36cf8d3036fd2cd0abcdf` |
| Lupin-Windows-x64.zip | 425,298,973 | `28ea9c2a5aa94a387b6e4e2dfd4e8fb26901e14af6caddbcbdf78ed110bdbe72` |
| lupin-0.17.4-1-x86_64.pkg.tar.zst | 463,538,112 | `cb48b01d2bb58f7e272eed5990520048d3c4e0c8aea65af0fa42eb464dec7af9` |
| lupin_0.17.4-1_amd64.deb | 431,463,292 | `4f5363e9cc68706f1ca9d80158bf18f4410dba4cc7c13eb3dea3b60b12021682` |

All four checksums are verified in `dist/SHA256SUMS-0.17.4.txt`. The builds retain both translation models and the unchanged native OCR readers. The Windows test wait loop explicitly yields to its Python worker while pumping Qt; no database-refresh behavior was changed for that test correction. Packaged verification describes staging-time checks; the completed record is supplied separately as `dist/VERIFICATION-0.17.4.md`.
