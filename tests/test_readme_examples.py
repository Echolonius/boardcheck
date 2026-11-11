"""Runs the example in README.md's "Check a bounty issue before you work on it"
section, so the findings the README shows are the ones the code returns.

The section holds two ``json`` blocks: the made-up bounty issue passed to
``check_listing`` as one listing, and the result. If the README or the checks
change so that the two no longer agree, this test fails.
"""

import json
import re
import unittest
from pathlib import Path

from agent_market_signals import mcp_server as m

_README = Path(__file__).resolve().parent.parent / "README.md"
_HEADING = "### Check a bounty issue before you work on it"
_HTML_COMMENT = re.compile(r"\s*<!--.*?-->", re.S)


def _json_blocks_under(heading):
    """The ``json`` code blocks between ``heading`` and the next heading."""
    text = _README.read_text(encoding="utf-8")
    if heading + "\n" not in text:
        raise AssertionError(f"README.md has no heading {heading!r}")
    section = text.split(heading + "\n", 1)[1]
    following = re.search(r"^#{1,6} ", section, re.M)
    if following:
        section = section[: following.start()]
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", section, re.S)]


class ReadmeBountyIssueExampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        blocks = _json_blocks_under(_HEADING)
        if len(blocks) != 2:
            raise AssertionError(
                f"expected two json blocks under {_HEADING!r} "
                f"(the listing and the result), found {len(blocks)}"
            )
        cls.listing, cls.shown = blocks

    def test_example_gives_the_findings_the_readme_shows(self):
        self.assertEqual(m.check_listing(self.listing), self.shown)

    def test_example_shows_the_text_and_fee_checks(self):
        # The example is there to show the checks that read one bounty's text
        # (AMS-006, AMS-008) and the fee check (AMS-007), all high.
        self.assertEqual(self.shown["listing_id"], self.listing["id"])
        self.assertEqual(
            [f["id"] for f in self.shown["findings"]], ["AMS-006", "AMS-007", "AMS-008"]
        )
        self.assertEqual({f["severity"] for f in self.shown["findings"]}, {"high"})

    def test_example_passes_the_issue_as_title_and_description(self):
        # Only id and created_at are required; the issue goes in as text.
        self.assertTrue({"id", "created_at", "title", "description"} <= set(self.listing))
        self.assertIsInstance(self.listing["title"], str)
        self.assertIsInstance(self.listing["description"], str)

    def test_visible_part_of_the_example_is_clean(self):
        # The README says the rendered issue looks ordinary: without the
        # hidden comment and the fee flag, nothing fires. The fee is not read
        # from the text, so the deposit sentence alone gives no finding.
        visible = dict(self.listing)
        visible.pop("requires_upfront_fee")
        self.assertIn("<!--", visible["description"])
        visible["description"] = _HTML_COMMENT.sub("", visible["description"])
        self.assertNotIn("<!--", visible["description"])
        self.assertIn("deposit", visible["description"])
        self.assertEqual(m.check_listing(visible)["findings"], [])


if __name__ == "__main__":
    unittest.main()
