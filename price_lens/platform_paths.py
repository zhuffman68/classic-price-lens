"""Paths for a source checkout or an extracted Windows portable bundle."""
from pathlib import Path
import getpass
import re
import sys

from PySide6.QtCore import QStandardPaths


def reader_binary(root):
    root = Path(root)
    name = "classic-screen-reader.exe" if sys.platform == "win32" else "classic-screen-reader"
    choices = [root / "bin" / name, root / "reader/target/release" / name, root / "reader/target/debug" / name]
    return next((path for path in choices if path.is_file()), choices[-1])


def capture_socket_name():
    if sys.platform == "win32":
        user = re.sub(r"[^a-zA-Z0-9_]", "_", getpass.getuser())
        return "ClassicPriceLens-stream-v1-" + user
    runtime = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation))
    return str(runtime / "classic-price-lens-stream-v1")


def capture_lock_path():
    cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    cache.mkdir(parents=True, exist_ok=True)
    return str(cache / "stream.lock")
