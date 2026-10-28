# Third-party components and sources

- **Minerva core**: [itechify/minerva](https://github.com/itechify/minerva), revision `7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`, MIT. The cloned repository retains its `LICENSE` and notices. Only the headless Rust library is linked; no upstream OS adapters, telemetry, branding or game-control features are run. Upstream's OCR fixtures remain in the local vendor checkout.
- **ocrs text-recognition.onnx**: Robert Knight, model unmodified, CC BY-SA 4.0. [Model](https://huggingface.co/robertknight/ocrs), [license](https://creativecommons.org/licenses/by-sa/4.0/). Full upstream notice: `vendor/minerva/crates/minerva-core/models/NOTICE.md`. ocrs/rten code uses MIT OR Apache-2.0.
- **PySide6 / Qt**: LGPLv3/GPLv3/commercial options; see [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html). Installed packages bundle unmodified shared libraries with their original license files; source checkouts can use system packages instead.
- **Linux packaged runtime**: CPython 3.14.9 from [Astral python-build-standalone 20261021](https://github.com/astral-sh/python-build-standalone/releases/tag/20261021), PSF license and included dependency notices. PySide6/Essentials/Addons/shiboken6 6.12.0 come from official PyPI manylinux x86_64 distributions. Download URLs and SHA-256 values are in `runtime-sources.json`. The OCR reader is statically linked with Rust's musl target; musl's MIT notices are included with the Rust standard-library notices.
- **Linux desktop shortcuts**: [dbus-next 0.2.3](https://github.com/altdesktop/python-dbus-next), MIT, bundled with its license file. It communicates only with the desktop's GlobalShortcuts portal. Windows uses `RegisterHotKey`; X11 uses a passive grab for the chosen chord. No keyboard-hook library is used.
- **Windows packaged/portable runtime**: CPython 3.14.9 from python.org (PSF license), PySide6/Essentials/Addons/shiboken6 6.12.0 from their official PyPI distributions. Their licenses and unmodified DLLs remain in `runtime`. Unused WebEngine/PDF distributions are omitted. Download URLs and SHA-256 values are recorded in `runtime-sources.json`.
- **Windows native TLS trust**: [truststore 0.10.5](https://github.com/sethmlarson/truststore), MIT. The verified wheel and its license ship only in the Windows runtime. HTTPS uses an explicitly supplied Windows-native verifying context, including configured proxy requests; no global SSL patch or certificate-verification bypass is used.
- **Windows reader runtime**: LLVM `libunwind.dll` from the verified llvm-mingw 20261020 release, Apache-2.0 with LLVM exceptions and included notices. `licenses/LLVM-MinGW-LICENSE.txt` is included in the portable folder.
- **Classic World reference catalog**: [OSMS Data Explorer](https://osmsdataexplorer.com/), cached locally at runtime, not bundled in our code.
- **Market prices**: [NiaMeowDB Classic World](https://meowdb.com/msclassic/free-market), requested at runtime with a descriptive application User-Agent. The app visibly credits and links each reference.
- **Whole-market prices**: [MesoWatch](https://meso.watch/), its live Classic World list read through a short-lived, installed browser. Snapshots stay in the user's local cache and are never bundled with source or releases. Individual fallback prices use NiaMeowDB.

MapleStory item names, game artwork and screenshots belong to their respective owners, including Nexon. This is a local independent tool, without affiliation or approval implied.

## Corresponding library sources

The packaged builds use unmodified shared libraries; application Python source is included and the libraries can be replaced with interface-compatible builds. Source downloads for the bundled versions are available here:

- [Qt 6.12.0 complete source](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/qt-everywhere-src-6.12.0.tar.xz)
- [Qt for Python / shiboken 6.12.0 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/pyside-setup-everywhere-src-6.12.0.tar.xz)
- [FFmpeg 9.0.1 source](https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz)
- [CPython 3.14.9 source](https://www.python.org/ftp/python/3.14.9/Python-3.14.9.tar.xz)
- [Minerva at the linked revision](https://github.com/itechify/minerva/tree/7e1aa7d418fb255bd66eb4dce848fc9eb305cd81), [Rust 1.98.1](https://github.com/rust-lang/rust/tree/1.98.1), and [LLVM MinGW release/source references](https://github.com/mstorsjo/llvm-mingw/releases/tag/20261020).

The release includes Rust dependency notices, the standard-library notices, the OCR model notice, LLVM runtime notices, and the unmodified Python/Qt package license files. Copyright in upstream game screenshot fixtures remains with their owners; they are used only for small offline OCR checks.


## Lupin header artwork and typeface

The animated Lupin is original MapleStory monster artwork, copyright Nexon, obtained unchanged from the public OSMS Data Explorer Classic World catalog (monster 35, move animation). Asset URL: https://osmsdataexplorer.com/data/images/monsters/70d804f09c8432cf87815c5b376a4c8b.webp . Lupin is an unofficial fan companion and is not affiliated with Nexon.

The previous wordmark used Nexon's official MapleStory Bold typeface; the bundled font is retained as a Korean glyph fallback. Its unmodified TTF and the distributor's copyright notice are included in `price_lens/resources/fonts/`. Official source: https://maplestory.nexon.com/Media/Font .

MesoWatch's public NiaDB ID index is used only to validate already-confirmed NiaMeowDB item mappings; it is separate from the whole-market price list. Source: https://meso.watch/js/niadb.js .

## Local Korean translation and revised header

- **Korean OCR:** PaddlePaddle korean_PP-OCRv5_mobile_rec, unmodified ONNX conversion and dictionary by [monkt/paddleocr-onnx](https://huggingface.co/monkt/paddleocr-onnx), Apache 2.0. Original [PaddlePaddle model](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec). Native input is 48 pixels high, as declared by the actual graph. The converter's generic config says 32; Lupin validates the graph and dictionary dimensions.
- **Korean-to-English model:** Helsinki-NLP/Tatoeba OPUS transformer-align, original `opus-2020-06-17.zip` from https://object.pouta.csc.fi/Tatoeba-MT-models/kor-eng/opus-2020-06-17.zip . The archive includes **CC BY 4.0**, retained as `models/korean-chat/LICENSE-OPUS.txt`. CTranslate2 converts the weights to int8; SentencePiece tokenizers are unchanged. The corresponding Hugging Face card links the original archive; its Apache label does not replace the license actually supplied with that archive.
- **English-to-Korean model:** Helsinki-NLP/Tatoeba OPUS `opusTCv20210807-sepvoc_transformer-big_2022-07-28`, original archive from https://object.pouta.csc.fi/Tatoeba-MT-models/eng-kor/opusTCv20210807-sepvoc_transformer-big_2022-07-28.zip . The supplied **CC BY 4.0** license is retained as `models/english-korean/LICENSE-OPUS.txt`; source and conversion details are in `OPUS-SOURCE.md`. CTranslate2 converts the original weights to int8, with unchanged source/target SentencePiece tokenizers. Input/output hashes are pinned in `packaging/compose-models.json`.
- **Inference/runtime:** CTranslate2 4.8.4 (MIT), SentencePiece 0.2.2 (Apache 2.0), ONNX Runtime 1.31.1 (MIT), NumPy 2.5.4 (BSD-3-Clause and included dependency notices), PyYAML 6.0.3 (MIT), FlatBuffers 25.12.19 (Apache 2.0), protobuf 7.36.2 (BSD-3-Clause), packaging 26.3 (Apache 2.0 OR BSD-2-Clause). Unmodified official wheel distributions include their license directories and notices. Sources and hashes are in the platform runtime manifests.
- **Wordmark:** [Pixelify Sans](https://fonts.google.com/specimen/Pixelify+Sans), SIL Open Font License 1.1. The original font and license are in `price_lens/resources/fonts`; the wordmark is outlined to SVG.
- **Header animations:** unmodified original GMS v83 Lupin GIFs from the public [MapleStory.io](https://maplestory.io/) game-data export API. Walk: https://maplestory.io/api/GMS/83/mob/3210800/render/move ; attack: https://maplestory.io/api/GMS/83/mob/3210800/render/attack1 . Underlying artwork belongs to Nexon. The earlier OSMS WebP preview omitted final frames. This original-game art reference does not establish current Classic World mechanics.

## Price-search item images

The price-search thumbnails use the public [OSMS Data Explorer](https://osmsdataexplorer.com/) current Classic World item images, matched by game item ID: `https://osmsdataexplorer.com/data/current/images/items/ID.png` (eight-digit ID). The underlying MapleStory item artwork belongs to Nexon. Images are fetched into a per-user cache, not bundled or inferred from a different game's catalog.

## Lupin application icon (v0.9.0)

The approved 32px portrait and skill-style frame were generated with the built-in image_gen tool using a public classic Lupin sprite as reference. Nexon owns the underlying MapleStory character design. The local master and nearest-neighbor PNG/ICO exports are described in [artwork notes](docs/ARTWORK.md). Earlier leaf/magnifier icon credits describe the previous icon.
