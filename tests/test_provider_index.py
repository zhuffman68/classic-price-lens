"""A public index can extend checked identities, never guess a new one or renew proof age."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from price_lens.data import Cache,MeowProvider
from price_lens.domain import Item
from price_lens.provider_index import load_index


class ProviderIndexTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.cache=Cache(Path(self.directory.name)/"cache.sqlite")
        self.provider=MeowProvider(self.cache)
        self.item=Item(1002000,"Example Hat")
        self.now=time.time()
        self.index={"entries":{"1002000":708},"fingerprint":"version-a","fetched_at":self.now}
        self.provider.index=self.index

    def tearDown(self):self.directory.cleanup()

    def verified(self,age=2*86400,**changes):
        self.cache.put("meow-id",self.item.game_id,{"id":708,"name":self.item.name,"index":"version-a",**changes},self.now-age)

    def test_unchanged_fresh_index_reuses_previously_verified_identity(self):
        self.verified()
        with patch("price_lens.data.get_json",side_effect=AssertionError("Identity request should be skipped")):
            self.assertEqual(self.provider.resolve_id(self.item),708)

    def test_index_entry_alone_never_identifies_a_new_item(self):
        with patch("price_lens.data.get_json",return_value={"items":[{"id":708,"name":self.item.name,"iconKey":1002000}]}) as get:
            self.assertEqual(self.provider.resolve_id(self.item),708)
            self.assertEqual(get.call_count,1)

    def test_changed_index_wrong_name_and_old_index_require_source_validation(self):
        for change,index in [({"index":"old-version"},self.index),({"name":"Other Hat"},self.index),({},dict(self.index,fetched_at=self.now-86401))]:
            with self.subTest(change=change,index=index):
                self.verified(**change);self.provider.index=index
                with patch("price_lens.data.get_json",return_value={"items":[{"id":708,"name":self.item.name,"iconKey":1002000}]}) as get:
                    self.assertEqual(self.provider.resolve_id(self.item),708);self.assertEqual(get.call_count,1)

    def test_enrolling_daily_identity_does_not_extend_its_provider_check_time(self):
        self.verified(age=100,index=None)
        with self.cache.connect() as db:before=db.execute("select saved from entries where kind='meow-id'").fetchone()[0]
        self.assertEqual(self.provider.resolve_id(self.item),708)
        with self.cache.connect() as db:after=db.execute("select saved from entries where kind='meow-id'").fetchone()[0]
        self.assertEqual(before,after)
        self.assertEqual(self.cache.get("meow-id",self.item.game_id)["index"],"version-a")

    def test_index_is_parsed_as_json_and_cached_for_a_day(self):
        import json
        entries={f"basil:{1000000+n:08}":n+1 for n in range(100)}
        body=("// published mapping\nwindow.NiaDBIds = "+json.dumps(entries)+";\n").encode()
        with patch("price_lens.provider_index.get_bytes",return_value=body) as get:
            first=load_index(self.cache);second=load_index(self.cache)
            self.assertEqual(first,second);self.assertEqual(get.call_count,1)
            self.assertEqual(len(first["entries"]),100)

    def test_executable_or_changed_index_format_is_rejected(self):
        for body in (b"window.NiaDBIds = {}; stealCookies();",b"<html>not an index</html>"):
            with patch("price_lens.provider_index.get_bytes",return_value=body):
                with self.assertRaises(ValueError):load_index(self.cache)
