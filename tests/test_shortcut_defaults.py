import unittest
from price_lens.shortcut_defaults import DEFAULTS,KEYS,LEGACY,load


class Settings:
    def __init__(self,values=None):self.values=dict(values or {})
    def value(self,key,default=None,**_):return self.values.get(key,default)
    def setValue(self,key,value):self.values[key]=value


class ShortcutMigrationTests(unittest.TestCase):
    def test_fresh_and_unmodified_legacy_defaults_use_the_same_chords(self):
        for settings in (Settings(),Settings({KEYS[k]:v for k,v in LEGACY.items()})):
            self.assertEqual(load(settings),DEFAULTS)
            self.assertEqual(load(settings),DEFAULTS)

    def test_custom_values_and_explicit_old_key_preferences_are_preserved(self):
        settings=Settings({'hotkey-sequence':'Ctrl+Shift+P','chat-hotkey':LEGACY['chat'],'chat-hotkey-custom':True})
        values=load(settings)
        self.assertEqual(values['prices'],'Ctrl+Shift+P');self.assertEqual(values['chat'],LEGACY['chat'])
        self.assertEqual(values['exp'],DEFAULTS['exp'])
