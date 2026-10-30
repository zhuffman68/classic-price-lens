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
        from .chat_text import glossary, HANGUL, numbers_preserved,recruiting_phrase,model_source,terms_preserved,unknown_shorthand
        if text in self.cache:
            self.cache.move_to_end(text);return self.cache[text]
        output=recruiting_phrase(text)
        note='Game-chat phrase'
        if output is None:output=glossary(text);note='Game-chat glossary'
        if output is None:
            partial=glossary(text,partial=True)
            if re.fullmatch(r"[\u3130-\u318f\u1100-\u11ff ?!]+",text):
                return "Unrecognized shorthand · see the original", "Partial · unknown Korean kept"
            prepared,required=model_source(text)
            tokens=self.source.encode(prepared,out_type=str)
            result=self.model.translate_batch([tokens],beam_size=1,max_decoding_length=72,repetition_penalty=1.15)[0]
            output=self.target.decode(result.hypotheses[0]);note="Approximate local translation"
            if HANGUL.search(output) or unknown_shorthand(text) or not terms_preserved(required,output) or len(result.hypotheses[0])>=72:
                output=partial or text;note='Partial · unknown Korean kept'
        if not numbers_preserved(text,output):
            output="Translation could not preserve the numbers. Please check the original."
            note="Numbers uncertain · original retained"
        self.cache[text]=(output,note)
        while len(self.cache)>256:self.cache.popitem(last=False)
        return output,note


def source_role(box,text,is_bubble,contexts=(),game_size=None):
    from PySide6.QtCore import QRect
    rect=QRect(*box)
    for context in contexts[:8]:
        if not isinstance(context,dict) or context.get('verified') is not True or context.get('role') not in ('store','chat','banner'):continue
        area=context.get('box')
        if not isinstance(area,list) or len(area)!=4 or any(type(v) is not int for v in area):continue
        overlap=rect.intersected(QRect(*area))
        if overlap.width()*overlap.height()>=rect.width()*rect.height()*.8:return context['role'],True
    if is_bubble:return 'bubble',True
    if re.search(r'(?:님의|님께서).*?(?:메시지|확성기|메가폰)',text):return 'banner',True
    # A conventional explicit speaker prefix is retained as evidence. Anonymous
    # store/banner prose never acquires a guessed player identity.
    sender=re.match(r'^\[?([A-Za-z0-9_\uac00-\ud7a3]{2,16})\]?\s*:\s*\S',text)
    if (sender and sender[1].casefold() not in ('판매','구매','모집','공지','알림','내용','sell','buy','notice')
            and game_size and box[0]<game_size[0]*.8 and box[1]>=game_size[1]*.5):return 'chat',True
    return 'text',False


def scan(image, recognizer, translator, emit, budget=.75, cancelled=lambda:False, exclude=(),contexts=(),memory=None):
    from .chat_scan import scan_frame
    return scan_frame(image,recognizer,translator,emit,source_role,budget=budget,cancelled=cancelled,
                      exclude=exclude,contexts=contexts,memory=memory)


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
    import threading
    condition=threading.Condition();state={'latest':None,'minimum':0,'closed':False,'error':None}
    def receive():
        try:
            while True:
                header=sys.stdin.buffer.readline(8193)
                if not header:break
                if len(header)>8192:raise ValueError('Header too large')
                request=json.loads(header)
                if 'cancel_before' in request:
                    with condition:
                        state['minimum']=max(state['minimum'],int(request['cancel_before']))
                        if state['latest'] and state['latest'][0]['id']<state['minimum']:state['latest']=None
                    continue
                w,h,stride=(int(request[k]) for k in ('width','height','stride'));size=stride*h
                if not(16<=w<=7680 and 16<=h<=4320 and w*3<=stride<=w*3+4 and size<=32*1024*1024):raise ValueError('Invalid frame size')
                data=sys.stdin.buffer.read(size)
                if len(data)!=size:break
                image=QImage(data,w,h,stride,QImage.Format.Format_RGB888).copy()
                with condition:state['latest']=(request,image);condition.notify()
        except Exception as error:
            with condition:state['error']=str(error)
        finally:
            with condition:state['closed']=True;condition.notify()
    threading.Thread(target=receive,name='local-frame-input',daemon=True).start()
    from .chat_scan import ScanMemory
    memory=ScanMemory()
    while True:
        with condition:
            condition.wait_for(lambda:state['latest'] is not None or state['closed'])
            if state['latest'] is None:
                if state['error']:send({'error':'Korean scan failed: '+state['error']});return 1
                break
            request,image=state['latest'];state['latest']=None
        identity=request['id']
        result=scan(image,recognizer,translator,lambda row:send({'id':identity,'row':row}),
                    cancelled=lambda:identity<state['minimum'],exclude=request.get('exclude',[])[:64],
                    contexts=request.get('contexts',[])[:8],memory=memory)
        send({'id':identity,'done':result})
    return 0


if __name__=="__main__":raise SystemExit(main())
