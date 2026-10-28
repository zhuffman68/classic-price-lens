import argparse
import signal
from pathlib import Path
import sys

from . import APP_NAME, LEGACY_APP_NAME, __version__


def main():
    parser = argparse.ArgumentParser(description="Tools for MapleStory Classic World")
    parser.add_argument("--version", action="version", version=APP_NAME + " " + __version__)
    control_options = parser.add_mutually_exclusive_group()
    control_options.add_argument("--quit", action="store_true", help="Close the running Lupin instance")
    control_options.add_argument("--toggle", action="store_true", help="Toggle reading/overlay in the running instance")
    control_options.add_argument("--minimize", action="store_true", help="Minimize the running panel using its tray preference")
    control_options.add_argument("--translate", action="store_true", help="Scan Korean text using the running instance's shared screen")
    control_options.add_argument("--prices",action="store_true",help="Toggle price reading without pausing EXP")
    control_options.add_argument("--exp",action="store_true",help="Start, pause or resume EXP tracking")
    control_options.add_argument('--compose',action='store_true',help='Open the English to Korean clipboard composer')
    parser.add_argument("--self-test", action="store_true", help="Check bundled OCR and overlay IPC without screen capture")
    parser.add_argument("--snapshot", type=Path, help="Read a saved shop screenshot")
    parser.add_argument("--capture", action="store_true", help="Open OS screen-sharing picker on startup")
    parser.add_argument("--kde", action="store_true", help="Use the KDE/Spectacle screenshot fallback")
    parser.add_argument("--cache", type=Path, help="Alternate local SQLite cache")
    args = parser.parse_args()
    from .qt_runtime import configure_qt
    configure_qt()
    if args.self_test:
        from .selftest import main as self_test
        return self_test()
    from PySide6.QtCore import QCoreApplication
    from .control import AppControl, request
    if args.quit or args.toggle or args.minimize or args.translate or args.prices or args.exp or args.compose:
        app = QCoreApplication(sys.argv[:1])
        app.setApplicationName(LEGACY_APP_NAME)
        app.setOrganizationName("LocalTools")
        command = "quit" if args.quit else "toggle" if args.toggle else "translate" if args.translate else "prices" if args.prices else "exp" if args.exp else 'compose' if args.compose else "minimize"
        answer = request(command, timeout=30000 if args.quit else 3000)
        if answer is None:
            if args.toggle or args.minimize or args.translate or args.prices or args.exp or args.compose:
                return 0
            probe = AppControl()
            if not probe.start():
                return 1
            probe.close()
            return 0
        return 0 if answer else 1
    from PySide6.QtWidgets import QApplication
    from .icons import app_icon
    from .platform_paths import cache_directory
    from .ui import LensWindow
    app = QApplication(["classic-price-lens"])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(LEGACY_APP_NAME)
    app.setOrganizationName("LocalTools")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("io.github.zhuffman68.ClassicPriceLens")
    control = AppControl(app)
    if not control.start():
        return 0 if request("activate") else 1
    root = Path(__file__).resolve().parent.parent
    app.setWindowIcon(app_icon(root))
    cache = args.cache or cache_directory() / "prices.sqlite"
    from .kde_window_policy import ensure_kde_window_policy
    ensure_kde_window_policy(app.platformName(), cache_directory())
    window = LensWindow(root, cache, args.snapshot, args.capture, args.kde)
    window.closed.connect(app.quit)
    def activate():
        if window.closing:
            return
        window.tray.restore()
    control.activate.connect(activate)
    control.quit.connect(window.close)
    control.toggle.connect(window.toggle_capture)
    control.minimize.connect(window.showMinimized)
    control.translate.connect(window.translate_chat)
    control.prices.connect(window.toggle_prices)
    control.exp.connect(window.on_exp_hotkey)
    control.compose.connect(window.open_composer)
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
    try:
        result = app.exec()
        # Keep installer IPC alive until in-flight network workers have exited.
        # Normal window closure has already stopped capture/OCR/annotations.
        window.service.pool.shutdown(wait=True, cancel_futures=True)
        return result
    finally:
        control.close()


if __name__ == "__main__":
    raise SystemExit(main())
