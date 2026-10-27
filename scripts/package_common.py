"""Shared source, fixture and notice staging; private runtime data is never copied."""
import json
from pathlib import Path
import shutil
import tarfile
import tomllib
import urllib.request
from download_runtime import fetch

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.sqlite*")


def stage_application(out):
    shutil.copytree(ROOT / "price_lens", out / "price_lens", dirs_exist_ok=True, ignore=IGNORE)
    shutil.copytree(ROOT / "tests", out / "tests", dirs_exist_ok=True, ignore=IGNORE)
    for name in ("README.md", "README-WINDOWS.md", "THIRD_PARTY.md", "VERIFICATION.md", "ARCHITECTURE.md"):
        shutil.copy2(ROOT / name, out / name)
    documentation = out / "docs"
    documentation.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs/TECHNICAL.md", documentation / "TECHNICAL.md")
    shutil.copy2(ROOT / "docs/ARTWORK.md", documentation / "ARTWORK.md")
    fixtures = ROOT / "vendor/minerva/samples"
    categories = {"player-shop": ["gems-and-ores", "live-greater-chaos-and-intermediate-scrolls", "equips-two-sold-out"],
                  "item-tooltip": ["screw@60,20"],
                  "exp-bar": ["100300__64.49--ideal-ratio-1366x768-strip"]}
    for category, names in categories.items():
        destination = out / "vendor/minerva/samples" / category
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            for suffix in (".png", ".json"):
                source = fixtures / category / (name + suffix)
                if source.is_file():
                    shutil.copy2(source, destination / source.name)
    destination = out / "selftest-data"
    destination.mkdir(exist_ok=True)
    for suffix in (".png", ".json"):
        shutil.copy2(fixtures / "player-shop" / ("gems-and-ores" + suffix), destination)


def stage_notices(out):
    licenses = out / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "vendor/minerva/LICENSE", licenses / "MINERVA-LICENSE.txt")
    shutil.copy2(ROOT / "vendor/minerva/crates/minerva-core/models/NOTICE.md", licenses / "OCR-MODEL-NOTICE.md")
    lock = tomllib.loads((ROOT / "reader/Cargo.lock").read_text())
    cargo = Path.home() / ".cargo/registry/src"
    sources = []
    fallbacks = json.loads((ROOT / "packaging/license-sources.json").read_text())
    downloads = ROOT / ".build-tools/license-downloads"
    downloads.mkdir(exist_ok=True)
    for package in lock["package"]:
        if not package.get("source", "").startswith("registry+"):
            continue
        name = f'{package["name"]}-{package["version"]}'
        directories = list(cargo.glob("*/" + name))
        if not directories:
            raise FileNotFoundError("Run cargo fetch before packaging: " + name)
        source = directories[0]
        notices = [p for p in source.iterdir() if p.is_file()
                   and p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "COPYRIGHT"))]
        destination = licenses / "rust" / name
        destination.mkdir(parents=True, exist_ok=True)
        if not notices:
            family = "rten-" + package["version"] if package["name"].startswith("rten-") else name
            if family not in fallbacks:
                raise FileNotFoundError("Dependency license missing: " + name)
            for entry in fallbacks[family]:
                fetch(entry, downloads)
                shutil.copy2(downloads / entry["name"], destination / entry["notice"])
        for path in notices:
            shutil.copy2(path, destination / path.name)
        sources.append({"name": package["name"], "version": package["version"],
                        "source": f'https://crates.io/crates/{package["name"]}/{package["version"]}'})
    (licenses / "rust/sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    rust = ROOT / ".build-tools/rustc-1.98.1-x86_64-unknown-linux-gnu/rustc/share/doc/rust"
    shutil.copytree(rust / "licenses", licenses / "rust-standard-library", dirs_exist_ok=True)
    shutil.copy2(rust / "COPYRIGHT-library.html", licenses / "rust-standard-library")
    ffmpeg = downloads / "ffmpeg-9.0.1.tar.xz"
    if not ffmpeg.exists():
        with urllib.request.urlopen("https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz", timeout=120) as source:
            with ffmpeg.open("wb") as target:
                shutil.copyfileobj(source, target)
    with tarfile.open(ffmpeg) as archive:
        for member in archive.getmembers():
            relative = Path(member.name).relative_to("ffmpeg-9.0.1")
            if member.isfile() and (relative.parts[0] == "LICENSE.md" or relative.parts[0].startswith("COPYING.")):
                destination = licenses / "ffmpeg" / relative.name
                destination.parent.mkdir(exist_ok=True)
                with archive.extractfile(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)


def assert_public_tree(out):
    for path in out.rglob("*"):
        relative = path.relative_to(out)
        if path.name == "evidence" or ".build-tools" in relative.parts or ".sqlite" in path.name or path.suffix == ".pyc":
            raise ValueError("Private/generated data in package: " + str(relative))
