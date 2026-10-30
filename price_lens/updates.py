"""Bounded GitHub release checks, signed manifests and verified downloads.

This module has no capture, game, Qt, installer or credential access. Native
installation is a separate, explicitly authorized operation.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote,urlparse
from urllib.request import Request,HTTPRedirectHandler,HTTPSHandler,build_opener

from .update_crypto import verify

REPOSITORY='zhuffman68/lupin'
API=f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES=f'https://github.com/{REPOSITORY}/releases'
MANIFEST='lupin-update.json'
SIGNATURE='lupin-update.sig.json'
MAX_PACKAGE=2_000_000_000
VERSION=re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z')
NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,160}\Z')


def version(value):
    if not isinstance(value,str) or not VERSION.fullmatch(value):raise ValueError('Invalid stable release version')
    return tuple(map(int,value.split('.')))


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def read_json(data):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('Duplicate update metadata key')
            result[key]=value
        return result
    def invalid_number(_):raise ValueError('Invalid number')
    return json.loads(data,object_pairs_hook=pairs,parse_constant=invalid_number)


def signed_manifest(data,signature,keys):
    document=read_json(data);signed=read_json(signature)
    if not isinstance(document,dict) or not isinstance(signed,dict) or not isinstance(signed.get('key_id'),str):raise ValueError('Invalid release signature metadata')
    key=keys.get('keys',{}).get(signed.get('key_id'))
    if not isinstance(key,str):raise ValueError('Unknown release signing key')
    try:valid=verify(bytes.fromhex(key),base64.b64decode(signed['signature'],validate=True),canonical(document))
    except (KeyError,TypeError,ValueError) as error:raise ValueError('Invalid release signature') from error
    if not valid:raise ValueError('Release signature did not verify')
    if document.get('schema')!=1 or document.get('repository')!=REPOSITORY:raise ValueError('Wrong update manifest')
    version(document.get('version'))
    if not isinstance(document.get('artifacts'),dict):raise ValueError('Invalid update artifacts')
    compatible=document.get('capture_compatible_from',[])
    if not isinstance(compatible,list) or len(compatible)>30:raise ValueError('Invalid capture compatibility list')
    for previous in compatible:
        if version(previous)>=version(document['version']):raise ValueError('Invalid capture compatibility version')
    return document


@dataclass(frozen=True)
class Target:
    name:str
    installable:bool
    root:Path


def target_for(root):
    root=Path(root).resolve()
    if platform.machine().lower() not in ('amd64','x86_64'):return Target('',False,root)
    if sys.platform=='win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{1E77CC5D-AE19-4808-AD70-E009B578BA74}_is1') as key:
                installed=Path(winreg.QueryValueEx(key,'InstallLocation')[0]).resolve()==root
        except OSError:installed=False
        packaged=(root/'runtime/pythonw.exe').is_file() and (root/'bin/lupin-screen-reader.exe').is_file()
        return Target('windows-installer-x64' if installed else 'windows-portable-x64',packaged,root)
    if sys.platform.startswith('linux'):
        try:release=platform.freedesktop_os_release();family=(release.get('ID','')+' '+release.get('ID_LIKE','')).split()
        except OSError:family=[]
        name='linux-arch-x64' if any(v in family for v in ('arch','manjaro')) else 'linux-debian-x64' if any(v in family for v in ('debian','ubuntu')) else ''
        return Target(name,root==Path('/opt/lupin') and bool(name),root)
    return Target('',False,root)


def descriptor(value):
    if not isinstance(value,dict) or not isinstance(value.get('name'),str) or not NAME.fullmatch(value['name']):raise ValueError('Invalid update filename')
    if type(value.get('bytes')) is not int or not 0<value['bytes']<=MAX_PACKAGE:raise ValueError('Invalid update size')
    if not isinstance(value.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',value['sha256']):raise ValueError('Invalid update checksum')
    return value


def artifact(document,target):
    if target=='windows-portable-x64' and target not in document.get('artifacts',{}):
        raise ValueError('Portable Windows builds are no longer published. Use the Windows installer from GitHub Releases.')
    value=descriptor(document.get('artifacts',{}).get(target))
    expected={'windows-installer-x64':f"Lupin-{document['version']}-Windows-x64-Setup.exe",'windows-portable-x64':'Lupin-Windows-x64.zip',
              'linux-arch-x64':f"lupin-{document['version']}-1-x86_64.pkg.tar.zst",'linux-debian-x64':f"lupin_{document['version']}-1_amd64.deb"}
    if value['name']!=expected.get(target):raise ValueError('Package does not match this platform or release')
    patches=value.get('patches',[])
    if not isinstance(patches,list) or len(patches)>10:raise ValueError('Invalid patch list')
    for patch in patches:
        descriptor(patch);version(patch.get('from_version'))
        if not re.fullmatch('[0-9a-f]{64}',patch.get('from_sha256','')):raise ValueError('Invalid patch base')
        if patch.get('format')!='lupin-zstd-chunks-1':raise ValueError('Unsupported release patch')
    return value


def asset_url(release,name):
    tag=release.get('tag_name','')
    if not isinstance(tag,str) or not tag.startswith('v'):raise ValueError('Invalid release tag')
    version(tag[1:])
    expected=f'https://github.com/{REPOSITORY}/releases/download/{tag}/{quote(name,safe="")}'
    matches=[asset for asset in release.get('assets',[]) if asset.get('name')==name]
    if len(matches)!=1 or matches[0].get('browser_download_url')!=expected:raise ValueError('Missing or unexpected release asset: '+name)
    return expected


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        check_url(newurl)
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def check_url(url):
    parsed=urlparse(url);host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not (
            host in ('api.github.com','github.com') or host.endswith('.githubusercontent.com')):raise ValueError('Untrusted update download URL')


class Cancelled(Exception):pass


class Transport:
    def __init__(self):
        from .tls import make_context
        self.opener=build_opener(SafeRedirect(),HTTPSHandler(context=make_context()))

    def get(self,url,*,limit=1_048_576,headers=None,cancel=None,destination=None,progress=None):
        check_url(url)
        request=Request(url,headers={'User-Agent':'Lupin-update-checker','Accept':'application/vnd.github+json',**(headers or {})})
        try:response=self.opener.open(request,timeout=15)
        except HTTPError as error:
            if error.code==304:return b'',dict(error.headers),304
            raise
        chunks=[];count=0;began=time.monotonic()
        stream=Path(destination).open('wb') if destination else None
        try:
            with response:
                declared=response.headers.get('Content-Length')
                if declared and int(declared)>limit:raise ValueError('Update download exceeds expected size')
                while True:
                    if cancel is not None and cancel.is_set():raise Cancelled()
                    if time.monotonic()-began>(900 if destination else 45):raise TimeoutError('Update download timed out')
                    chunk=response.read(min(262144,limit-count+1))
                    if not chunk:break
                    count+=len(chunk)
                    if count>limit:raise ValueError('Update download exceeds expected size')
                    if stream:stream.write(chunk)
                    else:chunks.append(chunk)
                    if progress:progress(count,limit)
                if stream:stream.flush();os.fsync(stream.fileno())
                return b''.join(chunks),dict(response.headers),response.status
        finally:
            if stream:stream.close()


def file_matches(path,value):
    path=Path(path)
    if not path.is_file() or path.stat().st_size!=value['bytes']:return False
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==value['sha256']


def validate_portable(path):
    """Reject traversal, symlinks, collisions and implausible unpacked sizes."""
    from pathlib import PurePosixPath
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)>10000 or sum(part.file_size for part in members)>4_000_000_000:raise ValueError('Portable update expands beyond its limit')
        seen=set()
        for part in members:
            name=part.filename.replace('\\','/');pure=PurePosixPath(name)
            if pure.is_absolute() or ':' in name or '..' in pure.parts or part.external_attr>>16&0o170000==0o120000:raise ValueError('Unsafe portable update path')
            key=name.rstrip('/').casefold()
            if key in seen:raise ValueError('Duplicate portable update path')
            seen.add(key)
        roots=['','Lupin-Windows-x64/']
        if not any(all(root+name in seen for name in ('runtime/pythonw.exe','price_lens/__init__.py','bin/lupin-screen-reader.exe')) for root in (r.casefold() for r in roots)):
            raise ValueError('Portable update is missing required files')


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_bytes(canonical(value));temporary.replace(path)


class ReleaseClient:
    def __init__(self,cache,keys,transport=None):
        self.cache=Path(cache);self.keys=keys;self.transport=transport or Transport()
        self.cache.mkdir(parents=True,exist_ok=True)

    def cached_offer(self,current,target):
        with (self.cache/'offer.json').open('rb') as stream:data=stream.read(524289)
        if len(data)>524288:raise ValueError('Saved update metadata is too large')
        saved=read_json(data)
        if saved['release'].get('draft') or saved['release'].get('prerelease'):raise ValueError('Saved offer is not a stable published release')
        document=signed_manifest(canonical(saved['manifest']),canonical(saved['signature']),self.keys)
        if version(document['version'])<=version(current):return None
        if saved['release'].get('tag_name')!='v'+document['version']:raise ValueError('Saved release versions differ')
        package=artifact(document,target);asset_url(saved['release'],package['name'])
        return dict(release=saved['release'],manifest=document,signature=saved['signature'],package=package)

    def check(self,current,target,cancel):
        try:state=read_json((self.cache/'check.json').read_bytes())
        except (OSError,ValueError):state={}
        headers={'If-None-Match':state['etag']} if isinstance(state.get('etag'),str) else {}
        data,response,status=self.transport.get(API,headers=headers,cancel=cancel)
        release=state.get('release') if status==304 else read_json(data)
        if not isinstance(release,dict) or release.get('draft') or release.get('prerelease'):raise ValueError('No stable release is available')
        newest=release.get('tag_name','').removeprefix('v')
        version(newest)
        atomic_json(self.cache/'check.json',dict(etag=response.get('ETag',state.get('etag')),release=release,checked_at=time.time()))
        if version(newest)<=version(current):return None
        raw,_,_=self.transport.get(asset_url(release,MANIFEST),limit=262144,cancel=cancel)
        signature,_,_=self.transport.get(asset_url(release,SIGNATURE),limit=4096,cancel=cancel)
        document=signed_manifest(raw,signature,self.keys)
        if document['version']!=newest:raise ValueError('Release and signed manifest versions differ')
        package=artifact(document,target)
        asset_url(release,package['name'])
        result=dict(release=release,manifest=document,signature=read_json(signature),package=package)
        atomic_json(self.cache/'offer.json',result)
        return result

    def download(self,offer,current,cancel,progress):
        package=offer['package'];release=offer['release']
        folder=self.cache/'packages';folder.mkdir(exist_ok=True)
        destination=folder/package['name']
        if file_matches(destination,package):self.keep_base(destination,package);return destination
        temporary=destination.with_suffix(destination.suffix+'.part')
        try:
            for patch in package.get('patches',[]):
                base=folder/('base-'+patch['from_sha256'])
                if patch['from_version']!=current or patch['bytes']>=package['bytes']*.8 or not base.is_file():continue
                with base.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=patch['from_sha256']:continue
                if cancel.is_set():raise Cancelled()
                patch_path=folder/(patch['name']+'.part')
                try:
                    self.transport.get(asset_url(release,patch['name']),limit=patch['bytes'],cancel=cancel,destination=patch_path,progress=progress)
                    if not file_matches(patch_path,patch):raise ValueError('Patch checksum mismatch')
                    from .update_delta import restore
                    def cancelled():
                        if cancel.is_set():raise Cancelled()
                    with base.open('rb') as source,patch_path.open('rb') as delta,temporary.open('wb') as out:
                        restore(source,delta,out,package['bytes'],cancelled)
                    if file_matches(temporary,package):
                        if package['name']=='Lupin-Windows-x64.zip':validate_portable(temporary)
                        temporary.replace(destination);self.keep_base(destination,package);return destination
                except Cancelled:raise
                except (OSError,ValueError,ImportError):pass
                finally:patch_path.unlink(missing_ok=True)
            self.transport.get(asset_url(release,package['name']),limit=package['bytes'],cancel=cancel,destination=temporary,progress=progress)
            if not file_matches(temporary,package):raise ValueError('Downloaded package checksum mismatch')
            if package['name']=='Lupin-Windows-x64.zip':validate_portable(temporary)
            temporary.replace(destination)
            self.keep_base(destination,package)
            return destination
        finally:temporary.unlink(missing_ok=True)

    def keep_base(self,path,package):
        """Hard-link two verified bases; never copy another full model payload."""
        folder=path.parent;base=folder/('base-'+package['sha256'])
        if not base.exists():
            try:os.link(path,base)
            except OSError:return
        os.utime(base,None)
        bases=sorted(folder.glob('base-*'),key=lambda p:p.stat().st_mtime,reverse=True)
        for old in bases[2:]:old.unlink(missing_ok=True)
        for old in folder.iterdir():
            if old!=path and old.is_file() and not old.name.startswith('base-') and not old.name.endswith('.part'):old.unlink(missing_ok=True)
