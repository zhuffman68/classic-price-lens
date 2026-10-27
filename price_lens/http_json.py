"""Bounded HTTPS reuse for public JSON GETs; no extra dependencies or polling."""
from collections import OrderedDict
import http.client
import io
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import APP_NAME, __version__

MAX_RESPONSE = 8*1024*1024
USER_AGENT = f"{APP_NAME}/{__version__} (Classic World screen-only companion)"


class JsonTransport:
    def __init__(self):
        self.local = threading.local()
        self.context = None
        self.context_lock = threading.Lock()

    def close(self):
        for connection, _ in getattr(self.local,"connections",{}).values():
            connection.close()
        self.local.connections = OrderedDict()

    def get(self, url, redirects=0):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("A public HTTPS URL is required")
        headers = {"User-Agent":USER_AGENT,"Accept":"application/json"}
        # Keep the operating system/user proxy behavior of urllib intact.
        proxies = urllib.request.getproxies()
        if (proxies.get("https") or proxies.get("all")) and not urllib.request.proxy_bypass(parsed.hostname):
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=12) as response:
                body = response.read(MAX_RESPONSE+1)
            if len(body)>MAX_RESPONSE:raise ValueError("Data response exceeds size limit")
            return json.loads(body)
        if self.context is None:
            with self.context_lock:
                if self.context is None:self.context = ssl.create_default_context()
        connections = getattr(self.local,"connections",None)
        if connections is None:
            connections = self.local.connections = OrderedDict()
        endpoint = (parsed.hostname,parsed.port or 443)
        path = urllib.parse.urlunsplit(("","",parsed.path or "/",parsed.query,""))
        for attempt in range(2):
            previous = connections.pop(endpoint,None)
            reused = previous is not None and time.monotonic()-previous[1] < 30
            if previous and not reused:previous[0].close()
            connection = previous[0] if reused else http.client.HTTPSConnection(*endpoint,timeout=12,context=self.context)
            try:
                connection.request("GET",path,headers=headers)
                response = connection.getresponse()
                body = response.read(MAX_RESPONSE+1)
                if len(body)>MAX_RESPONSE:raise ValueError("Data response exceeds size limit")
                status, reason, response_headers = response.status,response.reason,response.headers
                location = response.getheader("Location")
                closes = response.will_close
                response.close()
                if closes:connection.close()
                else:
                    connections[endpoint] = (connection,time.monotonic())
                    while len(connections)>4:connections.popitem(last=False)[1][0].close()
            except (http.client.RemoteDisconnected, http.client.CannotSendRequest,
                    http.client.ResponseNotReady, BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, ssl.SSLEOFError):
                connection.close()
                if reused and attempt==0:continue
                raise
            except Exception:
                connection.close()
                raise
            if status in (301,302,303,307,308) and location:
                if redirects >= 3:raise ValueError("Too many HTTPS redirects")
                return self.get(urllib.parse.urljoin(url,location),redirects+1)
            if status >= 400:
                raise urllib.error.HTTPError(url,status,reason,response_headers,io.BytesIO(body))
            return json.loads(body)


_transport = JsonTransport()


def get_json(url):
    return _transport.get(url)
