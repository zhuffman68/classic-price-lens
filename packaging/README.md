# Building installers and native packages

Published artifacts are in [GitHub Releases](https://github.com/zhuffman68/lupin/releases). End users need none of these build tools.

All runtime downloads are pinned by SHA-256 in `runtime-linux.json` and `runtime-windows.json`. The staging scripts copy only application source, tiny upstream OCR fixtures, tests, runtime files and dependency notices. They never copy screenshots, databases, settings or private evidence. Python/Qt run from the application directory; installed files do not depend on the build path or system Python version.

## Linux

Build requirements: Python 3.11+, Git, Cargo/Rust 1.98.1, the `x86_64-unknown-linux-musl` Rust target, `rust-lld`, `dpkg-deb`, makepkg, fakeroot and zstd. The combined package-builder script runs on Arch/Manjaro with Debian's `dpkg` tools installed. Build commands use two jobs/threads and low scheduling priority where supported.

Run `./setup.sh` to obtain the pinned Minerva source. Build the reader against musl to avoid depending on the build host's glibc version:

```sh
rustup target add x86_64-unknown-linux-musl
RUSTFLAGS='-C linker=rust-lld' cargo build --locked --release --target x86_64-unknown-linux-musl --manifest-path reader/Cargo.toml -j 2
cargo fetch --locked --manifest-path reader/Cargo.toml
python scripts/download_runtime.py linux
python scripts/package_linux.py
python scripts/build_linux_packages.py
```

The notice collector expects the official Rust 1.98.1 source-distribution notice files at `.build-tools/rustc-1.98.1-x86_64-unknown-linux-gnu/rustc/share/doc/rust/`. When using another build layout, stage those notices at that path before packaging. `license-sources.json` pins upstream notices omitted from some crates.io archives. Application/package version comes from `price_lens/__init__.py`; the package builder updates the staged PKGBUILD accordingly. The unchanged OCR reader can retain its own component version across Python/UI releases.

Output: `dist/lupin_VERSION-1_amd64.deb` and `dist/lupin-VERSION-1-x86_64.pkg.tar.zst`. Both install to `/opt/lupin`, with a launcher in `/usr/bin` and normal application-menu/icon entries. User caches and preferences are kept outside those paths. Neither package adds a daemon, service, autostart entry or custom system Qt libraries.

The bundled Qt manylinux runtime requires glibc 2.34+, targeting Debian 12+, Ubuntu 22.04+ and current Arch/Manjaro on x86_64. Desktop sharing also needs the installed desktop's portal backend. The package-manager dependency lists supply OS libraries rather than a second system Qt installation.

Optional clean distribution checks use bubblewrap and verified official OCI image layers, without Docker or host package writes:

```sh
python scripts/test_linux_packages.py debian bookworm-slim
python scripts/test_linux_packages.py ubuntu 22.04
```

These install dependencies/package, run offline and isolated X11 checks, verify installed checksums, then remove the package. They do not start screen sharing. Logs and test roots stay ignored under `evidence/` and `.build-tools/`.

`scripts/test_arch_package.py` uses a disposable pacman database under fakeroot. The X11 hotkey test sends input only to the Xvfb server created by the test harness, guarded by its temporary Xauthority path. Wayland shortcut contract tests marshal real D-Bus messages without changing desktop bindings. The source/development app uses a separate hidden desktop identity so it cannot shadow the installed menu entry.

## Windows

Compile the pinned Rust reader to `reader/target/x86_64-pc-windows-gnullvm/release/classic-screen-reader.exe` using Rust 1.98.1 and llvm-mingw 20261020. `package_windows.py` expects llvm-mingw's unmodified `libunwind.dll` and notices under `.build-tools/llvm-mingw-20261020-ucrt-ubuntu-22.04-x86_64/`. A native MSVC source-build route is also available through `setup-windows.ps1`.

```sh
python scripts/download_runtime.py windows
python scripts/package_windows.py
```

Install Inno Setup 6.7.3 or newer. `build-tools.json` pins the compiler installer used for this release. Compile natively:

```powershell
python scripts/build_windows_installer.py --iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

For cross-building on Linux, pass the compiler's filesystem path and an explicit, isolated Wine prefix using `--wine-prefix`. The script never chooses the default Wine prefix. `windows.iss` creates a per-user x64 installer with Start-menu/optional desktop shortcuts, a stable upgrade identifier, and an Apps uninstall entry. Upgrade and uninstall request shutdown only through Lupin's own local IPC endpoint; no game process is inspected or controlled.

The installed entry point is `runtime/pythonw.exe -B -m price_lens`. It waits for the user's **Start reading** action. `selftest-windows.bat` runs an offline check. `scripts/make_windows_zip.py` can also create a portable ZIP; archives remain unencrypted.

The Windows program folder is `%LOCALAPPDATA%\Programs\Lupin`. Upgrades move the former program directory while preserving additional files, per-user settings and caches. A canceled setup rolls the move back before commit. The shipped reader is named `lupin-screen-reader.exe` (`lupin-screen-reader` on Linux); its unchanged Rust build output retains its component name. Internal settings, IPC and desktop/portal identities stay stable for compatibility.

On Linux, `scripts/test_windows_installer.py --wine-prefix /path/to/isolated-prefix` validates install/upgrade/removal and the installed suite. Never point it at a game or default Wine prefix. Native Windows capture/physical hotkey testing remains separate from Wine verification.

## Updating itch.io

Install the official [Butler CLI](https://itch.io/docs/butler/installing.html) and authorize it once with `butler login`. From a checkout containing the current four builds, portable staging folder and `dist/SHA256SUMS.txt`:

```sh
python scripts/publish_itch.py --dry-run
python scripts/publish_itch.py
```

The default target is `zhuffman68/lupin`; `--project username/slug` selects another project. Dry-run validates checksums and prepares the local upload folders without network access. A real upload also checks the anonymous page's password form before and after publishing. It never changes project visibility or the shared password. Butler keeps authorization outside the repository; no credential belongs in source control.

The five stable channels are `windows-portable`, `windows-installer`, `linux-arch`, `linux-debian` and `checksums`. Subsequent uploads update the same channels, use the app's version number, and skip identical content. Source-only publisher checks run with `python -m unittest discover -s scripts/tests -q`.

Butler serves browser downloads as ZIPs. The portable channel contains the application; the other platform channels contain the native installer/package with an `INSTALL.txt` explaining extraction and installation. Original native package hashes apply after extraction. The portable download is reconstructed by itch.io, so use its included `build-manifest.json` for per-file hashes rather than comparing the generated ZIP to the standalone Windows ZIP hash.

Existing files uploaded manually through the browser are separate from Butler channels. The publisher leaves them in place; remove superseded manual entries from Edit project once the new channels are verified. Page descriptions, screenshots and password settings remain managed through the itch.io dashboard.

The app and native Linux packages are named Lupin/lupin. Pacman and DEB metadata explicitly replace `classic-price-lens`; test migration from v0.8.0 and upgrade through v0.9.0 and v0.10.0 before release. Internal installation/settings/desktop/portal IDs stay stable to preserve user data and sharing. Windows shortcuts use a fresh `lupin-scaled.ico` resource path. Public archives use Lupin/lupin names.

## Local Korean model bundle

Before staging either platform, install `requirements.txt` and run `python scripts/prepare_chat_models.py`. The script verifies pinned public model inputs, prepares int8 weights with CTranslate2 4.8.4, and verifies output hashes for **both** directions. `packaging/chat-models.json` covers Korean OCR/Korean-to-English; `packaging/compose-models.json` covers the original 2022 English-to-Korean Marian model. Its native vocabulary is converted deterministically to indexed YAML before weight conversion; the original tokenizers/license remain unchanged. `scripts/prepare_compose_model.py` can verify/prepare that bundle alone. `package_common.py` rejects missing/changed models and includes only the verified file allowlists. Both runtime manifests pin the OCR/translation wheels and their dependencies, shared by both workers. Staging extracts license directories. Private screenshot benchmarks remain ignored under `evidence/`. Model bundles add about 306 MiB before compression (95 MiB reader, 211 MiB writer), plus inference runtimes. Search thumbnails are runtime per-user cache data and must never be staged.

### Runtime trimming

Both stagers call `trim_runtime.py`. It checks actual Python Qt imports, retains the transitive binary dependencies of every remaining binding/plugin/helper, and records removed files and byte counts in `runtime-trim.json`. Both model bundles and their pinned hashes are unchanged. Platform/capture/media/image/TLS/font plugins, FFmpeg and software rendering are retained. Windows installer upgrades explicitly delete the manifest's unused app-owned paths; removing files only from a new archive would leave them installed after an upgrade. Re-run installed plugin, media, translation, fixture and package transaction checks after changing this allowlist.
