"""Validate three native builds and publish four password-gated itch channels."""
import argparse
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from price_lens import __version__

DEFAULT_PROJECT = "zhuffman68/lupin"


@dataclass(frozen=True)
class Upload:
    channel: str
    source: Path


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def artifact_names(version):
    return {
        "windows-installer": f"Lupin-{version}-Windows-x64-Setup.exe",
        "linux-arch": f"lupin-{version}-1-x86_64.pkg.tar.zst",
        "linux-debian": f"lupin_{version}-1_amd64.deb",
    }


def validate_release(dist, version):
    names = artifact_names(version)
    checksums = {}
    for line in (dist / "SHA256SUMS.txt").read_text().splitlines():
        value, name = line.split(None, 1)
        name = name.strip()
        if not re.fullmatch(r"[0-9a-f]{64}", value) or name in checksums:
            raise ValueError("Invalid or duplicate release checksum")
        checksums[name] = value
    if set(checksums) != set(names.values()):
        raise ValueError("SHA256SUMS.txt must list exactly this version's three native builds")
    for name, expected in checksums.items():
        if digest(dist / name) != expected:
            raise ValueError("Release checksum mismatch: " + name)
    return names, checksums


def installation_text(channel, name, version):
    instructions = {
        "windows-installer": f"Extract this download ZIP, then run {name}.\nOpen Lupin from the Start menu. Administrator access is not required.",
        "linux-arch": f"Extract this download ZIP. Open a terminal in the extracted folder and run:\n\n  sudo pacman -U ./{name}",
        "linux-debian": f"Extract this download ZIP. Open a terminal in the extracted folder and run:\n\n  sudo apt install ./{name}",
    }
    return (f"Lupin {version}\n\n{instructions[channel]}\n\n"
            "Python, Qt and OCR are included. Internet is needed for price updates.\n"
            "Linux screen sharing also needs PipeWire and a desktop sharing portal.\n\n"
            "Open the app, choose the game's display, click Start reading, and approve OS sharing if prompted.\n"
            "Keep the game's bottom status bar visible, then open a shop or hover an item.\n\n"
            "SHA256SUMS.txt lists the original build files. Verify the extracted installer/package, not itch.io's generated ZIP.\n")


def prepare_uploads(dist, version):
    names, checksums = validate_release(dist, version)
    stage = dist / "itch-staging" / version
    uploads = []
    for channel in ("windows-installer", "linux-arch", "linux-debian", "checksums"):
        folder = stage / channel
        if folder.is_symlink():
            raise ValueError("Refusing a symlinked staging directory")
        folder.mkdir(parents=True, exist_ok=True)
        name = names.get(channel)
        allowed = {"INSTALL.txt", "SHA256SUMS.txt"} | ({name} if name else set())
        if any(path.name not in allowed or path.is_symlink() or not path.is_file() for path in folder.iterdir()):
            raise ValueError("Unexpected files in managed staging directory: " + str(folder))
        if name:
            if not (folder / name).exists() or digest(folder / name) != checksums[name]:
                shutil.copy2(dist / name, folder / name)
            if digest(folder / name) != checksums[name]:
                raise ValueError("Staged installer checksum mismatch: " + name)
            text = installation_text(channel, name, version)
        else:
            text = (f"Lupin {version} checksums\n\n"
                    "SHA256SUMS.txt verifies the original release build files.\n"
                    "Extract the itch.io download ZIP before checking a native installer/package.\n")
        (folder / "INSTALL.txt").write_text(text, encoding="utf-8")
        shutil.copy2(dist / "SHA256SUMS.txt", folder / "SHA256SUMS.txt")
        uploads.append(Upload(channel, folder))
    return uploads


def project_url(project):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*", project):
        raise ValueError("Expected a lowercase itch.io username/project slug")
    owner, slug = project.split("/")
    return f"https://{owner}.itch.io/{slug}"


class PasswordGate(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.in_password_form = False
        self.protected = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "form":
            action = urllib.parse.urljoin(self.url, attrs.get("action", ""))
            self.in_password_form = action == self.url + "/password" and attrs.get("method", "").lower() == "post"
        elif tag == "input" and self.in_password_form:
            self.protected |= attrs.get("type") == "password" and attrs.get("name") == "game_password"

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_password_form = False


def verify_password_gate(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Lupin-publisher", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read(2_000_001)
    if len(html) > 2_000_000:
        raise ValueError("Project page exceeds the privacy-check size limit")
    page = PasswordGate(url)
    page.feed(html.decode("utf-8", errors="replace"))
    if not page.protected:
        raise ValueError("The anonymous project page did not show its password gate; uploads stopped without changing project visibility")


def push_command(butler, upload, project, version):
    return [str(butler), "push", str(upload.source), project + ":" + upload.channel,
            "--userversion", version, "--if-changed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--butler", type=Path, help="Explicit Butler executable")
    parser.add_argument("--dry-run", action="store_true", help="Validate/stage and print the plan; no login, network or uploads")
    args = parser.parse_args()
    url = project_url(args.project)
    uploads = prepare_uploads(ROOT / "dist", __version__)
    butler = args.butler.resolve() if args.butler else shutil.which("butler") or Path.home() / ".local/bin/butler"
    for upload in uploads:
        print(shlex.join(push_command(butler, upload, args.project, __version__)), flush=True)
    if args.dry_run:
        print("Validated local release and prepared four channels. No network requests or uploads were made.")
        return
    if not Path(butler).is_file():
        raise ValueError("Install Butler first: https://itch.io/docs/butler/installing.html")
    verify_password_gate(url)
    print("Anonymous password gate verified. Checking Butler access…", flush=True)
    env = {**os.environ, "GOMAXPROCS": "2"}
    subprocess.run([str(butler), "status", args.project], env=env, check=True)
    for upload in uploads:
        print("Publishing " + upload.channel, flush=True)
        subprocess.run(push_command(butler, upload, args.project, __version__), env=env, check=True)
    verify_password_gate(url)
    subprocess.run([str(butler), "status", args.project], env=env, check=True)
    print(f"Published {__version__} to {url}; anonymous password gate remains enabled.", flush=True)


if __name__ == "__main__":
    try:
        if sys.platform.startswith("linux"):
            os.nice(10)
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
