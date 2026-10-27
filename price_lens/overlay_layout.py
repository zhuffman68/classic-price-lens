"""Shared corner layout for independent, screen-pixel annotations."""
from PySide6.QtCore import QRect


def corner_offset(bounds, occupied):
    """Stack a status above other cards that occupy the game's right corner."""
    offset = 0
    game = QRect(*bounds)
    for row in occupied:
        if row.get('bounds') == bounds and (row.get('anchor') == 'bottom_right' or
                row.get('anchor') == 'bottom_left' and game.width()<720):
            height = 36+17*len(row.get('extra','').splitlines())
            offset = max(offset, int(row.get('bottom_offset', 0)) + height + 6)
    return min(offset, max(0, game.height()-48))
