"""Human- and agent-readable catalog of the integrity indicators.

Mirrors SPEC.md so an agent can discover, at runtime, exactly what this tool
checks and cite findings by stable ID.
"""

INDICATORS = [
    {
        "id": "AMS-001",
        "name": "view_application_inversion",
        "max_severity": "high",
        "summary": "Applications exceed views. Applying ordinarily requires "
        "viewing, so this is implausible and suggests fabricated engagement.",
    },
    {
        "id": "AMS-002",
        "name": "batch_creation_clustering",
        "max_severity": "warn",
        "summary": "Many listings created within the same tight time window — "
        "a signature of automated seeding rather than organic demand.",
    },
    {
        "id": "AMS-003",
        "name": "self_advertisement_ratio",
        "max_severity": "high",
        "summary": "Most listings are agents advertising themselves rather than "
        "buyers offering work — a supply glut presented as demand.",
    },
    {
        "id": "AMS-004",
        "name": "unpaid_work_risk",
        "max_severity": "warn",
        "summary": "Priced work with no escrow and no payment-evidence "
        "mechanism — payment depends entirely on poster discretion.",
    },
    {
        "id": "AMS-005",
        "name": "high_budget_bait",
        "max_severity": "warn",
        "summary": "A budget far above the platform median with zero views — a "
        "large number that attracts applicants while no real buyer is engaged.",
    },
    {
        "id": "AMS-006",
        "name": "prompt_injection_payload",
        "max_severity": "high",
        "summary": "Listing text contains instruction overrides or execution "
        "commands designed to hijack inspecting autonomous agent harnesses.",
    },
    {
        "id": "AMS-007",
        "name": "upfront_fee_gating",
        "max_severity": "high",
        "summary": "Listing requires an upfront fee or deposit to apply or bid "
        "and has no confirmed escrow (has_escrow is not true; a missing value "
        "counts as no escrow).",
    },
]
