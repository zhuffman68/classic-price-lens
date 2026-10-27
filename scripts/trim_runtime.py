"""Prune verified-unused Qt tooling/bindings; preserve capture, fonts and fallbacks.

Native Qt libraries are kept by transitive binary imports from the retained
bindings/plugins. All non-Qt native libraries and platform/media/TLS plugins
remain, including software OpenGL, FFmpeg and Wayland helpers.
"""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
QT_MODULES={'QtCore','QtGui','QtWidgets','QtNetwork','QtMultimedia','QtSvg','QtWebSockets','QtTest'}
DEV_PLUGINS={'designer','qmltooling','assetimporters','geometryloaders','renderers','sceneparsers','geoservices','position','sensors','texttospeech','sqldrivers'}


def imported_modules():
    required=set()
    for folder in ('price_lens','tests'):
        for path in (ROOT/folder).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('PySide6.'):
                    required.add(node.module.split('.')[1])
    return required


def trim(out,platform):
    unknown=imported_modules()-QT_MODULES
    if unknown:raise RuntimeError('Update the Qt runtime allowlist for '+str(sorted(unknown)))
    site=out/('runtime/Lib/site-packages' if platform=='windows' else 'runtime/lib/python3.14/site-packages')
    qt=site/'PySide6';removed=[]
    def remove(path,reason):
        if not path.exists():return
        size=sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink()) if path.is_dir() else path.lstat().st_size
        removed.append({'path':path.relative_to(out).as_posix(),'bytes':size,'reason':reason})
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    for relative in ('qml','Qt/qml','include','typesystems','doc','metatypes','Qt/metatypes','translations','Qt/translations'):
        remove(qt/relative,'Qt developer data or uninstalled UI translations')
    for path in list(qt.glob('*.pyi')):remove(path,'Static typing stub; no runtime imports')
    for path in list(qt.glob('Qt*')):
        if path.is_file() and (path.suffix=='.pyd' or path.name.endswith('.so')) and path.name.split('.')[0] not in QT_MODULES:
            remove(path,'Unused Python Qt binding')
    plugin_root=qt/('plugins' if platform=='windows' else 'Qt/plugins')
    for folder in DEV_PLUGINS:remove(plugin_root/folder,'Plugin for a feature absent from this QWidget app')
    # Qt libraries may also be loaded by a platform helper or plugin. Include all
    # retained helpers/plugins and non-Qt native libraries as dependency roots.
    native=list(qt.rglob('*.dll'))+list(qt.rglob('*.pyd')) if platform=='windows' else [p for p in qt.rglob('*') if p.is_file() and ('.so' in p.name or 'libexec' in p.parts)]
    libraries={p.name.casefold():p for p in native if p.name.startswith('Qt6') or p.name.startswith('libQt6')}
    roots=[p for p in native if p.name.casefold() not in libraries]
    seen=set();needed=set();pending=list(roots)
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        command=['objdump','-p',str(path)] if platform=='windows' else ['readelf','-d',str(path)]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:continue  # Scripts or Qt helper data are not binaries.
        names=re.findall(r'DLL Name:\s*(\S+)',result.stdout) if platform=='windows' else re.findall(r'\(NEEDED\).*?\[(.*?)\]',result.stdout)
        for name in names:
            key=name.casefold()
            if key in libraries and key not in needed:needed.add(key);pending.append(libraries[key])
    families={name.split('.so')[0] for name in needed}
    for name,path in libraries.items():
        if name not in needed and name.split('.so')[0] not in families:remove(path,'Unreferenced native Qt library (binary dependency closure)')
    if platform=='linux':
        for relative in ('pip','pip-26.2.dist-info'):
            remove(site/relative,'Build-time package installer')
        remove(out/'runtime/lib/python3.14/ensurepip','Build-time package installer bootstrap')
    report=out/'runtime-trim.json';report.write_text(json.dumps({'platform':platform,'bytesRemoved':sum(p['bytes'] for p in removed),'removed':removed,'retainedQtBindings':sorted(QT_MODULES)},indent=2)+'\n')
    print('Trimmed',platform,round(sum(p['bytes'] for p in removed)/1048576,1),'MiB; capture/plugins/model bundles retained',flush=True)
