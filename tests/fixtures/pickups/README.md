# Synthetic pickup OCR inputs

These PNGs contain generated system-log text, not screenshots or player data.
They preserve identical input pixels on Linux and Windows. Generating `Arial`
text during a test depended on the host's font mapping; the isolated Wine
environment sometimes produced missing-glyph boxes instead of letters.

The canonical rasters were rendered with Qt 6.11.2, Liberation Sans (the Linux
Arial substitute), and antialiasing disabled. Most use 14-pixel text, a dark
background, and right alignment. `same-amount-sizes.png` preserves the original
12-, 14-, and 16-pixel repeated-amount case. The faded case moves the same text
down 20 pixels and changes its brightness from `#eeeeee` to `#555555`.

`manifest.json` records the literal text, case parameters and PNG hashes.
Tests still run the native OCR engine and validate its amounts, non-currency
anchors, geometry, visual fingerprints, invalid-number rejection and budget
behavior. No production parser rules are relaxed for these fixtures.
