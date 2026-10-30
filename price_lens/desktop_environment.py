"""Forward only desktop settings needed by our unprivileged GUI and helpers.

Older updaters lost XWayland authentication and custom GLib schema locations.
The new GUI can recover missing values from the same user's session manager,
including when an older installed updater launches this version. Nothing here
changes the desktop manager or reads another process's environment.
"""
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys

GUI_ENV = (
    'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
    'DBUS_SESSION_BUS_ADDRESS', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP',
    'GSETTINGS_SCHEMA_DIR', 'XDG_DATA_DIRS', 'XDG_CONFIG_DIRS',
    'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'LANG', 'LC_CTYPE',
)


def clean_environment(values):
    if not isinstance(values, dict):
        return {}
    return {key: value for key, value in values.items()
            if key in GUI_ENV and isinstance(value, str) and 0 < len(value) < 4096
            and not any(character in value for character in ('\0', '\r', '\n'))}


def session_environment():
    """Read a small session-manager snapshot; never execute its shell syntax."""
    try:
        # A regular temporary file bounds Python memory even if the user manager
        # has an unusually large environment. It is private and immediately closed.
        import tempfile
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                ['/usr/bin/systemctl', '--user', 'show-environment'],
                stdout=output, stderr=subprocess.DEVNULL, timeout=2, check=False,
            )
            if result.returncode:
                return {}
            output.seek(0)
            raw = output.read(65537)
        if len(raw) > 65536:
            return {}
    except (OSError, subprocess.SubprocessError):
        return {}
    values = {}
    for line in raw.decode('utf-8', errors='replace').splitlines():
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) == 1 and '=' in parts[0]:
            key, value = parts[0].split('=', 1)
            if key in GUI_ENV:
                values[key] = value
    return clean_environment(values)


def recovered_environment(environ=None):
    current = clean_environment(dict(os.environ if environ is None else environ))
    if (not sys.platform.startswith('linux') or os.geteuid() == 0
            or not current.get('DISPLAY') or not current.get('XDG_RUNTIME_DIR')):
        return current
    if current.get('XAUTHORITY') and current.get('GSETTINGS_SCHEMA_DIR'):
        return current
    manager = session_environment()
    # A user manager can serve several graphical sessions. Never borrow another
    # display's cookie or replace a deliberate value in the current environment.
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR'):
        if current.get(key) and manager.get(key) != current[key]:
            return current
    for key, value in manager.items():
        if key in current:
            continue
        if key == 'XAUTHORITY':
            try:
                path = Path(value)
                info = path.stat()
                if not path.is_absolute() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                    continue
            except OSError:
                continue
        if key == 'GSETTINGS_SCHEMA_DIR':
            path = Path(value)
            if not path.is_absolute() or not (path / 'gschemas.compiled').is_file():
                continue
        current[key] = value
    return current


def restore_desktop_environment():
    recovered = recovered_environment()
    for key, value in recovered.items():
        if not os.environ.get(key):os.environ[key] = value
    return recovered
