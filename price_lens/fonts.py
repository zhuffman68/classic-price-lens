"""A bundled, readable interface font with consistent Windows/Linux metrics."""
from functools import lru_cache
from pathlib import Path
from PySide6.QtGui import QFont,QFontDatabase


@lru_cache(maxsize=1)
def interface_family():
    identity=QFontDatabase.addApplicationFont(str(Path(__file__).parent/'resources/fonts/InterVariable.ttf'))
    families=QFontDatabase.applicationFontFamilies(identity)
    return families[0] if families else QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


def interface_font(pixels,weight=QFont.Weight.Normal):
    font=QFont(interface_family());font.setPixelSize(pixels);font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    return font
