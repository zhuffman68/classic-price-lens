# Lupin 0.17.9

## Korean reading

- Recognize informal party-invitation requests, including `팟점여` and related forms.
- Use a bounded model-supplied OCR alternative only when one uncertain syllable
  completes an unambiguous supported phrase. Preserve names, explicit amounts and
  unknown text. Mark possible corrections and retain the first OCR reading.
- Check recently verified Korean text before full-window detection on a rescan.
  Cache unchanged English/empty candidates and continue the ordinary full-window
  queue. At most two priority results prevent new text from being starved.
- Match meaningful text and speaker headers independently of `@` padding, and
  recover modest movement with a bounded local pixel-template search. Uniform,
  different-speaker and ambiguous matches reject.
- Reuse recent-result widgets. Group consecutive equal same-speaker results with
  a repeat count without merging the underlying arrival records. Repeated scans
  of a continuous visible message do not create a new arrival.

## Documentation

The README is a shorter showcase of the four tabs with the approved price and
tracking GIFs. The app icon is removed from its header. Technical detail remains
in linked documentation. Demo GIFs are not included in application packages.

## Distribution

Normal releases now include only the Windows installer, Arch/Manjaro package and
Debian/Ubuntu package. Portable Windows downloads and patches are retired.
Checksums, signing preparation and publishing plans use these three native
formats. Existing portable users should switch to Windows Setup manually.

## Verification and delivery

Recorded-bubble OCR replay resolves the demonstrated ambiguous syllable and
produces the complete party invitation. The original remains available and its
possible correction is visible. Synthetic crowded-window first reads remain
load/font dependent; a fast known-source rescan is not a live half-second
guarantee. Complete source checks and package transaction results are recorded
in VERIFICATION.md and the report beside the final builds.

Both translation model bundles, runtime dependencies, capture helpers and native
OCR binaries are unchanged. Tests use isolated displays/roots and local fixtures.
No installed app is reloaded or upgraded; the user installs this release using
the app's signed GitHub updater. A real native updater authentication/install
remains a separate user acceptance check.
