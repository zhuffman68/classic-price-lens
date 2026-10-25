"""Write one SHA-256 list for all installer formats and the portable alternative."""
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from price_lens import __version__


def main():
    names = [f"ClassicPriceLens-{__version__}-Windows-x64-Setup.exe", "ClassicPriceLens-Windows-x64.zip",
             f"classic-price-lens-{__version__}-1-x86_64.pkg.tar.zst", f"classic-price-lens_{__version__}-1_amd64.deb"]
    lines = []
    for name in names:
        with (ROOT / "dist" / name).open("rb") as stream:
            lines.append(hashlib.file_digest(stream, "sha256").hexdigest() + "  " + name)
    output = ROOT / "dist/SHA256SUMS.txt"
    output.write_text("\n".join(lines) + "\n")
    print(output)


if __name__ == "__main__":
    main()
