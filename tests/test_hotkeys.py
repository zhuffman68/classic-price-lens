"""OS shortcut registration and our own messages; no game input or keyboard hooks."""
import asyncio
import ctypes
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QWidget

from price_lens.hotkeys import parse_shortcut
from price_lens.portal_hotkey import portal_trigger, PortalHotkey


class ShortcutTests(unittest.TestCase):
    def test_function_key_and_modifier_combo_are_portable(self):
        self.assertEqual(parse_shortcut("Alt+Ctrl+P").text, "Ctrl+Alt+P")
        self.assertEqual(parse_shortcut("F8").text, "F8")
        if sys.platform=="win32":
            with self.assertRaises(ValueError):parse_shortcut("F12")
        else:self.assertEqual(parse_shortcut("F12").text,"F12")
        self.assertEqual(portal_trigger("Ctrl+Alt+P"), "CTRL+ALT+p")
        self.assertEqual(portal_trigger("Ctrl+Shift+F10"), "CTRL+SHIFT+F10")

    def test_unmodified_typing_modifier_only_multistep_and_reserved_keys_are_rejected(self):
        for text in ("", "P", "Ctrl", "Ctrl+K, Ctrl+C"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_shortcut(text)


@unittest.skipUnless(sys.platform == "win32", "Windows registration requires Windows binaries")
class WindowsShortcutTests(unittest.TestCase):
    def test_registration_own_hotkey_message_and_release(self):
        from price_lens.hotkeys import WindowsHotkey
        app = QApplication.instance() or QApplication([])
        fired = []
        hotkey = WindowsHotkey(lambda: fired.append(True))
        try:
            self.assertEqual(hotkey.register("Ctrl+Alt+Shift+F9"), "Ctrl+Alt+Shift+F9")
            message = hotkey.MSG()
            message.message, message.wParam = 0x0312, hotkey.id
            self.assertTrue(hotkey.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message))[0])
            self.assertEqual(fired, [True])
            message.wParam += 10
            self.assertFalse(hotkey.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message))[0])
            self.assertEqual(hotkey.register("Ctrl+Alt+Shift+P"), "Ctrl+Alt+Shift+P")
            other_fired=[]
            other=WindowsHotkey(lambda:other_fired.append(True))
            try:
                other.register("Ctrl+Alt+Shift+F8")
                self.assertNotEqual(other.id,hotkey.id)
                message.wParam=other.id
                self.assertFalse(hotkey.nativeEventFilter(b"windows_dispatcher_MSG",ctypes.addressof(message))[0])
                self.assertTrue(other.nativeEventFilter(b"windows_dispatcher_MSG",ctypes.addressof(message))[0])
                self.assertEqual(other_fired,[True])
            finally:other.close()
        finally:
            hotkey.close()
        second = WindowsHotkey(lambda: None)
        try:
            self.assertEqual(second.register("Ctrl+Alt+Shift+F9"), "Ctrl+Alt+Shift+F9")
        finally:
            second.close()


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("CLASSIC_LENS_TEST_X11") == "1",
                     "Requires an explicitly isolated Xvfb display")
class X11ShortcutTests(unittest.TestCase):
    def test_os_shortcut_activates_on_isolated_xvfb_and_conflicts_are_reported(self):
        from price_lens.hotkeys import X11Hotkey
        # This test must never synthesize input on the user's display.
        self.assertTrue(Path(os.environ.get("XAUTHORITY", "")).parent.name.startswith("xvfb-run."))
        app = QApplication.instance() or QApplication([])
        window = QWidget()
        window.show()
        window.activateWindow()
        app.processEvents()
        fired = []
        first = X11Hotkey(lambda: fired.append(True))
        second = X11Hotkey(lambda: None)
        try:
            first.register("Ctrl+Shift+F10")
            with self.assertRaises(ValueError):
                second.register("Ctrl+Shift+F10")
            from ctypes.util import find_library
            test = ctypes.CDLL(find_library("Xtst") or "libXtst.so.6")
            test.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            test.XTestFakeKeyEvent.restype = ctypes.c_int
            modifiers = [first.api.XKeysymToKeycode(first.display, first.api.XStringToKeysym(name))
                         for name in (b"Control_L", b"Shift_L")]
            injection = first.api.XOpenDisplay(None)
            try:
                for code in modifiers + [first.binding[0]]:
                    test.XTestFakeKeyEvent(injection, code, 1, 0)
                for code in [first.binding[0]] + modifiers[::-1]:
                    test.XTestFakeKeyEvent(injection, code, 0, 0)
                # Sync a separate test connection so the shortcut connection's
                # events remain in its fd for QSocketNotifier to deliver.
                first.api.XSync(injection, 0)
            finally:
                first.api.XCloseDisplay(injection)
            end = time.monotonic() + 2
            while not fired and time.monotonic() < end:
                app.processEvents()
                time.sleep(0.001)
            self.assertEqual(fired, [True])
            first.close()
            self.assertEqual(second.register("Ctrl+Shift+F10"), "Ctrl+Shift+F10")
        finally:
            first.close()
            second.close()
            window.close()


@unittest.skipUnless(importlib.util.find_spec("dbus_next"), "Wayland portal dependency is Linux-only")
class PortalShortcutTests(unittest.IsolatedAsyncioTestCase):
    def portal(self):
        instance = PortalHotkey.__new__(PortalHotkey)
        instance.application_id = "io.github.zhuffman68.ClassicPriceLens.Test"
        instance.loop = asyncio.get_running_loop()
        instance.pending = {}
        instance.session = None
        instance.starting = True
        instance.closed = False
        instance.events, instance.descriptions = [], []
        instance.activated = lambda: instance.events.append(True)
        instance.changed = instance.descriptions.append
        return instance

    async def test_real_dbus_wire_shapes_and_response_before_method_reply(self):
        from dbus_next import Message, MessageType, Variant
        instance = self.portal()
        session = "/org/freedesktop/portal/desktop/session/test/lens"
        calls = []
        class Bus:
            unique_name = ":1.99"
            async def connect(self):
                return self
            def add_message_handler(self, callback):
                self.callback = callback
            async def call(self, message):
                message._marshall()  # Exercise real dbus-next signature/body validation.
                calls.append(message)
                if message.member in ("AddMatch", "Register"):
                    return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)
                token = message.body[-1]["handle_token"].value
                path = "/org/freedesktop/portal/desktop/request/1_99/" + token
                values = ({"session_handle": Variant("s", session)} if message.member == "CreateSession" else
                          {"shortcuts": Variant("a(sa{sv})", [])} if message.member == "ListShortcuts" else
                          {"shortcuts": Variant("a(sa{sv})", [["toggle-reading", {"trigger_description": Variant("s", "Ctrl+Alt+P")} ]])})
                self.callback(Message(message_type=MessageType.SIGNAL, path=path, interface="org.freedesktop.portal.Request",
                                      member="Response", signature="ua{sv}", body=[0, values]))
                return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1, signature="o", body=[path])
        with patch("dbus_next.aio.MessageBus", return_value=Bus()):
            await instance._start("CTRL+ALT+p")
        self.assertEqual([call.member for call in calls], ["AddMatch", "Register", "CreateSession", "ListShortcuts", "BindShortcuts"])
        self.assertEqual(instance.descriptions, ["Ctrl+Alt+P"])
        self.assertFalse(instance.starting)
        self.assertFalse(instance.pending)

    async def test_four_features_bind_in_one_session_and_dispatch_independently(self):
        from dbus_next import Message,MessageType,Variant
        instance=self.portal();calls=[];fired=[];session='/test/three'
        instance.actions={identity:dict(key=key,description=identity,
            activate=lambda identity=identity:fired.append(identity),changed=lambda value:None)
            for identity,key in [('toggle-prices','F10'),('toggle-exp','F11'),('translate-text','F12'),('compose-korean','F8')]}
        class Bus:
            unique_name=':1.99'
            async def connect(self):return self
            def add_message_handler(self,callback):self.callback=callback
            async def call(self,message):
                message._marshall();calls.append(message)
                if message.member in ('AddMatch','Register'):
                    return Message(message_type=MessageType.METHOD_RETURN,reply_serial=1)
                token=message.body[-1]['handle_token'].value
                path='/org/freedesktop/portal/desktop/request/1_99/'+token
                values=({'session_handle':Variant('s',session)} if message.member=='CreateSession' else
                        {'shortcuts':Variant('a(sa{sv})',[] if message.member=='ListShortcuts' else
                            [[k,{'trigger_description':Variant('s',v['key'])}] for k,v in instance.actions.items()])})
                self.callback(Message(message_type=MessageType.SIGNAL,path=path,interface='org.freedesktop.portal.Request',
                                      member='Response',signature='ua{sv}',body=[0,values]))
                return Message(message_type=MessageType.METHOD_RETURN,reply_serial=1,signature='o',body=[path])
        with patch('dbus_next.aio.MessageBus',return_value=Bus()):await instance._start('F10')
        self.assertEqual(sum(c.member=='CreateSession' for c in calls),1)
        bindings=next(c.body[1] for c in calls if c.member=='BindShortcuts')
        self.assertEqual([(identity,options['preferred_trigger'].value) for identity,options in bindings],
                         [('toggle-prices','F10'),('toggle-exp','F11'),('translate-text','F12'),('compose-korean','F8')])
        for action in instance.actions:
            for target in ('/other',session):
                instance._message(Message(message_type=MessageType.SIGNAL,path='/org/freedesktop/portal/desktop',
                    interface='org.freedesktop.portal.GlobalShortcuts',member='Activated',signature='osta{sv}',body=[target,action,1,{}]))
        self.assertEqual(fired,list(instance.actions))

    async def test_composer_receives_only_its_portal_activation_token(self):
        from dbus_next import Message,MessageType,Variant
        instance=self.portal();instance.session='/test/token';events=[]
        instance.actions={'compose-korean':{'token':lambda t:events.append(t),'activate':lambda:events.append('show')}}
        for session in ('/other','/test/token'):
            instance._message(Message(message_type=MessageType.SIGNAL,path='/org/freedesktop/portal/desktop',
                interface='org.freedesktop.portal.GlobalShortcuts',member='Activated',signature='osta{sv}',
                body=[session,'compose-korean',1,{'activation_token':Variant('s','our-popup-token')}]))
        self.assertEqual(events,['our-popup-token','show'])

    async def test_only_the_registered_session_and_action_can_activate(self):
        from dbus_next import Message, MessageType
        instance = self.portal()
        instance.session = "/test/session"
        for session, action in (("/other/session", "toggle-reading"), ("/test/session", "other"),
                                ("/test/session", "toggle-reading")):
            instance._message(Message(message_type=MessageType.SIGNAL, path="/org/freedesktop/portal/desktop",
                                      interface="org.freedesktop.portal.GlobalShortcuts", member="Activated",
                                      signature="osta{sv}", body=[session, action, 1, {}]))
        self.assertEqual(instance.events, [True])

    async def test_translation_and_pause_actions_are_independent(self):
        from dbus_next import Message,MessageType
        pause=self.portal();pause.session="/test/pause"
        translation=self.portal();translation.session="/test/translation";translation.action="translate-chat"
        message=Message(message_type=MessageType.SIGNAL,path="/org/freedesktop/portal/desktop",
                        interface="org.freedesktop.portal.GlobalShortcuts",member="Activated",
                        signature="osta{sv}",body=[translation.session,"translate-chat",1,{}])
        pause._message(message);translation._message(message)
        self.assertEqual(pause.events,[]);self.assertEqual(translation.events,[True])
