"""Exercise local signing preparation with disposable keys and fake payloads."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import release_updates
from price_lens.updates import artifact,signed_manifest


@unittest.skipUnless(shutil.which('openssl'),'Local release signing needs OpenSSL')
class ReleaseUpdateTests(unittest.TestCase):
    def test_prepare_all_platforms_signs_with_only_the_pinned_test_key(self):
        with tempfile.TemporaryDirectory() as temporary,contextlib.redirect_stdout(io.StringIO()):
            root=Path(temporary);key=root/'private/key.pem';trust=root/'public.json';destination=root/'dist';destination.mkdir()
            release_updates.keygen(key,trust)
            for name in ('Lupin-0.18.0-Windows-x64-Setup.exe','lupin-0.18.0-1-x86_64.pkg.tar.zst','lupin_0.18.0-1_amd64.deb'):
                (destination/name).write_bytes(b'Fixture payload only. Not an executable or package.')
            args=argparse.Namespace(version='0.18.0',key=key,trust=trust,dist=destination,base_manifest=None,base_dir=None,capture_compatible_from=[])
            release_updates.prepare(args)
            document=signed_manifest((destination/'lupin-update.json').read_bytes(),(destination/'lupin-update.sig.json').read_bytes(),json.loads(trust.read_text()))
            self.assertEqual(len(document['artifacts']),3)
            self.assertNotIn('windows-portable-x64',document['artifacts'])
            for target in document['artifacts']:artifact(document,target)
            self.assertFalse(any(path.suffix=='.pem' for path in destination.iterdir()))

    def test_keygen_will_not_put_a_private_key_inside_the_repository(self):
        with self.assertRaises(ValueError):release_updates.keygen(ROOT/'evidence/do-not-create.pem',ROOT/'evidence/do-not-create.json')
