"""Build native package-manager artifacts from a previously staged Linux runtime."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from package_common import ROOT, assert_public_tree

sys.path.insert(0, str(ROOT))
from price_lens import __version__

DEB_DEPENDS = """libc6 (>= 2.34), libstdc++6 (>= 12), libgcc-s1, libgl1, libegl1,
libopengl0, libdbus-1-3, libfontconfig1, libfreetype6, libx11-6, libx11-xcb1,
libxext6, libxfixes3, libxrender1, libxrandr2, libdrm2, libxi6, libxcb1, libxcb-cursor0, libxcb-glx0,
libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0,
libxcb-render0, libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0,
libxcb-xinerama0, libxcb-xkb1, libxkbcommon0, libxkbcommon-x11-0, libwayland-client0,
libwayland-cursor0, libwayland-egl1, libpulse0, libasound2 | libasound2t64,
libpipewire-0.3-0, pipewire-bin, xdg-desktop-portal, xwayland, ca-certificates""".replace("\n", " ")


def main():
    os.nice(10)
    stage = ROOT / "dist/linux-root"
    assert_public_tree(stage)
    if not (stage / "opt/classic-price-lens/runtime/bin/python3").is_file():
        raise FileNotFoundError("Run scripts/package_linux.py first")
    build = ROOT / ".build-tools/linux-packages"
    build.mkdir(exist_ok=True)
    deb = build / "deb-root"
    if deb.exists():
        shutil.rmtree(deb)
    shutil.copytree(stage, deb, symlinks=True)
    control = deb / "DEBIAN"
    control.mkdir()
    size = sum(p.stat().st_size for p in deb.rglob("*") if p.is_file() and not p.is_symlink()) // 1024
    (control / "control").write_text(
        f"Package: lupin\nVersion: {__version__}-1\nArchitecture: amd64\n"
        "Maintainer: zhuffman68 <99307526+zhuffman68@users.noreply.github.com>\n"
        "Section: games\nPriority: optional\nProvides: classic-price-lens\nConflicts: classic-price-lens\nReplaces: classic-price-lens\n"
        f"Installed-Size: {size}\nDepends: {DEB_DEPENDS}\n"
        "Recommends: xdg-desktop-portal-gtk | xdg-desktop-portal-kde | xdg-desktop-portal-gnome, fonts-dejavu-core\n"
        "Suggests: spectacle\nHomepage: https://github.com/zhuffman68/lupin\n"
        "Description: Tools for MapleStory Classic World\n"
        " Shows cached meso market references, tracks EXP and translates Korean\n"
        " speech bubbles locally. Uses OS screen sharing and independent\n"
        " click-through windows. Includes Python, Qt, OCR and translation models.\n")
    checksums = []
    for path in sorted(deb.rglob("*")):
        if path.is_file() and not path.is_symlink() and control not in path.parents:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "md5").hexdigest()
            checksums.append(digest + "  " + path.relative_to(deb).as_posix())
    (control / "md5sums").write_text("\n".join(checksums) + "\n")
    output = ROOT / f"dist/lupin_{__version__}-1_amd64.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "--threads-max=2", "-Zxz", "-z6", "--build", str(deb), str(output)], check=True)
    arch = build / "arch"
    arch.mkdir(exist_ok=True)
    payload = arch / "payload"
    if payload.exists() or payload.is_symlink():
        payload.unlink() if payload.is_symlink() else shutil.rmtree(payload)
    payload.symlink_to(stage, target_is_directory=True)
    text = re.sub(r"(?m)^pkgver=.*$", "pkgver=" + __version__, (ROOT / "packaging/PKGBUILD").read_text())
    (arch / "PKGBUILD").write_text(text)
    env = {**os.environ, "PKGDEST": str(ROOT / "dist"), "COMPRESSZST": "(zstd -c -T2 -10 -)",
           "MAKEFLAGS": "-j2"}
    # makepkg sources compression arrays from its configuration, not env strings.
    config = arch / "makepkg.conf"
    config.write_text("source /etc/makepkg.conf\nCOMPRESSZST=(zstd -c -T2 -10 -)\n"
                      "PACKAGER='zhuffman68 <99307526+zhuffman68@users.noreply.github.com>'\n")
    subprocess.run(["makepkg", "--force", "--nodeps", "--cleanbuild", "--config", str(config)], cwd=arch, env=env, check=True)
    renamed = ROOT / f"dist/lupin-{__version__}-1-x86_64.pkg.tar.zst"
    print("Built:", output.name, renamed.name, flush=True)


if __name__ == "__main__":
    main()
