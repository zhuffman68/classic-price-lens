"""Qt controller for our isolated local translator and short-lived pixel snapshots."""
import json
from pathlib import Path
import time

from PySide6.QtCore import QObject,QProcess,QProcessEnvironment,QRect,Signal,Qt,QTimer
from PySide6.QtGui import QImage


def stamp(image, box):
    """Small visual fingerprint; a moved/covered bubble retires its translation."""
    sample=image.copy(QRect(*box)).scaled(24,24,Qt.AspectRatioMode.IgnoreAspectRatio,
                 Qt.TransformationMode.FastTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    return bytes(sample.constBits())


class ChatTranslation(QObject):
    changed=Signal()
    status=Signal(str)

    def __init__(self,root,parent=None):
        super().__init__(parent)
        self.root=Path(root);self.process=None;self.ready=False;self.busy=False;self.identity=0
        self.buffer=b"";self.cards=[];self.frame=QImage();self.region=QRect();self.started=0
        self.enabled=False

    def enable(self,enabled):
        self.enabled=enabled
        if not enabled:self.close();return
        if self.process is not None:return
        models=self.root/"models/korean-chat"
        if not (models/"rec.onnx").is_file():
            self.status.emit("Local Korean models are missing. Reinstall Lupin or run scripts/prepare_chat_models.py from source.");return
        import sys
        self.process=QProcess(self)
        self.process.setWorkingDirectory(str(self.root))
        env=QProcessEnvironment.systemEnvironment()
        for name,value in (("OPENBLAS_NUM_THREADS","1"),("OMP_NUM_THREADS","2"),("OMP_WAIT_POLICY","PASSIVE")):
            env.insert(name,value)
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.receive)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError() if self.process else None)
        self.process.errorOccurred.connect(lambda *_:self.status.emit("The local Korean worker could not start."))
        self.process.finished.connect(self.finished)
        self.status.emit("Warming local Korean translation…")
        self.process.start(sys.executable,["-B","-m","price_lens.chat_worker",str(models)])

    def finished(self,*_):
        self.ready=self.busy=False
        if self.enabled:self.status.emit("Local translator stopped. Toggle Korean translation off and on to restart.")

    def receive(self):
        self.buffer+=bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>1024*1024:
            self.status.emit("Local translator response was too large.");self.close();return
        while b"\n" in self.buffer:
            line,self.buffer=self.buffer.split(b"\n",1)
            try:message=json.loads(line)
            except ValueError:continue
            if message.get("ready"):
                self.ready=True;self.status.emit("Ready · local Korean translation");continue
            if message.get("error"):
                self.busy=False;self.status.emit(message["error"]);continue
            if message.get("id")!=self.identity:
                if message.get("done"):self.busy=False
                continue
            if message.get("row") and time.monotonic()-self.started<2.5:
                row=message["row"];box=row["box"]
                row["stamp"]=stamp(self.frame,box)
                row["box"]=[box[0]+self.region.x(),box[1]+self.region.y(),box[2],box[3]]
                row["until"]=time.monotonic()+8
                self.cards.append(row);self.changed.emit()
            if message.get("done"):
                self.busy=False;self.frame=QImage();result=message["done"]
                self.status.emit(f"{result['count']} Korean message(s) · {result['elapsed_ms']:.0f} ms" if result["count"] else "No readable Korean speech bubbles found. Move near a message and try again.")

    def request(self,image,region,cursor):
        if not self.ready:
            self.status.emit("Local translation is warming up. Try again when Ready appears.");return False
        if self.busy:
            self.status.emit("Finishing the current Korean scan…");return False
        region=region.intersected(image.rect())
        if region.width()<16 or region.height()<16:return False
        if region.width()*region.height()*3>32*1024*1024:
            self.status.emit("The translation area is too large. Limit the reading area in Settings.");return False
        self.frame=image.copy(region);self.region=QRect(region);crop=self.frame.convertToFormat(QImage.Format.Format_RGB888)
        data=bytes(crop.constBits());self.identity+=1;self.cards=[];self.changed.emit()
        request={"id":self.identity,"width":crop.width(),"height":crop.height(),"stride":crop.bytesPerLine(),
                 "cursor":[cursor[0]-region.x(),cursor[1]-region.y()]}
        self.started=time.monotonic();self.busy=True
        self.process.write((json.dumps(request)+"\n").encode());self.process.write(data)
        identity=self.identity
        QTimer.singleShot(4000,lambda:self.timeout(identity))
        self.status.emit("Reading Korean speech bubbles…");return True

    def timeout(self,identity):
        if self.busy and self.identity==identity:
            self.close();self.status.emit("Local scan timed out and was stopped. Toggle translation off and on to retry.")

    def annotations(self,image,sx,sy,bounds):
        rows=[];keep=[];now=time.monotonic()
        for index,card in enumerate(self.cards):
            box=card["box"]
            current=stamp(image,box)
            old=card["stamp"]
            different=len(current)!=len(old) or sum(abs(a-b)>30 for a,b in zip(current,old))>len(old)*.08
            if now>card["until"] or different:continue
            keep.append(card)
            rows.append({"kind":"translation","key":f"chat:{self.identity}:{index}","x":round((box[0]+box[2])*sx)+8,
                         "y":round(box[1]*sy),"bounds":bounds,"name":(card["speaker"]+" · " if card["speaker"] else "")+card["note"],
                         "text":card["text"],"original":card["original"],"color":"#e3e9f2"})
        self.cards=keep
        return rows

    def clear(self):
        self.identity+=1;self.cards=[];self.changed.emit()

    def close(self):
        self.enabled=False;self.clear();self.ready=self.busy=False;self.frame=QImage()
        if self.process is not None:
            self.process.blockSignals(True);self.process.closeWriteChannel()
            if not self.process.waitForFinished(200):self.process.kill();self.process.waitForFinished(1000)
            self.process.deleteLater();self.process=None
        self.buffer=b""
