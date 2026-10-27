# Local Korean chat translation

Open **Translation** to enable local translation, translate now, see recent results, or change the shortcut. Default: **F12** on Linux, **F9** on Windows because Windows reserves F12. On Wayland the desktop authorizes all three app shortcuts in one session, separately from screen sharing. A desktop shortcut can also run `lupin --translate`. The first request enables and preloads the worker if needed; turning translation off unloads it.

Keep the game visible and screen reading active. Press the shortcut with the pointer near the message you want. Nearby speech bubbles are processed first, with up to four cards per snapshot. If the first scan finds nothing, one fresh-frame retry uses a slightly wider bubble-color tolerance; it does not start continuous scanning. English appears above the Korean original. Cards expire after eight seconds, or sooner if the source bubble moves, changes or is covered. This version does not follow moving bubbles; press the shortcut again once they settle. It does not yet read the expanded chat-history panel, megaphone banners, dark bubbles or arbitrary Korean text elsewhere on the desktop.

The source is the existing approved shared frame, cropped to the detected game area or an explicitly chosen reading area. No second capture session, game process access, input hook, window inspection, network translation, telemetry or automatic reply is used. Translation never uploads or stores screenshots or chat. Two small in-memory caches remember repeated text/crops until the worker exits. Price requests and their scheduler are independent.

## Meaning and numbers

Game phrases use a conservative glossary; ordinary text falls back to a local model. Partial translations retain unknown Korean and are labelled accordingly. The original remains visible because OCR and translation can both be wrong. A glossary does not establish mechanics or terminology frequency in Classic World.

Explicit amounts use English units: `25만` = `250k`, `250만` = `2.5m`, `1억` = `100m`. Bare `250` stays `250`; the app never supplies an unstated multiplier or currency. ATT values, levels and scroll percentages are not automatically interpreted as prices. A translation that drops, invents or changes a numeric value is rejected in favour of the original. This check cannot recover digits that OCR itself misread.

## Performance and resource boundary

The feature is off until enabled. Its one persistent worker preloads CPU-only Korean PP-OCRv5 mobile recognition and int8 OPUS-MT Korean–English. Recognition and translation use at most two compute threads each, sequentially, with passive waiting. Linux gives only this worker a lower scheduling priority. Idle time blocks on its own input pipe; there is no continuous chat OCR. Requests are bounded to one snapshot at a time, with a 1.5-second scan budget checked between bubbles. Price/EXP reading continues independently.

On 2026-10-27, the six user-provided screenshots were tested locally under the machine's existing load, without changing other workloads. After preloading, the first result on the five screenshots containing Korean speech bubbles arrived in **72–225 ms**, including local IPC/OCR/translation. The busiest full scan took **831 ms**; repeated full scans ranged **19–29 ms**. The sixth image had no readable Korean speech bubble and returned no card. Worker startup was **778 ms**, warm PSS about **229 MiB**, with zero CPU ticks during a two-second idle sample. These measurements exclude live capture age, compositor latency and fade completion; they do not guarantee a half-second live response on every machine. Private screenshots and detailed transcripts are not shipped.

## Source builds

Install `requirements.txt`, then run `python scripts/prepare_chat_models.py`. Public inputs, versions, sizes and SHA-256 values are pinned in `packaging/chat-models.json` and the runtime manifests. The preparation script converts the original Marian model to int8 with CTranslate2 4.8.4 and verifies the resulting files. Models live in the ignored `models/korean-chat` folder; installers include them, so translation needs no network download at runtime. No GPU, PyTorch or cloud API key is required. Licenses and attribution are in THIRD_PARTY.md and the model folder.
