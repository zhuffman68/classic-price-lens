"""Exercise pacman install/check/remove in a disposable root, never the host database."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if "--in-fakeroot" not in sys.argv:
        subprocess.run(["fakeroot", sys.executable, __file__, "--in-fakeroot"], check=True)
        return
    folder = ROOT / ".build-tools/test-roots/pacman"
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "var/lib/pacman").mkdir(parents=True)
    (folder / "cache").mkdir()
    (folder / "user-cache").mkdir()
    config = folder / "pacman.conf"
    config.write_text("[options]\nArchitecture = auto\nSigLevel = Never\n")
    marker = folder / "user-cache/preserve.txt"
    marker.write_text("Keep user data.\n")
    package = max((ROOT / "dist").glob("lupin-*-x86_64.pkg.tar.zst"), key=lambda p: p.stat().st_mtime)
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    log_path = evidence / "package-pacman.log"
    pacman = ["pacman", "--root", str(folder), "--dbpath", str(folder / "var/lib/pacman"),
              "--cachedir", str(folder / "cache"), "--logfile", str(folder / "pacman.log"),
              "--config", str(config), "--noconfirm", "--ask", "4"]
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONDONTWRITEBYTECODE": "1",
           "XDG_CACHE_HOME": str(folder / "user-cache")}
    with log_path.open("w") as log:
        def run(command, cwd=None):
            subprocess.run(command, cwd=cwd or ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        # Only dependency checks are skipped: dependencies come from the host,
        # while all package/database writes are confined to this disposable root.
        previous = ROOT / "dist/lupin-0.8.0-1-x86_64.pkg.tar.zst"
        if previous.exists():
            run([*pacman, "-Udd", str(previous)])
        run([*pacman, "-Udd", str(package)])
        launcher = folder / "usr/bin/classic-price-lens"
        alias = folder / "usr/bin/lupin"
        assert alias.is_symlink() and alias.resolve() == launcher, "Lupin launcher missing"
        desktop = folder / "usr/share/applications/io.github.zhuffman68.ClassicPriceLens.desktop"
        assert "Name=Lupin\n" in desktop.read_text(), "Application menu name is stale"
        run([str(alias), "--version"])
        run([str(launcher), "--version"])
        run([str(launcher), "--self-test"])
        app = folder / "opt/classic-price-lens"
        run([str(app / "runtime/bin/python3"), "-B", "-m", "unittest", "discover", "-s", "tests", "-q"], app)
        run([*pacman, "-Qkk", "lupin"])
        run([*pacman, "-Rdd", "lupin"])
        assert not launcher.exists(), "Uninstall left launcher behind"
        assert not alias.is_symlink(), "Uninstall left Lupin alias behind"
        assert not app.exists(), "Uninstall left application files behind"
        assert marker.is_file(), "Uninstall removed user data"
    print("PASS: pacman install, launch, offline OCR/overlay, tests, file checks and removal", flush=True)
    print("Log:", log_path, flush=True)


if __name__ == "__main__":
    main()
