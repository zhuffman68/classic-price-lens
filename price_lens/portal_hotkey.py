"""Wayland global shortcuts through the desktop portal, without key interception."""
import asyncio
from concurrent.futures import CancelledError
import configparser
import os
import stat
import tempfile
import threading
import uuid
from pathlib import Path
import sys

from . import APP_NAME,LEGACY_APP_NAME

SERVICE = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
INTERFACE = "org.freedesktop.portal.GlobalShortcuts"


class PortalError(RuntimeError):
    def __init__(self, name, message):
        super().__init__(message)
        self.name = name


def _desktop_value(text):
    return str(text).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t')


def _development_entry(root,program):
    # Desktop Entry string escaping runs before Exec argument unquoting. Both
    # layers are required for literal quotes, dollar signs and backslashes.
    argument=''.join('\\'+char if char in '\\"`$' else char for char in str(program).replace('%','%%'))
    return dict(Type='Application',Name=_desktop_value(APP_NAME+' (development)'),NoDisplay='true',
                Exec=_desktop_value('"'+argument+'" -m price_lens --capture'),Path=_desktop_value(root),
                Icon=_desktop_value(root/'price_lens/resources/icon.png'),Terminal='false')


def _desktop_fields(text):
    parser=configparser.ConfigParser(interpolation=None);parser.optionxform=str
    try:
        parser.read_string(text)
        if parser.defaults() or parser.sections()!=['Desktop Entry']:return {}
        return dict(parser['Desktop Entry'])
    except configparser.Error:
        return {}


def _refresh_development_entry(desktop,values):
    previous=None
    if desktop.exists() or desktop.is_symlink():
        # Never follow a desktop-entry symlink or replace a different launcher.
        info=desktop.lstat()
        if not stat.S_ISREG(info.st_mode):return
        with desktop.open(encoding='utf-8',errors='replace') as stream:text=stream.read(65537)
        if len(text)>65536:return
        previous=_desktop_fields(text)
        if all(previous.get(key)==value for key,value in values.items()):return
        legacy_names={'Lupin (development)',APP_NAME+' (development)',LEGACY_APP_NAME+' (development)'}
        owned=(previous.get('X-Lupin-Development')=='true' or
               previous.get('Type')=='Application' and previous.get('NoDisplay')=='true'
               and previous.get('Name') in legacy_names and previous.get('Terminal')=='false'
               and previous.get('Exec','').endswith(' -m price_lens --capture'))
        if not owned:return
    contents='[Desktop Entry]\n'+''.join(key+'='+value+'\n' for key,value in values.items())+'X-Lupin-Development=true\n'
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=desktop.parent,
                                         prefix='.'+desktop.stem+'-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(contents);stream.flush();os.fsync(stream.fileno())
        temporary.chmod(stat.S_IMODE(info.st_mode) if previous is not None else 0o644)
        os.replace(temporary,desktop)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def application_identity():
    """Installed builds have a desktop entry; source runs get a separate hidden identity."""
    root = Path(__file__).resolve().parents[1]
    identity = "io.github.zhuffman68.ClassicPriceLens"
    if any((root / "bin" / name).is_file() for name in ("lupin-screen-reader", "classic-screen-reader")):
        return identity
    from PySide6.QtCore import QStandardPaths
    identity += ".Development"
    directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ApplicationsLocation))
    directory.mkdir(parents=True, exist_ok=True)
    desktop = directory / (identity + ".desktop")
    _refresh_development_entry(desktop,_development_entry(root,sys.executable))
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
    action = "toggle-prices"
    actions=None

    def __init__(self, activated, changed, status, action="toggle-prices",actions=None):
        self.action = action
        self.actions=actions
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
                    command={'toggle-prices':'--prices','toggle-exp':'--exp','translate-text':'--translate','compose-korean':'--compose'}.get(self.action,'--toggle')
                    self.status("Global shortcut: " + str(error) + ". Desktop fallback: lupin "+command)
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
            if self.actions and message.body[0]==self.session and message.body[1] in self.actions:
                binding=self.actions[message.body[1]]
                token=message.body[3].get('activation_token') if len(message.body)>3 else None
                if token is not None and binding.get('token'):binding['token'](token.value)
                binding['activate']()
            elif message.body[:2] == [self.session, self.action]:
                self.activated()
        elif message.interface == INTERFACE and message.member == "ShortcutsChanged":
            if message.body[0] == self.session:
                self._description(message.body[1])

    def _description(self, shortcuts):
        found=False
        for identity, options in shortcuts:
            if self.actions and identity in self.actions:
                value=options.get('trigger_description');self.actions[identity]['changed'](value.value if value else 'Desktop shortcut');found=True
            elif identity == self.action:
                value = options.get("trigger_description")
                self.changed(value.value if value else "Desktop shortcut")
                found=True
        return found

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
            await self._retire_legacy()
            token = "lens_" + uuid.uuid4().hex
            result = await self._request("CreateSession", "a{sv}",
                                         [{"handle_token": Variant("s", token), "session_handle_token": Variant("s", "lens_" + uuid.uuid4().hex)}], token)
            self.session = result["session_handle"].value
            token = "lens_" + uuid.uuid4().hex
            previous = await self._request("ListShortcuts", "oa{sv}",
                                            [self.session, {"handle_token": Variant("s", token)}], token)
            previous_shortcuts=previous.get("shortcuts", Variant("a(sa{sv})", [])).value
            if self._description(previous_shortcuts):
                # Bind the existing action to this session, reusing stored consent.
                preferred = None
            token = "lens_" + uuid.uuid4().hex
            options = {"description": Variant("s", "Translate Korean text in Classic World" if self.action == "translate-text" else "Pause or resume Lupin")}
            if preferred:
                options["preferred_trigger"] = Variant("s", preferred)
            bindings=[[self.action,options]]
            if self.actions:
                previous_ids={identity for identity,_ in previous_shortcuts}
                bindings=[]
                for identity,binding in self.actions.items():
                    values={'description':Variant('s',binding['description'])}
                    if identity not in previous_ids:values['preferred_trigger']=Variant('s',portal_trigger(binding['key']))
                    bindings.append([identity,values])
            result = await self._request("BindShortcuts", "oa(sa{sv})sa{sv}",
                                         [self.session, bindings, "", {"handle_token": Variant("s", token)}], token)
            if not self._description(result.get("shortcuts", Variant("a(sa{sv})", [])).value):
                self.status("No shortcut is assigned. Use Hotkey… to choose one.")
        finally:
            self.starting = False

    async def _retire_legacy(self):
        from dbus_next import Message
        app='io.github.zhuffman68.ClassicPriceLens'
        if self.application_id not in (app,app+'.Development'):return
        obsolete=[(self.application_id,'toggle-reading'),(self.application_id,'translate-chat')]
        if self.application_id==app:obsolete += [(app+'.Development','toggle-reading'),(app+'.Development','translate-chat')]
        # KDE remembers removed portal actions. Retire only our obsolete IDs;
        # other desktops simply lack this optional app-owned cleanup endpoint.
        for component,action in obsolete:
            try:
                await asyncio.wait_for(self.bus.call(Message(destination='org.kde.kglobalaccel',path='/kglobalaccel',
                    interface='org.kde.KGlobalAccel',member='unregister',signature='ss',body=[component,action])),timeout=2)
            except Exception:break

    def configure(self):
        if self.session:
            self._submit(self._call(INTERFACE, "ConfigureShortcuts", "osa{sv}", [self.session, "", {}]))
        else:
            from .hotkeys import DEFAULT_HOTKEY
            self.register(DEFAULT_HOTKEY)

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
