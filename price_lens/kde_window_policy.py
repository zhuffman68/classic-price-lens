"""A narrowly scoped KDE rule, since Wayland ignores Qt's maximize-button hint."""
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


GROUP = "lupin-normal-window"
VALUES = {
    "Description": "Lupin: keep the panel resizable without maximizing",
    "wmclass": r"(?i)^(io\.github\.zhuffman68\.ClassicPriceLens|classic-price-lens)$",
    "wmclassmatch": "3", "wmclasscomplete": "false", "types": "1",
    "maximizehoriz": "false", "maximizehorizrule": "2",
    "maximizevert": "false", "maximizevertrule": "2",
}


def ensure_kde_window_policy(platform_name, cache, *, environ=None):
    """Install/update only our rule, once as needed; never change other windows."""
    env = os.environ if environ is None else environ
    if (sys.platform != "linux" or platform_name in ("offscreen", "minimal")
            or "KDE" not in env.get("XDG_CURRENT_DESKTOP", "").upper().split(":")):
        return False
    writer, dbus = shutil.which("kwriteconfig6"), shutil.which("qdbus6")
    if not writer or not dbus:
        return False
    target = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kwinrulesrc"
    try:
        original = target.read_bytes() if target.exists() else None
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.optionxform = str
        config.read_string((original or b"").decode("utf-8"))
        rules = [value for value in config.get("General", "rules", fallback="").split(",") if value]
        edits = [(GROUP, key, value) for key, value in VALUES.items()
                 if config.get(GROUP, key, fallback="").replace("\\\\", "\\") != value]
        if GROUP not in rules:
            rules.insert(0, GROUP)
            edits.append(("General", "rules", ",".join(rules)))
        if config.get("General", "count", fallback=None) != str(len(rules)):
            edits.append(("General", "count", str(len(rules))))
        if not edits:
            return True
        # Keep a byte-for-byte recovery copy before changing desktop settings.
        backup = Path(cache) / "window-policy-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup.mkdir(parents=True, mode=0o700)
        mode = target.stat().st_mode & 0o777 if original is not None else None
        if original is not None:
            (backup / "kwinrulesrc").write_bytes(original)
            (backup / "kwinrulesrc").chmod(0o600)
        (backup / "manifest.json").write_text(json.dumps({"target": str(target), "existed": original is not None, "mode": mode}))
        for group, key, value in edits:
            subprocess.run([writer, "--file", str(target), "--group", group, "--key", key, value],
                           check=True, capture_output=True, timeout=3)
        subprocess.run([dbus, "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
                       check=True, capture_output=True, timeout=3)
        return True
    except (OSError, UnicodeError, configparser.Error, subprocess.SubprocessError):
        # The cross-platform Qt guard remains active if KDE tools are unavailable.
        return False
