"""Tests for the MCP tool functions.

The tool functions are plain and dependency-free, so these run without the
``mcp`` package installed. A final test builds the real FastMCP server only if
``mcp`` is available.
"""

import importlib.util
import unittest

from agent_market_signals import mcp_server as m

HAS_MCP = importlib.util.find_spec("mcp") is not None

VIEWS_TRACKED_BOARD = (
    [
        {
            "id": "bait",
            "created_at": "2026-01-14T12:00:00Z",
            "views": 0,
            "applications": 22,
            "budget": 2000.0,
            "has_escrow": False,
            "has_payment_evidence": False,
        }
    ]
    + [
        {"id": f"ad{i}", "created_at": "2026-02-01T09:00:00Z", "views": 6,
         "is_self_advertisement": True}
        for i in range(9)
    ]
)


class TestScanListings(unittest.TestCase):
    def test_scan_flags_bait_and_summarizes(self):
        report = m.scan_listings(VIEWS_TRACKED_BOARD)
        self.assertEqual(report["listings_scanned"], 10)
        self.assertGreater(report["summary"]["high"], 0)
        indicators = {f["indicator"] for f in report["findings"]}
        self.assertIn("view_application_inversion", indicators)

    def test_accepts_iso_z_timestamps(self):
        # Should not raise on a trailing-Z timestamp.
        m.scan_listings([{"id": "a", "created_at": "2026-01-01T00:00:00Z"}])


class TestCheckListing(unittest.TestCase):
    def test_single_bad_listing_flags(self):
        out = m.check_listing(
            {"id": "x", "created_at": "2026-01-14T12:00:00Z", "views": 0,
             "applications": 20, "budget": 6.0, "has_escrow": False,
             "has_payment_evidence": False}
        )
        self.assertEqual(out["listing_id"], "x")
        kinds = {f["indicator"] for f in out["findings"]}
        self.assertIn("view_application_inversion", kinds)
        self.assertIn("unpaid_work_risk", kinds)

    def test_clean_listing_is_empty(self):
        out = m.check_listing(
            {"id": "ok", "created_at": "2026-01-14T12:00:00Z", "views": 100,
             "applications": 3, "budget": 40.0, "has_escrow": True,
             "has_payment_evidence": True}
        )
        self.assertEqual(out["findings"], [])


class TestCatalogAndObservation(unittest.TestCase):
    def test_list_indicators_returns_stable_ids(self):
        ids = {i["id"] for i in m.list_indicators()}
        self.assertEqual(ids, {"AMS-001", "AMS-002", "AMS-003", "AMS-004", "AMS-005", "AMS-006", "AMS-007", "AMS-008"})

    def test_make_observation_is_privacy_preserving(self):
        obs = m.make_observation(VIEWS_TRACKED_BOARD)
        self.assertIsNotNone(obs)
        self.assertNotIn("bait", str(obs))
        self.assertIn("indicators_fired", obs)

    def test_make_observation_refuses_tiny_sample(self):
        self.assertIsNone(
            m.make_observation([{"id": "a", "created_at": "2026-01-01T00:00:00Z"}])
        )


@unittest.skipUnless(HAS_MCP, "mcp package not installed")
class TestServerBuilds(unittest.TestCase):
    def test_build_server_registers_tools(self):
        # Constructing the server validates every tool signature against MCP.
        server = m.build_server()
        self.assertIsNotNone(server)


if __name__ == "__main__":
    unittest.main()
