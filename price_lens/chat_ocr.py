"""Local speech-bubble OCR. Imported only inside the bounded chat worker."""
from collections import OrderedDict
import hashlib
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


def pixels(image):
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    return np.frombuffer(bytes(image.constBits()), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()*3].reshape(image.height(),image.width(),3)


def components(mask):
    parents, boxes, areas, previous = [], [], [], []
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    for y,row in enumerate(mask):
        edges=np.flatnonzero(np.diff(np.r_[False,row,False]));runs=[];j=0
        for x,right in zip(edges[::2],edges[1::2]):
            if right-x<2:continue
            while j<len(previous) and previous[j][1]<=x:j+=1
            ids=[];k=j
            while k<len(previous) and previous[k][0]<right:
                ids.append(find(previous[k][2]));k+=1
            if not ids:
                i=len(parents);parents.append(i);boxes.append([int(x),y,int(right),y+1]);areas.append(0)
            else:
                i=ids[0]
                for other in ids[1:]:
                    other=find(other);i=find(i)
                    if i!=other:
                        parents[other]=i;b=boxes[other];c=boxes[i]
                        boxes[i]=[min(b[0],c[0]),min(b[1],c[1]),max(b[2],c[2]),max(b[3],c[3])];areas[i]+=areas[other]
            b=boxes[i];b[:]=[min(b[0],int(x)),min(b[1],y),max(b[2],int(right)),y+1]
            areas[i]+=right-x;runs.append((x,right,i))
        previous=runs
    return [(box,areas[i]) for i,box in enumerate(boxes) if find(i)==i]


def bubbles(image):
    """Connected runs of Classic's neutral bubble fill; no full-scene OCR.

    A one-level tolerance permits normal capture rounding. Exclude large UI
    panels and scenery by component size, fill ratio and subsequent text checks.
    """
    a = pixels(image)
    mask = (a[:,:,0]>=237)&(a[:,:,0]<=239)&(a[:,:,1]==a[:,:,0])&(a[:,:,2]==a[:,:,0])
    result=[]
    scale=max(1,image.width()/1366)
    for (x,y,right,bottom),area in components(mask):
        w,h=right-x,bottom-y
        if 55<=w<=420*scale and 22<=h<=360*scale and area/(w*h)>.60:
            result.append([x,y,w,h])
    return result[:32]


def text_regions(image,exclude=()):
    """Contrast/geometry candidates throughout the game, including chat panels.

    Existing Korean OCR confirms language and confidence; no detector model or
    whole-desktop read is introduced. Our own overlay rectangles are excluded.
    """
    rgb=pixels(image);a=rgb.mean(2).astype('int16')
    neighbours=[np.roll(a,d,axis=axis) for d in (-3,3) for axis in (0,1)]
    low=np.minimum.reduce(neighbours);high=np.maximum.reduce(neighbours)
    neutral=rgb.max(2).astype('int16')-rgb.min(2)<45
    masks=[neutral&(rgb.min(2)>185)&(a-low>50),neutral&(a<110)&(high-a>75)]
    result=[]
    for ink in masks:
        ink[:4]=False;ink[-4:]=False;ink[:,:4]=False;ink[:,-4:]=False
        for x,y,w,h in exclude:
            ink[max(0,y):min(image.height(),y+h),max(0,x):min(image.width(),x+w)]=False
        expanded=ink.copy()
        for delta in range(1,4):
            expanded[:,delta:]|=ink[:,:-delta];expanded[:,:-delta]|=ink[:,delta:]
        # Vertical dilation joins text to nearby sprites and panel frames.
        # Keep the native baselines so crowded banners remain separate lines.
        for (x,y,right,bottom),_ in components(expanded):
            w,h=right-x,bottom-y
            if 24<=w<=1000 and 7<=h<=44 and w/h>=1.7:
                density=ink[y:bottom,x:right].mean()
                if .07<=density<=.7:result.append([max(0,x-1),max(0,y-1),min(image.width()-x+1,w+2),min(image.height()-y+1,h+2)])
    merged=[]
    for box in sorted(result,key=lambda b:(round((b[1]+b[3]/2)/4),b[0])):
        x,y,w,h=box
        if merged:
            old=merged[-1];ox,oy,ow,oh=old
            if abs((y+h/2)-(oy+oh/2))<=3 and -6<=x-(ox+ow)<=12 and x+w-ox<=1000:
                old[:]=[ox,min(y,oy),max(x+w,ox+ow)-ox,max(y+h,oy+oh)-min(y,oy)];continue
        merged.append(box)
    return sorted(merged,key=lambda b:(not (b[2]>=160 and b[3]<=30),b[1],b[0]))[:96]


def lines(image):
    a=pixels(image);dark=a.min(2)<160;bands=[];start=None
    for y,on in enumerate(np.r_[dark.sum(1)>=2,False]):
        if on and start is None:start=y
        if not on and start is not None:
            if 6<=y-start<=40:
                ink=np.flatnonzero(dark[start:y].any(0))
                if len(ink)>=3 and ink[-1]-ink[0]>=7:
                    left,right=max(0,int(ink[0])-1),min(image.width(),int(ink[-1])+2)
                    bands.append((image.copy(left,max(0,start-1),right-left,min(image.height(),y+1)-max(0,start-1)),y-start))
            start=None
    return bands[:24]


class Recognizer:
    def __init__(self, root):
        import onnxruntime as ort
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        for kind in ("intra_op", "inter_op"):
            options.add_session_config_entry("session."+kind+".allow_spinning","0")
        self.session=ort.InferenceSession(str(Path(root)/"rec.onnx"),sess_options=options,providers=["CPUExecutionProvider"])
        self.chars=[""]+(Path(root)/"dict.txt").read_text(encoding="utf-8").splitlines()+[" "]
        shape=self.session.get_inputs()[0].shape
        self.height=shape[2]
        if self.height!=48 or self.session.get_outputs()[0].shape[-1]!=len(self.chars):
            raise ValueError("Unexpected Korean OCR model or dictionary")
        self.cache=OrderedDict()

    def read(self, image):
        key=(image.width(),image.height(),hashlib.blake2s(pixels(image).tobytes(),digest_size=16).digest())
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        width=min(1920,max(16,round(image.width()*self.height/image.height())))
        image=image.scaled(width,self.height,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        data=(pixels(image)[:,:,::-1].astype("float32")/127.5-1).transpose(2,0,1)[None]
        probability=self.session.run(None,{self.session.get_inputs()[0].name:data})[0][0]
        best=probability.argmax(1);text=[];confidence=[];last=0
        for index,char in enumerate(best):
            if char and char!=last:text.append(self.chars[char]);confidence.append(float(probability[index,char]))
            last=char
        result=("".join(text),sum(confidence)/len(confidence) if confidence else 0)
        self.cache[key]=result
        while len(self.cache)>256:self.cache.popitem(last=False)
        return result
