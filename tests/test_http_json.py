"""Real local HTTP/1.1 exchanges test reuse without contacting a price service."""
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import socket
import threading
import time
from concurrent.futures import CancelledError,ThreadPoolExecutor
import unittest
from unittest.mock import patch
import urllib.error

from price_lens.http_json import JsonTransport,RequestToken,request_scope


class JsonTransportTests(unittest.TestCase):
    def setUp(self):
        self.ports=[]
        ports=self.ports
        self.entered=threading.Event();self.release=threading.Event()
        entered,release=self.entered,self.release
        class Handler(BaseHTTPRequestHandler):
            protocol_version="HTTP/1.1"
            def handle(self):
                try:super().handle()
                except (ConnectionResetError,BrokenPipeError):pass
            def do_GET(self):
                ports.append(self.client_address[1])
                if self.path=="/slow":entered.set();release.wait(5)
                body=json.dumps({"code":"fm_not_tradeable"} if self.path=="/bad" else {"value":42}).encode()
                self.send_response(400 if self.path=="/bad" else 200)
                self.send_header("Content-Length",str(len(body)))
                self.send_header("Content-Type","application/json")
                if self.path=="/close":self.send_header("Connection","close")
                self.end_headers()
                if self.path=="/slow-body":self.wfile.flush();entered.set();release.wait(5)
                try:self.wfile.write(body);self.wfile.flush()
                except (OSError,ValueError):return
                if self.path=="/drop":
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection=True
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.transport=JsonTransport()
        def connection(host,port,timeout,context):
            self.assertTrue(context.check_hostname)
            return http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=timeout)
        self.patchers=[patch('price_lens.http_json.http.client.HTTPSConnection',side_effect=connection),
                       patch('price_lens.http_json.urllib.request.getproxies',return_value={})]
        for patcher in self.patchers:patcher.start()

    def tearDown(self):
        self.release.set()
        self.transport.close()
        for patcher in reversed(self.patchers):patcher.stop()
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def test_two_gets_reuse_one_connection_and_decode_json(self):
        self.assertEqual(self.transport.get('https://market.test/good'),{"value":42})
        self.assertEqual(self.transport.get('https://market.test/good'),{"value":42})
        self.assertEqual(len(self.ports),2)
        self.assertEqual(len(set(self.ports)),1)

    def test_coverage_error_preserves_http_error_body(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.transport.get('https://market.test/bad')
        self.assertEqual(error.exception.code,400)
        self.assertEqual(json.loads(error.exception.read()),{"code":"fm_not_tradeable"})
        error.exception.close()
        self.assertEqual(self.transport.get('https://market.test/good'),{"value":42})
        self.assertEqual(len(set(self.ports)),1)

    def test_closed_idle_connection_is_reconnected_once(self):
        self.transport.get('https://market.test/drop')
        self.assertEqual(self.transport.get('https://market.test/good'),{"value":42})
        self.assertEqual(len(set(self.ports)),2)

    def test_response_size_is_bounded(self):
        with patch('price_lens.http_json.MAX_RESPONSE',8):
            with self.assertRaisesRegex(ValueError,'size limit'):
                self.transport.get('https://market.test/good')

    def test_plain_http_or_embedded_credentials_are_rejected(self):
        for url in ('http://market.test/good','https://name:secret@market.test/good'):
            with self.assertRaises(ValueError):self.transport.get(url)

    def test_cancellation_interrupts_a_real_waiting_socket_without_retry(self):
        token=RequestToken()
        def fetch():
            try:
                with request_scope(token):return self.transport.get('https://market.test/slow')
            finally:self.transport.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(fetch)
            self.assertTrue(self.entered.wait(2))
            started=time.monotonic();token.cancel()
            with self.assertRaises(CancelledError):future.result(timeout=1)
            self.assertLess(time.monotonic()-started,.5)
            self.assertEqual(len(self.ports),1)

    def test_cancelled_scope_never_starts_a_request(self):
        token=RequestToken();token.cancel()
        with self.assertRaises(CancelledError):
            with request_scope(token):self.transport.get('https://market.test/good')
        self.assertEqual(self.ports,[])

    def test_scoped_reader_preserves_reuse_and_coverage_error_body(self):
        with request_scope(RequestToken()):
            self.assertEqual(self.transport.get('https://market.test/good'),{"value":42})
            with self.assertRaises(urllib.error.HTTPError) as error:self.transport.get('https://market.test/bad')
            self.assertEqual(json.loads(error.exception.read()),{"code":"fm_not_tradeable"})
            error.exception.close()
        self.assertEqual(self.transport.get('https://market.test/good'),{"value":42})
        self.assertEqual(len(set(self.ports)),1)

    def test_scoped_connection_close_response_keeps_body_readable(self):
        with request_scope(RequestToken()):
            self.assertEqual(self.transport.get('https://market.test/close'),{"value":42})

    def test_cancellation_also_interrupts_a_wait_for_the_response_body(self):
        token=RequestToken()
        def fetch():
            try:
                with request_scope(token):return self.transport.get('https://market.test/slow-body')
            finally:self.transport.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(fetch);self.assertTrue(self.entered.wait(2))
            started=time.monotonic();token.cancel()
            with self.assertRaises(CancelledError):future.result(timeout=1)
            self.assertLess(time.monotonic()-started,.5)


if __name__ == "__main__":unittest.main()
