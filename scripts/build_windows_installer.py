"""Compile a per-user Inno Setup installer, natively or in an explicit Wine prefix."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from price_lens import __version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path, required=True, help="Path to the Inno Setup compiler executable")
    parser.add_argument("--wine-prefix", type=Path, help="Required on Linux; an isolated build prefix")
    args = parser.parse_args()
    compiler = args.iscc.resolve()
    if not compiler.is_file():
        raise FileNotFoundError(compiler)
    command = [str(compiler), "/Qp", "/DAppVersion=" + __version__, str(ROOT / "packaging/windows.iss")]
    env = os.environ.copy()
    if sys.platform != "win32":
        if not args.wine_prefix:
            parser.error("Use --wine-prefix with an isolated build prefix")
        os.nice(10)
        env.update(WINEPREFIX=str(args.wine_prefix.resolve()), WINEDEBUG="-all",
                   WINEDLLOVERRIDES="mscoree,mshtml=;winemenubuilder.exe=d")
        command[-1] = subprocess.check_output(["winepath", "-w", command[-1]], env=env, text=True).strip()
        command.insert(0, "wine")
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    output = ROOT / f"dist/ClassicPriceLens-{__version__}-Windows-x64-Setup.exe"
    if not output.is_file():
        raise FileNotFoundError(output)
    print("Built:", output, f"({output.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
