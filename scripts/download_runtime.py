"""Download pinned runtime archives and verify their publisher SHA-256 values."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(entry, folder):
    path = folder / entry["name"]
    if path.exists() and hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == entry["sha256"]:
        return path.name + " (verified cache)"
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(entry["url"], timeout=120) as source, temporary.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        with temporary.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("SHA-256 mismatch: " + path.name)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path.name + " (downloaded and verified)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=["linux", "windows", "build-tools"])
    args = parser.parse_args()
    manifest = "build-tools.json" if args.platform == "build-tools" else f"runtime-{args.platform}.json"
    entries = json.loads((ROOT / "packaging" / manifest).read_text())
    folder = ROOT / ".build-tools" / (args.platform + "-downloads")
    folder.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as executor:
        for result in executor.map(lambda entry: fetch(entry, folder), entries):
            print(result, flush=True)


if __name__ == "__main__":
    main()
