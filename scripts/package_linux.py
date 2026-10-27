"""Stage the bundled Linux runtime and standard filesystem layout for DEB/pacman."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import zipfile

from package_common import ROOT, stage_application, stage_notices, assert_public_tree
from trim_runtime import trim

STAGE = ROOT / "dist/linux-root"
OUT = STAGE / "opt/classic-price-lens"
DOWNLOADS = ROOT / ".build-tools/linux-downloads"


def main():
    # Recreate only the generated staging tree; never reuse bytecode or runtime caches.
    if STAGE.exists():
        shutil.rmtree(STAGE)
    OUT.mkdir(parents=True)
    manifest = json.loads((ROOT / "packaging/runtime-linux.json").read_text())
    for entry in manifest:
        path = DOWNLOADS / entry["name"]
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == entry["sha256"], path.name
    python = next(DOWNLOADS.glob("cpython-*.tar.gz"))
    with tarfile.open(python) as archive:
        archive.extractall(OUT, filter="data")
    (OUT / "python").rename(OUT / "runtime")
    site = OUT / "runtime/lib/python3.14/site-packages"
    site.mkdir(parents=True, exist_ok=True)
    for entry in manifest:
        if not entry["name"].endswith(".whl"):continue
        wheel = DOWNLOADS/entry["name"]
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(site)
    # Developer tools, headers, bytecode and QML are unused by this QWidget app.
    for base in (OUT / "runtime",):
        for path in list(base.rglob("__pycache__")):
            shutil.rmtree(path)
    for relative in ("include", "share/man", "lib/python3.14/idlelib", "lib/python3.14/turtledemo"):
        shutil.rmtree(OUT / "runtime" / relative, ignore_errors=True)
    for path in (OUT / "runtime/lib").rglob("*.a"):
        path.unlink()  # Static developer libraries are not used by the runtime.
    trim(OUT,'linux')
    (OUT / "bin").mkdir()
    reader = ROOT / "reader/target/x86_64-unknown-linux-musl/release/classic-screen-reader"
    shutil.copy2(reader, OUT / "bin/classic-screen-reader")
    stage_application(OUT)
    stage_notices(OUT)
    (OUT / "runtime-sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    destinations = {
        "packaging/classic-price-lens": "usr/bin/classic-price-lens",
        "packaging/classic-price-lens.desktop": "usr/share/applications/io.github.zhuffman68.ClassicPriceLens.desktop",
        "price_lens/resources/icon.png": "usr/share/icons/hicolor/256x256/apps/io.github.zhuffman68.Lupin-scaled.png",
        "price_lens/resources/icon.svg": "usr/share/icons/hicolor/scalable/apps/io.github.zhuffman68.Lupin-scaled.svg",
        "README.md": "usr/share/doc/classic-price-lens/README.md",
        "THIRD_PARTY.md": "usr/share/doc/classic-price-lens/copyright",
    }
    for size in (16,20,22,24,28,32,40,48,56,64,96,128):
        destinations[f"price_lens/resources/icon-{size}.png"] = (
            f"usr/share/icons/hicolor/{size}x{size}/apps/io.github.zhuffman68.Lupin-scaled.png")
    for source, relative in destinations.items():
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
    (STAGE / "usr/bin/classic-price-lens").chmod(0o755)
    alias = STAGE / "usr/bin/lupin"
    alias.symlink_to("classic-price-lens")
    # ZIP wheel extraction does not preserve executable permissions for Qt helpers.
    for path in (site / "PySide6/Qt/libexec").glob("*"):
        if path.is_file():
            path.chmod(0o755)
    assert_public_tree(STAGE)
    size = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file() and not p.is_symlink())
    print("Linux staging tree:", STAGE, f"({size / 1024 / 1024:.1f} MiB)", flush=True)


if __name__ == "__main__":
    main()
