"""Real local HTTP/1.1 exchanges test reuse without contacting a price service."""
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import socket
import threading
import unittest
from unittest.mock import patch
import urllib.error

from price_lens.http_json import JsonTransport


class JsonTransportTests(unittest.TestCase):
    def setUp(self):
        self.ports=[]
        ports=self.ports
        class Handler(BaseHTTPRequestHandler):
            protocol_version="HTTP/1.1"
            def do_GET(self):
                ports.append(self.client_address[1])
                body=json.dumps({"code":"fm_not_tradeable"} if self.path=="/bad" else {"value":42}).encode()
                self.send_response(400 if self.path=="/bad" else 200)
                self.send_header("Content-Length",str(len(body)))
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(body);self.wfile.flush()
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


if __name__ == "__main__":unittest.main()
