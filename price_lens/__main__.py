import argparse
import signal
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from .ui import LensWindow


def main():
    parser = argparse.ArgumentParser(description="Classic World screen-only market companion")
    parser.add_argument("--snapshot", type=Path, help="Read a saved shop screenshot")
    parser.add_argument("--capture", action="store_true", help="Open OS screen-sharing picker on startup")
    parser.add_argument("--kde", action="store_true", help="Use KDE OS screenshots of the selected monitor every 3 seconds")
    parser.add_argument("--cache", type=Path, help="Alternate local SQLite cache")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Classic Price Lens")
    app.setOrganizationName("LocalTools")
    root = Path(__file__).resolve().parent.parent
    cache = args.cache or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "prices.sqlite"
    window = LensWindow(root, cache, args.snapshot, args.capture, args.kde)
    # Place our own window on the middle display, without touching other windows.
    screens = app.screens()
    if len(screens) > 1:
        screen = sorted(screens, key=lambda s: s.geometry().x())[len(screens) // 2]
        geometry = screen.availableGeometry()
        window.move(geometry.right() - window.width() - 24, geometry.y() + 48)
    window.show()
    signal.signal(signal.SIGTERM, lambda signum, frame: window.close())
    signal.signal(signal.SIGINT, lambda signum, frame: window.close())
    if hasattr(signal, "SIGUSR1"):
        def handoff(signum, frame):
            window.keep_capture = True
            window.close()
        signal.signal(signal.SIGUSR1, handoff)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
