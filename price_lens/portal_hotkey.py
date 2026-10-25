"""Wayland global shortcuts through the desktop portal, without key interception."""
import asyncio
from concurrent.futures import CancelledError
import threading
import uuid
from pathlib import Path
import sys

SERVICE = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
INTERFACE = "org.freedesktop.portal.GlobalShortcuts"


class PortalError(RuntimeError):
    def __init__(self, name, message):
        super().__init__(message)
        self.name = name


def application_identity():
    """Installed builds have a desktop entry; source runs get a separate hidden identity."""
    root = Path(__file__).resolve().parents[1]
    identity = "io.github.zhuffman68.ClassicPriceLens"
    if (root / "bin/classic-screen-reader").is_file():
        return identity
    from PySide6.QtCore import QStandardPaths
    identity += ".Development"
    directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ApplicationsLocation))
    directory.mkdir(parents=True, exist_ok=True)
    desktop = directory / (identity + ".desktop")
    if not desktop.exists():
        def value(text):
            return str(text).replace("\\", "\\\\").replace("\n", "\\n")
        program = str(sys.executable).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
        desktop.write_text("[Desktop Entry]\nType=Application\nName=Classic Price Lens (development)\nNoDisplay=true\n"
                           f'Exec="{program}" -m price_lens --capture\nPath={value(root)}\n'
                           f"Icon={value(root / 'price_lens/resources/icon.png')}\nTerminal=false\n")
    return identity


def portal_trigger(text):
    from .hotkeys import parse_shortcut
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence
    spec = parse_shortcut(text)
    prefixes = "".join(tag for qt, tag in ((Qt.ControlModifier, "CTRL+"), (Qt.AltModifier, "ALT+"),
                                          (Qt.ShiftModifier, "SHIFT+"), (Qt.MetaModifier, "LOGO+"))
                       if spec.modifiers & qt.value)
    key = QKeySequence(spec.key).toString(QKeySequence.SequenceFormat.PortableText)
    return prefixes + key.lower() if len(key) == 1 else prefixes + key


class PortalHotkey:
    def __init__(self, activated, changed, status):
        self.application_id = application_identity()
        self.activated, self.changed, self.status = activated, changed, status
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="desktop-shortcut", daemon=True)
        self.thread.start()
        self.bus = None
        self.session = None
        self.pending = {}
        self.starting = False
        self.closed = False

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        for task in asyncio.all_tasks(self.loop):
            task.cancel()
        self.loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(self.loop), return_exceptions=True))
        self.loop.close()

    def _submit(self, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        def done(result):
            try:
                result.result()
            except (asyncio.CancelledError, CancelledError):
                pass
            except Exception as error:
                if not self.closed:
                    self.status("Global shortcut: " + str(error) + ". Desktop fallback: classic-price-lens --toggle")
        future.add_done_callback(done)

    def register(self, text):
        if not self.session and not self.starting:
            self.starting = True
            self._submit(self._start(portal_trigger(text)))
        return None

    def _message(self, message):
        from dbus_next import MessageType
        if self.closed or message.message_type != MessageType.SIGNAL:
            return
        if message.interface == "org.freedesktop.portal.Request" and message.member == "Response":
            pending = self.pending.get(message.path)
            if pending and not pending.done():
                pending.set_result(message.body)
        elif message.interface == INTERFACE and message.member == "Activated":
            if message.body[:2] == [self.session, "toggle-reading"]:
                self.activated()
        elif message.interface == INTERFACE and message.member == "ShortcutsChanged":
            if message.body[0] == self.session:
                self._description(message.body[1])

    def _description(self, shortcuts):
        for identity, options in shortcuts:
            if identity == "toggle-reading":
                value = options.get("trigger_description")
                self.changed(value.value if value else "Desktop shortcut")
                return True
        return False

    async def _call(self, interface, member, signature="", body=None, path=PATH):
        from dbus_next import Message, MessageType
        reply = await asyncio.wait_for(self.bus.call(Message(destination=SERVICE, path=path, interface=interface,
                                                            member=member, signature=signature, body=body or [])), timeout=10)
        if reply.message_type == MessageType.ERROR:
            raise PortalError(reply.error_name, reply.body[0] if reply.body else reply.error_name)
        return reply.body

    async def _request(self, member, signature, body, token):
        expected = "/org/freedesktop/portal/desktop/request/" + self.bus.unique_name[1:].replace(".", "_") + "/" + token
        future = self.loop.create_future()
        self.pending[expected] = future
        try:
            response = await self._call(INTERFACE, member, signature, body)
            actual = response[0]
            if actual != expected:
                self.pending[actual] = future
            code, values = await asyncio.wait_for(future, timeout=120)
            if code:
                raise RuntimeError("Shortcut registration was canceled" if code == 1 else "Desktop shortcut registration failed")
            return values
        finally:
            for path in [path for path, value in self.pending.items() if value is future]:
                self.pending.pop(path, None)

    async def _start(self, preferred):
        from dbus_next import Message, MessageType, Variant
        from dbus_next.aio import MessageBus
        try:
            self.bus = await MessageBus().connect()
            self.bus.add_message_handler(self._message)
            reply = await asyncio.wait_for(self.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                                                interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                                                                body=["type='signal',sender='org.freedesktop.portal.Desktop'"])), timeout=10)
            if reply.message_type == MessageType.ERROR:
                raise RuntimeError("Cannot subscribe to the desktop shortcut service")
            try:
                await self._call("org.freedesktop.host.portal.Registry", "Register", "sa{sv}",
                                 [self.application_id, {}])
            except PortalError as error:
                if error.name not in ("org.freedesktop.DBus.Error.UnknownMethod", "org.freedesktop.DBus.Error.UnknownInterface"):
                    raise
            token = "lens_" + uuid.uuid4().hex
            result = await self._request("CreateSession", "a{sv}",
                                         [{"handle_token": Variant("s", token), "session_handle_token": Variant("s", "lens_" + uuid.uuid4().hex)}], token)
            self.session = result["session_handle"].value
            token = "lens_" + uuid.uuid4().hex
            previous = await self._request("ListShortcuts", "oa{sv}",
                                            [self.session, {"handle_token": Variant("s", token)}], token)
            if self._description(previous.get("shortcuts", Variant("a(sa{sv})", [])).value):
                # Bind the existing action to this session, reusing stored consent.
                preferred = None
            token = "lens_" + uuid.uuid4().hex
            options = {"description": Variant("s", "Pause or resume Classic Price Lens")}
            if preferred:
                options["preferred_trigger"] = Variant("s", preferred)
            result = await self._request("BindShortcuts", "oa(sa{sv})sa{sv}",
                                         [self.session, [["toggle-reading", options]], "", {"handle_token": Variant("s", token)}], token)
            if not self._description(result.get("shortcuts", Variant("a(sa{sv})", [])).value):
                self.status("No shortcut is assigned. Use Hotkey… to choose one.")
        finally:
            self.starting = False

    def configure(self):
        if self.session:
            self._submit(self._call(INTERFACE, "ConfigureShortcuts", "osa{sv}", [self.session, "", {}]))
        else:
            self.register("Ctrl+Alt+P")

    def close(self):
        self.closed = True
        async def shutdown():
            try:
                if self.session and self.bus:
                    await self._call("org.freedesktop.portal.Session", "Close", path=self.session)
            finally:
                for future in self.pending.values():
                    future.cancel()
                if self.bus:
                    self.bus.disconnect()
                self.loop.call_soon(self.loop.stop)
        if self.loop.is_running():
            self._submit(shutdown())
