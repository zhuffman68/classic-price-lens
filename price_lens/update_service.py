"""One asynchronous update job and configurable checks while Lupin is open."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError

from PySide6.QtCore import QObject,QTimer,Signal,Qt

from . import __version__
from .updates import ReleaseClient,Cancelled,read_json,atomic_json,target_for


class UpdateService(QObject):
    changed=Signal()
    available=Signal(str)
    restart_requested=Signal()
    notice=Signal(str,str)
    completed=Signal(str,object,object)
    transfer=Signal(int,int)

    def __init__(self,root,cache,settings,parent=None,*,client=None,target=None,clock=time.time):
        super().__init__(parent)
        self.root=Path(root);self.cache=Path(cache);self.settings=settings;self.clock=clock
        self.target=target or target_for(root)
        if client is None:
            try:keys=read_json((self.root/'price_lens/resources/update-keys.json').read_bytes())
            except (OSError,ValueError):keys={}
            client=ReleaseClient(self.cache,keys)
        self.client=client;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-updates')
        self.timer=QTimer(self);self.timer.timeout.connect(self.check)
        self.auth_timer=QTimer(self);self.auth_timer.setSingleShot(True);self.auth_timer.setInterval(120000);self.auth_timer.timeout.connect(self.cancel)
        self.completed.connect(self.finish,Qt.ConnectionType.QueuedConnection)
        self.transfer.connect(self.on_progress,Qt.ConnectionType.QueuedConnection)
        self.state='idle';self.offer=None;self.error='';self.progress=(0,0);self.closed=False
        self.cancelled=threading.Event();self.helper=None;self.committed=False;self.downloaded=None
        self.last_checked=float(settings.value('update-last-check',0,type=float))
        self.not_before=float(settings.value('update-retry-after',0,type=float))
        try:self.offer=client.cached_offer(__version__,self.target.name)
        except Exception:pass  # Optional cache never blocks startup or authorizes an unverified file.
        self.previous_result=None
        if self.target.installable:
            path=self.cache/'last-result.json' if self.target.name.startswith('windows-') else Path(f'/var/cache/lupin-updates/last-result-{os.getuid()}.json')
            try:
                with path.open('rb') as stream:result=read_json(stream.read(8193))
                if isinstance(result,dict) and type(result.get('ok')) is bool:
                    self.previous_result=result
                    if not result['ok']:self.error='The previous update did not finish. Lupin has reopened.'
            except (OSError,ValueError):pass

    @property
    def busy(self):return self.state in ('checking','downloading','preparing','cancelling')

    def configure(self):
        self.timer.stop()
        minutes=self.settings.value('update-interval-minutes',360,type=int)
        if self.target.installable and type(minutes) is int and 15<=minutes<=10080:self.timer.start(minutes*60000)

    def start(self):
        self.configure()
        self.changed.emit()
        if self.previous_result:
            result=self.previous_result;identity=str(result.get('attempt',''))+str(result.get('version',''))+str(result['ok'])
            if self.settings.value('update-result-notified','')!=identity:
                self.settings.setValue('update-result-notified',identity)
                QTimer.singleShot(0,lambda:self.notice.emit('Lupin updated' if result['ok'] else 'Lupin update did not finish',
                    'The updated app is ready.' if result['ok'] else 'Lupin has reopened. Open Settings to retry.') if not self.closed else None)
        if self.target.installable and self.settings.value('update-on-launch',True,type=bool):
            delay=max(1500,min(604800000,round((max(self.last_checked+60,self.not_before)-self.clock())*1000)))
            QTimer.singleShot(delay,self.check)

    def submit(self,kind,work):
        self.cancelled=threading.Event();cancel=self.cancelled
        def run():
            result=error=None
            try:result=work(cancel)
            except Exception as caught:error=caught
            if self.closed:return
            try:self.completed.emit(kind,result,error)
            except RuntimeError:pass
        self.pool.submit(run)

    def check(self):
        if self.closed or self.busy or self.committed:return
        if self.clock()<max(self.last_checked+60,self.not_before):return
        if not self.target.name:self.error='Updates are not available for this platform';self.changed.emit();return
        self.state='checking';self.error='';self.changed.emit()
        self.submit('check',lambda cancel:self.client.check(__version__,self.target.name,cancel))

    def download_install(self):
        if self.closed or self.busy or not self.offer or not self.target.installable or self.committed:return
        self.state='downloading';self.error='';self.progress=(0,self.offer['package']['bytes']);self.changed.emit()
        offer=self.offer
        self.submit('download',lambda cancel:self.client.download(offer,__version__,cancel,self.report_progress))

    def report_progress(self,count,total):
        now=time.monotonic()
        if count==total or now-getattr(self,'last_progress',0)>=.15:
            self.last_progress=now
            try:self.transfer.emit(count,total)
            except RuntimeError:pass

    def on_progress(self,count,total):
        if not self.closed and self.state=='downloading':self.progress=(count,total);self.changed.emit()

    def prepare_install(self,cancel):
        if cancel.is_set():raise Cancelled()
        folder=Path(tempfile.mkdtemp(prefix='job-',dir=self.cache));folder.chmod(0o700)
        env_keys=('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','XDG_SESSION_TYPE','XDG_CURRENT_DESKTOP','LANG')
        plan=dict(schema=1,offer=self.offer,target=self.target.name,root=str(self.root.resolve()),
                  package_path=str(self.downloaded.resolve()),relaunch_env={key:os.environ[key] for key in env_keys if key in os.environ})
        request=folder/'request.json';atomic_json(request,plan);request.chmod(0o600)
        if sys.platform=='win32':
            script=folder/'install.ps1';shutil.copyfile(self.root/'price_lens/resources/update-windows.ps1',script)
            command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-Plan',str(request)]
        else:command=['pkexec','--disable-internal-agent','/usr/lib/lupin/lupin-update','--request',str(request)]
        options=dict(stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if sys.platform=='win32':options['creationflags']=subprocess.CREATE_NO_WINDOW
        self.helper=subprocess.Popen(command,**options)
        if cancel.is_set():self.release_helper();raise Cancelled()
        data=self.helper.stdout.readline(4097)
        if cancel.is_set():raise Cancelled()
        if len(data)>4096:raise ValueError('Unexpected installer response')
        try:ready=read_json(data)
        except ValueError:raise ValueError('Installation was not authorized or could not be prepared')
        if not ready.get('ready'):raise ValueError(ready.get('error','The update could not be prepared'))
        return True

    def finish(self,kind,result,error):
        if self.closed:return
        if kind=='check':self.last_checked=self.clock();self.settings.setValue('update-last-check',self.last_checked)
        if kind=='prepare':self.auth_timer.stop()
        if self.cancelled.is_set() or isinstance(error,Cancelled):
            self.release_helper();self.state='available' if self.offer else 'idle';self.error='';self.changed.emit();return
        if error is not None:
            self.release_helper();self.state='available' if self.offer else 'idle'
            if isinstance(error,HTTPError):
                if error.code in (403,429):
                    deadlines=[self.clock()+900]
                    for header,relative in (('X-RateLimit-Reset',False),('Retry-After',True)):
                        value=error.headers.get(header)
                        if value is None:continue
                        try:deadlines.append(float(value)+(self.clock() if relative else 0))
                        except (ValueError,TypeError):
                            if relative:
                                try:
                                    from email.utils import parsedate_to_datetime
                                    deadlines.append(parsedate_to_datetime(value).timestamp())
                                except (ValueError,TypeError,OverflowError):pass
                    self.not_before=max(deadlines)
                    self.settings.setValue('update-retry-after',self.not_before)
                self.error='Release feed unavailable' if error.code==404 else 'Update connection unavailable'
            elif isinstance(error,(ValueError,OSError,TimeoutError)):self.error=str(error)[:200]
            else:self.error='The update could not be completed'
            self.changed.emit();return
        if kind=='check':
            self.not_before=0;self.settings.setValue('update-retry-after',0)
            self.offer=result;self.state='available' if result else 'idle'
            if result and self.settings.value('update-notified-version','')!=result['manifest']['version']:
                value=result['manifest']['version'];self.settings.setValue('update-notified-version',value);self.available.emit(value)
        elif kind=='download':
            self.downloaded=Path(result);self.state='preparing';self.auth_timer.start()
            self.submit('prepare',self.prepare_install)
        elif kind=='prepare':
            self.state='preparing';self.changed.emit();self.restart_requested.emit();return
        self.changed.emit()

    def commit(self,resume_capture=False):
        if self.closed or self.helper is None or self.cancelled.is_set() or self.committed:return False
        compatible=__version__ in self.offer['manifest'].get('capture_compatible_from',[])
        try:
            self.helper.stdin.write(json.dumps(dict(install=True,resume_capture=bool(resume_capture and compatible))).encode()+b'\n');self.helper.stdin.flush()
        except (OSError,ValueError):
            self.release_helper();self.error='The installer exited before the update could start';self.state='available';self.changed.emit();return False
        self.committed=True;self.state='installing';self.changed.emit();return True

    def release_helper(self):
        if self.helper is not None and not self.committed:
            try:self.helper.stdin.close()
            except (OSError,ValueError):pass
            try:
                if self.helper.poll() is None:self.helper.terminate()
            except OSError:pass
            self.helper=None

    def cancel(self):
        if not self.busy:return
        self.cancelled.set();self.release_helper();self.state='cancelling';self.changed.emit()

    def close(self):
        self.closed=True;self.timer.stop();self.auth_timer.stop()
        if not self.committed:self.cancelled.set();self.release_helper()
        self.pool.shutdown(wait=False,cancel_futures=True)
