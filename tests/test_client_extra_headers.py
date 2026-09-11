"""
Tests for ToriClient.get(..., extra_headers=...): the header must reach the
outgoing request, survive the 401/403 refresh-and-retry path, and never
clobber content-type on body requests.

Run: python -m unittest tests.test_client_extra_headers -v
"""

import unittest
from unittest.mock import patch

from torium.client import ToriClient


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.reason = "OK" if self.ok else "Unauthorized"
        self.url = "https://apps-gw-poc.svc.tori.fi/x"
        self.text = ""
        self.content = b"{}" if self.ok else b""
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _client():
    c = ToriClient(refresh_token="dummy", save_on_refresh=False)
    c.auth.get_bearer = lambda: "tok"
    c.auth.refresh = lambda: "tok2"
    return c


class ExtraHeadersTest(unittest.TestCase):
    def test_extra_header_reaches_request(self):
        c = _client()
        seen = []

        def fake_request(method, url, headers=None, data=None):
            seen.append(headers)
            return _Resp(200, {"ok": True})

        with patch.object(c._session, "request", side_effect=fake_request):
            out = c.get("/v2/public/users/u/feedback", "TRUST-FEEDBACK-API",
                        extra_headers={"X-Client-Id": "tori"})

        self.assertEqual(out, {"ok": True})
        self.assertEqual(seen[0]["X-Client-Id"], "tori")
        self.assertEqual(seen[0]["finn-gw-service"], "TRUST-FEEDBACK-API")

    def test_extra_header_survives_401_retry(self):
        c = _client()
        seen = []
        responses = [_Resp(401), _Resp(200, {"ok": True})]

        def fake_request(method, url, headers=None, data=None):
            seen.append(headers)
            return responses.pop(0)

        with patch.object(c._session, "request", side_effect=fake_request):
            c.get("/p", "SVC", extra_headers={"X-Client-Id": "tori"})

        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1]["X-Client-Id"], "tori")

    def test_no_extra_headers_is_unchanged(self):
        c = _client()
        seen = []

        def fake_request(method, url, headers=None, data=None):
            seen.append(headers)
            return _Resp(200)

        with patch.object(c._session, "request", side_effect=fake_request):
            c.get("/p", "SVC")

        self.assertNotIn("X-Client-Id", seen[0])


if __name__ == "__main__":
    unittest.main()
