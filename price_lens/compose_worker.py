"""Demand-driven English to Korean inference. UTF-8 pipes only; no OS/game access."""
import json
import os
from pathlib import Path
import sys


def send(value):
    sys.stdout.buffer.write((json.dumps(value,ensure_ascii=False)+'\n').encode('utf-8'))
    sys.stdout.buffer.flush()


def main():
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='2';os.environ['OMP_WAIT_POLICY']='PASSIVE'
    if hasattr(os,'nice'):os.nice(10)
    try:
        import ctranslate2,sentencepiece
        root=Path(sys.argv[1])
        source=sentencepiece.SentencePieceProcessor(model_file=str(root/'source.spm'))
        target=sentencepiece.SentencePieceProcessor(model_file=str(root/'target.spm'))
        model=ctranslate2.Translator(str(root/'translation'),device='cpu',compute_type='int8',intra_threads=2,inter_threads=1)
        model.translate_batch([source.encode('Hello.',out_type=str)],beam_size=1,max_decoding_length=12)
        send({'ready':True})
    except Exception:
        send({'error':'The local English to Korean model could not load. Reinstall Lupin or prepare the bundled models.'});return 1
    for line in sys.stdin.buffer:
        identity=None
        try:
            if len(line)>16384:raise ValueError('Request too large')
            request=json.loads(line);identity=request['id'];text=request['text']
            if not isinstance(text,str) or len(text)>2000:raise ValueError('Invalid text')
            result=model.translate_batch([source.encode(text,out_type=str)],beam_size=2,max_decoding_length=128,repetition_penalty=1.1)[0]
            if len(result.hypotheses[0])>=128:raise ValueError('Shorten the message')
            send({'id':identity,'text':target.decode(result.hypotheses[0])})
        except Exception:
            send({'id':identity,'error':'The local translator could not finish this draft. Try a shorter message.'})
    return 0


if __name__=='__main__':raise SystemExit(main())
