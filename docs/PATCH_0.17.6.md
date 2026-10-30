# Lupin 0.17.6

- On-screen item cards remain for one second between sightings. When the grace expires, the empty card area collapses and recent items move up without needing a map or window change. First appearances and interrupted transitions measure the current card layout.
- Hovering a shop listing's verified description switches the Prices page to that item's card, then animates back to the retained shop list when the description closes. This GUI focus does not hide game labels, create history entries for hidden listings or change offer verification.
- Inventory pricing distinguishes the hovered item from its equipped comparison when native descriptions fit against the right edge. Selection uses captured inventory and description geometry rather than choosing the nearest name or whichever item has a price.
- Recent-item asking-price captions read “Last seen price”, with space for long amounts. Their underlying price meaning and retention rules are unchanged.
- “Show meso overlay” aligns with the right edge of the tracking page.
- A stable captured character identity can refine its display spelling from corroborating fresh reads. Corrections preserve gains, rates, timers and session identity. Legacy history without a matching visual proof is not renamed, and opaque proof keys stay out of CSV exports.
- Korean scanning alternates bubbles and other visible text, including colored chat, shops and megaphones. Matching bubble/chat arrivals share one event and prefer the bubble's location; a verified partial bubble upgrades its existing card instead of leaving a second fragment behind.
- Translation popups size around their text, stay closer to the source and avoid other cards where space permits. Scanning and finishing states agree between the GUI and indicator; restarting rejects obsolete work.
- Complete party-recruiting phrases retain explicit jobs and person counts. Mixed sentences now reach the local model before a partial-glossary fallback, with known-term and numeric checks. The original Korean remains available because local prose translation is still approximate.

The screen-only boundary, full-market refresh schedule and both bundled local translation models remain unchanged. No game integration or fuzzy item-name lookup was added. Private diagnostic captures and recordings are excluded from packages.

Verification and platform limits are recorded in VERIFICATION.md and beside the local builds. Uploads and permanent host installation remain separate. The active app and sharing session are not reloaded while recording is in progress.

```sh
sudo pacman -U /home/zach/Projects/maple-market-overlay/dist/lupin-0.17.6-1-x86_64.pkg.tar.zst
```

Windows: run Lupin-0.17.6-Windows-x64-Setup.exe. Debian/Ubuntu: install lupin_0.17.6-1_amd64.deb with apt.

## Local artifacts

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Lupin-0.17.6-Windows-x64-Setup.exe | 408,892,403 | `fc43f41c9a6ef8f7c201d11eeeecf0da1bc378846d63b0fa6a00591b1e0e75fb` |
| Lupin-Windows-x64.zip | 425,375,939 | `a12eda4138711cb6d636219198ecf8c52e4ddd34379ecc824f24fa2d43dff951` |
| lupin-0.17.6-1-x86_64.pkg.tar.zst | 463,640,586 | `b88a1027b50e36e33f141c0f3cb5640983ddd78e103831e5ee9584e663e89df4` |
| lupin_0.17.6-1_amd64.deb | 431,555,580 | `ef8cea7d2a5c2d375a9d476e1dd1ee068a16f1eddc1f14008ade0f4152c8b316` |

The final transaction report is supplied as `dist/VERIFICATION-0.17.6.md`; `dist/SHA256SUMS-0.17.6.txt` verifies all four files.

597 source tests and all four installed suites pass. Native Rust checks pass 20 tests; GNU, musl and Windows/Wine readers each pass 31 supplied/generated image/sequence checks. Physical Windows game capture and live crowded-scene acceptance remain separate from these results. Nothing is uploaded or installed on the host.
