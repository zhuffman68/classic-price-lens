"""Prepare pinned English to Korean data with the already bundled CPU runtime."""
import json
from pathlib import Path
import shutil
import zipfile
from download_runtime import fetch

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    from prepare_chat_models import verify
    manifest=json.loads((ROOT/'packaging/compose-models.json').read_text())
    output=ROOT/'models/english-korean'
    try:verify(output,manifest['outputs']);print('Local Korean writer model already verified');return
    except (OSError,ValueError):pass
    downloads=ROOT/'.build-tools/chat-model-downloads';downloads.mkdir(parents=True,exist_ok=True)
    entry=manifest['inputs'][0];print(fetch(entry,downloads));archive=downloads/entry['name']
    source=downloads/'en-ko-2022';source.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();weights=next(n for n in names if n.endswith('.npz'))
        for name in (weights,'source.spm','target.spm','LICENSE','README.md'):
            (source/name).write_bytes(z.read(name))
        vocabs=[]
        for suffix in ('src','trg'):
            name=next(n for n in names if n.endswith('.'+suffix+'.vocab'))
            tokens=z.read(name).decode('utf-8').splitlines()
            path=source/(suffix+'.vocab.yml')
            path.write_text(''.join(json.dumps(token,ensure_ascii=False)+': '+str(i)+'\n' for i,token in enumerate(tokens)),encoding='utf-8')
            vocabs.append(str(path))
    from ctranslate2.converters import MarianConverter
    output.mkdir(parents=True,exist_ok=True)
    MarianConverter(str(source/weights),vocabs).convert(str(output/'translation'),quantization='int8',force=True)
    for path in (output/'translation').glob('*.json'):
        path.write_bytes(path.read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8'))
    for src,dst in [('source.spm','source.spm'),('target.spm','target.spm'),('LICENSE','LICENSE-OPUS.txt'),('README.md','OPUS-SOURCE.md')]:shutil.copy2(source/src,output/dst)
    verify(output,manifest['outputs'])
    (output/'manifest.json').write_text(json.dumps(manifest['outputs'],indent=2)+'\n')
    print('Verified local Korean writer model:',output)
