# Application icon

The approved icon keeps the original v3 orange maple leaf and magnifier artwork, with a revised silver rim, charcoal keyline and stepped corners. Its frame was checked against a classic skill-list screenshot and previewed against black at 32px and 48px before approval.

The original motif was drawn after inspecting genuine 32×32 classic skill icons: Power Strike, Slash Blast, Iron Body, Improved HP Recovery, Meso Up, Pickpocket and Haste.

Research: [MapleRoyals skill library](https://royals.ms/forum/threads/mapleroyals-skill-library.209540/), which links the original 32×32 reference artwork. Only art style was referenced; this private server is not a source for Classic World balance or market prices. Reference images and rejected proposals are not included in the release.

The artwork and revised frame were produced with the **built-in image_gen tool**. During final export, the v3 interior was retained pixel-for-pixel: all 780 interior pixels match, with only the surrounding frame and its four corner pixels replaced. This avoids softening the artwork through repeated redraws. Each PNG and Windows ICO size uses nearest-neighbor scaling from the final native 32px tile. The panel, tray, desktop shortcuts and README use this same approved artwork.

Production files are `price_lens/resources/icon-*.png`, `price_lens/resources/icon.png`, and `packaging/icon.ico`. The editable master is `artwork/classic-price-lens-icon-master.png`. The frame prompt below describes the generated input; the unchanged v3 interior was restored in the final native export.

## Border generation prompt

Use case: precise-object-edit
Image 1 is the EDIT TARGET, a pixel icon with an orange leaf and magnifying glass and a layered silver frame. Image 2 is the user's classic MapleStory skill-icon reference.
Keep the layered white/silver/charcoal border in Image 1, and keep the leaf and magnifying glass. Correct ONLY the mottled, smoky and partly transparent BACKGROUND inside the frame: replace all of it with a clean, completely opaque flat pale ivory color. Remove every trace of noise, texture, grain, clouding, gradients and transparent holes. All pixels inside the frame must be opaque.
The rim must retain its actual nested structure like Image 2: a dark outside contour with tiny stepped rounded corners, a continuous bright white/silver rim, and a fine dark inside keyline separating that rim from the ivory center. Keep this rim wide enough to remain visibly layered when the whole icon is 32 pixels square: three logical pixels total, with each line crisp and one pixel wide. Neutral gray and silver only on the rim, no blue stripe. The bright rim must be continuous on all four sides and plainly visible against black.
Preserve the orange leaf, gold magnifying glass, and compact 32x32 pixel-art feel. Draw only sharp uniform square pixels with flat colors; no smooth shading or antialiasing. Deliver one full-bleed square skill tile on a fully opaque canvas. No surrounding mockup, padding, extra objects, text, or transparent background.


## Lupin header (v0.7.0)

The application icon remains the approved skill-style artwork. The header adds an unchanged, three-frame classic Lupin animation from OSMS Data Explorer and an SVG wordmark outlined from Nexon's official MapleStory Bold font. Source links and notices are in THIRD_PARTY.md and resources/fonts/LICENSE-Maplestory.txt. Runtime artwork is entirely local; the movie pauses when hidden, minimised, or Reduce motion is enabled. The README uses the same local WebP and SVG assets.

## Lupin header (v0.8.0)

The wordmark now uses Pixelify Sans SemiBold (SIL OFL 1.1), outlined to local SVG paths. The unmodified font and license are bundled. The approved orange application icon is unchanged.

The complete classic GMS v83 Lupin exports are used instead of OSMS's shortened WebP previews. Public source: https://maplestory.io/api/GMS/83/mob/3210800/render/move and https://maplestory.io/api/GMS/83/mob/3210800/render/attack1 . No installed game files were read. Nexon owns the underlying character artwork.

Walk delays: 120, 150, 150, 250 ms (670 ms). Attack delays: 200, 150, 300, 100, 100, 250, 300, 100, 100, 150, 500 ms (2250 ms). Qt plays the original files at 100% speed. After 18 complete walk cycles, the header plays one attack sequence. All frames are drawn at native pixel size without interpolation; the fixed canvas accommodates both animations. Both pause while hidden/minimized or with Reduce motion. The schedule is decorative, not an assertion about Classic World's combat AI cooldowns. Classic World timing has not been measured live; the reference is the complete original-game export.
