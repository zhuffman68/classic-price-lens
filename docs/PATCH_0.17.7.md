# Lupin 0.17.7 — source changes

## Prices

- Increase active-card GUI grace to two seconds. Brief unknown names in the same
  verified shop slot retain the previous presentation, without restoring an old
  observation, overlay identity, asking price or individual API request.
- Reserve a constant narrow scroll gutter. Removing a scrollbar no longer widens
  cards, rewraps their text and prematurely finishes the active/history transition.
  Empty scrollbar handles/tracks are not painted.
- Resolve a mostly self-covered native title only through its exact known shop
  slot, current pointer, matching exposed page guards and independent native body.
  Contradictory items/pages and unproved sources still reject; no fuzzy search.
- When the hovered row's listing label overlaps its description, place one clear
  reference outside the description. Clear listings get no duplicate reference.
  Fading pixels do not change this placement decision.

## Application updates

- Public GitHub stable-release checks on launch and a configurable timer; default
  six hours, with Check now and separate launch/periodic toggles.
- A Settings badge, tray notification/action and compact Download & install sheet
  without moving Prices content. Announcements are deduplicated by version.
- Pinned Ed25519 signatures, exact platform/version identities, hashes, sizes,
  redirect limits, one background job, cancellation and persisted rate backoff.
  Saved offers are reverified so a retry does not require another network check.
- Native per-user Windows installation or portable directory swap. Linux uses a
  narrow root-owned polkit helper, independently verified/root-staged artifacts,
  exact native package identity checks and the normal package manager.
- Installation begins after explicit commit and the GUI's pipe closes. Tracking
  is saved; settings, watchlist and caches remain in their user directories.
  Result receipts announce completion/failure once after relaunch. Windows closes
  capture helpers before replacing DLLs; signed compatible releases may reconnect.
- Both model bundles and Python requirements are unchanged. Patch processing is
  chunked, with capped decoder memory and a verified full-download fallback.

Actual archive probes found a useful 22.7 MB patch for the 425.4 MB portable ZIP.
Native installer/package patches remain nearly full-sized and are omitted by the
80-percent usefulness rule. Native updates therefore use full downloads with the
current packaging. See [update details](UPDATES.md).

## Verification and release status

- 627 source tests pass, with three platform/offscreen skips, in 66.513 seconds.
- 155 Windows UI/core tests pass under the bundled runtime in isolated Wine in
  46.231 seconds. Nine local release-script tests pass. These are not native
  Windows installer transactions or physical gameplay acceptance.
- All four existing 0.17.5 → 0.17.6 archives reconstruct with exact target SHA-256
  hashes. Peak patch-process RSS is about 81–96 MiB. Real Arch/DEB metadata queries
  confirm the package-name/version/architecture checks without installing them.
- The test bootstrap sets offscreen mode before QApplication. GUI/native-helper
  QA runs on distinct virtual displays with Wayland unset, protecting the desktop.
- Offscreen layout screenshots use fake items/prices and no OS capture. Native
  readers, capture code, vendor revision and both model bundles are unchanged.
- No 0.17.7 installer/package build, host installation, live app reload, source
  push, publication or repository visibility change has been performed. Native
  updater transactions and a signed public-feed check remain release checks for
  the eventual packages. Existing 0.17.6 artifacts are unchanged.

## GIF

The separate 13.8-second two-shop GIF retains the original capture and timing.
Its stable source-weighted palette restores colored label fidelity. No source
grading or transfer adjustment is used in v3. Private video/evidence remain
outside application packages and source commits.
