# Lupin artwork

## Application icon

The approved master is `artwork/lupin-icon-master.png`, a native 32×32 Lupin
portrait with a classic skill-style frame. The user approved proposal 1; rejected
proposals and private reference screenshots are not release assets.

`scripts/export_icons.py` reads that master directly. It writes native-size PNGs
and the scalable pixel-rectangle SVG under `price_lens/resources/`, plus the
Windows `packaging/icon.ico`. Integer enlargements retain the source pixels;
fractional sizes use one filtered resize from the master. The `Lupin-scaled` and
`lupin-scaled.ico` resource names refresh shell icon caches while preserving
application identity. Do not redraw the approved master when changing exports.

The portrait was created with the built-in image_gen tool using a public classic
Lupin sprite and the supplied skill-border reference. Nexon owns the underlying
character design. No installed game asset was accessed. See
[THIRD_PARTY.md](../THIRD_PARTY.md) for attribution.

## Header sprite and wordmark

The bundled Lupin walk/attack GIFs are complete public original-game exports.
Their original frame delays are preserved, with no interpolation. The header
pauses while hidden/minimized or with Reduce motion enabled. Its attack schedule
is decorative; it does not establish Classic World combat cooldowns.

The local SVG wordmark uses outlined Pixelify Sans SemiBold glyphs. The unmodified
font and its SIL OFL notice are bundled. MapleStory Bold is retained separately
as a Korean glyph fallback.

The README header uses the transparent sprite GIF and transparent SVG wordmark.
Neither has a rectangular background. Keep only the width attribute in README
image markup: GitHub's image fallback can add a muted background when both width
and height are specified. Verify light/dark and signed-in/out rendering after a
README change; do not paint a GitHub theme color into the artwork.

Older icon and header research is retained in the source-only documentation
archive. Historical masters under `artwork/` are provenance, not export inputs.
