"""Native-size pixel-art icons shared by the panel and tray."""
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon


def app_icon(root):
    icon = QIcon()
    resources = root / "price_lens/resources"
    for size in (16, 24, 32, 48, 64, 128, 256):
        name = "icon.png" if size == 256 else f"icon-{size}.png"
        icon.addFile(str(resources / name), QSize(size, size))
    return icon
