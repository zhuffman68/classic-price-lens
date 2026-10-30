# Developing Lupin

Start with the [README](../README.md) for installation and the
[architecture](../ARCHITECTURE.md) for component boundaries. Read `AGENTS.md`
before changing the source. Run the commands below from a repository checkout;
installing a release does not require a compiler or Python installation.

## Source setup

Use Python 3.11 or newer supported by `requirements.txt`, Rust 1.90 or newer,
Git and the platform's C/C++ build tools. Release toolchain versions and runtime
hashes are pinned in `packaging/`; release builds use those manifests rather
than whichever versions happen to be installed.

On Linux, install the WebKitGTK 4.1/GTK 3 development headers and `pkg-config`.
Debian/Ubuntu packages are `build-essential pkg-config libwebkit2gtk-4.1-dev`;
Arch/Manjaro uses `base-devel pkgconf webkit2gtk-4.1 gtk3`.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./setup.sh
./run.sh
```

`setup.sh` obtains and checks Minerva's pinned revision, builds the screen reader
with two Cargo jobs, and builds the native market helper. It does not modify the
game or the installed Lupin package. Keep Minerva pinned at
`7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`.

On Windows, use an x64 Visual Studio Developer PowerShell:

```powershell
.\setup-windows.ps1
.\run-windows.bat
```

The setup script creates `.venv`, installs the Python dependencies, and builds
the reader and native WebView2 market helper. Fetching prices also needs the
production Microsoft WebView2 runtime; release Setup prepares it when missing.

For local Korean reading and writing, prepare the verified model bundles once:

```sh
python scripts/prepare_chat_models.py
```

Use `.venv\Scripts\python.exe` for that command on Windows. Model downloads and
converted weights stay in ignored `models/` and `.build-tools/` directories.
`prepare_compose_model.py` prepares or verifies only the English-to-Korean bundle.

## Tests

Tests may drive Lupin's own UI, fixtures and an isolated desktop. Never send input
to the game or interrupt an existing screen-sharing session. On a Linux desktop,
isolate GUI/native-helper checks with Xvfb, not just Qt's offscreen plugin:

```sh
env -u WAYLAND_DISPLAY -u WAYLAND_SOCKET xvfb-run -a env \
  QT_QPA_PLATFORM=offscreen GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 \
  QT_QUICK_BACKEND=software OMP_NUM_THREADS=2 RAYON_NUM_THREADS=2 \
  nice -n 10 .venv/bin/python -B -m unittest discover -s tests -q
python -B -m unittest discover -s scripts/tests -q
cargo check --locked --manifest-path reader/Cargo.toml -j 2
```

The installed Windows `selftest-windows.bat` runs `python -m price_lens
--self-test`: bundled OCR, local overlay IPC and a synthetic media frame without
screen capture. Package tests, Wine checks and fixture tests do not establish
physical Windows capture, shortcut or fullscreen acceptance. Record those limits
in [VERIFICATION.md](../VERIFICATION.md).

## Build and release tools

| Tools | Purpose |
| --- | --- |
| `download_runtime.py`, `build_market_helpers.py` | Obtain pinned inputs and build the platform market helper. |
| `prepare_chat_models.py`, `prepare_compose_model.py` | Verify and prepare both local translation directions. |
| `package_common.py`, `package_linux.py`, `package_windows.py`, `trim_runtime.py` | Stage the application, notices and verified models; trim unused runtime files. |
| `build_linux_packages.py`, `build_windows_installer.py` | Produce Arch, DEB and Windows Setup packages. |
| `test_arch_package.py`, `test_linux_packages.py`, `test_windows_installer.py` | Check install, upgrade, uninstall and installed offline behavior in isolated environments. |
| `release_checksums.py`, `release_updates.py` | Validate the three release artifacts and prepare signed GitHub update metadata. |
| `publish_itch.py` | Validate and upload the existing itch.io channels through Butler. |
| `export_icons.py` | Export platform icons from the approved native Lupin master. |

All tools in the table live under `scripts/`. Follow the
[packaging guide](https://github.com/zhuffman68/lupin/blob/main/packaging/README.md)
for pinned toolchains and complete platform commands, and
[update documentation](UPDATES.md) for signing and installation behavior.
Windows portable archives are retired; normal releases contain only Windows
Setup, Arch/Manjaro and Debian/Ubuntu packages.

Keep signing keys, credentials, user databases, caches, drafts, recordings and
private test evidence out of Git and release stages. Stable internal
settings/socket/desktop/portal IDs remain necessary for upgrades. Building or
passing tests does not authorize publication or changes to a running installation.

macOS is not a validated release target. Linux-specific XWayland/KDE adapters and
Windows-specific runtime preparation need separate platform alternatives before
claiming support.
