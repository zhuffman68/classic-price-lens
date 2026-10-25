"""Install, upgrade and remove the Windows build in an explicit isolated Wine prefix."""
import argparse
import os
from pathlib import Path
import subprocess
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "{1E77CC5D-AE19-4808-AD70-E009B578BA74}_is1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wine-prefix", type=Path, required=True)
    args = parser.parse_args()
    prefix = args.wine_prefix.resolve()
    if prefix == Path.home() / ".wine":
        parser.error("Use an isolated test prefix, never the default/game prefix")
    env = {**os.environ, "WINEPREFIX": str(prefix), "WINEDEBUG": "-all", "WINEDLLOVERRIDES": "mscoree,mshtml=",
           "QT_QPA_PLATFORM": "offscreen"}
    installer = max((ROOT / "dist").glob("ClassicPriceLens-*-Windows-x64-Setup.exe"), key=lambda p: p.stat().st_mtime)
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    log_path = evidence / "windows-installer-wine.log"
    key = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_ID

    def unix_path(path):
        return Path(subprocess.check_output(["winepath", "-u", path], env=env, text=True).strip())

    local = subprocess.check_output(["wine", "cmd", "/c", "echo %LOCALAPPDATA%"], env=env, text=True).strip()
    app = unix_path(local) / "Programs/Classic Price Lens"
    runtime = app / "runtime/python.exe"
    gui_runtime = app / "runtime/pythonw.exe"
    if app.exists() and not runtime.exists():
        # Remove only residue from earlier test artifacts in this isolated prefix.
        shutil.rmtree(app)

    with log_path.open("w") as log:
        def run(command, cwd=None, timeout=120):
            subprocess.run(["wine", *map(str, command)], cwd=cwd or ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)

        run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"])
        assert (app / "unins000.exe").is_file(), "Uninstall entry point missing"
        run(["reg", "query", key, "/v", "DisplayVersion"])
        run([runtime, "-B", "-m", "price_lens", "--version"], app)
        run([runtime, "-B", "-m", "price_lens", "--self-test"], app)
        run([runtime, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"], app)
        cache_code = ("from PySide6.QtCore import QCoreApplication; "
                      "from price_lens.platform_paths import cache_directory; app=QCoreApplication([]); "
                      "app.setApplicationName('Classic Price Lens'); app.setOrganizationName('LocalTools'); "
                      "print(cache_directory())")
        cache = subprocess.check_output(["wine", str(runtime), "-B", "-c", cache_code], cwd=app, env=env, text=True).strip()
        marker = unix_path(cache) / "installer-preservation-check.txt"
        marker.write_text("Keep user data during upgrade/removal.\n")

        def start_ui():
            process = subprocess.Popen(["wine", str(gui_runtime), "-B", "-m", "price_lens"],
                                       cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT)
            script = ("from PySide6.QtCore import QCoreApplication; "
                      "from price_lens.control import request; app=QCoreApplication([]); "
                      "app.setApplicationName('Classic Price Lens'); app.setOrganizationName('LocalTools'); "
                      "raise SystemExit(0 if request('activate', timeout=500) else 1)")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert process.poll() is None, "App exited before becoming ready"
                probe = subprocess.run(["wine", str(runtime), "-B", "-c", script], cwd=app, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=5)
                if probe.returncode == 0:
                    return process
                time.sleep(0.1)
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError("Own app IPC did not become ready")

        first = start_ui()
        run([gui_runtime, "-B", "-m", "price_lens"], app, timeout=10)
        assert first.poll() is None, "Second launch replaced the existing app"
        run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"])
        assert first.wait(timeout=30) == 0, "Upgrade did not close the existing app cleanly"
        assert marker.is_file(), "Upgrade removed user cache"
        second = start_ui()
        run([app / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
        assert second.wait(timeout=30) == 0, "Uninstall did not close the app cleanly"
        deadline = time.monotonic() + 10
        while app.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not app.exists(), "Uninstall left application files behind"
        assert marker.is_file(), "Uninstall removed user cache"
        result = subprocess.run(["wine", "reg", "query", key], env=env, stdout=log, stderr=subprocess.STDOUT)
        assert result.returncode != 0, "Uninstall registration was not removed"
    print("PASS: per-user install, OCR/overlay, tests, second launch, running-app upgrade/removal and cache retention", flush=True)
    print("Log:", log_path, flush=True)
    print("Wine binary/installer checks; native Windows desktop capture remains untested.", flush=True)


if __name__ == "__main__":
    main()
