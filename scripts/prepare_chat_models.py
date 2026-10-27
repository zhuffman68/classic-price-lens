"""Download verified public models and prepare the local int8 chat bundle.

Run with requirements.txt installed. No screenshots or private data are read.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

from download_runtime import fetch

ROOT=Path(__file__).resolve().parents[1]


def verify(folder,files):
    for name,expected in files.items():
        path=folder/name
        with path.open("rb") as handle:digest=hashlib.file_digest(handle,"sha256").hexdigest()
        if path.stat().st_size!=expected["size"] or digest!=expected["sha256"]:
            raise ValueError("Unexpected prepared chat model: "+name)


def prepare_incoming():
    os.environ["OMP_NUM_THREADS"]="2";os.environ["OPENBLAS_NUM_THREADS"]="1"
    manifest=json.loads((ROOT/"packaging/chat-models.json").read_text())
    output=ROOT/"models/korean-chat"
    try:
        verify(output,manifest["outputs"]);print("Local chat models already verified");return
    except (OSError,ValueError):pass
    downloads=ROOT/".build-tools/chat-model-downloads";downloads.mkdir(parents=True,exist_ok=True)
    for entry in manifest["inputs"]:print(fetch(entry,downloads),flush=True)
    source=downloads/"source";source.mkdir(exist_ok=True)
    required=("opus.spm32k-spm32k.transformer-align.model1.npz.best-perplexity.npz","opus.spm32k-spm32k.vocab.yml","source.spm","target.spm","LICENSE","README.md")
    with zipfile.ZipFile(downloads/"opus-ko-en.zip") as archive:
        for name in required:
            with archive.open(name) as handle,(source/name).open("wb") as target:shutil.copyfileobj(handle,target)
    output.mkdir(parents=True,exist_ok=True)
    from ctranslate2.converters import MarianConverter
    MarianConverter(str(source/required[0]),[str(source/required[1])]).convert(str(output/"translation"),quantization="int8",force=True)
    # Conversion on Windows must produce the same canonical bytes as Linux.
    for path in (output/"translation").glob("*.json"):
        path.write_bytes(path.read_text(encoding="utf-8").replace("\r\n","\n").encode("utf-8"))
    for name in ("rec.onnx","dict.txt","LICENSE-PADDLEOCR.txt"):shutil.copy2(downloads/name,output/name)
    for src,dst in (("source.spm","source.spm"),("target.spm","target.spm"),("LICENSE","LICENSE-OPUS.txt"),("README.md","OPUS-SOURCE.md")):
        shutil.copy2(source/src,output/dst)
    verify(output,manifest["outputs"])
    (output/"manifest.json").write_text(json.dumps(manifest["outputs"],indent=2)+"\n")
    print("Verified chat models:",output)


def main():
    prepare_incoming()
    from prepare_compose_model import prepare
    prepare()


if __name__=="__main__":main()
