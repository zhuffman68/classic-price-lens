"""Narrow native Linux update helper, run by pkexec from root-owned files.

Reverify the signed manifest and a root-owned copy before acknowledging readiness.
The GUI keeps running during authentication. Installation starts only after its
explicit commit and EOF on its own pipe, after tracking and capture have closed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent.parent
if not __package__:sys.path.insert(0,str(ROOT))
from price_lens import __version__
from price_lens.updates import artifact,read_json,signed_manifest,target_for,version,atomic_json
from price_lens.desktop_environment import clean_environment


def validate_plan(plan,root,current,target,keys):
    if not isinstance(plan,dict):raise ValueError('Invalid update request')
    if Path(plan.get('root','')).resolve()!=root:raise ValueError('Wrong Lupin installation')
    if not target.installable or plan.get('target')!=target.name:raise ValueError('Wrong native package target')
    if not isinstance(plan.get('startup_token'),str) or not re.fullmatch(r'[0-9a-f]{64}',plan['startup_token']):
        raise ValueError('Restart Lupin before preparing another update')
    offer=plan['offer']
    document=signed_manifest(json.dumps(offer['manifest']).encode(),json.dumps(offer['signature']).encode(),keys)
    if version(document['version'])<=version(current):raise ValueError('Update is not newer than this installation')
    package=artifact(document,target.name)
    return package,document['version'],current in document.get('capture_compatible_from',[])


def prepare(plan,uid,stage):
    if ROOT!=Path('/opt/lupin'):raise ValueError('Not a system Lupin installation')
    keys=read_json((ROOT/'price_lens/resources/update-keys.json').read_bytes())
    target=target_for(ROOT)
    package,new_version,compatible=validate_plan(plan,ROOT,__version__,target,keys)
    if shutil.disk_usage(stage).free<package['bytes']*3+100_000_000:raise ValueError('Not enough free space to install Lupin')
    source=Path(plan['package_path'])
    descriptor=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
    destination=stage/package['name'];digest=hashlib.sha256();count=0
    with os.fdopen(descriptor,'rb') as incoming,destination.open('xb') as out:
        if os.fstat(incoming.fileno()).st_uid!=uid:raise ValueError('Downloaded package has the wrong owner')
        while block:=incoming.read(262144):
            count+=len(block)
            if count>package['bytes']:raise ValueError('Downloaded package is too large')
            digest.update(block);out.write(block)
    if count!=package['bytes'] or digest.hexdigest()!=package['sha256']:raise ValueError('Root-staged package checksum mismatch')
    destination.chmod(0o644)
    verify_native_identity(destination,target.name,new_version)
    command=['/usr/bin/pacman','-U','--noconfirm',str(destination)] if target.name=='linux-arch-x64' else [
        '/usr/bin/apt-get','-y','--no-install-recommends','install',str(destination)]
    return command,new_version,compatible


def verify_native_identity(path,target,new_version):
    arch=target=='linux-arch-x64'
    command=['/usr/bin/pacman','-Qip',str(path)] if arch else ['/usr/bin/dpkg-deb','--field',str(path),'Package','Version','Architecture']
    try:result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=15,env={**os.environ,'LC_ALL':'C'})
    except (OSError,subprocess.SubprocessError) as error:raise ValueError('The native package could not be inspected') from error
    fields=dict((key.strip(),value.strip()) for line in result.stdout.splitlines() if ':' in line for key,value in [line.split(':',1)])
    if fields.get('Name' if arch else 'Package')!='lupin' or fields.get('Version')!=new_version+'-1' or fields.get('Architecture')!=('x86_64' if arch else 'amd64'):
        raise ValueError('The package identity does not match this Lupin release')


def relaunch(plan,uid,resume_capture=False,*,job=None):
    import pwd
    account=pwd.getpwuid(uid)
    supplied=plan.get('relaunch_env',{})
    if not isinstance(supplied,dict):supplied={}
    env={'PATH':'/usr/bin:/bin','HOME':account.pw_dir,'USER':account.pw_name,'LOGNAME':account.pw_name,
         **clean_environment(supplied)}
    if job is not None:
        env['LUPIN_UPDATE_JOB']=str(job)
        env['LUPIN_UPDATE_TOKEN']=plan['startup_token']
    return subprocess.Popen(['/usr/bin/lupin']+(['--capture'] if resume_capture else []),cwd=account.pw_dir,env=env,user=uid,group=account.pw_gid,
        extra_groups=os.getgrouplist(account.pw_name,account.pw_gid),start_new_session=True,
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',type=Path,required=True);args=parser.parse_args()
    stage=None;committed=False;plan=None;uid=None;lock=None;child=None
    try:
        if sys.platform!='linux' or os.geteuid()!=0:raise ValueError('System authentication is required')
        uid=int(os.environ.get('PKEXEC_UID','0'))
        if uid<=0:raise ValueError('Missing invoking user')
        fd=os.open(args.request,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            if os.fstat(stream.fileno()).st_uid!=uid:raise ValueError('Update request has the wrong owner')
            data=stream.read(524289)
        if len(data)>524288:raise ValueError('Update request is too large')
        plan=read_json(data)
        cache=Path('/var/cache/lupin-updates');cache.mkdir(mode=0o755,exist_ok=True)
        if cache.stat().st_uid!=0 or cache.stat().st_mode&0o022:raise ValueError('Unsafe system update cache')
        import fcntl
        lock=(cache/'install.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stage=Path(tempfile.mkdtemp(prefix='install-',dir=cache));stage.chmod(0o755)
        command,new_version,compatible=prepare(plan,uid,stage)
        print('{"ready":true}',flush=True)
        commit=read_json(sys.stdin.buffer.readline(256))
        if commit.get('install') is not True or sys.stdin.buffer.read(1)!=b'':return 1
        committed=True
        with (stage/'install.log').open('wb') as log:
            result=subprocess.run(command,env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:shutil.copyfile(stage/'install.log',cache/f'last-install-{uid}.log')
        status=cache/f'last-result-{uid}.json'
        attempt=args.request.parent.name
        token=plan.get('startup_token','')
        verified_startup=result.returncode==0
        atomic_json(status,dict(version=new_version,ok=False,status='starting' if verified_startup else 'finished',attempt=attempt));status.chmod(0o644)
        child=relaunch(plan,uid,compatible and commit.get('resume_capture') is True,job=args.request.parent if verified_startup else None)
        if verified_startup:
            from price_lens.update_startup import wait_for_startup
            healthy=wait_for_startup(args.request.parent,token,new_version,child)
            atomic_json(status,dict(version=new_version,ok=healthy,attempt=attempt,reason='' if healthy else 'startup'));status.chmod(0o644)
        else:
            healthy=False
            atomic_json(status,dict(version=new_version,ok=False,attempt=attempt));status.chmod(0o644)
        return 0 if healthy else 1
    except (OSError,ValueError,KeyError,TypeError) as error:
        try:print(json.dumps(dict(error=str(error))),flush=True)
        except BrokenPipeError:pass
        if committed and plan and uid:
            try:
                status=cache/f'last-result-{uid}.json'
                atomic_json(status,dict(version=new_version,ok=False,attempt=args.request.parent.name));status.chmod(0o644)
                if child is None:relaunch(plan,uid)
            except OSError:pass
        return 1
    finally:
        # Keep only a small result and a failed transaction log, not another
        # copy of the installer/models in the root cache.
        if stage:shutil.rmtree(stage,ignore_errors=True)
        if lock:lock.close()


if __name__=='__main__':raise SystemExit(main())
