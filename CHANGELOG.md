# Changelog

All notable changes to this project are documented here. Indicator IDs (`AMS-*`) are stable;
see [SPEC.md](SPEC.md) for the versioning policy.

## Unreleased

On `main` since 0.6.0, not yet part of a numbered release (no 0.7.0 has been tagged or released).

- **AMS-006 `prompt_injection_payload`** (`high`): fires when a listing's `title`, `description`
  or `instructions` contain one of a fixed list of instruction-override or shell-command phrases
  (letter case ignored), or when the listing has `has_prompt_injection: true`. Runs in `scan()` and
  in the site's browser version.
- **AMS-007 `upfront_fee_gating`** (`high`): fires when `requires_upfront_fee` is `true` and
  `has_escrow` is not `true` (a missing `has_escrow` counts as no escrow). Runs in `scan()`; the
  site's browser version does not run it.
- Five new optional listing fields for these checks: `title`, `description`, `instructions`,
  `has_prompt_injection`, `requires_upfront_fee` (see [SCHEMA.md](SCHEMA.md)).
- **`generate_certificate()`** and a fifth MCP tool, **`generate_audit_certificate`**: turn a scan
  into a JSON summary (verdict, counts, timestamp and a short hash-based ID) with Markdown/HTML
  badge snippets. It is not signed and is built from whatever listings are passed in.
- Neither new check is in the JS↔Python parity test yet, and the single-listing `check_listing`
  MCP tool still runs only AMS-001 and AMS-004.
- **Fixed version drift again:** `__init__.__version__` said `0.7.0` while `pyproject.toml` (and
  so `--version`) said `0.6.0`; both now say `0.6.0`.

## 0.6.0 — 2026-07-13

Robustness release: the detector logic exists in two places (the Python reference and the
browser port on the site), and this release makes it impossible for them to drift silently.

- **JS↔Python parity test.** A shared fixture battery (`tests/parity_fixtures.json`) runs through
  both the Python `scan()` and the site's detector under Node; `tests/test_parity.py` asserts they
  produce identical findings, verdict, summary, and coverage — and that the threshold constants
  match. CI now runs Node so the site's port is tested on every push. Change one implementation and
  not the other and the build goes red. The parity check compares the human-readable finding
  **text** too, not just the finding identity/verdict/summary.
- **Site and library now render identical finding text** (fixes found by an adversarial review of
  this release): a timestamp with no explicit offset is interpreted as **UTC** in both
  implementations (Python previously used the host's local timezone, which could shift the AMS-002
  time buckets on a non-UTC machine); and numbers/percentages use matched formatting, so Python no
  longer prints `5e+06` / `82%` where the site prints `5000000` / `83%`. Finding identity, verdict,
  and summary were already identical; this aligns the explanatory text as well.
- **Single source for the site's detectors.** The `norm`/`median`/`scan` code moved out of
  `index.html` into `docs/boardcheck.js`, which the site *and* the parity test both load. The site's
  CSP was updated to allow that same-origin script (`script-src 'self' 'unsafe-inline'`).
- **Tunable thresholds.** `scan(listings, Thresholds(...))` lets you tune the cutoffs; the
  field-informed defaults (self-ad 0.80, budget 3× median, cluster 3/1 s) are unchanged and now
  have one authoritative home (`agent_market_signals/thresholds.py`) with documented provenance in
  SPEC.md. No default value changed, so scan results are identical to 0.5.x.
- **Findings carry the stable AMS id.** Each finding dict now includes `id` (`AMS-001` … `AMS-005`)
  alongside the existing `indicator` name, so callers can cite the id the SPEC guarantees is stable.
- **Observation schema → 0.2.** `indicators_fired` now lists AMS ids rather than detector function
  names, so the shared privacy-preserving format survives internal renames. (Privacy properties are
  unchanged; ids are no more identifying than names.)
- **Fixed version drift:** `__init__.__version__` said `0.5.0` while `pyproject.toml` said `0.5.2`;
  both are now `0.6.0`.

## 0.5.2 — 2026-07-12

- CLI hardening: proper `--help`/`--version`, `-` reads stdin, and unreadable
  paths / malformed JSON / non-array input produce a one-line error with exit
  code 2 instead of a traceback. New CLI test suite (6 tests).
- Site: redesign (minimalist monochrome, auto light/dark), human/agent mode
  toggle, XSS-hardened result rendering (all dynamic values via textContent),
  and `llms.txt` for agent discovery.

## 0.5.1 — 2026-07-12

**Packaging fix (important if you installed 0.5.0 via pip):** stale `build/` and `*.egg-info/`
directories were committed to the repository, and setuptools packaged the outdated code inside
them — a `pip install` of "0.5.0" was missing the `verdict` field and other 0.5.0 changes.
Removed the stale artifacts and ignored them permanently. Reinstall with
`pip install --force-reinstall --no-cache-dir "git+https://github.com/Echolonius/agent-market-signals"`.

Also new: the project site with an in-browser detector demo, now at https://echolonius.github.io/boardcheck/

## 0.5.0
- Add an at-a-glance `verdict` to scan reports: `high_risk` / `caution` / `clear`. Deliberately
  categorical, not a false-precise 0–100 score.
- Continuous integration (GitHub Actions) running the suite on Python 3.9–3.12.
- Project logo and documented changelog.

## 0.4.0
- MCP server: expose the detectors as tools an agent can call at decision time
  (`scan_listings`, `check_listing`, `list_indicators`, `make_observation`).
- `mcp` kept as an optional extra so the core stays dependency-free.
- `Listing.from_dict` / `parse_created_at` helpers shared by the CLI and server.

## 0.3.0
- Privacy-preserving, opt-in contribution primitive (`to_observation`) with a k-anonymity floor
  and no identifiers — the safe core of the improvement "flywheel" (see FLYWHEEL.md).

## 0.2.0
- Open specification (SPEC.md) with stable indicator IDs `AMS-001`–`AMS-005`.
- Accuracy: infer `views_tracked` platform-wide and suppress view-based indicators when a platform
  does not expose views (removes a class of false positives).
- Data-coverage reporting in scan output.
- Installable from GitHub via `pyproject.toml`.

## 0.1.0
- Initial release: five dependency-free detectors, `scan()` orchestration, CLI, tests, and a
  synthetic example dataset.
