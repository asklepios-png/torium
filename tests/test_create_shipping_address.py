"""
Regression test: create()'s ToriDiili shipping origin (shippingInfo.city/
postalCode) must always be the seller's home address, never the item's own
postal_code — those are different things. Bug: both were previously filled
from the single postal_code argument, so an item listed from a different
town than the seller's home silently sent the wrong shipping origin.

Run: python -m unittest tests.test_create_shipping_address -v
"""

import unittest
from unittest.mock import patch

from torium.listings import ListingsAPI

# HOME_CITY/HOME_POSTAL_CODE are read from the environment (never hardcoded —
# this is a public repo), so tests patch them to fixed, clearly-fake values.
_TEST_HOME_CITY = "Testikaupunki"
_TEST_HOME_POSTAL_CODE = "00000"


class FakeClient:
    """Records calls; simulates the adinput + delivery endpoints create() drives."""

    def __init__(self):
        self.calls: list[tuple] = []

    def adinput_post(self, path, service="", body=b"", content_type=None):
        self.calls.append(("adinput_post", path))
        if "withModel" in path:
            return {}, 'W/"1"', "https://x/adinput/ad/recommerce/999/"
        return {"order-id": 1, "is-completed": True}, "", ""

    def adinput_get(self, path):
        self.calls.append(("adinput_get", path))
        return {}, 'W/"2"'

    def adinput_put(self, path, json_body, etag):
        self.calls.append(("adinput_put", path, json_body))
        return {"etag": 'W/"2"'}

    def post(self, path, service, json_body=None):
        self.calls.append(("post", path, service, json_body))
        return {}

    def delivery_calls(self):
        return [c for c in self.calls if c[0] == "post" and "/delivery" in c[1]]


class CreateShippingAddressTest(unittest.TestCase):
    @patch("torium.listings.HOME_CITY", _TEST_HOME_CITY)
    @patch("torium.listings.HOME_POSTAL_CODE", _TEST_HOME_POSTAL_CODE)
    def test_shipping_defaults_to_home_address_regardless_of_item_postal_code(self):
        """Item is in a different town (96100) than home (HOME_POSTAL_CODE)."""
        client = FakeClient()
        api = ListingsAPI(client)

        api.create(
            "Title", "Desc", 10, "193", "96100",
            shipping=True,
        )

        [delivery_call] = client.delivery_calls()
        body = delivery_call[3]
        self.assertEqual(body["shippingInfo"]["city"], _TEST_HOME_CITY)
        self.assertEqual(body["shippingInfo"]["postalCode"], _TEST_HOME_POSTAL_CODE)

    def test_shipping_without_home_env_configured_raises(self):
        """No TORI_HOME_CITY/TORI_HOME_POSTAL_CODE set and no explicit override."""
        client = FakeClient()
        api = ListingsAPI(client)

        with patch("torium.listings.HOME_CITY", None), \
             patch("torium.listings.HOME_POSTAL_CODE", None):
            with self.assertRaises(ValueError):
                api.create("Title", "Desc", 10, "193", "96100", shipping=True)

    def test_explicit_shipping_address_overrides_home_default(self):
        client = FakeClient()
        api = ListingsAPI(client)

        api.create(
            "Title", "Desc", 10, "193", "96100",
            shipping=True, city="Turku", shipping_postal_code="20100",
        )

        [delivery_call] = client.delivery_calls()
        body = delivery_call[3]
        self.assertEqual(body["shippingInfo"]["city"], "Turku")
        self.assertEqual(body["shippingInfo"]["postalCode"], "20100")

    @patch("torium.listings.HOME_CITY", _TEST_HOME_CITY)
    @patch("torium.listings.HOME_POSTAL_CODE", _TEST_HOME_POSTAL_CODE)
    def test_item_location_unaffected_by_home_address(self):
        """The listing's own location must still use the item's postal_code."""
        client = FakeClient()
        api = ListingsAPI(client)

        api.create("Title", "Desc", 10, "193", "96100", shipping=True)

        update_call = next(c for c in client.calls if c[0] == "adinput_put")
        values = update_call[2]
        self.assertEqual(values["location"], [{"country": "FI", "postal-code": "96100"}])


if __name__ == "__main__":
    unittest.main()
