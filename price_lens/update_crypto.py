"""Verify release signatures with OpenSSL, already used by the runtime's TLS.

Only a public Ed25519 key is shipped. Signing keys never enter an app package.
No third-party Python crypto dependency or handwritten signature algorithm.
"""
import ctypes as C
import ctypes.util
from functools import lru_cache
from pathlib import Path
import sys


@lru_cache(maxsize=1)
def crypto():
    name=str(Path(sys.executable).parent/'libcrypto-3.dll') if sys.platform=='win32' else C.util.find_library('crypto')
    if not name:raise ValueError('OpenSSL is unavailable for update verification')
    library=C.CDLL(name)
    for name,args,result in (
        ('EVP_PKEY_new_raw_public_key_ex',[C.c_void_p,C.c_char_p,C.c_char_p,C.c_void_p,C.c_size_t],C.c_void_p),
        ('EVP_PKEY_free',[C.c_void_p],None),('EVP_MD_CTX_new',[],C.c_void_p),('EVP_MD_CTX_free',[C.c_void_p],None),
        ('EVP_DigestVerifyInit',[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],C.c_int),
        ('EVP_DigestVerify',[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t],C.c_int)):
        function=getattr(library,name);function.argtypes=args;function.restype=result
    return library


def verify(public_key,signature,message):
    if len(public_key)!=32 or len(signature)!=64:return False
    lib=crypto();key_bytes=C.create_string_buffer(public_key);sig=C.create_string_buffer(signature);data=C.create_string_buffer(message)
    key=lib.EVP_PKEY_new_raw_public_key_ex(None,b'ED25519',None,key_bytes,len(public_key))
    context=lib.EVP_MD_CTX_new()
    if not key or not context:
        if key:lib.EVP_PKEY_free(key)
        if context:lib.EVP_MD_CTX_free(context)
        raise ValueError('Cannot initialize update signature verification')
    try:
        return lib.EVP_DigestVerifyInit(context,None,None,None,key)==1 and lib.EVP_DigestVerify(context,sig,len(signature),data,len(message))==1
    finally:lib.EVP_MD_CTX_free(context);lib.EVP_PKEY_free(key)
