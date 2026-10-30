"""Only missing, session-matching GUI variables may reach our unprivileged GUI."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from price_lens import desktop_environment as desktop


@unittest.skipUnless(sys.platform.startswith('linux'),'Linux session-manager recovery')
class DesktopEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name);self.authority=self.path/'Xauthority';self.authority.write_bytes(b'own fixture')
        self.schemas=self.path/'schemas';self.schemas.mkdir();(self.schemas/'gschemas.compiled').write_bytes(b'fixture')
        self.current={'DISPLAY':':90','WAYLAND_DISPLAY':'wayland-fixture','XDG_RUNTIME_DIR':str(self.path/'runtime'),'LANG':'en_CA.UTF-8'}
        self.manager={**self.current,'XAUTHORITY':str(self.authority),'GSETTINGS_SCHEMA_DIR':str(self.schemas),'DBUS_SESSION_BUS_ADDRESS':'unix:path=/fixture/bus'}
        for name,value in [('sys.platform','linux'),('os.geteuid',1000)]:
            p=patch('price_lens.desktop_environment.'+name,return_value=value) if name.startswith('os.') else patch('price_lens.desktop_environment.'+name,value)
            p.start();self.addCleanup(p.stop)

    def recover(self,manager=None,current=None):
        with patch.object(desktop,'session_environment',return_value=self.manager if manager is None else manager):
            return desktop.recovered_environment(self.current if current is None else current)

    def test_matching_session_recovers_only_missing_allowlisted_values(self):
        manager={**self.manager,'LANG':'ko_KR.UTF-8'}
        result=self.recover(manager,current={**self.current,'LD_PRELOAD':'/bad','PYTHONPATH':'/bad','QT_QPA_PLATFORM':'bad'})
        self.assertEqual(result['XAUTHORITY'],str(self.authority));self.assertEqual(result['GSETTINGS_SCHEMA_DIR'],str(self.schemas))
        self.assertEqual(result['LANG'],'en_CA.UTF-8')
        self.assertTrue(set(result)<=set(desktop.GUI_ENV))
        self.assertFalse({'LD_PRELOAD','PYTHONPATH','QT_QPA_PLATFORM'}&set(result))
        deliberate={**self.current,'XAUTHORITY':'/deliberate','GSETTINGS_SCHEMA_DIR':'/deliberate'}
        self.assertEqual(self.recover(current=deliberate),deliberate)

    def test_other_display_wayland_or_runtime_is_never_borrowed(self):
        for key in ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR'):
            changed={**self.manager,key:'other-session'}
            self.assertEqual(self.recover(changed),self.current,key)
            changed=dict(self.manager);changed.pop(key)
            self.assertEqual(self.recover(changed),self.current,key)

    def test_xauthority_must_be_an_absolute_owned_regular_file(self):
        for value in ('relative',str(self.path),str(self.path/'missing')):
            result=self.recover({**self.manager,'XAUTHORITY':value});self.assertNotIn('XAUTHORITY',result)
        if hasattr(os,'getuid'):
            with patch.object(desktop.os,'getuid',return_value=os.getuid()+1):self.assertNotIn('XAUTHORITY',self.recover())

    def test_schema_directory_requires_the_compiled_schema_file(self):
        for value in ('relative',str(self.path/'missing'),str(self.path)):
            result=self.recover({**self.manager,'GSETTINGS_SCHEMA_DIR':value});self.assertNotIn('GSETTINGS_SCHEMA_DIR',result)

    def test_root_windows_and_non_graphical_sessions_skip_manager_reads(self):
        with patch.object(desktop,'session_environment',side_effect=AssertionError('No session access')):
            with patch.object(desktop.os,'geteuid',return_value=0):self.assertEqual(desktop.recovered_environment(self.current),self.current)
            with patch.object(desktop.sys,'platform','win32'):self.assertEqual(desktop.recovered_environment(self.current),self.current)
            for missing in ('DISPLAY','XDG_RUNTIME_DIR'):
                current=dict(self.current);current.pop(missing)
                self.assertEqual(desktop.recovered_environment(current),current)

    def test_invalid_values_are_discarded_before_forwarding(self):
        self.assertEqual(desktop.clean_environment(None),{})
        for value in ('','a\0b','a\nb','a\rb','x'*4096,True,42):
            self.assertEqual(desktop.clean_environment({'DISPLAY':value,'LD_PRELOAD':'/bad'}),{})

    def test_systemctl_output_is_bounded_parsed_without_shell_and_filters_keys(self):
        payload=b"DISPLAY=:90\nXAUTHORITY='/tmp/own authority'\nLANG='$(touch /should-not-exist)'\nLD_PRELOAD=/bad\nBROKEN='\n"
        seen=[]
        def command(args,**kwargs):
            seen.append((args,kwargs));kwargs['stdout'].write(payload);return SimpleNamespace(returncode=0)
        with patch.object(desktop.subprocess,'run',side_effect=command):values=desktop.session_environment()
        self.assertEqual(values['XAUTHORITY'],'/tmp/own authority');self.assertEqual(values['LANG'],'$(touch /should-not-exist)')
        self.assertNotIn('LD_PRELOAD',values);self.assertEqual(seen[0][0],['/usr/bin/systemctl','--user','show-environment'])
        self.assertNotIn('shell',seen[0][1]);self.assertEqual(seen[0][1]['timeout'],2)
        payload=b'DISPLAY=:90\n'+b'x'*65537
        with patch.object(desktop.subprocess,'run',side_effect=command):self.assertEqual(desktop.session_environment(),{})
        with patch.object(desktop.subprocess,'run',side_effect=subprocess.TimeoutExpired('systemctl',2)):self.assertEqual(desktop.session_environment(),{})

    def test_restore_does_not_replace_existing_environment_values(self):
        with patch.dict(os.environ,{'DISPLAY':':kept'},clear=True),patch.object(desktop,'recovered_environment',return_value={'DISPLAY':':other','XAUTHORITY':str(self.authority)}):
            desktop.restore_desktop_environment()
            self.assertEqual(os.environ['DISPLAY'],':kept');self.assertEqual(os.environ['XAUTHORITY'],str(self.authority))

    def test_restore_repairs_blank_values_that_recovery_treats_as_missing(self):
        recovered={'XAUTHORITY':str(self.authority),'GSETTINGS_SCHEMA_DIR':str(self.schemas)}
        with patch.dict(os.environ,{'XAUTHORITY':'','GSETTINGS_SCHEMA_DIR':''},clear=True),patch.object(desktop,'recovered_environment',return_value=recovered):
            desktop.restore_desktop_environment()
            self.assertEqual(os.environ['XAUTHORITY'],str(self.authority))
            self.assertEqual(os.environ['GSETTINGS_SCHEMA_DIR'],str(self.schemas))


if __name__=='__main__':unittest.main()
