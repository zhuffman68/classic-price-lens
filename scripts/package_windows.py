"""Assemble a portable x64 Windows folder from verified official runtime downloads."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from package_common import stage_application, stage_notices, assert_public_tree

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / ".build-tools/windows-downloads"
OUT = ROOT / "dist/Lupin-Windows-x64"
READER = ROOT / "reader/target/x86_64-pc-windows-gnullvm/release/classic-screen-reader.exe"


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    runtime = OUT / "runtime"
    runtime.mkdir(exist_ok=True)
    manifest = json.loads((ROOT / "packaging/runtime-windows.json").read_text())
    for entry in manifest:
        path = DOWNLOADS / entry["name"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path.name
    python = next(DOWNLOADS.glob("python-*-embed-amd64.zip"))
    with zipfile.ZipFile(python) as archive:
        archive.extractall(runtime)
    site = runtime / "Lib/site-packages"
    site.mkdir(parents=True, exist_ok=True)
    for entry in manifest:
        if not entry["name"].endswith(".whl"):continue
        path = DOWNLOADS/entry["name"]
        with zipfile.ZipFile(path) as archive:
            archive.extractall(site)
    pth = next(runtime.glob("python*._pth"))
    python_zip = next(runtime.glob("python3*.zip"))
    pth.write_text(f"{python_zip.name}\n.\n..\nLib/site-packages\nimport site\n", encoding="utf-8")
    stage_application(OUT)
    for name in ("run-windows.bat", "selftest-windows.bat", "windows-selftest.py"):
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copy2(ROOT / "packaging/icon.ico", OUT / "lupin.ico")
    (OUT / "bin").mkdir(exist_ok=True)
    if READER.is_file():
        shutil.copy2(READER, OUT / "bin/classic-screen-reader.exe")
        toolchain = ROOT / ".build-tools/llvm-mingw-20261020-ucrt-ubuntu-22.04-x86_64"
        shutil.copy2(toolchain / "x86_64-w64-mingw32/bin/libunwind.dll", OUT / "bin/libunwind.dll")
    else:
        print("Runtime staged; Windows reader build still pending")
    stage_notices(OUT)
    licenses = OUT / "licenses"
    toolchain = ROOT / ".build-tools/llvm-mingw-20261020-ucrt-ubuntu-22.04-x86_64"
    shutil.copy2(toolchain / "LICENSE.TXT", licenses / "LLVM-MinGW-LICENSE.txt")
    (OUT / "runtime-sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in list(OUT.rglob("__pycache__")):
        shutil.rmtree(path)
    assert_public_tree(OUT)
    print("Portable folder:", OUT)
    print("Files:", sum(1 for path in OUT.rglob("*") if path.is_file()))


if __name__ == "__main__":
    main()
