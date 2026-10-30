"""Streaming release deltas with an 8 MiB dictionary per chunk.

Reconstruct the exact signed native installer/package, then let its package
manager install it. Models and managed install files are never patched in place.
"""
import struct

MAGIC=b'LUPIN-D1\n'
CHUNK=8*1024*1024


def make(base,target,out):
    from compression import zstd
    out.write(MAGIC)
    while block:=target.read(CHUNK):
        previous=base.read(CHUNK)
        dictionary=zstd.ZstdDict(previous,is_raw=True).as_prefix if previous else None
        packed=zstd.compress(block,options={zstd.CompressionParameter.compression_level:3,
            zstd.CompressionParameter.window_log:25,zstd.CompressionParameter.enable_long_distance_matching:1},zstd_dict=dictionary)
        out.write(struct.pack('!II',len(block),len(packed)));out.write(packed)


def restore(base,patch,out,expected,cancel=None):
    from compression import zstd
    if patch.read(len(MAGIC))!=MAGIC:raise ValueError('Unknown update patch format')
    total=0
    while header:=patch.read(8):
        if cancel:cancel()
        if len(header)!=8:raise ValueError('Truncated update patch')
        length,packed=struct.unpack('!II',header)
        if not 0<length<=CHUNK or not 0<packed<=CHUNK+1024*1024 or total+length>expected:raise ValueError('Oversized update patch chunk')
        encoded=patch.read(packed)
        if len(encoded)!=packed:raise ValueError('Truncated update patch chunk')
        previous=base.read(CHUNK)
        dictionary=zstd.ZstdDict(previous,is_raw=True).as_prefix if previous else None
        decoder=zstd.ZstdDecompressor(zstd_dict=dictionary,options={zstd.DecompressionParameter.window_log_max:25})
        try:decoded=decoder.decompress(encoded,max_length=length+1)
        except zstd.ZstdError as error:raise ValueError('Invalid update patch frame') from error
        if len(decoded)!=length or not decoder.eof or decoder.unused_data:raise ValueError('Invalid update patch chunk')
        out.write(decoded);total+=len(decoded)
    if total!=expected:raise ValueError('Incomplete update patch')
