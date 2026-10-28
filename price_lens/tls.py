"""Use Windows certificate-chain validation, retaining normal HTTPS checks."""
import ssl
import sys
import urllib.error


def make_context():
    if sys.platform == "win32":
        # CryptoAPI can retrieve missing issuers on a fresh Windows install.
        # An explicit context keeps this local to our HTTP transport.
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()


def retryable_catalog_error(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (500, 502, 503, 504)
    return isinstance(error, (OSError, urllib.error.URLError))


def catalog_error_text(message):
    text = message.casefold()
    if "certificate" in text and any(word in text for word in ("verif", "issuer", "chain")):
        return "The secure item connection could not be verified. Check the system date, then retry."
    return "Item names are unavailable. Check your connection and retry."
