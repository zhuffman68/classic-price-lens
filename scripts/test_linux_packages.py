"""Test a DEB in isolated official Debian/Ubuntu filesystems using bubblewrap.

No host package installation, screen sharing, or game interaction occurs.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def prepare(image, tag):
    folder = ROOT / ".build-tools/test-roots" / (image + "-" + tag)
    marker = folder / ".classic-lens-test-root"
    if marker.exists():
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/{image}:pull"
    token = json.load(urllib.request.urlopen(token_url))["token"]
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"}

    def get(path):
        request = urllib.request.Request(f"https://registry-1.docker.io/v2/library/{image}/" + path, headers=headers)
        return urllib.request.urlopen(request, timeout=120).read()

    manifest = json.loads(get("manifests/" + tag))
    if "manifests" in manifest:
        reference = next(m for m in manifest["manifests"] if m.get("platform", {}).get("architecture") == "amd64"
                         and m["platform"].get("os") == "linux")["digest"]
        data = get("manifests/" + reference)
        assert hashlib.sha256(data).hexdigest() == reference.split(":")[1]
        manifest = json.loads(data)

    def safe_member(member, destination):
        # Rootfs absolute links are made relative so extraction stays contained.
        if member.issym() and member.linkname.startswith("/"):
            member = member.replace(linkname=posixpath.relpath(member.linkname, "/" + posixpath.dirname(member.name)))
        if member.islnk():
            member = member.replace(linkname=member.linkname.lstrip("/"))
        if member.isdev() or member.isfifo():
            return None
        return tarfile.data_filter(member, destination)

    for layer in manifest["layers"]:
        data = get("blobs/" + layer["digest"])
        assert hashlib.sha256(data).hexdigest() == layer["digest"].split(":")[1]
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(folder, filter=safe_member)
    (folder / "usr/sbin/policy-rc.d").write_text("#!/bin/sh\nexit 101\n")
    (folder / "usr/sbin/policy-rc.d").chmod(0o755)
    marker.write_text(json.dumps(manifest, indent=2) + "\n")
    return folder


def run(folder, command, log):
    args = ["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--unshare-pid", "--die-with-parent",
            "--bind", str(folder), "/", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/run", "--tmpfs", "/tmp",
            "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf", "--ro-bind", str(ROOT / "dist"), "/mnt/packages",
            "--clearenv", "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "--setenv", "HOME", "/root", "--setenv", "LANG", "C.UTF-8", "--setenv", "DEBIAN_FRONTEND", "noninteractive",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--chdir", "/", *command]
    subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", choices=["debian", "ubuntu"])
    parser.add_argument("tag")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    folder = prepare(args.image, args.tag)
    # The user namespace maps only root; apt's _apt UID cannot be represented.
    (folder / "etc/apt/apt.conf.d/99-classic-lens-test").write_text(
        'APT::Sandbox::User "root";\nDir::Bin::dpkg "/usr/local/bin/dpkg-fakeroot";\n')
    wrapper = folder / "usr/local/bin/dpkg-fakeroot"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\nexport FAKEROOTDONTTRYCHOWN=1\nexec fakeroot-sysv /usr/bin/dpkg "$@"\n')
    wrapper.chmod(0o755)
    # Slim OCI images exclude documentation. Include our package's docs so the
    # check validates every shipped file, as on a normal desktop installation.
    (folder / "etc/dpkg/dpkg.cfg.d/zz-classic-lens-test").write_text(
        'path-include=/usr/share/doc/classic-price-lens\n'
        'path-include=/usr/share/doc/classic-price-lens/*\n')
    print("Verified official test root:", folder, flush=True)
    if args.prepare_only:
        return
    package = max((ROOT / "dist").glob("lupin_*_amd64.deb"), key=lambda path: path.stat().st_mtime)
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    log_path = evidence / f"package-{args.image}-{args.tag}.log"
    with log_path.open("w") as log:
        run(folder, ["apt-get", "update", "-qq"], log)
        # Bootstrap the distribution's own fakeroot to emulate ownership of
        # dependency files whose non-root UIDs are outside this user namespace.
        run(folder, ["sh", "-c", "cd /root && apt-get download fakeroot libfakeroot && for archive in ./*.deb; do dpkg-deb -x \"$archive\" /; done"], log)
        run(folder, ["apt-get", "install", "-y", "--no-install-recommends", "/mnt/packages/" + package.name,
                     "xvfb", "xauth", "fonts-dejavu-core", "libxtst6"], log)
        run(folder, ["classic-price-lens", "--version"], log)
        run(folder, ["lupin", "--version"], log)
        run(folder, ["test", "-L", "/usr/bin/lupin"], log)
        run(folder, ["test", "-f", "/usr/share/pipewire/client.conf"], log)
        run(folder, ["classic-price-lens", "--self-test"], log)
        run(folder, ["env", "QT_QPA_PLATFORM=xcb", "xvfb-run", "-a", "classic-price-lens", "--self-test"], log)
        run(folder, ["sh", "-c", "cd /opt/classic-price-lens && QT_QPA_PLATFORM=xcb CLASSIC_LENS_TEST_X11=1 xvfb-run -a runtime/bin/python3 -B -m unittest discover -s tests -p test_hotkeys.py -v"], log)
        run(folder, ["sh", "-c", "cd /opt/classic-price-lens && QT_QPA_PLATFORM=offscreen runtime/bin/python3 -m unittest discover -s tests -q"], log)
        run(folder, ["dpkg", "--verify", "classic-price-lens"], log)
        run(folder, ["md5sum", "--check", "--quiet", "/var/lib/dpkg/info/classic-price-lens.md5sums"], log)
        run(folder, ["apt-get", "remove", "-y", "classic-price-lens"], log)
        run(folder, ["test", "!", "-e", "/usr/bin/classic-price-lens"], log)
        run(folder, ["test", "!", "-L", "/usr/bin/lupin"], log)
    print("PASS: install, offline OCR/overlay, X11 plugin, tests, package checksums and removal:", args.image, args.tag, flush=True)
    print("Log:", log_path, flush=True)


if __name__ == "__main__":
    main()
