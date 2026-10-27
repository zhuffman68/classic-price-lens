# Local Korean chat translation

The Translation tab has independent **Read Korean** and **Write Korean** pages. Reading uses the approved shared game image; writing needs only an English draft. Neither direction uses cloud translation or game input.

## Read Korean

Open **Read Korean** to enable speech-bubble translation, translate now, see recent results, or change the shortcut. Default: **F12** on Linux, **F9** on Windows because Windows reserves F12. On Wayland the desktop authorizes the four app shortcuts in one session, separately from screen sharing. A desktop shortcut can also run `lupin --translate`. The first request enables and preloads the worker if needed; turning speech-bubble translation off unloads its worker.

Keep the game visible and screen reading active. Press the shortcut with the pointer near the message you want. Nearby speech bubbles are processed first, with up to four cards per snapshot. If the first scan finds nothing, one fresh-frame retry uses a slightly wider bubble-color tolerance; it does not start continuous scanning. English appears above the Korean original. Cards expire after eight seconds, or sooner if the source bubble moves, changes or is covered. This version does not follow moving bubbles; press the shortcut again once they settle. It does not yet read the expanded chat-history panel, megaphone banners, dark bubbles or arbitrary Korean text elsewhere on the desktop.

The source is the existing approved shared frame, cropped to the detected game area or an explicitly chosen reading area. No second capture session, game process access, input hook, window inspection, network translation, telemetry or automatic reply is used. Translation never uploads or stores screenshots or chat. Two small in-memory caches remember repeated text/crops until the worker exits. Price requests and their scheduler are independent.

## Meaning and numbers

Game phrases use a conservative glossary; ordinary text falls back to a local model. Partial translations retain unknown Korean and are labelled accordingly. The original remains visible because OCR and translation can both be wrong. A glossary does not establish mechanics or terminology frequency in Classic World.

Explicit amounts use English units: `25만` = `250k`, `250만` = `2.5m`, `1억` = `100m`. Bare `250` stays `250`; the app never supplies an unstated multiplier or currency. ATT values, levels and scroll percentages are not automatically interpreted as prices. A translation that drops, invents or changes a numeric value is rejected in favour of the original. This check cannot recover digits that OCR itself misread.

## Performance and resource boundary

The feature is off until enabled. Its one persistent worker preloads CPU-only Korean PP-OCRv5 mobile recognition and int8 OPUS-MT Korean–English. Recognition and translation use at most two compute threads each, sequentially, with passive waiting. Linux gives only this worker a lower scheduling priority. Idle time blocks on its own input pipe; there is no continuous chat OCR. Requests are bounded to one snapshot at a time, with a 1.5-second scan budget checked between bubbles. Price/EXP reading continues independently.

On 2026-10-27, the six user-provided screenshots were tested locally under the machine's existing load, without changing other workloads. After preloading, the first result on the five screenshots containing Korean speech bubbles arrived in **72–225 ms**, including local IPC/OCR/translation. The busiest full scan took **831 ms**; repeated full scans ranged **19–29 ms**. The sixth image had no readable Korean speech bubble and returned no card. Worker startup was **778 ms**, warm PSS about **229 MiB**, with zero CPU ticks during a two-second idle sample. These measurements exclude live capture age, compositor latency and fade completion; they do not guarantee a half-second live response on every machine. Private screenshots and detailed transcripts are not shipped.

## Write Korean

**F8** opens an independent, compact composer; the same draft is available inline on **Write Korean**. The shortcut is configurable alongside the other three actions. `lupin --compose` opens the running app's composer through its own local IPC. Wayland uses the portal's activation token to focus only Lupin's own popup. No game handle, input listener, synthetic keystroke or automatic paste is used.

Typing produces a local preview after a 180 ms debounce. Only **Enter** or **Translate & Copy** writes the current validated Korean draft to the OS Unicode clipboard. A native notification and inline confirmation acknowledge the copy. The user chooses the chat field, pastes and sends. Editing, closing or cancelling the popup prevents a late translation from copying. Nothing saves drafts or outgoing history to disk; the small result cache lasts only for the app session.

Common shorthand includes WTB/WTS, B>/S>, LF/LFM/LF1M/LFG, KPQ/PQ, WG, GFA/GMA, ea, c/o, s/b, a/w, pmo, firm/nego/obo, whisper requests, cc/ch, levels and common social abbreviations. Exact supported trade/party/social fragments use a deterministic glossary. Known catalog item names remain English; the model must preserve masked item/map names and mentions exactly once. Ambiguous shorthand such as PC/PT/MA stays visible with a note rather than receiving a guessed interpretation. English item names remain appropriate to the server's catalog; this does not invent Korean official names.

Numeric validation checks explicit values, multipliers, currency and percentage roles. Equivalent Korean amounts are restored to the user's English notation before copying: 250k and 2.5m remain 250k and 2.5m. Bare 250 never becomes 250k or an invented meso amount. A missing/changed protected value blocks copying. Validation cannot establish the correctness of ordinary prose, so freeform output is labelled approximate.

Freeform English uses the original Helsinki-NLP/Tatoeba **2022 English–Korean transformer-big** model, converted to CTranslate2 int8. Its separate worker loads only when a draft needs it, uses at most two passive CPU compute threads, and unloads after 90 seconds unused. Disabling speech-bubble reading does not disable writing. The bundled model adds about 211 MiB on disk; warm worker PSS measured about 263 MiB. During a two-second idle sample it used zero CPU ticks.

On 2026-10-27, a local 12-draft benchmark measured **190–320 ms** for warm freeform inference and **770 ms** for the first cold freeform draft, including worker IPC and validation. Glossary fragments took about **0.1–1.1 ms**. These measurements exclude the typing debounce, OS focus/clipboard delivery and compositor presentation. Existing workloads were left untouched. They are not a half-second guarantee, and numeric preservation is not a translation-quality guarantee.

The user manually confirmed Korean clipboard paste in their Linux game setup. Unicode clipboard/inference/installer checks under Wine remain separate from native Windows game paste and focus behavior.

## Source builds

Install `requirements.txt`, then run `python scripts/prepare_chat_models.py`. Public inputs, versions, sizes and SHA-256 values are pinned in `packaging/chat-models.json`, `packaging/compose-models.json` and the runtime manifests. The preparation scripts convert the original Marian models to int8 with CTranslate2 4.8.4 and verify the resulting files. Models live in ignored `models/korean-chat` and `models/english-korean` folders; installers include them, so translation needs no network download at runtime. No GPU, PyTorch or cloud API key is required. Licenses and attribution are in THIRD_PARTY.md and each model folder.
