"""One local, demand-driven OCR/translation process. No desktop or network access.

Input is a bounded JSON header followed by RGB bytes from our existing capture.
Only results leave the worker. Nothing is written to disk.
"""
import json
import os
from pathlib import Path
import re
import sys
import time
from collections import OrderedDict


class Translator:
    def __init__(self, root):
        import ctranslate2
        import sentencepiece
        root=Path(root)
        self.source=sentencepiece.SentencePieceProcessor(model_file=str(root/"source.spm"))
        self.target=sentencepiece.SentencePieceProcessor(model_file=str(root/"target.spm"))
        self.model=ctranslate2.Translator(str(root/"translation"),device="cpu",compute_type="int8",intra_threads=2,inter_threads=1)
        self.model.translate_batch([self.source.encode("오늘 날씨가 좋습니다.",out_type=str)],beam_size=1,max_decoding_length=12)
        self.cache=OrderedDict()

    def translate(self, text):
        from .chat_text import glossary, HANGUL, numbers_preserved
        if text in self.cache:
            self.cache.move_to_end(text);return self.cache[text]
        output=glossary(text)
        note="Game-chat glossary"
        if output is None:
            output=glossary(text,partial=True)
            note="Partial · unknown Korean kept"
        if output is None:
            tokens=self.source.encode(text,out_type=str)
            result=self.model.translate_batch([tokens],beam_size=1,max_decoding_length=72,repetition_penalty=1.15)[0]
            output=self.target.decode(result.hypotheses[0]);note="Approximate local translation"
        if not numbers_preserved(text,output):
            output="Translation could not preserve the numbers. Please check the original."
            note="Numbers uncertain · original retained"
        self.cache[text]=(output,note)
        while len(self.cache)>256:self.cache.popitem(last=False)
        return output,note


def scan(image, cursor, recognizer, translator, emit, budget=1.5):
    from .chat_ocr import bubbles, lines
    from .chat_text import HANGUL, normalize
    start=time.perf_counter();candidates=bubbles(image)
    # Nearby speech bubbles arrive first. The hotkey does not track player names.
    candidates.sort(key=lambda b:(b[0]+b[2]/2-cursor[0])**2+(b[1]+b[3]/2-cursor[1])**2)
    found=0
    for box in candidates:
        if found>=4 or time.perf_counter()-start>budget:break
        x,y,w,h=box;crop=image.copy(x+2,y+2,w-4,h-4)
        read=[]
        for line,height in lines(crop):
            text,confidence=recognizer.read(line)
            if confidence<.80:continue
            read.append(text)
        if not read:continue
        sender="";first=re.match(r"^([^:]{1,24})\s*:\s*(.*)$",read[0])
        if first:sender=first[1].strip();read[0]=first[2]
        text=normalize(" ".join(read))
        if not HANGUL.search(text):continue
        # A lone Korean character amongst Latin advertising is a common OCR error.
        korean=len(HANGUL.findall(text))
        if korean<2 and not re.fullmatch(r"[\u3130-\u318f]{1,8}",text):continue
        english,note=translator.translate(text)
        emit({"box":box,"speaker":sender,"original":text,"text":english,"note":note,
              "elapsed_ms":round((time.perf_counter()-start)*1000,1)})
        found+=1
    return {"count":found,"elapsed_ms":round((time.perf_counter()-start)*1000,1)}


def send(message):
    # Windows pipes can default to a legacy code page. The IPC is always UTF-8.
    sys.stdout.buffer.write((json.dumps(message,ensure_ascii=False)+"\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def main():
    # Scoped to our process. Do not change scheduling or settings of other apps.
    os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="2";os.environ["OMP_WAIT_POLICY"]="PASSIVE"
    if hasattr(os,"nice"):os.nice(10)
    try:
        from PySide6.QtGui import QImage
        from .chat_ocr import Recognizer
        root=Path(sys.argv[1]);recognizer=Recognizer(root);translator=Translator(root)
        # Warm only our models so the first hotkey does not pay kernel setup costs.
        warm=QImage(80,14,QImage.Format.Format_RGB888);warm.fill(0xeeeeee);recognizer.read(warm)
        translator.translate("안녕하세요")
        send({"ready":True})
    except Exception as error:
        send({"error":"Local Korean models could not load: "+str(error)});return 1
    while True:
        header=sys.stdin.buffer.readline(8193)
        if not header:break
        try:
            if len(header)>8192:raise ValueError("Header too large")
            request=json.loads(header);w,h,stride=(int(request[k]) for k in ("width","height","stride"))
            size=stride*h
            if not (16<=w<=7680 and 16<=h<=4320 and w*3<=stride<=w*3+4 and size<=32*1024*1024):raise ValueError("Invalid frame size")
            data=sys.stdin.buffer.read(size)
            if len(data)!=size:break
            image=QImage(data,w,h,stride,QImage.Format.Format_RGB888).copy()
            identity=request["id"]
            result=scan(image,request.get("cursor",[w//2,h//2]),recognizer,translator,
                        lambda row:send({"id":identity,"row":row}))
            send({"id":identity,"done":result})
        except Exception as error:
            send({"error":"Korean scan failed: "+str(error)});return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
