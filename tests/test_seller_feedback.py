"""
Tests for feedback: buyer/seller reviews via the TRUST-FEEDBACK-API endpoint.

The endpoint is GET /v2/public/users/{owner_urn}/feedback?pageSize=&page=,
served by the TRUST-FEEDBACK-API gateway service. Requires an X-Client-Id
header with any non-empty value (same quirk as TRUST-PROFILE-API) or the
gateway 400s. owner_urn is the "sdrn:aurora.tori.fi:user:{id}" form from
owner(ad_id)["owner_urn"]. Response: {"paging": {...}, "feedbacks": [...]}.
Captured live from the Android app 2026-09-11 (owner 868071115, 8 reviews,
single page).

Run: python -m unittest tests.test_seller_feedback -v
"""

import unittest
import urllib.parse

from torium.listings import ListingsAPI

_URN = "sdrn:aurora.tori.fi:user:868071115"


def _entry(feedback_id: int, name: str, text) -> dict:
    return {
        "role": "BUYER",
        "segmentExternalId": "tori-recommerce",
        "feedback": {
            "feedbackId": feedback_id,
            "textReview": text,
            "score": 1.0,
            "givenAt": "2026-09-06T15:56:33.393925Z",
            "reply": None,
        },
        "transactional": False,
        "name": name,
        "avatarUrl": "https://img.tori.net/dynamic/220x220c/profile_placeholders/default",
        "localProfileId": "1161875868",
        "verified": True,
        "overallScore": 0.98,
        "numberOfReceivedFeedbacks": 14,
    }


def _page_of(path: str) -> int:
    query = urllib.parse.urlparse(path).query
    return int(urllib.parse.parse_qs(query).get("page", ["0"])[0])


class PagedFakeClient:
    """Serves /v2/public/users/{urn}/feedback pages and records each call."""

    def __init__(self, pages):
        # pages: list per 0-indexed page of (entries, page_count)
        self.pages = pages
        self.calls: list[tuple] = []

    def get(self, path, service, extra_headers=None):
        self.calls.append((path, service, extra_headers))
        page = _page_of(path)
        entries, page_count = self.pages[page]
        return {
            "paging": {"current": page, "pageCount": page_count, "pageSize": 50, "totalCount": len(entries)},
            "feedbacks": entries,
        }


class SellerFeedbackTest(unittest.TestCase):
    def test_single_page_returns_all_entries_and_hits_feedback_endpoint(self):
        client = PagedFakeClient([([_entry(1, "Jorma", "Hyvä kauppa"), _entry(2, "Kalle", None)], 1)])
        api = ListingsAPI(client)

        entries = api.feedback(_URN)

        self.assertEqual([e["feedback"]["feedbackId"] for e in entries], [1, 2])
        self.assertEqual(len(client.calls), 1)
        path, service, extra_headers = client.calls[0]
        self.assertEqual(service, "TRUST-FEEDBACK-API")
        self.assertIn(f"/v2/public/users/{_URN}/feedback", path)
        self.assertIn("pageSize=50", path)
        self.assertEqual(extra_headers, {"X-Client-Id": "tori"})

    def test_paginates_until_page_count_reached(self):
        client = PagedFakeClient([
            ([_entry(1, "A", "x")], 2),
            ([_entry(2, "B", "y")], 2),
        ])
        api = ListingsAPI(client)

        entries = api.feedback(_URN)

        self.assertEqual([e["feedback"]["feedbackId"] for e in entries], [1, 2])
        self.assertEqual(len(client.calls), 2)
        pages = [_page_of(p) for p, _, _ in client.calls]
        self.assertEqual(pages, [0, 1])

    def test_max_results_caps_and_stops_early(self):
        client = PagedFakeClient([
            ([_entry(1, "A", "x"), _entry(2, "B", "y")], 3),  # more pages exist
        ])
        api = ListingsAPI(client)

        entries = api.feedback(_URN, max_results=1)

        self.assertEqual(len(entries), 1)
        self.assertEqual(len(client.calls), 1)  # did not fetch further pages

    def test_no_feedback_returns_empty_list(self):
        client = PagedFakeClient([([], 1)])
        api = ListingsAPI(client)

        self.assertEqual(api.feedback(_URN), [])

    def test_malformed_paging_terminates_after_one_call(self):
        for page_count in (None, "1", 0, -1):
            with self.subTest(page_count=page_count):
                client = PagedFakeClient([([_entry(1, "A", "x")], page_count)])
                api = ListingsAPI(client)

                entries = api.feedback(_URN)

                self.assertEqual(len(entries), 1)
                self.assertEqual(len(client.calls), 1)

    def test_empty_later_page_stops_without_error(self):
        client = PagedFakeClient([
            ([_entry(1, "A", "x")], 3),
            ([], 3),  # server claims 3 pages but page 1 is empty
        ])
        api = ListingsAPI(client)

        entries = api.feedback(_URN)

        self.assertEqual(len(entries), 1)
        self.assertEqual(len(client.calls), 2)


class _FakeListings:
    def __init__(self, owner, entries):
        self._owner = owner
        self._entries = entries

    def owner(self, ad_id):
        return self._owner

    def feedback(self, owner_urn):
        return self._entries


class _FakeClient:
    def __init__(self, owner, entries):
        self.listings = _FakeListings(owner, entries)


class GetSellerFeedbackToolTest(unittest.TestCase):
    """The MCP tool's compaction is its only real logic — pin its output shape."""

    def _run(self, owner, entries):
        import json
        from unittest.mock import patch
        from torium import mcp_server

        with patch.object(mcp_server, "_get_client", return_value=_FakeClient(owner, entries)):
            return json.loads(mcp_server.get_seller_feedback(46592793))

    def test_compacts_entries(self):
        out = self._run(
            {"owner_id": 868071115, "owner_urn": _URN},
            [_entry(15586657, "Jorma", "Hyvä kauppa")],
        )

        self.assertEqual(out["owner_id"], 868071115)
        self.assertEqual(out["count"], 1)
        row = out["feedback"][0]
        self.assertEqual(row["reviewer_name"], "Jorma")
        self.assertEqual(row["role"], "BUYER")
        self.assertEqual(row["text"], "Hyvä kauppa")
        self.assertEqual(row["score"], 1.0)
        self.assertEqual(row["reviewer_review_count"], 14)

    def test_null_feedback_block_does_not_crash(self):
        entry = _entry(1, "A", None)
        entry["feedback"] = None

        out = self._run({"owner_id": 1, "owner_urn": _URN}, [entry])

        self.assertEqual(out["count"], 1)
        self.assertIsNone(out["feedback"][0]["text"])
        self.assertIsNone(out["feedback"][0]["score"])

    def test_missing_owner_urn_returns_error_json(self):
        out = self._run({"owner_id": None, "owner_urn": ""}, [])

        self.assertIn("error", out)
        self.assertEqual(out["ad_id"], 46592793)


if __name__ == "__main__":
    unittest.main()
