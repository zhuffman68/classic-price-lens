"""Keep this process and its helpers on the Qt plugins shipped with PySide."""
import os
from pathlib import Path


def configure_qt():
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    plugins = str(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)).resolve())
    # Desktop-wide plugin paths can contain a different Qt minor version.
    # Set both the live search list and the environment inherited by helpers.
    os.environ["QT_PLUGIN_PATH"] = plugins
    os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    QCoreApplication.setLibraryPaths([plugins])
