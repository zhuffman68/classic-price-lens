"""Certificate validation remains required for normal and proxied HTTP."""
import ssl
import types
import unittest
import urllib.error
from unittest.mock import Mock, patch

from price_lens.tls import make_context, catalog_error_text, retryable_catalog_error
from price_lens.http_json import JsonTransport


class TlsTests(unittest.TestCase):
    def test_linux_uses_normal_verified_openssl_context(self):
        with patch('price_lens.tls.sys.platform','linux'):
            context=make_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)

    def test_windows_uses_explicit_native_validation_without_global_ssl_injection(self):
        factory=Mock(return_value=object())
        library=types.SimpleNamespace(SSLContext=factory)
        with patch('price_lens.tls.sys.platform','win32'), patch.dict('sys.modules',{'truststore':library}):
            context=make_context()
        factory.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        self.assertIs(context,factory.return_value)

    def test_proxy_path_receives_the_same_verified_context(self):
        context=ssl.create_default_context()
        response=Mock();response.read.return_value=b'{"value": 12}'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        transport=JsonTransport()
        with patch('price_lens.http_json.make_context',return_value=context), \
             patch('price_lens.http_json.urllib.request.getproxies',return_value={'https':'http://proxy.test:8080'}), \
             patch('price_lens.http_json.urllib.request.proxy_bypass',return_value=False), \
             patch('price_lens.http_json.urllib.request.urlopen',return_value=response) as fetch:
            self.assertEqual(transport.get('https://items.test/catalog'),{'value':12})
        self.assertIs(fetch.call_args.kwargs['context'],context)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)

    def test_certificate_failure_has_a_specific_user_message(self):
        self.assertIn('secure item connection',catalog_error_text('[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate'))
        self.assertIn('connection',catalog_error_text('connection refused'))

    def test_only_transient_catalog_failures_are_eligible_for_one_retry(self):
        self.assertTrue(retryable_catalog_error(TimeoutError()))
        self.assertTrue(retryable_catalog_error(ssl.SSLCertVerificationError('missing issuer')))
        self.assertFalse(retryable_catalog_error(ValueError('catalog format changed')))
        for status in (400,403,404,429):
            error=urllib.error.HTTPError('https://items.test',status,'',{},None)
            try:self.assertFalse(retryable_catalog_error(error))
            finally:error.close()
        error=urllib.error.HTTPError('https://items.test',503,'',{},None)
        try:self.assertTrue(retryable_catalog_error(error))
        finally:error.close()


if __name__ == '__main__':unittest.main()
