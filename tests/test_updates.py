"""Signed release checks/downloads, no real HTTP, installs or credentials."""
import base64
import ctypes as C
import hashlib
import io
import json
from pathlib import Path
import random
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from price_lens.update_crypto import crypto,verify
from price_lens.update_delta import CHUNK,MAGIC,make,restore
from price_lens.updates import API,MANIFEST,SIGNATURE,REPOSITORY,ReleaseClient,Cancelled,canonical,version,read_json,signed_manifest,artifact,asset_url,check_url

# RFC 8032 section 7.1 test key. Never used for production release signing.
SEED=bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
PUBLIC='d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a'
KEYS={'keys':{'test':PUBLIC}}


def sign(document):
    lib=crypto()
    for name,args,result in (
        ('EVP_PKEY_new_raw_private_key_ex',[C.c_void_p,C.c_char_p,C.c_char_p,C.c_void_p,C.c_size_t],C.c_void_p),
        ('EVP_DigestSignInit',[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],C.c_int),
        ('EVP_DigestSign',[C.c_void_p,C.c_void_p,C.POINTER(C.c_size_t),C.c_void_p,C.c_size_t],C.c_int)):
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    seed=C.create_string_buffer(SEED);key=lib.EVP_PKEY_new_raw_private_key_ex(None,b'ED25519',None,seed,32);context=lib.EVP_MD_CTX_new()
    try:
        data=canonical(document);buffer=C.create_string_buffer(data);out=C.create_string_buffer(64);size=C.c_size_t(64)
        if lib.EVP_DigestSignInit(context,None,None,None,key)!=1 or lib.EVP_DigestSign(context,out,C.byref(size),buffer,len(data))!=1:raise AssertionError('Fixture signing failed')
        return dict(key_id='test',signature=base64.b64encode(out.raw[:size.value]).decode())
    finally:lib.EVP_MD_CTX_free(context);lib.EVP_PKEY_free(key)


def describe(name,data):return dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def offer(data=b'new installer',target='windows-installer-x64'):
    names={'windows-installer-x64':'Lupin-0.18.0-Windows-x64-Setup.exe','linux-arch-x64':'lupin-0.18.0-1-x86_64.pkg.tar.zst','linux-debian-x64':'lupin_0.18.0-1_amd64.deb','windows-portable-x64':'Lupin-Windows-x64.zip'}
    package=describe(names[target],data)
    document=dict(schema=1,repository=REPOSITORY,version='0.18.0',artifacts={target:package})
    release=dict(tag_name='v0.18.0',draft=False,prerelease=False,assets=[dict(name=name,browser_download_url=f'https://github.com/{REPOSITORY}/releases/download/v0.18.0/{name}') for name in (MANIFEST,SIGNATURE,package['name'])])
    return dict(manifest=document,signature=sign(document),package=package,release=release)


class FakeTransport:
    def __init__(self,selected,data):
        self.offer=selected;self.calls=[];self.not_modified=False
        self.content={API:canonical(selected['release']),asset_url(selected['release'],MANIFEST):canonical(selected['manifest']),
                      asset_url(selected['release'],SIGNATURE):canonical(selected['signature']),asset_url(selected['release'],selected['package']['name']):data}

    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if kwargs.get('cancel') and kwargs['cancel'].is_set():raise Cancelled()
        if url==API and self.not_modified:return b'',{'ETag':'test-etag'},304
        value=self.content[url]
        if kwargs.get('destination'):
            Path(kwargs['destination']).write_bytes(value)
            if kwargs.get('progress'):kwargs['progress'](len(value),len(value))
        return value,{'ETag':'test-etag'},200


class UpdateTests(unittest.TestCase):
    def setUp(self):self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name)

    def client(self,selected,data):
        transport=FakeTransport(selected,data);return ReleaseClient(self.root,KEYS,transport),transport

    def test_rfc8032_known_signature_and_corruption(self):
        signature=bytes.fromhex('e5564300c360ac729086e2cc806e828a' '84877f1eb8e5d974d873e06522490155' '5fb8821590a33bacc61e39701cf9b46b' 'd25bf5f0595bbe24655141438e7a100b')
        self.assertTrue(verify(bytes.fromhex(PUBLIC),signature,b''))
        self.assertFalse(verify(bytes.fromhex(PUBLIC),signature,b'changed'))
        self.assertFalse(verify(bytes.fromhex(PUBLIC),signature[:-1],b''))

    def test_manifest_signature_and_repository_are_required(self):
        selected=offer();doc=selected['manifest'];signature=canonical(selected['signature'])
        self.assertEqual(signed_manifest(canonical(doc),signature,KEYS),doc)
        changed={**doc,'version':'0.19.0'}
        with self.assertRaises(ValueError):signed_manifest(canonical(changed),signature,KEYS)
        with self.assertRaises(ValueError):signed_manifest(canonical(doc),signature,{'keys':{}})
        wrong={**doc,'repository':'someone/else'}
        with self.assertRaises(ValueError):signed_manifest(canonical(wrong),canonical(sign(wrong)),KEYS)
        with self.assertRaises(ValueError):read_json(b'{"schema":1,"schema":2}')
        with self.assertRaises(ValueError):signed_manifest(b'[]',b'[]',KEYS)

    def test_versions_are_numeric_and_stable_only(self):
        self.assertGreater(version('0.10.0'),version('0.9.9'))
        for value in ('v1.2.3','1.2.3-beta','1.2','01.2.3',None):
            with self.subTest(value=value),self.assertRaises(ValueError):version(value)

    def test_windows_installed_target_does_not_need_the_portable_build_manifest(self):
        import contextlib,types
        from price_lens.updates import target_for
        (self.root/'runtime').mkdir();(self.root/'runtime/pythonw.exe').touch()
        (self.root/'bin').mkdir();(self.root/'bin/lupin-screen-reader.exe').touch()
        registry=types.SimpleNamespace(HKEY_CURRENT_USER=0,OpenKey=lambda *_:contextlib.nullcontext(0),QueryValueEx=lambda *_:(str(self.root),1))
        with patch('price_lens.updates.sys.platform','win32'),patch.dict('sys.modules',winreg=registry),patch('price_lens.updates.platform.machine',return_value='AMD64'):
            target=target_for(self.root)
        self.assertTrue(target.installable);self.assertEqual(target.name,'windows-installer-x64')

    def test_release_asset_is_bound_to_exact_repo_tag_name_and_platform(self):
        selected=offer();document=selected['manifest']
        with self.assertRaises(ValueError):artifact(document,'linux-arch-x64')
        selected['release']['assets'][-1]['browser_download_url']='https://github.com/other/repo/releases/download/v0.18.0/setup.exe'
        with self.assertRaises(ValueError):asset_url(selected['release'],selected['package']['name'])
        for url in ('http://github.com/test','https://github.com.evil.example/file','https://user:password@github.com/file','file:///tmp/file','https://github.com:444/file'):
            with self.subTest(url=url),self.assertRaises(ValueError):check_url(url)

    def test_github_check_uses_etag_and_revalidates_the_signed_manifest(self):
        selected=offer();client,transport=self.client(selected,b'new installer');cancel=threading.Event()
        self.assertEqual(client.check('0.17.7','windows-installer-x64',cancel)['manifest'],selected['manifest'])
        transport.not_modified=True
        self.assertIsNotNone(client.check('0.17.7','windows-installer-x64',cancel))
        calls=[kwargs for url,kwargs in transport.calls if url==API]
        self.assertEqual(calls[1]['headers'],{'If-None-Match':'test-etag'})

    def test_no_downgrade_or_download_for_a_newer_local_preview(self):
        selected=offer();client,transport=self.client(selected,b'new installer')
        self.assertIsNone(client.check('0.19.0','windows-installer-x64',threading.Event()))
        self.assertEqual([url for url,_ in transport.calls],[API])

    def test_saved_offer_revalidates_its_signature_without_network_access(self):
        selected=offer();client,_=self.client(selected,b'new installer');client.check('0.17.7','windows-installer-x64',threading.Event())
        again,transport=self.client(selected,b'new installer')
        self.assertEqual(again.cached_offer('0.17.7','windows-installer-x64')['package'],selected['package']);self.assertEqual(transport.calls,[])
        saved=read_json((self.root/'offer.json').read_bytes());saved['manifest']['version']='0.19.0';(self.root/'offer.json').write_bytes(canonical(saved))
        with self.assertRaises(ValueError):again.cached_offer('0.17.7','windows-installer-x64')

    def test_download_verifies_and_reuses_a_cached_package(self):
        data=b'new installer';selected=offer(data);client,transport=self.client(selected,data);cancel=threading.Event()
        first=client.download(selected,'0.17.7',cancel,lambda *_:None)
        self.assertEqual(first.read_bytes(),data)
        self.assertEqual(client.download(selected,'0.17.7',cancel,lambda *_:None),first)
        self.assertEqual(len(transport.calls),1)
        self.assertTrue((self.root/'packages'/('base-'+selected['package']['sha256'])).exists())

    def test_invalid_or_cancelled_download_never_becomes_an_installer(self):
        selected=offer();client,_=self.client(selected,b'corrupt')
        with self.assertRaises(ValueError):client.download(selected,'0.17.7',threading.Event(),lambda *_:None)
        self.assertFalse((self.root/'packages'/selected['package']['name']).exists())
        self.assertEqual(list(self.root.rglob('*.part')),[])
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):client.download(selected,'0.17.7',cancel,lambda *_:None)

    def test_chunked_patch_roundtrip_across_the_dictionary_boundary(self):
        old=random.Random(68).randbytes(CHUNK+1024);new=old[:900]+b'changed'+old[907:]
        patch=io.BytesIO();make(io.BytesIO(old),io.BytesIO(new),patch)
        self.assertLess(len(patch.getvalue()),len(new)//10)
        out=io.BytesIO();restore(io.BytesIO(old),io.BytesIO(patch.getvalue()),out,len(new));self.assertEqual(out.getvalue(),new)
        for malformed in (b'bad',MAGIC+struct.pack('!II',CHUNK+1,1)+b'x',patch.getvalue()[:-1]):
            with self.subTest(size=len(malformed)),self.assertRaises(ValueError):
                restore(io.BytesIO(old),io.BytesIO(malformed),io.BytesIO(),len(new))

    def test_corrupt_patch_falls_back_to_full_verified_download(self):
        old=b'old installer'*2000;data=old[:100]+b'changed'+old[107:];selected=offer(data);delta=io.BytesIO();make(io.BytesIO(old),io.BytesIO(data),delta)
        patch=describe('test-delta.zst',delta.getvalue());patch.update(from_version='0.17.7',from_sha256=hashlib.sha256(old).hexdigest(),format='lupin-zstd-chunks-1')
        selected['package']['patches']=[patch];selected['signature']=sign(selected['manifest'])
        selected['release']['assets'].append(dict(name=patch['name'],browser_download_url=f'https://github.com/{REPOSITORY}/releases/download/v0.18.0/{patch["name"]}'))
        client,transport=self.client(selected,data);folder=self.root/'packages';folder.mkdir();(folder/('base-'+patch['from_sha256'])).write_bytes(old)
        transport.content[asset_url(selected['release'],patch['name'])]=b'bad patch'
        result=client.download(selected,'0.17.7',threading.Event(),lambda *_:None)
        self.assertEqual(result.read_bytes(),data);self.assertEqual(len(transport.calls),2)

    def test_valid_patch_reconstructs_exact_native_package_without_full_download(self):
        old=b'old native package'*4000;data=old[:100]+b'changed'+old[107:];selected=offer(data,target='linux-arch-x64')
        delta=io.BytesIO();make(io.BytesIO(old),io.BytesIO(data),delta)
        patch=dict(describe('native-delta.zst',delta.getvalue()),from_version='0.17.7',from_sha256=hashlib.sha256(old).hexdigest(),format='lupin-zstd-chunks-1')
        selected['package']['patches']=[patch];selected['signature']=sign(selected['manifest'])
        selected['release']['assets'].append(dict(name=patch['name'],browser_download_url=f'https://github.com/{REPOSITORY}/releases/download/v0.18.0/{patch["name"]}'))
        client,transport=self.client(selected,data);folder=self.root/'packages';folder.mkdir();(folder/('base-'+patch['from_sha256'])).write_bytes(old)
        transport.content[asset_url(selected['release'],patch['name'])]=delta.getvalue()
        result=client.download(selected,'0.17.7',threading.Event(),lambda *_:None)
        self.assertEqual(result.read_bytes(),data);self.assertEqual([url for url,_ in transport.calls],[asset_url(selected['release'],patch['name'])])
