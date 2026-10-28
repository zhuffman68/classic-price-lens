import configparser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from price_lens.kde_window_policy import GROUP, VALUES, ensure_kde_window_policy


class KDEWindowPolicyTests(unittest.TestCase):
    def test_scoped_rule_preserves_other_rules_backs_up_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'kwinrulesrc'
            original = b'[General]\nrules=existing\ncount=1\n\n[existing]\nDescription=Keep this\n'
            target.write_bytes(original)
            def run(command, **kwargs):
                if command[0] != 'kwriteconfig6':return
                config = configparser.ConfigParser(interpolation=None)
                config.optionxform = str
                config.read(target)
                group, key, value = command[4], command[6], command[7]
                if not config.has_section(group):config.add_section(group)
                config.set(group, key, value)
                with target.open('w') as stream:config.write(stream)
            env = {'XDG_CURRENT_DESKTOP': 'KDE', 'XDG_CONFIG_HOME': directory}
            with patch('price_lens.kde_window_policy.sys.platform', 'linux'), patch('price_lens.kde_window_policy.shutil.which', side_effect=lambda name:name), patch('price_lens.kde_window_policy.subprocess.run', side_effect=run) as execute:
                self.assertTrue(ensure_kde_window_policy('wayland', root/'cache', environ=env))
                config = configparser.ConfigParser(interpolation=None)
                config.optionxform = str;config.read(target)
                self.assertEqual(config.get('existing','Description'),'Keep this')
                self.assertEqual(config.get('General','rules'),GROUP+',existing')
                self.assertEqual(config.get('General','count'),'2')
                for key,value in VALUES.items():self.assertEqual(config.get(GROUP,key),value)
                backup = next((root/'cache/window-policy-backups').iterdir())
                self.assertEqual((backup/'kwinrulesrc').read_bytes(),original)
                self.assertTrue(json.loads((backup/'manifest.json').read_text())['existed'])
                execute.reset_mock()
                self.assertTrue(ensure_kde_window_policy('wayland', root/'cache', environ=env))
                execute.assert_not_called()

    def test_no_desktop_changes_on_windows_other_desktops_or_offscreen(self):
        with patch('price_lens.kde_window_policy.shutil.which') as which:
            self.assertFalse(ensure_kde_window_policy('offscreen', Path('/unused'), environ={'XDG_CURRENT_DESKTOP':'KDE'}))
            self.assertFalse(ensure_kde_window_policy('wayland', Path('/unused'), environ={'XDG_CURRENT_DESKTOP':'GNOME'}))
            with patch('price_lens.kde_window_policy.sys.platform', 'win32'):
                self.assertFalse(ensure_kde_window_policy('windows', Path('/unused'), environ={'XDG_CURRENT_DESKTOP':'KDE'}))
            which.assert_not_called()
