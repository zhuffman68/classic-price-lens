# Public HUD test fragments

Derived from the MIT-licensed public samples at Minerva revision `7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`:

- `area-minimap.png`: `(0, 0, 356, 108)` from `samples/minimap/victoria-road__kerning-city.png`; static header and map title.
- `area-footer-edge.png`: `(332, 1158, 1248, 16)` from `samples/minimap/victoria-road__kerning-city--window.png`; static border above the character/status portion, without names or chat.
- `area-level-box.png`: `(7, 1, 76, 37)` from `samples/status-bar/34__wizard-(fire,-poison)__Egbert--ideal-ratio-1366x768.png`; LV box and level digits only, without job/name.

Tests compose these on generated backgrounds, move and scale them, cover anchors and place real public shop fixtures outside the resulting game area. No live desktop or game input is used in automated tests. Local captures used for additional verification remain in ignored evidence and are not distributed.
