"""Native-size pixel-art icons shared by the panel and tray."""
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon


def app_icon(root):
    resources = root / "price_lens/resources"
    icon = QIcon()
    for size in (16,20,22,24,28,32,40,48,56,64,96,128,256):
        name = "icon.png" if size == 256 else f"icon-{size}.png"
        icon.addFile(str(resources / name), QSize(size, size))
    return icon
