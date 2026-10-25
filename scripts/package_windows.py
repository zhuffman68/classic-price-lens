"""Assemble a portable x64 Windows folder from verified official runtime downloads."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / ".build-tools/windows-downloads"
OUT = ROOT / "dist/ClassicPriceLens-Windows-x64"
READER = ROOT / "reader/target/x86_64-pc-windows-gnullvm/release/classic-screen-reader.exe"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runtime = OUT / "runtime"
    runtime.mkdir(exist_ok=True)
    manifest = json.loads((DOWNLOADS / "downloads.json").read_text())
    for entry in manifest:
        path = DOWNLOADS / entry["name"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path.name
    python = next(DOWNLOADS.glob("python-*-embed-amd64.zip"))
    with zipfile.ZipFile(python) as archive:
        archive.extractall(runtime)
    site = runtime / "Lib/site-packages"
    site.mkdir(parents=True, exist_ok=True)
    for prefix in ("shiboken6-", "pyside6_essentials-", "pyside6_addons-", "pyside6-"):
        path = next(DOWNLOADS.glob(prefix + "*.whl"))
        with zipfile.ZipFile(path) as archive:
            archive.extractall(site)
    pth = next(runtime.glob("python*._pth"))
    python_zip = next(runtime.glob("python3*.zip"))
    pth.write_text(f"{python_zip.name}\n.\n..\nLib/site-packages\nimport site\n", encoding="utf-8")
    shutil.copytree(ROOT / "price_lens", OUT / "price_lens", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("run-windows.bat", "selftest-windows.bat", "windows-selftest.py", "README-WINDOWS.md", "THIRD_PARTY.md", "VERIFICATION.md"):
        shutil.copy2(ROOT / name, OUT / name)
    (OUT / "bin").mkdir(exist_ok=True)
    if READER.is_file():
        shutil.copy2(READER, OUT / "bin/classic-screen-reader.exe")
        toolchain = ROOT / ".build-tools/llvm-mingw-20261020-ucrt-ubuntu-22.04-x86_64"
        shutil.copy2(toolchain / "x86_64-w64-mingw32/bin/libunwind.dll", OUT / "bin/libunwind.dll")
    else:
        print("Runtime staged; Windows reader build still pending")
    fixture_dir = ROOT / "vendor/minerva/samples"
    # Keep the tiny upstream OCR fixtures for the offline self-test, with notices.
    for category, names in {"player-shop": ["gems-and-ores", "live-greater-chaos-and-intermediate-scrolls", "equips-two-sold-out"],
                            "item-tooltip": ["screw@60,20"]}.items():
        destination = OUT / "vendor/minerva/samples" / category
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            for suffix in (".png", ".json"):
                source = fixture_dir / category / (name + suffix)
                if source.exists():
                    shutil.copy2(source, destination / source.name)
    selftest = OUT / "selftest-data"
    selftest.mkdir(exist_ok=True)
    for name in ("gems-and-ores.png", "gems-and-ores.json"):
        shutil.copy2(fixture_dir / "player-shop" / name, selftest / name)
    shutil.copytree(ROOT / "tests", OUT / "tests", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    licenses = OUT / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "vendor/minerva/LICENSE", licenses / "MINERVA-LICENSE.txt")
    shutil.copy2(ROOT / "vendor/minerva/crates/minerva-core/models/NOTICE.md", licenses / "OCR-MODEL-NOTICE.md")
    toolchain = ROOT / ".build-tools/llvm-mingw-20261020-ucrt-ubuntu-22.04-x86_64"
    shutil.copy2(toolchain / "LICENSE.TXT", licenses / "LLVM-MinGW-LICENSE.txt")
    (OUT / "runtime-sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Portable folder:", OUT)
    print("Files:", sum(1 for path in OUT.rglob("*") if path.is_file()))


if __name__ == "__main__":
    main()
