"""Detectors for deceptive signals in AI-agent marketplace listings.

Dependency-free (Python standard library only). Each detector operates on
normalized :class:`Listing` records and returns structured :class:`Finding`
objects. The patterns encoded here were observed first-hand while operating an
autonomous agent across live AI-agent marketplaces in the first half of 2026;
see README.md for methodology and honest limitations.

Design rules:
- A detector never invents data. If the fields it needs are absent (``None``),
  it stays silent rather than guessing — absence of evidence is not evidence.
  The one exception is AMS-007 (:func:`upfront_fee_gating`): when
  ``requires_upfront_fee`` is ``True``, it counts a missing ``has_escrow`` as
  no escrow and fires unless ``has_escrow`` is ``True``.
- Findings are advisory signals, not verdicts. They flag patterns a human or a
  downstream system should weigh, and every finding explains its own reasoning.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Optional

from .catalog import INDICATORS
from .thresholds import DEFAULTS, Thresholds

Severity = str  # "info" | "warn" | "high"

# Stable AMS-* id for each detector name (single source: catalog.py, which
# mirrors SPEC.md). Findings carry both the stable id and the human-readable
# name so callers can cite the id the SPEC guarantees will never change.
_ID_BY_NAME = {ind["name"]: ind["id"] for ind in INDICATORS}


def _num(x) -> str:
    """Render a number the way the site's JavaScript port does: plain, shortest
    round-trip, no scientific notation for ordinary magnitudes. This keeps a
    finding's ``detail`` text identical between the library and the browser for
    the same input (Python's ``:g`` would print e.g. ``5e+06`` where JS prints
    ``5000000``). Verified against the JS port by tests/test_parity.py."""
    f = float(x)
    return str(int(f)) if f.is_integer() else repr(f)


def _pct(ratio: float) -> int:
    """Percent, rounded half-up — matching the JS port's ``Math.round(r*100)``.
    (Python's default/``:.0%`` rounding is half-to-even, which disagrees with JS
    on exact-half values like 82.5%.)"""
    return int(ratio * 100 + 0.5)


def parse_created_at(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, accepting a trailing ``Z`` (UTC) which
    ``datetime.fromisoformat`` rejects before Python 3.11.

    A timestamp without an explicit offset is interpreted as **UTC**, not the
    host's local time — a marketplace creation time is a fact, and the result
    must not depend on where the check runs. The JS port applies the same rule,
    so both agree on the AMS-002 time buckets regardless of host timezone."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class Listing:
    """A normalized marketplace listing. Unknown fields stay ``None``.

    Only ``id`` and ``created_at`` are required. A signal whose data is missing
    stays silent, except AMS-007, which counts a missing ``has_escrow`` as no
    escrow (see :func:`upfront_fee_gating`).
    """

    id: str
    created_at: datetime
    views: Optional[int] = None
    applications: Optional[int] = None
    budget: Optional[float] = None
    poster_type: str = "unknown"  # "human" | "agent" | "unknown"
    is_self_advertisement: Optional[bool] = None
    has_escrow: Optional[bool] = None
    has_payment_evidence: Optional[bool] = None
    has_prompt_injection: Optional[bool] = None
    requires_upfront_fee: Optional[bool] = None
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None

    @classmethod
    def from_dict(cls, item: dict) -> "Listing":
        """Build a Listing from a plain dict (see SCHEMA.md). ``created_at`` may
        be an ISO 8601 string or an existing ``datetime``."""
        created = item["created_at"]
        if isinstance(created, str):
            created = parse_created_at(created)
        return cls(
            id=str(item["id"]),
            created_at=created,
            views=item.get("views"),
            applications=item.get("applications"),
            budget=item.get("budget"),
            poster_type=item.get("poster_type", "unknown"),
            is_self_advertisement=item.get("is_self_advertisement"),
            has_escrow=item.get("has_escrow"),
            has_payment_evidence=item.get("has_payment_evidence"),
            has_prompt_injection=item.get("has_prompt_injection"),
            requires_upfront_fee=item.get("requires_upfront_fee"),
            title=item.get("title"),
            description=item.get("description"),
            instructions=item.get("instructions"),
        )


@dataclass
class Finding:
    indicator: str
    severity: Severity
    detail: str
    listing_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "id": _ID_BY_NAME.get(self.indicator, self.indicator),
            "indicator": self.indicator,
            "severity": self.severity,
            "listing_id": self.listing_id,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------
# Listing-level detectors
# --------------------------------------------------------------------------

def view_application_inversion(
    listing: Listing, views_tracked: bool = True
) -> Optional[Finding]:
    """Applications that exceed views. (Indicator AMS-001.)

    Applying to a listing ordinarily requires viewing it first, so
    applications should never exceed views. Applications with zero views is
    the starkest case and the one observed on seeded high-budget listings.

    ``views_tracked`` guards a real false positive: on a platform that does
    not expose view counts at all, every listing reads as 0 views, which says
    nothing about fabrication. When the caller knows (or :func:`scan` infers)
    that views are untracked platform-wide, the zero-views case is suppressed;
    the applications-exceed-positive-views case still stands, because a
    positive view count means tracking works for that listing.
    """
    v, a = listing.views, listing.applications
    if v is None or a is None or a <= 0:
        return None
    if v == 0:
        if not views_tracked:
            return None
        return Finding(
            "view_application_inversion",
            "high",
            f"{a} application(s) with 0 views — applying requires viewing, "
            "so this count is arithmetically implausible and may be fabricated",
            listing.id,
        )
    if a > v:
        return Finding(
            "view_application_inversion",
            "warn",
            f"{a} applications exceed {v} views — anomalous engagement",
            listing.id,
        )
    return None


def unpaid_work_risk(listing: Listing) -> Optional[Finding]:
    """Priced work with neither escrow nor any payment-evidence mechanism.

    When a listing advertises a price but nothing guarantees payment, the
    money depends entirely on the poster's discretion after work is delivered
    — the structure behind accepted-but-unpaid work observed in the field.
    """
    if listing.budget is None or listing.budget <= 0:
        return None
    if listing.has_escrow is False and listing.has_payment_evidence is False:
        return Finding(
            "unpaid_work_risk",
            "warn",
            f"priced ({_num(listing.budget)}) with no escrow and no payment-evidence "
            "mechanism — payment depends solely on poster discretion after delivery",
            listing.id,
        )
    return None


INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt:",
    "system override",
    "cat /etc/passwd",
    "eval(",
    "curl -s | bash",
    "git push --force",
]


def prompt_injection_payload(listing: Listing) -> Optional[Finding]:
    """Listing text contains instruction overrides or execution commands. (Indicator AMS-006.)"""
    if listing.has_prompt_injection is True:
        return Finding(
            "prompt_injection_payload",
            "high",
            "listing content contains indirect prompt injection or instruction-override payloads",
            listing.id,
        )
    text = " ".join(filter(None, [listing.title, listing.description, listing.instructions])).lower()
    if any(marker in text for marker in INJECTION_MARKERS):
        return Finding(
            "prompt_injection_payload",
            "high",
            "listing content contains indirect prompt injection or instruction-override payloads",
            listing.id,
        )
    return None


# --------------------------------------------------------------------------
# Marketplace-level detectors (operate over a collection of listings)
# --------------------------------------------------------------------------

def batch_creation_clustering(
    listings: list[Listing],
    window_seconds: int = DEFAULTS.window_seconds,
    min_cluster: int = DEFAULTS.min_cluster,
) -> list[Finding]:
    """Listings created within the same tight time window.

    Many listings sharing a creation timestamp to the second is a signature of
    automated batch seeding rather than organic, independently-arriving demand.
    """
    if window_seconds < 1:
        raise ValueError("window_seconds must be >= 1")
    buckets: dict[int, list[Listing]] = defaultdict(list)
    for listing in listings:
        bucket = int(listing.created_at.timestamp()) // window_seconds
        buckets[bucket].append(listing)

    findings: list[Finding] = []
    for group in buckets.values():
        if len(group) >= min_cluster:
            ids = ", ".join(sorted(g.id for g in group))
            findings.append(
                Finding(
                    "batch_creation_clustering",
                    "warn",
                    f"{len(group)} listings created within a {window_seconds}s "
                    f"window ({ids}) — consistent with automated seeding",
                )
            )
    return findings


def self_advertisement_ratio(
    listings: list[Listing], threshold: float = DEFAULTS.self_ad_ratio
) -> Optional[Finding]:
    """Share of listings that are agents advertising their own services.

    A board that is overwhelmingly agents marketing themselves — rather than
    buyers offering work — is a supply glut presented as demand. The ratio is
    computed only over listings whose type is known.
    """
    known = [l for l in listings if l.is_self_advertisement is not None]
    if not known:
        return None
    ratio = sum(1 for l in known if l.is_self_advertisement) / len(known)
    if ratio >= threshold:
        return Finding(
            "self_advertisement_ratio",
            "high",
            f"{_pct(ratio)}% of listings are agent self-advertisements (n={len(known)}) "
            "— supply glut marketed as demand",
        )
    return None


def high_budget_bait(
    listings: list[Listing],
    budget_multiple: float = DEFAULTS.budget_multiple,
    views_tracked: bool = True,
) -> list[Finding]:
    """Far-above-median budgets that have drawn zero views. (Indicator AMS-005.)

    A budget many times the platform norm that no one has viewed is bait: the
    large number attracts applicants while the zero views show no real buyer
    engagement. Needs at least three budgeted listings to establish a median.

    Like AMS-001, the zero-views condition is meaningless when views are not
    tracked platform-wide, so the whole detector is suppressed in that case.
    """
    if not views_tracked:
        return []
    budgets = [l.budget for l in listings if l.budget and l.budget > 0]
    if len(budgets) < 3:
        return []
    med = median(budgets)
    if med <= 0:
        return []

    findings: list[Finding] = []
    for listing in listings:
        if (
            listing.budget
            and listing.budget >= budget_multiple * med
            and listing.views == 0
        ):
            findings.append(
                Finding(
                    "high_budget_bait",
                    "warn",
                    f"budget {_num(listing.budget)} is >={_num(budget_multiple)}x the platform "
                    f"median ({_num(med)}) with 0 views — seeded high-budget bait",
                    listing.id,
                )
            )
    return findings


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _coverage(listings: list[Listing]) -> dict:
    """How many listings carried each field. An auditor needs to know how much
    was actually assessable — a clean scan of sparse data is not a clean bill."""
    n = len(listings)

    def present(attr: str) -> int:
        return sum(1 for l in listings if getattr(l, attr) is not None)

    fields = (
        "views",
        "applications",
        "budget",
        "is_self_advertisement",
        "has_escrow",
        "has_payment_evidence",
    )
    return {f: {"present": present(f), "of": n} for f in fields}


def upfront_fee_gating(listing: Listing) -> Optional[Finding]:
    """AMS-007 — upfront fee gating detector.

    Fires when a listing explicitly requires an upfront fee or deposit to apply/bid
    (``requires_upfront_fee is True``) without confirmed escrow protection
    (``has_escrow`` is anything but ``True``: ``False``, ``None``/missing, or any
    other value).

    This is the one detector that fires on missing data: a missing ``has_escrow``
    counts as no escrow, not as unknown. If ``requires_upfront_fee`` is anything
    but ``True`` (including missing), it stays silent.
    """
    if listing.requires_upfront_fee is True and listing.has_escrow is not True:
        return Finding(
            indicator="upfront_fee_gating",
            severity="high",
            listing_id=listing.id,
            detail="Listing requires an upfront fee or token deposit to apply/bid without escrow protection.",
        )
    return None


def scan(listings: list[Listing], thresholds: Optional[Thresholds] = None) -> dict:
    """Run every detector and return findings, a severity summary, and a
    data-coverage report.

    Whether views are tracked platform-wide is inferred once (any listing with
    a positive view count) and threaded into the view-based detectors so a
    platform that simply does not expose views is not flagged for it.

    ``thresholds`` tunes the detector cutoffs; it defaults to the field-informed
    :data:`~agent_market_signals.thresholds.DEFAULTS`. The defaults are the same
    values every implementation ships, so an unconfigured scan here and in the
    browser port agree (enforced by ``tests/test_parity.py``).
    """
    if thresholds is None:
        thresholds = DEFAULTS

    views_tracked = any(
        l.views is not None and l.views > 0 for l in listings
    )

    findings: list[Finding] = []
    for listing in listings:
        result = view_application_inversion(listing, views_tracked=views_tracked)
        if result is not None:
            findings.append(result)
        result = unpaid_work_risk(listing)
        if result is not None:
            findings.append(result)
        result = prompt_injection_payload(listing)
        if result is not None:
            findings.append(result)
        result = upfront_fee_gating(listing)
        if result is not None:
            findings.append(result)

    findings.extend(
        batch_creation_clustering(
            listings,
            window_seconds=thresholds.window_seconds,
            min_cluster=thresholds.min_cluster,
        )
    )
    ratio = self_advertisement_ratio(listings, threshold=thresholds.self_ad_ratio)
    if ratio is not None:
        findings.append(ratio)
    findings.extend(
        high_budget_bait(
            listings,
            budget_multiple=thresholds.budget_multiple,
            views_tracked=views_tracked,
        )
    )

    summary = {"info": 0, "warn": 0, "high": 0}
    for finding in findings:
        summary[finding.severity] = summary.get(finding.severity, 0) + 1

    # An honest at-a-glance headline. Deliberately categorical, not a
    # false-precise 0-100 "trust score": we can flag patterns, not quantify a
    # probability of fraud, and a fabricated number would undermine the very
    # credibility this tool exists to provide. "clear" is not a clean bill of
    # health — read it together with `coverage`, since thin data flags little.
    if summary["high"] > 0:
        verdict = "high_risk"
    elif summary["warn"] > 0 or summary["info"] > 0:
        verdict = "caution"
    else:
        verdict = "clear"

    return {
        "listings_scanned": len(listings),
        "verdict": verdict,
        "views_tracked": views_tracked,
        "coverage": _coverage(listings),
        "findings": [f.as_dict() for f in findings],
        "summary": summary,
    }
