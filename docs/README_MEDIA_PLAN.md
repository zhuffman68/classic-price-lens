# README screenshots and demos

The README is arranged by feature, with commented media slots beside the relevant
copy. Replace each comment with its screenshot or preview when a real capture is
ready. Keep uncaptured slots invisible; do not add broken image links.

All demonstrations should use the running app and actual game pixels. Synthetic
test balances and prices are useful for testing, but are not showcase footage.
The user drives game actions; recording must remain ordinary OS screen capture.

## Capture list

| Feature | What to capture | Suggested asset |
| --- | --- | --- |
| Overview | Classic World and the compact app side by side, with one readable overlay | `lupin-overview.png` |
| Shop prices | Open a populated shop, let references load, hover a listing and move away | `shop-prices.gif` |
| Inventory/equipment | Hover an inventory item and an equipped item; keep the native name and market card readable | `inventory-equipment.png` |
| Price search | Type a name, show item thumbnails, select a result, inspect the price age, then clear it | `item-search.gif` |
| EXP/meso tracking | Track real training with a visible wallet; show aligned rates, timer, ETA and bottom-left overlay | `tracking.mp4` |
| History | Show actual labeled runs, character/map filtering and the CSV export control | `training-history.png` |
| Read Korean | Show Korean text, activate the scan and capture the English/original popup | `read-korean.gif` |
| Write Korean | Type a trade message, review the Korean preview and explicitly copy it; include the notification | `write-korean.gif` |
| Desktop controls | Show the display dropdown, horizontal page slide, hotkey editor and tray menu | `desktop-controls.mp4` |

One clear still can cover several related options. The overview should be a
clickable full-size image; the detailed feature crops should be readable at normal
README width. Keep captures focused on the app and game, rather than the whole
desktop.

## Recording order

1. Capture shop prices, inventory/equipped items and search while in a market.
2. Record training once rates have stabilized. Keep the inventory wallet visible
   for the meso example; record enough real progress to show useful values.
3. Save the run, then capture history with map labels and notes.
4. Capture a real Korean message when one is visible. The writer and desktop
   controls can be recorded independently of gameplay.

The already-approved sharing session should be reused where practical. A smooth
desktop recording can be kept as the source for shorter README crops. Do not add
game input automation to make a demonstration.

## Formats and size targets

- **PNG** for screenshots and UI text. Avoid scaling a still up after capture.
- **GIF** for short loops of roughly 4–8 seconds. Crop first, then use a limited
  palette and about 12–15 fps. Aim for 2–3 MB or less per preview.
- **MP4/H.264** for longer sequences, preferably 10–25 seconds with no audio.
  Keep text sharp, use a fast-start file and aim for a few MB per clip.
- Keep a higher-quality source recording outside the repository; commit only the
  selected, cropped media under `docs/media/`.

Use static or GIF previews directly in the README. For a longer video, link a
still preview to the MP4 so the README remains useful without embedded playback.

Example, once the files exist:

```md
![Shop price references beside the listings](docs/media/shop-prices.gif)

[![EXP and meso tracking](docs/media/tracking-preview.png)](docs/media/tracking.mp4)
```

Check each preview at ordinary README width before including it. The item name,
price or rate that demonstrates the feature should be readable without zooming.
Publishing remains on hold; preparing media does not upload it.
