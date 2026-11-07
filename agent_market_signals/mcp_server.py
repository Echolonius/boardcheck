"""Optional MCP (Model Context Protocol) server: exposes the detectors as tools
an AI agent can call at decision time.

Install the optional dependency and run it:

    pip install "agent-market-signals[mcp] @ git+https://github.com/Echolonius/agent-market-signals"
    agent-market-signals-mcp

The server runs locally over stdio. It hosts nothing and sends nothing anywhere;
it is a connector between an MCP-capable client (Claude Desktop, Claude Code, and
others) and this library.

The tool functions below are plain and dependency-free, so they can be tested
without the ``mcp`` package. Only :func:`build_server` imports it.
"""

from __future__ import annotations

from typing import Optional

from .catalog import INDICATORS
from .detectors import (
    Listing,
    agent_bait_listing,
    scan,
    unpaid_work_risk,
    view_application_inversion,
)
from .observation import to_observation


def scan_listings(listings: list[dict]) -> dict:
    """Scan a batch of AI-agent marketplace listings for deceptive integrity
    signals. Runs all eight checks (AMS-001 to AMS-008): fabricated engagement,
    seeded/astroturfed listings, supply-glut boards, unpaid-work risk,
    high-budget bait, prompt-injection text in a listing's title, description
    or instructions, an upfront fee or deposit required without confirmed
    escrow, and bounty bait written for agents (requests for a private key,
    seed phrase or API token, download-and-run instructions, hidden text).
    Returns findings, a severity summary, and a data-coverage report.

    Use this to verify a marketplace before trusting its numbers or committing
    time to it — e.g. before an agent decides where to look for paid work. Each
    listing is a dict; only ``id`` and ``created_at`` are required.
    """
    parsed = [Listing.from_dict(item) for item in listings]
    return scan(parsed)


def check_listing(listing: dict) -> dict:
    """Check a SINGLE listing for red flags before bidding on or accepting it:
    application/view inversion (AMS-001, fabricated interest), unpaid-work risk
    (AMS-004, priced with no escrow or payment evidence) and agent bait
    (AMS-008: asks for your private key, seed phrase or API token, tells you to
    download and run remote code, refuses human submissions, claims escrow you
    cannot check, or hides text that gives an AI reader orders). Returns findings for
    that one listing.
    """
    parsed = Listing.from_dict(listing)
    findings = []
    for detector in (view_application_inversion, unpaid_work_risk, agent_bait_listing):
        result = detector(parsed)
        if result is not None:
            findings.append(result.as_dict())
    return {"listing_id": parsed.id, "findings": findings}


def list_indicators() -> list[dict]:
    """List the integrity indicators this tool checks: stable AMS-* IDs, names,
    maximum severity, and a plain-language summary of each. Lets an agent
    discover what can be checked and cite findings precisely by ID.
    """
    return INDICATORS


def make_observation(listings: list[dict], min_sample: int = 5) -> Optional[dict]:
    """OPT-IN: produce a privacy-preserving, non-reversible summary of a scan
    that MAY be contributed to improve the shared thresholds over time. It
    contains no platform name, no listings, and no identity — only coarse
    buckets and boolean flags. Returns null if the sample is too small to share
    safely. Nothing is sent anywhere by this call; sharing is a separate,
    manual step.
    """
    parsed = [Listing.from_dict(item) for item in listings]
    return to_observation(parsed, min_sample=min_sample)


from .certificate import generate_certificate


def generate_audit_certificate(listings: list[dict], platform_name: str) -> dict:
    """Generate a machine-readable Boardcheck Audit Certificate and embeddable
    verification badge for a marketplace based on its current listings batch.
    """
    parsed = [Listing.from_dict(item) for item in listings]
    scan_result = scan(parsed)
    return generate_certificate(scan_result, platform_name=platform_name)


TOOLS = (scan_listings, check_listing, list_indicators, make_observation, generate_audit_certificate)


def build_server():
    """Construct the FastMCP server. Imports the optional ``mcp`` dependency."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("agent-market-signals")
    for tool in TOOLS:
        server.tool()(tool)
    return server


def main() -> None:
    """Run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
