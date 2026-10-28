"""Display selection is explicit; only Wayland capture needs the OS picker."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect
from price_lens.capture_platform import uses_system_picker, screen_for_rectangle


class CapturePlatformTests(unittest.TestCase):
    def test_windows_does_not_promise_a_linux_picker(self):
        with patch('price_lens.capture_platform.sys.platform','win32'), patch.dict('os.environ',{'WAYLAND_DISPLAY':'wayland-0'},clear=True):
            self.assertFalse(uses_system_picker())

    def test_wayland_requires_portal_and_x11_uses_the_display_directly(self):
        with patch('price_lens.capture_platform.sys.platform','linux'):
            with patch.dict('os.environ',{'WAYLAND_DISPLAY':'wayland-0'},clear=True):
                self.assertTrue(uses_system_picker())
            with patch.dict('os.environ',{},clear=True):
                self.assertFalse(uses_system_picker())

    def test_screen_selection_matches_geometry_and_never_substitutes_primary(self):
        first=SimpleNamespace(geometry=lambda:QRect(-1920,0,1920,1080))
        second=SimpleNamespace(geometry=lambda:QRect(0,0,1920,1080))
        self.assertIs(screen_for_rectangle([first,second],QRect(0,0,1920,1080)),second)
        self.assertIs(screen_for_rectangle([first,second],QRect(-1920,0,1920,1080)),first)
        self.assertIsNone(screen_for_rectangle([first,second],QRect(1920,0,1920,1080)))


if __name__ == '__main__':unittest.main()
