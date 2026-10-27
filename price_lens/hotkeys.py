"""OS-registered shortcuts only. No keyboard listeners, game handles or input hooks."""
import ctypes
from dataclasses import dataclass
import os
import sys
import itertools

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QSocketNotifier, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence

DEFAULT_HOTKEY = "F10"


@dataclass(frozen=True)
class Shortcut:
    text: str
    key: int
    modifiers: int


def parse_shortcut(text):
    sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1 or sequence.isEmpty():
        raise ValueError("Choose one key or one key combination.")
    chord = sequence[0]
    key, modifiers = chord.key().value, chord.keyboardModifiers().value
    if key in (0, Qt.Key.Key_unknown.value, Qt.Key.Key_Control.value, Qt.Key.Key_Shift.value,
               Qt.Key.Key_Alt.value, Qt.Key.Key_Meta.value):
        raise ValueError("Include a key as well as any modifiers.")
    if key == Qt.Key.Key_F12.value and sys.platform=="win32":
        raise ValueError("F12 is reserved on Windows. Choose another key.")
    if not modifiers and not (Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F35.value
                              or key in (Qt.Key.Key_Pause.value, Qt.Key.Key_ScrollLock.value)):
        raise ValueError("Use a function key, or combine a key with Ctrl, Alt, Shift or Meta.")
    return Shortcut(sequence.toString(QKeySequence.SequenceFormat.PortableText), key, modifiers)


class WindowsHotkey(QAbstractNativeEventFilter):
    """RegisterHotKey posts WM_HOTKEY to this app's own message queue."""
    ids = itertools.count(0x45AA, 2)
    def __init__(self, callback):
        super().__init__()
        from ctypes import wintypes
        self.MSG = wintypes.MSG
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.UnregisterHotKey.restype = wintypes.BOOL
        self.callback = callback
        self.id = None
        self.id_base = next(self.ids)
        QGuiApplication.instance().installNativeEventFilter(self)

    def register(self, text):
        spec = parse_shortcut(text)
        modifiers = 0x4000  # MOD_NOREPEAT
        for qt, native in ((Qt.ControlModifier, 2), (Qt.AltModifier, 1), (Qt.ShiftModifier, 4), (Qt.MetaModifier, 8)):
            if spec.modifiers & qt.value:
                modifiers |= native
        special = {Qt.Key_Tab: 9, Qt.Key_Backspace: 8, Qt.Key_Return: 13, Qt.Key_Enter: 13,
                   Qt.Key_Escape: 27, Qt.Key_Space: 32, Qt.Key_Home: 36, Qt.Key_End: 35,
                   Qt.Key_PageUp: 33, Qt.Key_PageDown: 34, Qt.Key_Insert: 45, Qt.Key_Delete: 46,
                   Qt.Key_Left: 37, Qt.Key_Up: 38, Qt.Key_Right: 39, Qt.Key_Down: 40,
                   Qt.Key_Pause: 19, Qt.Key_ScrollLock: 145}
        if Qt.Key_F1.value <= spec.key <= Qt.Key_F24.value:
            virtual = 0x70 + spec.key - Qt.Key_F1.value
        elif spec.key in special:
            virtual = special[spec.key]
        elif 0x30 <= spec.key <= 0x5A:
            virtual = spec.key
        elif 0x20 <= spec.key < 0x10000:
            self.api.VkKeyScanW.argtypes = [ctypes.c_wchar]
            self.api.VkKeyScanW.restype = ctypes.c_short
            mapped = self.api.VkKeyScanW(chr(spec.key))
            if mapped == -1:
                raise ValueError("That key is unavailable in the active keyboard layout.")
            virtual = mapped & 255
            for native_bit, modifier in ((1, 4), (2, 2), (4, 1)):
                if (mapped >> 8) & native_bit:
                    modifiers |= modifier
        else:
            raise ValueError("Choose a letter, number, navigation key or F1–F24.")
        new_id = self.id_base+1 if self.id == self.id_base else self.id_base
        if not self.api.RegisterHotKey(None, new_id, modifiers, virtual):
            raise ValueError("That shortcut is reserved or already used. Choose another combination.")
        if self.id is not None:
            self.api.UnregisterHotKey(None, self.id)
        self.id = new_id
        return spec.text

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            event = self.MSG.from_address(int(message))
            if event.message == 0x0312 and self.id is not None and event.wParam == self.id:
                self.callback()
                return True, 0
        return False, 0

    def close(self):
        if self.id is not None:
            self.api.UnregisterHotKey(None, self.id)
            self.id = None
        if QGuiApplication.instance():
            QGuiApplication.instance().removeNativeEventFilter(self)


class X11Hotkey:
    """An X11 passive grab for one registered chord, on our own X connection."""
    def __init__(self, callback):
        from ctypes.util import find_library
        self.api = ctypes.CDLL(find_library("X11") or "libX11.so.6")
        signatures = {
            "XOpenDisplay": (ctypes.c_void_p, [ctypes.c_char_p]),
            "XDefaultRootWindow": (ctypes.c_ulong, [ctypes.c_void_p]),
            "XConnectionNumber": (ctypes.c_int, [ctypes.c_void_p]),
            "XStringToKeysym": (ctypes.c_ulong, [ctypes.c_char_p]),
            "XKeysymToKeycode": (ctypes.c_ubyte, [ctypes.c_void_p, ctypes.c_ulong]),
            "XkbKeycodeToKeysym": (ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_int, ctypes.c_int]),
            "XGrabKey": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int]),
            "XUngrabKey": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]),
            "XPending": (ctypes.c_int, [ctypes.c_void_p]),
            "XNextEvent": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p]),
            "XSync": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
            "XCloseDisplay": (ctypes.c_int, [ctypes.c_void_p]),
            "XSetErrorHandler": (ctypes.c_void_p, [ctypes.c_void_p]),
            "XkbSetDetectableAutoRepeat": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.api, name)
            function.restype, function.argtypes = result, args
        self.display = self.api.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("No X11 desktop is available for shortcut registration.")
        self.root = self.api.XDefaultRootWindow(self.display)
        supported = ctypes.c_int()
        self.api.XkbSetDetectableAutoRepeat(self.display, 1, ctypes.byref(supported))
        self.notifier = QSocketNotifier(self.api.XConnectionNumber(self.display), QSocketNotifier.Type.Read)
        self.notifier.activated.connect(self.receive)
        self.callback = callback
        self.binding = None
        self.down = False

    def register(self, text):
        spec = parse_shortcut(text)
        if (Qt.Key_F1.value <= spec.key <= Qt.Key_F12.value
                and spec.modifiers & Qt.ControlModifier.value and spec.modifiers & Qt.AltModifier.value):
            raise ValueError("Ctrl+Alt+function keys are reserved for Linux virtual consoles. Choose another combination.")
        if Qt.Key_F1.value <= spec.key <= Qt.Key_F35.value:
            name = "F" + str(spec.key - Qt.Key_F1.value + 1)
        else:
            names = {Qt.Key_Space: "space", Qt.Key_Tab: "Tab", Qt.Key_Backspace: "BackSpace",
                     Qt.Key_Escape: "Escape", Qt.Key_Return: "Return", Qt.Key_Enter: "Return",
                     Qt.Key_PageUp: "Prior", Qt.Key_PageDown: "Next", Qt.Key_ScrollLock: "Scroll_Lock",
                     Qt.Key_Plus: "plus", Qt.Key_Minus: "minus"}
            name = names.get(spec.key, chr(spec.key).lower() if spec.key < 256 else QKeySequence(spec.key).toString())
        symbol = self.api.XStringToKeysym(name.encode())
        keycode = self.api.XKeysymToKeycode(self.display, symbol)
        if not symbol or not keycode:
            raise ValueError("That key is unavailable in the active keyboard layout.")
        modifiers = 0
        for qt, native in ((Qt.ControlModifier, 4), (Qt.AltModifier, 8), (Qt.ShiftModifier, 1), (Qt.MetaModifier, 64)):
            if spec.modifiers & qt.value:
                modifiers |= native
        if (self.api.XkbKeycodeToKeysym(self.display, keycode, 0, 0) != symbol
                and self.api.XkbKeycodeToKeysym(self.display, keycode, 0, 1) == symbol):
            modifiers |= 1
        binding = keycode, modifiers
        if binding == self.binding:
            return spec.text
        errors = []
        callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        handler = callback_type(lambda display, event: (errors.append(True), 0)[1])
        previous = self.api.XSetErrorHandler(ctypes.cast(handler, ctypes.c_void_p))
        try:
            for locks in (0, 2, 16, 18):  # Caps Lock / Num Lock do not change the chord.
                self.api.XGrabKey(self.display, keycode, modifiers | locks, self.root, 0, 1, 1)
            self.api.XSync(self.display, 0)
        finally:
            self.api.XSetErrorHandler(previous)
        if errors:
            self.ungrab(binding)
            raise ValueError("That shortcut is already used. Choose another combination.")
        self.ungrab(self.binding)
        self.binding = binding
        self.down = False
        return spec.text

    def ungrab(self, binding):
        if binding:
            for locks in (0, 2, 16, 18):
                self.api.XUngrabKey(self.display, binding[0], binding[1] | locks, self.root)
            self.api.XSync(self.display, 0)

    def receive(self, *args):
        event = (ctypes.c_long * 24)()
        while self.display and self.api.XPending(self.display):
            self.api.XNextEvent(self.display, ctypes.byref(event))
            event_type = ctypes.c_int.from_buffer(event).value
            if event_type == 2 and not self.down:
                self.down = True
                self.callback()
            elif event_type == 3:
                self.down = False

    def close(self):
        if self.display:
            self.notifier.setEnabled(False)
            self.ungrab(self.binding)
            self.api.XCloseDisplay(self.display)
            self.display = None
            self.binding = None


class HotkeyManager(QObject):
    activated = Signal()
    activation_token = Signal(str)
    changed = Signal(str)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.portal = sys.platform == "linux" and bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland")
        self.backend = None
        self.text = None
        self.action = "toggle-reading"
        self.actions=None

    def start(self, text=DEFAULT_HOTKEY):
        try:
            if self.backend is not None and not self.portal and self.text == parse_shortcut(text).text:
                return True
            if self.backend is None:
                if sys.platform == "win32":
                    self.backend = WindowsHotkey(self.activated.emit)
                elif self.portal:
                    from .portal_hotkey import PortalHotkey
                    self.backend = PortalHotkey(self.activated.emit, self.changed.emit, self.status.emit, action=self.action,actions=self.actions)
                elif sys.platform == "linux":
                    self.backend = X11Hotkey(self.activated.emit)
                else:
                    raise RuntimeError("Use a desktop shortcut that runs classic-price-lens --toggle.")
            description = self.backend.register(text)
            if description:
                self.text = description
                self.changed.emit(description)
            return True
        except (OSError, RuntimeError, ValueError, ImportError) as error:
            self.status.emit(str(error))
            return False

    def configure(self):
        if self.backend is not None and self.portal:
            self.backend.configure()
        else:
            self.start()

    def close(self):
        if self.backend is not None:
            self.backend.close()
            self.backend = None
            self.text = None
