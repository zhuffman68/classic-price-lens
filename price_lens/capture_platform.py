"""Describe the OS capture flow without promising a picker on every platform."""
import os
import sys


def uses_system_picker():
    return sys.platform == "linux" and bool(
        os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("QT_SCREEN_CAPTURE_BACKEND") == "pipewire")


def screen_for_rectangle(screens, rectangle):
    return next((screen for screen in screens if screen.geometry() == rectangle), None)

