"""Build small native system-web-view helpers, without bundling a browser engine."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from download_runtime import fetch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/market-fetch"
OUTPUT = ROOT / ".build-tools/market-helper"


def windows(compiler=None):
    manifest = json.loads((ROOT / "packaging/market-runtime.json").read_text())
    downloads = ROOT / ".build-tools/market-downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    for entry in manifest["files"]:
        fetch(entry, downloads)
    sdk = ROOT / ".build-tools/webview2-sdk"
    sdk.mkdir(exist_ok=True)
    with zipfile.ZipFile(downloads / manifest["files"][0]["name"]) as archive:
        archive.extractall(sdk)
    target = OUTPUT / "windows"
    target.mkdir(parents=True, exist_ok=True)
    if compiler is None and sys.platform == "win32" and shutil.which("cl"):
        compiler = Path(shutil.which("cl"))
    if compiler is None:
        compiler = next((ROOT / ".build-tools").glob("llvm-mingw-*/bin/x86_64-w64-mingw32-clang++"), None)
    if compiler is None:
        raise FileNotFoundError("Provide --windows-compiler with the x64 LLVM-MinGW clang++ path")
    if compiler.name.lower() in ("cl", "cl.exe"):
        (sdk / "build/native/include/EventToken.h").unlink(missing_ok=True)
        command = [str(compiler), "/nologo", "/std:c++20", "/O1", "/MT", "/EHsc", "/I", str(sdk / "build/native/include"),
                   str(SOURCE / "market_fetch_windows.cpp"), "/Fo" + str(target / "market-fetch.obj"),
                   "/Fe" + str(target / "lupin-market-fetch.exe"), "/link", "/SUBSYSTEM:WINDOWS", "ole32.lib", "uuid.lib", "shell32.lib"]
    else:
        # Microsoft's SDK spells EventToken.h with Windows casing. MinGW's
        # header is lowercase; use its exact path on case-sensitive build hosts.
        header = compiler.resolve().parents[1] / "generic-w64-mingw32/include/eventtoken.h"
        if not header.exists():
            header = compiler.parent.parent / "generic-w64-mingw32/include/eventtoken.h"
        (sdk / "build/native/include/EventToken.h").write_text('#include "' + header.as_posix() + '"\n')
        command = [str(compiler), "-std=c++20", "-Os", "-s", "-static", "-municode", "-mwindows", "-fms-extensions",
                   "-I", str(sdk / "build/native/include"), str(SOURCE / "market_fetch_windows.cpp"),
                   "-o", str(target / "lupin-market-fetch.exe"), "-lole32", "-luuid", "-lshell32"]
    subprocess.run(command, check=True)
    shutil.copy2(sdk / "build/native/x64/WebView2Loader.dll", target / "WebView2Loader.dll")
    print("Built:", target, flush=True)


def linux(root=None):
    target = OUTPUT / "linux"
    target.mkdir(parents=True, exist_ok=True)
    if root:
        # An Ubuntu 22.04 build root keeps the distributed helper's glibc floor
        # compatible with supported distributions. No host package writes occur.
        command = ["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--unshare-pid", "--die-with-parent",
                   "--bind", str(root.resolve()), "/", "--ro-bind", str(SOURCE), "/src",
                   "--bind", str(target), "/out", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                   "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
                   "--chdir", "/src", "make", "OUT=/out/lupin-market-fetch", "-B"]
    else:
        command = ["make", "-C", str(SOURCE), "OUT=" + str(target / "lupin-market-fetch"), "-B"]
    subprocess.run(command, check=True)
    print("Built:", target, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("linux", "windows"))
    parser.add_argument("--linux-root", type=Path)
    parser.add_argument("--windows-compiler", type=Path)
    args = parser.parse_args()
    if args.target == "windows":
        windows(args.windows_compiler)
    else:
        linux(args.linux_root)


if __name__ == "__main__":
    main()
