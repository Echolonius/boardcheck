"""agent_market_signals — detect deceptive signals in AI-agent marketplaces.

Dependency-free toolkit. See README.md for methodology and limitations.
"""

from .certificate import generate_certificate
from .detectors import (
    Finding,
    Listing,
    batch_creation_clustering,
    high_budget_bait,
    scan,
    self_advertisement_ratio,
    unpaid_work_risk,
    upfront_fee_gating,
    view_application_inversion,
)
from .observation import to_observation
from .thresholds import DEFAULTS, Thresholds

__all__ = [
    "DEFAULTS",
    "Finding",
    "Listing",
    "Thresholds",
    "batch_creation_clustering",
    "generate_certificate",
    "high_budget_bait",
    "scan",
    "self_advertisement_ratio",
    "to_observation",
    "unpaid_work_risk",
    "upfront_fee_gating",
    "view_application_inversion",
]

__version__ = "0.7.0"
