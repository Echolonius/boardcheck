"""Boardcheck Audit Certificate & Verification Badge Generator.

Enables marketplace operators, agents, and auditors to generate verifiable
integrity certificates and embeddable badges for compliant agent job boards.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict


def generate_certificate(
    scan_result: Dict[str, Any],
    platform_name: str,
    issuer: str = "Boardcheck Standard v0.2",
) -> Dict[str, Any]:
    """Generate a machine-readable audit certificate from a scan result."""
    now_iso = datetime.now(timezone.utc).isoformat()
    verdict = scan_result.get("verdict", "unknown")
    listings_scanned = scan_result.get("listings_scanned", 0)
    summary = scan_result.get("summary", {})

    is_compliant = verdict == "clear"

    payload_raw = f"{platform_name}:{verdict}:{listings_scanned}:{now_iso}"
    cert_hash = hashlib.sha256(payload_raw.encode("utf-8")).hexdigest()[:16]

    badge_markdown = (
        f"[![Boardcheck Verified: {verdict.upper()}](https://img.shields.io/badge/Boardcheck-{verdict.upper()}-"
        f"{'brightgreen' if is_compliant else 'yellow' if verdict == 'caution' else 'red'})]"
        f"(https://echolonius.github.io/boardcheck/)"
    )

    badge_html = (
        f'<a href="https://echolonius.github.io/boardcheck/" target="_blank" rel="noopener">'
        f'<img src="https://img.shields.io/badge/Boardcheck-{verdict.upper()}-'
        f'{"brightgreen" if is_compliant else "yellow" if verdict == "caution" else "red"}" '
        f'alt="Boardcheck {verdict.upper()}" /></a>'
    )

    return {
        "@context": "https://schema.org",
        "@type": "BoardcheckIntegrityCertificate",
        "certificate_id": f"BC-CERT-{cert_hash}",
        "platform_name": platform_name,
        "issued_at": now_iso,
        "issuer": issuer,
        "verdict": verdict,
        "is_compliant": is_compliant,
        "listings_scanned": listings_scanned,
        "summary": summary,
        "badge": {
            "markdown": badge_markdown,
            "html": badge_html,
        },
    }
