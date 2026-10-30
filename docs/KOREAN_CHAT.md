# Local Korean chat translation

The Translation tab has independent **Read Korean** and **Write Korean** pages. Reading uses the approved shared game image; writing needs only an English draft. Neither direction uses cloud translation or game input.

## Read Korean

Enable **Korean translation** under Read Korean, or press **Super/Win+F11** to enable it and begin a scan. All four shortcuts use the same configuration flow: the OS shortcut chooser on Wayland, or one shared editor on Windows/X11. A desktop shortcut can also run `lupin --translate`. Disabling reading unloads its worker; writing remains independent.

Each activation scans the full detected Classic World window for four seconds by default, without requiring the pointer near a message. The scan alternates visible speech bubbles with high-confidence text-line candidates, including colored chat, shop text and megaphones. Source roles require structural or explicit prefix/context evidence; unidentified prose stays ordinary text. It has one worker and no overlapping frame jobs. Pressing the shortcut again restarts the scan window, cancels older work between model operations and rejects late results. Scan time is adjustable from 1 to 10 seconds. The GUI and overlay distinguish scanning from finishing an outstanding translation.

English appears beside the source with the Korean original below. Cards size around their text and prefer a five-pixel source gap, avoiding other popups and existing annotations when space permits. Stable placement follows modest verified movement instead of repeatedly changing sides. Cards remain while matching source pixels are visible and stay another 1.5 seconds after disappearance by default. That delay is adjustable from 0 to 5 seconds. Scanning/translating/loading status appears briefly in game; a no-result notice disappears after 2.5 seconds. Recent text remains on the Translation page until cleared or the app exits. A source that moves far, is obscured or uses unusual colors may require another scan; recognition is not guaranteed for every text style.

A short, bounded event ledger coalesces matching speaker/message text arriving in both a bubble and chat. It prefers the visible bubble anchor, retains both source locations for visibility checks and keeps a single history entry. A verified partial crop of the same bubble can upgrade to its complete reading atomically. Different speakers and separately established repeat messages remain independent; there is no global fuzzy name/text merge.

The source is the existing approved shared frame, cropped to the detected game area or an explicitly chosen reading area. No second capture session, game process access, input hook, window inspection, network translation, telemetry or automatic reply is used. Translation never uploads or saves screenshots or chat to disk. Bounded in-memory caches remember repeated text/crops until the worker exits. Price requests and their scheduler are independent.

## Meaning and numbers

Complete game phrases use a conservative glossary or explicit party-recruiting/join templates. Ordinary and mixed sentences reach the local model before any partial-glossary fallback; known terms and explicit numeric roles must survive. Partial translations retain unknown Korean and are labelled accordingly. The bundled model can still mistranslate ordinary grammar. The original remains visible because OCR and translation can both be wrong. A glossary does not establish mechanics or terminology frequency in Classic World.

Explicit amounts use English units: `25만` = `250k`, `250만` = `2.5m`, `1억` = `100m`. Bare `250` stays `250`; the app never supplies an unstated multiplier or currency. ATT values, levels and scroll percentages are not automatically interpreted as prices. A translation that drops, invents or changes a numeric value is rejected in favour of the original. This check cannot recover digits that OCR itself misread.

## Performance and resource boundary

The feature is off until enabled. One CPU-only worker preloads the existing PP-OCRv5 recognition and int8 OPUS-MT models. Inference uses at most two passive compute threads; Linux lowers only this worker's scheduling priority. There is no continuous OCR after the requested scan ends. Frames remain in memory, pending jobs do not accumulate, and price/EXP reading continues independently. Disabling unloads the worker.

The six supplied screenshots are private test inputs. First-result timings vary with existing machine load, model/cache warmth, the number of English candidates and whether the message is a bubble or a banner. The half-second target is a goal rather than a guarantee; capture age, compositor presentation and appearance animation add time. Current release measurements and remaining platform limits are in VERIFICATION.md. No other application or workload is stopped or reprioritized for benchmarking.

## Write Korean

**Super/Win+F8** opens an independent, compact composer; the same draft is available inline on **Write Korean**. The shortcut is configurable alongside the other three actions. `lupin --compose` opens the running app's composer through its own local IPC. Wayland uses the portal's activation token to focus only Lupin's own popup. No game handle, input listener, synthetic keystroke or automatic paste is used.

Typing produces a local preview after a 180 ms debounce. Only **Enter** or **Translate & Copy** writes the current validated Korean draft to the OS Unicode clipboard. A native notification and inline confirmation acknowledge the copy. The user chooses the chat field, pastes and sends. Editing, closing or cancelling the popup prevents a late translation from copying. Nothing saves drafts or outgoing history to disk; the small result cache lasts only for the app session.

Common shorthand includes WTB/WTS, B>/S>, LF/LFM/LF1M/LFG, KPQ/PQ, WG, GFA/GMA, ea, c/o, s/b, a/w, pmo, firm/nego/obo, whisper requests, cc/ch, levels and common social abbreviations. Exact supported trade/party/social fragments use a deterministic glossary. Known catalog item names remain English; the model must preserve masked item/map names and mentions exactly once. Ambiguous shorthand such as PC/PT/MA stays visible with a note rather than receiving a guessed interpretation. English item names remain appropriate to the server's catalog; this does not invent Korean official names.

Numeric validation checks explicit values, multipliers, currency and percentage roles. Equivalent Korean amounts are restored to the user's English notation before copying: 250k and 2.5m remain 250k and 2.5m. Bare 250 never becomes 250k or an invented meso amount. A missing/changed protected value blocks copying. Validation cannot establish the correctness of ordinary prose, so freeform output is labelled approximate.

Freeform English uses the original Helsinki-NLP/Tatoeba **2022 English–Korean transformer-big** model, converted to CTranslate2 int8. Its separate worker loads only when a draft needs it, uses at most two passive CPU compute threads, and unloads after 90 seconds unused. Disabling Korean reading does not disable writing. The bundled model adds about 211 MiB on disk; warm worker PSS measured about 263 MiB. During a two-second idle sample it used zero CPU ticks.

On 2026-10-27, a local 12-draft benchmark measured **190–320 ms** for warm freeform inference and **770 ms** for the first cold freeform draft, including worker IPC and validation. Glossary fragments took about **0.1–1.1 ms**. These measurements exclude the typing debounce, OS focus/clipboard delivery and compositor presentation. Existing workloads were left untouched. They are not a half-second guarantee, and numeric preservation is not a translation-quality guarantee.

The user manually confirmed Korean clipboard paste in their Linux game setup. Unicode clipboard/inference/installer checks under Wine remain separate from native Windows game paste and focus behavior.

## Source builds

Install `requirements.txt`, then run `python scripts/prepare_chat_models.py`. Public inputs, versions, sizes and SHA-256 values are pinned in `packaging/chat-models.json`, `packaging/compose-models.json` and the runtime manifests. The preparation scripts convert the original Marian models to int8 with CTranslate2 4.8.4 and verify the resulting files. Models live in ignored `models/korean-chat` and `models/english-korean` folders; installers include them, so translation needs no network download at runtime. No GPU, PyTorch or cloud API key is required. Licenses and attribution are in THIRD_PARTY.md and each model folder.
