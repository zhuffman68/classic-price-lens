"""Prepare signed GitHub update assets locally. Never publishes or uploads.

Private keys belong outside this repository; only public keys ship in Lupin.
Optional deltas use bounded chunks and are kept only below 80% of a full file.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from price_lens import __version__
from price_lens.updates import REPOSITORY,MANIFEST,SIGNATURE,canonical,version,descriptor,file_matches,signed_manifest
from price_lens.update_delta import make

TRUST=ROOT/'price_lens/resources/update-keys.json'


def public_key(key):
    encoded=subprocess.check_output(['openssl','pkey','-in',str(key),'-pubout','-outform','DER'],stderr=subprocess.DEVNULL)
    if len(encoded)!=44 or encoded[:12]!=bytes.fromhex('302a300506032b6570032100'):raise ValueError('Signing key is not Ed25519')
    return encoded[12:]


def keygen(key,trust):
    key=key.resolve()
    if key.is_relative_to(ROOT):raise ValueError('Keep private signing keys outside the repository')
    key.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    try:subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(key)],check=True,capture_output=True)
    except Exception:key.unlink(missing_ok=True);raise
    raw=public_key(key);identity=hashlib.sha256(raw).hexdigest()[:16]
    existing=json.loads(trust.read_text()) if trust.exists() else dict(schema=1,repository=REPOSITORY,keys={})
    existing['keys'][identity]=raw.hex();trust.parent.mkdir(parents=True,exist_ok=True);trust.write_bytes(canonical(existing)+b'\n')
    print('Created release signing key; public key ID:',identity)


def describe(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return descriptor(dict(name=path.name,bytes=path.stat().st_size,sha256=digest))


def prepare(args):
    version(args.version)
    names={'windows-installer-x64':f'Lupin-{args.version}-Windows-x64-Setup.exe','windows-portable-x64':'Lupin-Windows-x64.zip',
           'linux-arch-x64':f'lupin-{args.version}-1-x86_64.pkg.tar.zst','linux-debian-x64':f'lupin_{args.version}-1_amd64.deb'}
    keys=json.loads(args.trust.read_text());raw_key=public_key(args.key)
    identity=hashlib.sha256(raw_key).hexdigest()[:16]
    if keys.get('keys',{}).get(identity)!=raw_key.hex():raise ValueError('Signing key is not pinned in the application')
    old=json.loads(args.base_manifest.read_text()) if args.base_manifest else None
    if old and (not args.base_dir or version(old['version'])>=version(args.version)):raise ValueError('A patch needs an older base release directory')
    document=dict(schema=1,repository=REPOSITORY,version=args.version,artifacts={},capture_compatible_from=args.capture_compatible_from)
    for previous in args.capture_compatible_from:
        if version(previous)>=version(args.version):raise ValueError('Capture compatibility must refer to an older version')
    for target,name in names.items():
        path=args.dist/name;value=describe(path)
        if old and target in old.get('artifacts',{}):
            previous=old['artifacts'][target];base=args.base_dir/previous['name']
            if not file_matches(base,previous):raise ValueError('Base release artifact checksum does not match: '+target)
            delta=args.dist/f'Lupin-update-{target}-{old["version"]}-to-{args.version}.zst'
            with base.open('rb') as source,path.open('rb') as updated,delta.open('wb') as out:make(source,updated,out)
            if delta.stat().st_size<value['bytes']*.8:
                value['patches']=[dict(describe(delta),from_version=old['version'],from_sha256=previous['sha256'],format='lupin-zstd-chunks-1')]
            else:delta.unlink()
        document['artifacts'][target]=value
    destination=args.dist/MANIFEST;destination.write_bytes(canonical(document))
    temporary=args.dist/(SIGNATURE+'.raw')
    try:
        subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(args.key),'-in',str(destination),'-out',str(temporary)],check=True,capture_output=True)
        signature=dict(key_id=identity,signature=base64.b64encode(temporary.read_bytes()).decode('ascii'))
        signed_manifest(destination.read_bytes(),canonical(signature),keys)
        (args.dist/SIGNATURE).write_bytes(canonical(signature))
    finally:temporary.unlink(missing_ok=True)
    print('Prepared signed update metadata and useful patches only; nothing uploaded.')


def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='command',required=True)
    generate=commands.add_parser('keygen');generate.add_argument('--key',required=True,type=Path);generate.add_argument('--trust',type=Path,default=TRUST)
    release=commands.add_parser('prepare');release.add_argument('--key',required=True,type=Path);release.add_argument('--trust',type=Path,default=TRUST)
    release.add_argument('--version',default=__version__);release.add_argument('--dist',type=Path,default=ROOT/'dist')
    release.add_argument('--base-manifest',type=Path);release.add_argument('--base-dir',type=Path)
    release.add_argument('--capture-compatible-from',action='append',default=[])
    args=parser.parse_args()
    if args.command=='keygen':keygen(args.key,args.trust)
    else:prepare(args)


if __name__=='__main__':main()
