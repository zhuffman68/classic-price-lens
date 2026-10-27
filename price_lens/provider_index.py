"""A public ID index extends already-verified mappings; it never identifies a new item."""
import hashlib
import json
import re
import time

from .http_json import get_bytes

INDEX_URL="https://meso.watch/js/niadb.js"


def load_index(cache):
    saved=cache.get("identity-index","mesowatch",86400)
    if saved:return saved
    body=get_bytes(INDEX_URL)
    if len(body)>256*1024:raise ValueError("Provider ID index exceeds its size limit")
    # Parse only the published JSON assignment. Never evaluate downloaded code.
    match=re.search(rb"(?:^|\n)window\.NiaDBIds\s*=\s*(\{[^;]+\});?\s*$",body)
    if not match:raise ValueError("Provider ID index format changed")
    document=json.loads(match[1])
    entries={str(int(k.split(":")[1])):v for k,v in document.items()
             if re.fullmatch(r"basil:\d{8}",k) and type(v) is int and v>0}
    if not 100<=len(entries)<=10000:raise ValueError("Provider ID index has an unexpected number of items")
    canonical=json.dumps(entries,sort_keys=True,separators=(",",":")).encode()
    result={"entries":entries,"fingerprint":hashlib.sha256(canonical).hexdigest(),"fetched_at":time.time()}
    cache.put("identity-index","mesowatch",result)
    return result
