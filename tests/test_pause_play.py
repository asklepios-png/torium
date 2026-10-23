"""
Regression tests for pause()/play() (hide/un-hide a listing from search).

Verifies the native gateway call shape — PUT /ads/pause/{id} and
PUT /ads/play/{id}, both on the AD-ACTION service, no body — matches what
listings.py actually sends. The exact paths were confirmed 2026-10-23 from
the Tori web app's own per-ad action list (GET /my-items/api/summary returns
each listing's available actions, including name/method/url for PAUSE and
PLAY), not yet live-tested against this native signed endpoint directly.

Run: python -m unittest tests.test_pause_play -v
"""

import unittest

from torium.listings import ListingsAPI


class FakeClient:
    def __init__(self):
        self.calls: list[tuple] = []

    def put(self, path, service, json_body=None):
        self.calls.append(("put", path, service, json_body))


class PausePlayTest(unittest.TestCase):
    def test_pause_calls_correct_endpoint(self):
        client = FakeClient()
        api = ListingsAPI(client)
        api.pause(12265237)
        self.assertEqual(client.calls, [("put", "/ads/pause/12265237", "AD-ACTION", None)])

    def test_play_calls_correct_endpoint(self):
        client = FakeClient()
        api = ListingsAPI(client)
        api.play(12265237)
        self.assertEqual(client.calls, [("put", "/ads/play/12265237", "AD-ACTION", None)])


if __name__ == "__main__":
    unittest.main()
