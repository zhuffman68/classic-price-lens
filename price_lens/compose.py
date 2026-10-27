"""Shared outgoing draft state. Explicit copying only, never game input or focus control."""
from collections import OrderedDict
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject,QProcess,QProcessEnvironment,QTimer,Signal
from PySide6.QtGui import QGuiApplication
from .outgoing_text import LIMIT,clean,expand,protect,template,validate,warnings


class KoreanComposer(QObject):
    changed=Signal()
    copied=Signal(str)

    def __init__(self,root,parent=None):
        super().__init__(parent);self.root=Path(root)
        self.text='';self.expanded='';self.result='';self.note='';self.error='';self.status='Write a message in English.'
        self.identity=0;self.result_id=None;self.copy_pending=None;self.names=()
        self.process=None;self.ready=False;self.inflight=None;self.queued=None;self.buffer=b'';self.cache=OrderedDict()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.preview)
        self.idle=QTimer(self);self.idle.setSingleShot(True);self.idle.setInterval(90000);self.idle.timeout.connect(self.unload)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.setInterval(12000);self.deadline.timeout.connect(self.timed_out)

    @property
    def busy(self):return bool(self.inflight or self.queued or self.process is not None and not self.ready)

    def set_names(self,items):
        names=tuple(sorted({item.name for item in items}))
        if names==self.names:return
        self.names=names
        self.cache.clear()
        # A newly loaded catalog can protect names that an earlier draft did
        # not know. Retire that result and any pending copy before recomputing.
        if self.text:
            text=self.text;self.text='';self.set_text(text)

    def set_text(self,value):
        value=clean(value)[:LIMIT]
        if value==self.text:return
        self.identity+=1;self.text=value;self.expanded='';self.result='';self.result_id=None;self.note='';self.error=''
        self.queued=None;self.copy_pending=None;self.status='Preparing a Korean preview…' if value else 'Write a message in English.'
        self.timer.stop()
        if value:self.timer.start()
        self.changed.emit()

    def preview(self):
        if not self.text:return
        self.expanded=expand(self.text);self.error=''
        cached=self.cache.get(self.expanded)
        if cached is not None:
            self.cache.move_to_end(self.expanded);self.accept(self.identity,*cached);return
        try:direct=template(self.expanded,self.names)
        except ValueError as error:self.failed(str(error));return
        if direct is not None:
            self.accept(self.identity,direct,'Common game-chat phrasing');return
        try:self.queued=(self.identity,protect(self.expanded,self.names))
        except ValueError as error:self.failed(str(error));return
        self.status='Translating locally…' if self.ready else 'Loading the local Korean writer…'
        self.idle.stop();self.start_worker();self.flush();self.changed.emit()

    def request_copy(self):
        if not self.text:return
        self.copy_pending=self.identity;self.timer.stop()
        if self.result_id==self.identity and self.result:self.copy_result()
        else:self.preview()

    def cancel_copy(self):self.copy_pending=None

    def accept(self,identity,text,note):
        if identity!=self.identity:return
        try:self.result=validate(self.expanded,text)
        except ValueError as error:
            self.result='';self.result_id=None;self.error=str(error);self.copy_pending=None
        else:
            self.result_id=identity;self.error='';self.note=' · '.join([note]+warnings(self.expanded))
            self.cache[self.expanded]=(self.result,note)
            while len(self.cache)>64:self.cache.popitem(last=False)
            self.status='Korean preview ready.'
        self.changed.emit()
        if self.copy_pending==identity and self.result:self.copy_result()

    def copy_result(self):
        if self.copy_pending!=self.identity or self.result_id!=self.identity or not self.result:return
        self.copy_pending=None
        QGuiApplication.clipboard().setText(self.result)
        self.copied.emit(self.result)

    def start_worker(self):
        if self.process is not None:return
        models=self.root/'models/english-korean'
        if not (models/'translation/model.bin').is_file():
            self.error='The English to Korean model is missing. Reinstall Lupin or run scripts/prepare_chat_models.py.'
            self.queued=None;self.copy_pending=None;return
        process=QProcess(self);self.process=process
        process.setWorkingDirectory(str(self.root));env=QProcessEnvironment.systemEnvironment()
        for key,value in [('OPENBLAS_NUM_THREADS','1'),('OMP_NUM_THREADS','2'),('OMP_WAIT_POLICY','PASSIVE')]:env.insert(key,value)
        process.setProcessEnvironment(env);process.readyReadStandardOutput.connect(self.receive)
        process.readyReadStandardError.connect(lambda:process.readAllStandardError())
        process.finished.connect(lambda *_:self.finished(process))
        process.errorOccurred.connect(lambda *_:self.worker_error(process))
        process.start(sys.executable,['-B','-m','price_lens.compose_worker',str(models)]);self.deadline.start()

    def worker_error(self,process):
        if self.process is process:
            self.failed('The local Korean writer could not start.');self.unload()

    def flush(self):
        if not self.ready or self.inflight or not self.queued:return
        self.inflight=self.queued;self.queued=None;identity,prepared=self.inflight
        self.process.write((json.dumps({'id':identity,'text':prepared.masked},ensure_ascii=False)+'\n').encode('utf-8'))
        self.deadline.start()

    def receive(self):
        if self.process is None:return
        self.buffer+=bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>65536:self.failed('The local translator returned an invalid response.');self.unload();return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:message=json.loads(line)
            except ValueError:continue
            if message.get('ready'):
                self.ready=True;self.deadline.stop();self.flush()
                if not self.inflight and not self.queued:self.idle.start()
                self.changed.emit();continue
            self.deadline.stop();job=self.inflight;self.inflight=None
            if message.get('error'):
                if job is None or job[0]==self.identity:self.failed(message['error'])
            elif job and message.get('id')==job[0] and job[0]==self.identity:
                try:restored=job[1].restore(message.get('text',''))
                except ValueError as error:self.failed(str(error))
                else:self.accept(job[0],restored,'Approximate translation · review before pasting')
            self.flush()
            if not self.inflight and not self.queued:self.idle.start()
            self.changed.emit()

    def failed(self,message):
        self.error=message;self.copy_pending=None;self.result='';self.result_id=None;self.changed.emit()

    def timed_out(self):
        self.failed('The local translator took too long. Try again with a shorter message.');self.unload()

    def finished(self,process):
        if self.process is not process:return
        self.process=None;self.ready=False;self.deadline.stop()
        if self.inflight or self.queued:self.failed('The local Korean writer stopped. Try again.')
        self.inflight=self.queued=None;process.deleteLater();self.changed.emit()

    def unload(self):
        self.idle.stop();self.deadline.stop();self.ready=False;self.inflight=self.queued=None;self.buffer=b''
        if self.process is not None:
            process=self.process;self.process=None;process.blockSignals(True);process.closeWriteChannel()
            if not process.waitForFinished(200):process.kill();process.waitForFinished(1000)
            process.deleteLater()
        self.changed.emit()

    def close(self):
        self.timer.stop();self.cancel_copy();self.unload();self.cache.clear()
