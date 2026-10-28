"""Bounded HTTPS reuse for public JSON GETs; no extra dependencies or polling."""
from collections import OrderedDict
from concurrent.futures import CancelledError
from contextlib import contextmanager
from contextvars import ContextVar
import http.client
import io
import json
import select
import ssl
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import APP_NAME, __version__
from .tls import make_context

MAX_RESPONSE = 8*1024*1024
USER_AGENT = f"{APP_NAME}/{__version__} (Classic World screen-only companion)"
_request_token = ContextVar("price_request_token", default=None)


class RequestToken:
    """Interrupt only sockets belonging to an abandoned public HTTP request."""
    def __init__(self):
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.connections = set()

    def check(self):
        if self.cancelled.is_set():raise CancelledError()

    def attach(self, connection):
        with self.lock:
            self.check()
            self.connections.add(connection)

    def detach(self, connection):
        with self.lock:self.connections.discard(connection)

    def cancel(self):
        with self.lock:
            if self.cancelled.is_set():return
            self.cancelled.set()
            for connection in self.connections:
                stream = connection.sock
                if stream:
                    try:stream.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                connection.close()


@contextmanager
def request_scope(token):
    previous = _request_token.set(token)
    try:
        token.check()
        yield
        token.check()
    finally:_request_token.reset(previous)


class _ResponseReader(io.RawIOBase):
    """Poll only our HTTP socket, so cancellation works on Windows as well as Unix."""
    def __init__(self,sock,token):
        super().__init__()
        self.sock=sock
        self.token=token
        self.timeout=sock.gettimeout()
        self.deadline=time.monotonic()+12
        # Retain makefile's socket reference: HTTPConnection may close its own
        # reference before a Connection: close response body has been consumed.
        self.holder=sock.makefile("rb",buffering=0)
        sock.setblocking(False)

    def readable(self):return True

    def readinto(self,buffer):
        writing=False
        while True:
            self.token.check()
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise TimeoutError("Price response timed out")
            pending=getattr(self.sock,"pending",lambda:0)()
            if not pending:
                reads,writes,_=select.select([] if writing else [self.sock],[self.sock] if writing else [],[],min(.05,remaining))
                if not reads and not writes:continue
            self.token.check()
            try:return self.sock.recv_into(buffer)
            except ssl.SSLWantWriteError:writing=True
            except (ssl.SSLWantReadError,BlockingIOError):writing=False

    def close(self):
        if not self.closed:
            try:self.sock.settimeout(self.timeout)
            except OSError:pass
            self.holder.close()
        super().close()


class _ResponseSocket:
    def __init__(self,sock,token):self.sock,self.token=sock,token
    def makefile(self,mode):return io.BufferedReader(_ResponseReader(self.sock,self.token))


class _CancellableResponse(http.client.HTTPResponse):
    def __init__(self,sock,*args,**kwargs):
        super().__init__(_ResponseSocket(sock,_request_token.get()),*args,**kwargs)


class JsonTransport:
    def __init__(self):
        self.local = threading.local()
        self.context = None
        self.context_lock = threading.Lock()

    def close(self):
        for connection, _ in getattr(self.local,"connections",{}).values():
            connection.close()
        self.local.connections = OrderedDict()

    def get(self, url, redirects=0, *, decode=True):
        token = _request_token.get()
        if token:token.check()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("A public HTTPS URL is required")
        headers = {"User-Agent":USER_AGENT,"Accept":"application/json"}
        if self.context is None:
            with self.context_lock:
                if self.context is None:self.context = make_context()
        # Keep the operating system/user proxy behavior of urllib intact.
        proxies = urllib.request.getproxies()
        if (proxies.get("https") or proxies.get("all")) and not urllib.request.proxy_bypass(parsed.hostname):
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=12,context=self.context) as response:
                body = response.read(MAX_RESPONSE+1)
            if len(body)>MAX_RESPONSE:raise ValueError("Data response exceeds size limit")
            if token:token.check()
            return json.loads(body) if decode else body
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
                if token:token.attach(connection)
                connection.request("GET",path,headers=headers)
                if token:token.check()
                connection.response_class = _CancellableResponse if token else http.client.HTTPResponse
                response = connection.getresponse()
                body = response.read(MAX_RESPONSE+1)
                if token:token.check()
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
                if token:token.check()
                if reused and attempt==0:continue
                raise
            except Exception:
                connection.close()
                if token:token.check()
                raise
            finally:
                if token:token.detach(connection)
            if status in (301,302,303,307,308) and location:
                if redirects >= 3:raise ValueError("Too many HTTPS redirects")
                return self.get(urllib.parse.urljoin(url,location),redirects+1,decode=decode)
            if status >= 400:
                raise urllib.error.HTTPError(url,status,reason,response_headers,io.BytesIO(body))
            return json.loads(body) if decode else body


_transport = JsonTransport()


def get_json(url):
    return _transport.get(url)


def get_bytes(url):
    return _transport.get(url,decode=False)
