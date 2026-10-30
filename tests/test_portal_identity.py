"""Generated development identity repair uses only a temporary applications tree."""
import ctypes
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QStandardPaths
from price_lens import portal_hotkey as portal

IDENTITY='io.github.zhuffman68.ClassicPriceLens'


@unittest.skipUnless(sys.platform.startswith('linux'),'Wayland desktop entries')
class PortalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name);self.root=self.path/'source root';self.root.mkdir()
        self.applications=self.path/'applications';self.desktop=self.applications/(IDENTITY+'.Development.desktop')
        self.program=self.path/'runtime with spaces'/'python3';self.program.parent.mkdir();self.program.touch();self.program.chmod(0o700)
        for p in (patch.object(portal,'__file__',str(self.root/'price_lens/portal_hotkey.py')),
                  patch.object(portal.sys,'executable',str(self.program)),
                  patch.object(QStandardPaths,'writableLocation',return_value=str(self.applications))):
            p.start();self.addCleanup(p.stop)

    def legacy(self,*,correct=False):
        self.applications.mkdir(exist_ok=True)
        program=str(self.program) if correct else '/opt/classic-price-lens/runtime/bin/python3'
        name='Lupin' if correct else 'Classic Price Lens'
        root=self.root if correct else Path('/old/source')
        text=('[Desktop Entry]\nType=Application\nName='+name+' (development)\nNoDisplay=true\n'
              +'Exec="'+program+'" -m price_lens --capture\nPath='+str(root)+'\n'
              +'Icon='+str(root/'price_lens/resources/icon.png')+'\nTerminal=false\n')
        self.desktop.write_text(text);return text

    def validate(self):
        validator=shutil.which('desktop-file-validate')
        if validator:
            result=subprocess.run([validator,str(self.desktop)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_new_source_identity_is_hidden_and_uses_current_runtime_root_and_name(self):
        self.assertEqual(portal.application_identity(),IDENTITY+'.Development')
        fields=portal._desktop_fields(self.desktop.read_text())
        self.assertEqual(fields['Name'],'Lupin (development)');self.assertEqual(fields['NoDisplay'],'true')
        self.assertEqual(fields['Exec'],'"'+str(self.program)+'" -m price_lens --capture')
        self.assertEqual(fields['Path'],str(self.root));self.assertEqual(fields['Icon'],str(self.root/'price_lens/resources/icon.png'))
        self.assertEqual(fields['X-Lupin-Development'],'true');self.validate()

    def test_stale_classic_price_lens_runtime_is_repaired_atomically(self):
        previous=self.legacy();sibling=self.applications/'unrelated.desktop';sibling.write_text('untouched')
        replace=os.replace;calls=[]
        def commit(source,destination):
            self.assertEqual(self.desktop.read_text(),previous)
            self.assertEqual(Path(source).parent,self.applications);self.assertEqual(Path(destination),self.desktop)
            self.assertIn(str(self.program),Path(source).read_text());calls.append(True);replace(source,destination)
        with patch.object(portal.os,'replace',side_effect=commit):portal.application_identity()
        self.assertEqual(calls,[True]);self.assertNotIn('/opt/classic-price-lens',self.desktop.read_text())
        self.assertIn('Name=Lupin (development)',self.desktop.read_text());self.assertEqual(sibling.read_text(),'untouched')
        self.assertEqual(list(self.applications.glob('*.tmp')),[]);self.validate()

    def test_correct_generated_file_is_unchanged_including_legacy_without_marker(self):
        for old_style in (True,False):
            if old_style:self.legacy(correct=True)
            else:self.desktop.unlink();portal.application_identity()
            before=self.desktop.read_bytes();info=self.desktop.stat()
            with patch.object(portal.os,'replace',side_effect=AssertionError('No rewrite required')):portal.application_identity()
            self.assertEqual(self.desktop.read_bytes(),before)
            self.assertEqual((self.desktop.stat().st_ino,self.desktop.stat().st_mtime_ns),(info.st_ino,info.st_mtime_ns))

    def test_source_root_and_product_name_changes_refresh_only_the_generated_entry(self):
        portal.application_identity();new=self.path/'moved source';new.mkdir()
        with patch.object(portal,'__file__',str(new/'price_lens/portal_hotkey.py')),patch.object(portal,'APP_NAME','Renamed Lupin'):
            portal.application_identity()
        fields=portal._desktop_fields(self.desktop.read_text())
        self.assertEqual(fields['Path'],str(new));self.assertEqual(fields['Name'],'Renamed Lupin (development)')
        self.assertEqual(fields['Icon'],str(new/'price_lens/resources/icon.png'))

    def test_unrelated_entry_or_symlink_at_the_same_name_is_preserved(self):
        self.applications.mkdir();unrelated='[Desktop Entry]\nType=Application\nName=Another app\nNoDisplay=true\nExec=/usr/bin/other\n'
        self.desktop.write_text(unrelated);portal.application_identity();self.assertEqual(self.desktop.read_text(),unrelated)
        target=self.path/'outside.desktop';target.write_text(self.legacy());self.desktop.unlink();self.desktop.symlink_to(target)
        before=target.read_bytes();portal.application_identity()
        self.assertTrue(self.desktop.is_symlink());self.assertEqual(target.read_bytes(),before)

    def test_failed_atomic_replace_preserves_previous_file_and_removes_temporary(self):
        old=self.legacy()
        with patch.object(portal.os,'replace',side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError):portal.application_identity()
        self.assertEqual(self.desktop.read_text(),old)
        self.assertEqual(list(self.applications.iterdir()),[self.desktop])

    def test_installed_reader_identity_never_creates_or_rewrites_a_user_launcher(self):
        for name in ('lupin-screen-reader','classic-screen-reader'):
            binary=self.root/'bin'/name;binary.parent.mkdir(exist_ok=True);binary.touch()
            with patch.object(QStandardPaths,'writableLocation',side_effect=AssertionError('Installed identity needs no generated entry')):
                self.assertEqual(portal.application_identity(),IDENTITY)
            binary.unlink()
        self.assertFalse(self.applications.exists())

    def test_exec_quotes_round_trip_through_desktop_parser_without_a_shell(self):
        program=self.path/'python "quoted" \\ $cash `tick`';program.touch();program.chmod(0o700)
        with patch.object(portal.sys,'executable',str(program)):portal.application_identity()
        self.validate()
        try:gio=ctypes.CDLL('libgio-2.0.so.0');gobject=ctypes.CDLL('libgobject-2.0.so.0');glib=ctypes.CDLL('libglib-2.0.so.0')
        except OSError:self.skipTest('GLib desktop-entry parser is unavailable')
        gio.g_desktop_app_info_new_from_filename.argtypes=[ctypes.c_char_p];gio.g_desktop_app_info_new_from_filename.restype=ctypes.c_void_p
        gio.g_app_info_get_commandline.argtypes=[ctypes.c_void_p];gio.g_app_info_get_commandline.restype=ctypes.c_char_p
        gobject.g_object_unref.argtypes=[ctypes.c_void_p];gobject.g_object_unref.restype=None
        glib.g_shell_parse_argv.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)),ctypes.POINTER(ctypes.c_void_p)]
        glib.g_shell_parse_argv.restype=ctypes.c_int
        glib.g_strfreev.argtypes=[ctypes.POINTER(ctypes.c_char_p)];glib.g_strfreev.restype=None
        info=gio.g_desktop_app_info_new_from_filename(os.fsencode(self.desktop));self.assertTrue(info)
        argv=ctypes.POINTER(ctypes.c_char_p)();argc=ctypes.c_int();error=ctypes.c_void_p()
        try:
            # Decode the Desktop Entry string through Gio first, then inspect
            # GLib's parsed argument vector. This never invokes a shell/program.
            commandline=gio.g_app_info_get_commandline(info)
            self.assertTrue(glib.g_shell_parse_argv(commandline,ctypes.byref(argc),ctypes.byref(argv),ctypes.byref(error)))
            try:self.assertEqual([os.fsdecode(argv[i]) for i in range(argc.value)],[str(program),'-m','price_lens','--capture'])
            finally:glib.g_strfreev(argv)
        finally:gobject.g_object_unref(info)

    def test_exec_literal_percent_is_not_an_unknown_field_code(self):
        program=self.path/'python%custom'
        with patch.object(portal.sys,'executable',str(program)):portal.application_identity()
        self.assertIn('python%%custom',self.desktop.read_text());self.validate()


if __name__=='__main__':unittest.main()
