import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from price_lens.platform_paths import reader_binary
from price_lens.portal_hotkey import application_identity


class PlatformPathsTests(unittest.TestCase):
    def test_shipped_lupin_reader_takes_precedence_on_both_platforms(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bin').mkdir()
            for platform,extension in [('linux',''),('win32','.exe')]:
                modern=root/'bin'/('lupin-screen-reader'+extension)
                legacy=root/'bin'/('classic-screen-reader'+extension)
                modern.touch();legacy.touch()
                with patch('price_lens.platform_paths.sys.platform',platform):
                    self.assertEqual(reader_binary(root),modern)

    def test_source_and_older_installations_keep_their_reader_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);legacy=root/'bin/classic-screen-reader'
            legacy.parent.mkdir();legacy.touch()
            with patch('price_lens.platform_paths.sys.platform','linux'):
                self.assertEqual(reader_binary(root),legacy)
                legacy.unlink()
                source=root/'reader/target/release/classic-screen-reader'
                source.parent.mkdir(parents=True);source.touch()
                self.assertEqual(reader_binary(root),source)

    def test_renamed_packaged_reader_preserves_the_approved_portal_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bin').mkdir();(root/'bin/lupin-screen-reader').touch()
            with patch('price_lens.portal_hotkey.__file__',str(root/'price_lens/portal_hotkey.py')):
                self.assertEqual(application_identity(),'io.github.zhuffman68.ClassicPriceLens')
