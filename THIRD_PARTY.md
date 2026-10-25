# Third-party components and sources

- **Minerva core**: [itechify/minerva](https://github.com/itechify/minerva), revision `7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`, MIT. The cloned repository retains its `LICENSE` and notices. Only the headless Rust library is linked; no upstream OS adapters, telemetry, branding or game-control features are run. Upstream's OCR fixtures remain in the local vendor checkout.
- **ocrs text-recognition.onnx**: Robert Knight, model unmodified, CC BY-SA 4.0. [Model](https://huggingface.co/robertknight/ocrs), [license](https://creativecommons.org/licenses/by-sa/4.0/). Full upstream notice: `vendor/minerva/crates/minerva-core/models/NOTICE.md`. ocrs/rten code uses MIT OR Apache-2.0.
- **PySide6 / Qt**: installed system package, LGPLv3/GPLv3/commercial options; see [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html).
- **Windows portable runtime**: CPython 3.14.9 from python.org (PSF license), PySide6/Essentials/Addons/shiboken6 6.12.0 from their official PyPI distributions. Their licenses and unmodified DLLs remain in `runtime`. Unused WebEngine/PDF distributions are omitted. Download URLs and SHA-256 values are recorded in `runtime-sources.json`.
- **Windows reader runtime**: LLVM `libunwind.dll` from the verified llvm-mingw 20261020 release, Apache-2.0 with LLVM exceptions and included notices. `licenses/LLVM-MinGW-LICENSE.txt` is included in the portable folder.
- **Classic World reference catalog**: [OSMS Data Explorer](https://osmsdataexplorer.com/), cached locally at runtime, not bundled in our code.
- **Market prices**: [NiaMeowDB Classic World](https://meowdb.com/msclassic/free-market), requested at runtime with a descriptive application User-Agent. The app visibly credits and links each reference.
- **Optional imported market snapshots**: [MesoWatch](https://meso.watch/), user-supplied dated Classic World files. No MesoWatch data is bundled. The prototype does not automate requests to its protected endpoints.

MapleStory item names, game artwork and screenshots belong to their respective owners, including Nexon. This is a local independent tool, without affiliation or approval implied.

## Corresponding library sources

The portable build uses unmodified shared libraries; the application Python source is included and the DLLs can be replaced with interface-compatible builds. Source downloads for the bundled versions are available here:

- [Qt 6.12.0 complete source](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/qt-everywhere-src-6.12.0.tar.xz)
- [Qt for Python / shiboken 6.12.0 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/pyside-setup-everywhere-src-6.12.0.tar.xz)
- [FFmpeg 9.0.1 source](https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz)
- [CPython 3.14.9 source](https://www.python.org/ftp/python/3.14.9/Python-3.14.9.tar.xz)
- [Minerva at the linked revision](https://github.com/itechify/minerva/tree/7e1aa7d418fb255bd66eb4dce848fc9eb305cd81), [Rust 1.98.1](https://github.com/rust-lang/rust/tree/1.98.1), and [LLVM MinGW release/source references](https://github.com/mstorsjo/llvm-mingw/releases/tag/20261020).

The release includes Rust dependency notices, the standard-library notices, the OCR model notice, LLVM runtime notices, and the unmodified Python/Qt package license files. Copyright in upstream game screenshot fixtures remains with their owners; they are used only for small offline OCR checks.
