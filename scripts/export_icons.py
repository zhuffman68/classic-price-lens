"""Export the approved 32px artwork directly at desktop and fractional-DPI sizes."""
import hashlib
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer,QByteArray,QIODevice,Qt
from PySide6.QtGui import QImage

ROOT=Path(__file__).resolve().parents[1]
SIZES=(16,20,22,24,28,32,40,48,56,64,96,128,256)


def png_bytes(image):
    data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer,'PNG')
    return bytes(data)


def main():
    master=ROOT/'artwork/lupin-icon-master.png';digest=hashlib.sha256(master.read_bytes()).hexdigest()
    image=QImage(str(master)).convertToFormat(QImage.Format.Format_RGBA8888)
    assert image.width()==image.height()==32
    resources=ROOT/'price_lens/resources';frames=[]
    for size in SIZES:
        # Integer enlargements keep exact source pixels. Other sizes are filtered
        # once from the master, rather than shrinking a previously enlarged PNG.
        mode=Qt.TransformationMode.FastTransformation if size%32==0 else Qt.TransformationMode.SmoothTransformation
        frame=image.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,mode)
        name='icon.png' if size==256 else f'icon-{size}.png'
        (resources/name).write_bytes(png_bytes(frame));frames.append((size,png_bytes(frame)))
    rects=[]
    for y in range(32):
        x=0
        while x<32:
            color=image.pixelColor(x,y);right=x+1
            while right<32 and image.pixelColor(right,y)==color:right+=1
            if color.alpha():
                opacity=f' opacity="{color.alpha()/255:.6f}"' if color.alpha()<255 else ''
                rects.append(f'<rect x="{x}" y="{y}" width="{right-x}" height="1" fill="{color.name()}"{opacity}/>')
            x=right
    (resources/'icon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'+''.join(rects)+'</svg>\n')
    # PNG-backed ICO frames are supported by the supported Windows 10+ versions.
    selected=[(size,data) for size,data in frames if size!=22 and size!=28 and size!=56]
    offset=6+16*len(selected);entries=[]
    for size,data in selected:
        entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset));offset+=len(data)
    (ROOT/'packaging/icon.ico').write_bytes(struct.pack('<HHH',0,1,len(selected))+b''.join(entries)+b''.join(data for _,data in selected))
    assert hashlib.sha256(master.read_bytes()).hexdigest()==digest
    print('Exported',len(SIZES),'native sizes and scalable pixel artwork; approved master unchanged:',digest)


if __name__=='__main__':main()
