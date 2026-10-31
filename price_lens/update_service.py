"""One asynchronous update job and configurable checks while Lupin is open."""
from concurrent.futures import ThreadPoolExecutor
import json
from math import ceil,isfinite
import os
import secrets
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
from .desktop_environment import recovered_environment


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
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.periodic_check)
        self.launch_timer=QTimer(self);self.launch_timer.setSingleShot(True);self.launch_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.launch_timer.timeout.connect(self.launch_check)
        self.auth_timer=QTimer(self);self.auth_timer.setSingleShot(True);self.auth_timer.setInterval(120000);self.auth_timer.timeout.connect(self.cancel)
        self.completed.connect(self.finish,Qt.ConnectionType.QueuedConnection)
        self.transfer.connect(self.on_progress,Qt.ConnectionType.QueuedConnection)
        self.result_timer=QTimer(self);self.result_timer.setInterval(250);self.result_timer.timeout.connect(self.poll_result)
        self.ready_notice_timer=QTimer(self);self.ready_notice_timer.setInterval(100);self.ready_notice_timer.timeout.connect(self.poll_ready_notice)
        self.pending_result_notice=None
        self.state='idle';self.offer=None;self.error='';self.progress=(0,0);self.closed=False
        self.cancelled=threading.Event();self.helper=None;self.committed=False;self.downloaded=None
        for field,key in (('last_checked','update-last-check'),('not_before','update-retry-after')):
            try:value=float(settings.value(key,0,type=float))
            except (TypeError,ValueError):value=0
            setattr(self,field,value if isfinite(value) and value>=0 else 0)
        try:self.offer=client.cached_offer(__version__,self.target.name)
        except Exception:pass  # Optional cache never blocks startup or authorizes an unverified file.
        self.previous_result=None
        if self.target.installable:
            path=self.cache/'last-result.json' if self.target.name.startswith('windows-') else Path(f'/var/cache/lupin-updates/last-result-{os.getuid()}.json')
            try:
                with path.open('rb') as stream:result=read_json(stream.read(8193))
                if isinstance(result,dict) and type(result.get('ok')) is bool and result.get('status')!='starting':
                    self.previous_result=result
                    if not result['ok']:self.error='The previous update did not finish. Lupin has reopened.'
            except (OSError,ValueError):pass

    @property
    def busy(self):return self.state in ('checking','downloading','preparing','cancelling')

    def configure(self):
        if not self.settings.value('update-on-launch',True,type=bool):self.launch_timer.stop()
        self.schedule()

    def periodic_interval(self):
        minutes=self.settings.value('update-interval-minutes',360,type=int)
        return minutes*60 if self.target.installable and type(minutes) is int and 15<=minutes<=10080 else None

    @staticmethod
    def delay_ms(seconds):
        # Keep long server deadlines intact; one Qt timer wait is at most a week.
        return max(1,ceil(min(604800,max(0,seconds))*1000))

    def schedule(self):
        self.timer.stop()
        interval=self.periodic_interval()
        if self.closed or self.committed or interval is None:return
        now=self.clock()
        due=self.last_checked+interval if self.last_checked else now+interval
        if self.not_before:due=self.not_before
        due=max(due,self.last_checked+60,self.not_before)
        self.timer.start(self.delay_ms(max(1 if self.busy else 0,due-now)))

    def periodic_check(self):
        if self.closed or self.committed or self.periodic_interval() is None:return
        if self.busy:self.timer.start(1000);return
        if not self.check():self.schedule()

    def launch_check(self):
        if self.closed or self.committed or not self.target.installable or not self.settings.value('update-on-launch',True,type=bool):return
        remaining=max(self.last_checked+60,self.not_before)-self.clock()
        if self.busy or remaining>0:
            self.launch_timer.start(self.delay_ms(max(1 if self.busy else 0,remaining)));return
        self.check()

    def start(self):
        if self.closed:return
        self.configure()
        self.changed.emit()
        if self.previous_result:self.announce_result(self.previous_result)
        if self.target.installable and self.settings.value('update-on-launch',True,type=bool):
            delay=max(1500,self.delay_ms(max(self.last_checked+60,self.not_before)-self.clock()))
            self.launch_timer.start(delay)

    def announce_result(self,result):
        identity=str(result.get('attempt',''))+str(result.get('version',''))+str(result['ok'])
        if self.settings.value('update-result-notified','')==identity:return
        # Older installed helpers can only report transaction success. Even
        # that first upgrade must not announce GUI readiness before our helper
        # has answered from the new app's event loop.
        if result['ok'] and not self.startup_health():
            if self.pending_result_notice is None:self.ready_notice_deadline=time.monotonic()+15
            self.pending_result_notice=result;self.ready_notice_timer.start();return
        self.settings.setValue('update-result-notified',identity)
        message=('The updated app is ready.' if result['ok'] else
                 'Lupin installed, but its overlay could not start. Restart Lupin from the application launcher.'
                 if result.get('reason')=='startup' else 'Lupin has reopened. Open Settings to retry.')
        QTimer.singleShot(0,lambda:self.notice.emit('Lupin updated' if result['ok'] else 'Lupin update needs attention',message) if not self.closed else None)

    def startup_health(self):
        parent=self.parent()
        return parent is None or not hasattr(parent,'overlay') or bool(getattr(parent.overlay,'ready',False))

    def poll_ready_notice(self):
        result=self.pending_result_notice
        if self.closed or result is None:self.ready_notice_timer.stop();return
        if not self.startup_health() and time.monotonic()<self.ready_notice_deadline:return
        self.ready_notice_timer.stop();self.pending_result_notice=None
        if self.startup_health():self.announce_result(result);return
        self.error='The update installed, but the overlay could not start.'
        self.announce_result({**result,'ok':False,'reason':'startup'})
        # Acknowledge the original legacy record after health is known, so it
        # cannot produce a false success message on a later normal launch.
        identity=str(result.get('attempt',''))+str(result.get('version',''))+str(result['ok'])
        self.settings.setValue('update-result-notified',identity);self.changed.emit()

    def watch_result(self,attempt):
        self.result_attempt=attempt;self.result_deadline=time.monotonic()+25;self.result_timer.start()

    def poll_result(self):
        if self.closed or time.monotonic()>self.result_deadline:self.result_timer.stop();return
        path=self.cache/'last-result.json' if self.target.name.startswith('windows-') else Path(f'/var/cache/lupin-updates/last-result-{os.getuid()}.json')
        try:
            with path.open('rb') as stream:result=read_json(stream.read(8193))
        except (OSError,ValueError):return
        if (not isinstance(result,dict) or result.get('attempt')!=self.result_attempt
                or result.get('status')=='starting' or type(result.get('ok')) is not bool):return
        self.result_timer.stop();self.previous_result=result
        self.error='' if result['ok'] else ('The update installed, but the overlay could not start.' if result.get('reason')=='startup' else 'The previous update did not finish. Lupin has reopened.')
        self.announce_result(result);self.changed.emit()

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
        if self.closed or self.busy or self.committed:return False
        if self.clock()<max(self.last_checked+60,self.not_before):return False
        if not self.target.name:self.error='Updates are not available for this platform';self.changed.emit();return False
        self.timer.stop();self.launch_timer.stop()
        self.state='checking';self.error='';self.changed.emit()
        self.submit('check',lambda cancel:self.client.check(__version__,self.target.name,cancel))
        return True

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
        plan=dict(schema=1,offer=self.offer,target=self.target.name,root=str(self.root.resolve()),
                  package_path=str(self.downloaded.resolve()),relaunch_env=recovered_environment(),startup_token=secrets.token_hex(32))
        request=folder/'request.json';atomic_json(request,plan);request.chmod(0o600)
        if sys.platform=='win32':
            script=folder/'install.ps1';shutil.copyfile(self.root/'price_lens/resources/update-windows.ps1',script)
            command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-Plan',str(request)]
        else:command=['pkexec','--disable-internal-agent','/usr/lib/lupin/lupin-update','--request',str(request)]
        options=dict(stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=str(folder.resolve()))
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
            self.release_helper();self.state='available' if self.offer else 'idle';self.error=''
            if kind=='check':self.schedule()
            self.changed.emit();return
        if error is not None:
            self.release_helper();self.state='available' if self.offer else 'idle'
            if isinstance(error,HTTPError):
                if error.code in (403,429):
                    deadlines=[self.clock()+900]
                    for header,relative in (('X-RateLimit-Reset',False),('Retry-After',True)):
                        value=(error.headers or {}).get(header)
                        if value is None:continue
                        try:
                            deadline=float(value)+(self.clock() if relative else 0)
                            if isfinite(deadline):deadlines.append(deadline)
                        except (ValueError,TypeError):
                            if relative:
                                try:
                                    from email.utils import parsedate_to_datetime
                                    deadline=parsedate_to_datetime(value).timestamp()
                                    if isfinite(deadline):deadlines.append(deadline)
                                except (ValueError,TypeError,OverflowError):pass
                    self.not_before=max(deadlines)
                    self.settings.setValue('update-retry-after',self.not_before)
                self.error='Release feed unavailable' if error.code==404 else 'Update connection unavailable'
            elif isinstance(error,(ValueError,OSError,TimeoutError)):self.error=str(error)[:200]
            else:self.error='The update could not be completed'
            if kind=='check':self.schedule()
            self.changed.emit();return
        if kind=='check':
            self.not_before=0;self.settings.setValue('update-retry-after',0)
            self.offer=result;self.state='available' if result else 'idle'
            if result and self.settings.value('update-notified-version','')!=result['manifest']['version']:
                value=result['manifest']['version'];self.settings.setValue('update-notified-version',value);self.available.emit(value)
            self.schedule()
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
        self.closed=True;self.timer.stop();self.launch_timer.stop();self.auth_timer.stop();self.result_timer.stop();self.ready_notice_timer.stop()
        if not self.committed:self.cancelled.set();self.release_helper()
        self.pool.shutdown(wait=False,cancel_futures=True)
