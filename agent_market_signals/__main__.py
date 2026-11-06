"""CLI: scan a JSON file of listings for deceptive marketplace signals.

The input is a JSON array of listing objects; see SCHEMA.md for the fields
(``created_at`` is ISO 8601). Output is a JSON report on stdout; exit code is
1 if any "high"-severity finding was raised, 0 otherwise, 2 on usage or input
errors (useful in CI / cron).
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version

from .detectors import Listing, scan


def load_listings(raw: list[dict]) -> list[Listing]:
    return [Listing.from_dict(item) for item in raw]


def _version() -> str:
    try:
        return version("agent-market-signals")
    except PackageNotFoundError:  # running from a source tree
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-market-signals",
        description="Scan agent-marketplace listings for integrity signals "
        "(AMS-001..AMS-007). Prints a JSON report to stdout.",
        epilog="Exit codes: 0 no high-severity findings, 1 high-severity "
        "finding present, 2 usage or input error.",
    )
    parser.add_argument(
        "listings",
        help="path to a JSON array of listings (see SCHEMA.md), or - for stdin",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_version()}"
    )
    args = parser.parse_args(argv)

    try:
        if args.listings == "-":
            raw = json.load(sys.stdin)
        else:
            with open(args.listings, encoding="utf-8") as fh:
                raw = json.load(fh)
        if not isinstance(raw, list):
            raise ValueError("input must be a JSON array of listing objects")
        report = scan(load_listings(raw))
    except (OSError, ValueError, KeyError) as exc:
        # OSError: unreadable path; ValueError: bad JSON (JSONDecodeError) or
        # non-array input; KeyError: listing missing a required field.
        print(f"agent-market-signals: error: {exc}", file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if report["summary"].get("high", 0) > 0 else 0


def _console() -> None:
    """Entry point for the ``agent-market-signals`` console script."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
