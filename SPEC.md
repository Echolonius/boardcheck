# Agent Marketplace Integrity Signals — Specification v0.2

An open, implementation-neutral specification for detecting deceptive signals in
AI-agent marketplaces. Anyone — a marketplace operator, a buyer's or seller's agent,
a third-party auditor, a researcher, or a solo user telling their agent "go find me
work" — can implement or cite this specification to reason about marketplace integrity
in a shared vocabulary.

This document defines *what* the indicators are. The Python package in this repository
is a **reference implementation**; it is not the specification, and conforming
implementations may exist in any language.

## Status and scope

- **Version:** 0.2 (pre-1.0; indicator IDs are stable, thresholds and wording may change).
- **These are heuristics, not proof.** An indicator flags a pattern that merits human or
  system attention. A flagged listing is not proven deceptive; an unflagged one is not
  proven honest. Conforming implementations MUST NOT present findings as verdicts.
- **Neutral by design.** The specification names no platforms and endorses no parties. It
  describes patterns detectable from data a marketplace already publishes.

## Data model

A **listing** is a record with the following fields. Only `id` and `created_at` are
required; any other field MAY be absent, and indicators that need an absent field simply
do not run. For boolean fields, absent means *unknown* and MUST NOT be treated as `false`.
**One exception to both rules:** AMS-007 counts an absent `has_escrow` the same as `false`
(no escrow), so it fires whenever `requires_upfront_fee` is `true` and `has_escrow` is not
`true` (see AMS-007 below).

| Field | Type | Meaning |
|---|---|---|
| `id` | string | stable identifier |
| `created_at` | timestamp (ISO 8601) | creation time |
| `views` | integer | times viewed |
| `applications` | integer | applications/bids received |
| `budget` | number | advertised price |
| `poster_type` | `human` \| `agent` \| `unknown` | who posted |
| `is_self_advertisement` | boolean | listing is an agent marketing itself, not a buyer offering work |
| `has_escrow` | boolean | funds escrowed before work begins |
| `has_payment_evidence` | boolean | platform provides a verifiable record that priced work gets paid |
| `requires_upfront_fee` | boolean | platform/listing requires an upfront fee or deposit to apply/bid |
| `title` | string | listing title; AMS-006 searches it together with `description` and `instructions` (joined with spaces, letter case ignored); AMS-008 reads all three too |
| `description` | string | listing description; searched by AMS-006 and AMS-008 (see `title`) |
| `instructions` | string | any instructions text on the listing; searched by AMS-006 and AMS-008 (see `title`) |
| `has_prompt_injection` | boolean | `true` marks the listing as carrying a prompt-injection payload (e.g. flagged by another tool), and AMS-006 then fires without reading the text; `false` or absent leaves the text search on |

## Severity

`info` (context), `warn` (anomalous, weigh it), `high` (arithmetically implausible or
structurally exposed). Implementations MAY map these to their own scales but MUST preserve
the relative ordering.

## Verdict

A scan MAY carry an at-a-glance `verdict`: `high_risk` (any high-severity finding),
`caution` (only warn/info findings), or `clear` (none). This is deliberately categorical, not a
0–100 score: the indicators flag patterns, they do not quantify a probability of fraud, and a
false-precise number would misrepresent that. `clear` is not a clean bill of health — it must be
read together with coverage, since sparse data flags little.

## Environmental inference

Before evaluating listing-level indicators, an implementation SHOULD infer **`views_tracked`**:
true if any listing carries a positive view count. When false, the platform is presumed not
to expose views, and indicators whose logic depends on a zero-view reading (AMS-001 zero-view
case, AMS-005) MUST be suppressed to avoid a systematic false positive.

## Indicators

### AMS-001 — view/application inversion
**Fires when** applications exceed views. **`high`** when applications > 0 and views = 0
(and `views_tracked`); **`warn`** when applications > views > 0.
**Rationale:** applying ordinarily requires viewing, so applications cannot exceed views;
the inversion suggests fabricated engagement.
**Known false positives:** platforms that do not track views (handled by `views_tracked`);
bulk application imports.

### AMS-002 — batch creation clustering
**Fires when** a number of listings (default ≥ 3) share a creation timestamp within a tight
window (default 1 second). Severity `warn`.
**Rationale:** organic demand arrives independently; many listings created in the same second
indicate automated seeding.
**Known false positives:** legitimate bulk imports or platform migrations. Tunable via window
and minimum-cluster size.

### AMS-003 — self-advertisement ratio
**Fires when** the share of listings that are agent self-advertisements meets or exceeds a
threshold (default 80%), computed only over listings whose type is known. Severity `high`.
**Rationale:** a board that is overwhelmingly agents marketing themselves is a supply glut
presented to newcomers as demand.
**Known false positives:** directories that are explicitly agent catalogs (context-dependent;
tune or disable there).

### AMS-004 — unpaid-work risk
**Fires when** a listing advertises a positive budget while `has_escrow` and
`has_payment_evidence` are both explicitly `false`. Severity `warn`.
**Rationale:** priced work with no payment guarantee depends entirely on poster discretion
after delivery — the structure behind accepted-but-unpaid work.
**Known false positives:** none inherent; requires both fields to be known-false, not unknown.

### AMS-005 — high-budget bait
**Fires when** a listing's budget is at least a multiple (default 3×) of the platform median
budget and has zero views (requires `views_tracked` and ≥ 3 budgeted listings for a median).
Severity `warn`.
**Rationale:** a far-above-norm budget nobody has viewed attracts applicants while showing no
real buyer engagement.
**Known false positives:** genuinely large, newly-posted, not-yet-viewed listings; tune the
multiple to the platform.

### AMS-006 — indirect prompt injection payload
**Fires when** a listing's text content (title, description, or instructions) contains instruction-override patterns (e.g., `ignore previous instructions`, `system override`, `cat /etc/passwd`, `eval(`, `curl -s | bash`), or when `has_prompt_injection` is `true`.
Severity **`high`**.
**Rationale:** malicious listing posters or untrusted sellers attempt to trick inspecting AI agent harnesses into executing unauthorized system operations, exfiltrating credentials, or bypassing host security controls.
**Known false positives:** legitimate security research, benchmark datasets, or educational listings (handled via context tuning).

### AMS-007 — upfront fee gating
**Fires when** a listing or platform explicitly requires applicants or bidding agents to pay an upfront fee or deposit (`requires_upfront_fee` is `true`) while `has_escrow` is anything other than `true` (`false`, `null` or absent). An absent `has_escrow` therefore counts as no escrow: this is the only indicator that fires on missing data (see Data model). If `requires_upfront_fee` is anything other than `true`, including absent, AMS-007 does not fire.
Severity **`high`**.
**Rationale:** requiring upfront payment before work starts without escrow guarantees creates a high structural risk of fee exploitation.
**Known false positives:** platforms with fully refunded, escrow-backed bidding deposits; listings that do have escrow but do not record it (`has_escrow` absent), since absent counts as no escrow.

### AMS-008 — agent-bait listing
**Fires when** a listing's text (`title`, `description` and `instructions`) is written to bait an AI
agent rather than to hire anyone. At most one finding per listing; its detail names every sign found.

- **`high`** when the text asks for a wallet private key, seed or recovery phrase to be sent, shared,
  posted or pasted ("send us your private key", "paste your seed phrase"), or for an API or access
  token to be sent to the poster or posted where the poster can read it ("share your API key in this
  issue"); or when it tells the solver to download and run remote code: a `curl`/`wget` download piped
  or substituted into a shell or interpreter (`curl … | python3`, `bash <(curl …)`), a downloaded
  script run straight after (`wget …/v.py && python3 v.py`), or "download verify.py and run it".
- **`warn`** when the text says human submissions will not be reviewed or that only automated agents
  are accepted; links two or more different hosts on one line that mentions escrow (code hosts such as
  github.com are not counted); promises automatic payout on merge, or a `/claim`- or `/attempt`-style
  payout, while giving nothing to check (no link with a path on a named host, no on-chain address or
  transaction hash); or carries hidden text an agent would read but a person would not see:
  zero-width characters (U+200B–U+200D, U+2060, and U+FEFF anywhere but the start of a field),
  bidirectional control characters (U+202A–U+202E, U+2066–U+2069), or an HTML comment (`<!-- … -->`,
  or an unclosed `<!--`) aimed at an AI reader. A comment counts only if it names one (AI, agent,
  assistant, LLM, language model, ChatGPT, GPT, Claude, Copilot, Gemini), says "if you are an AI / a
  bot / an LLM …", "ignore all/any/the previous/above/prior …", "system prompt" or "instructions for
  the model/agent/AI …", or would meet the secret or remote-code test above on its own.

Matching ignores the case of ASCII letters, Markdown `*` and backticks, curly apostrophes and runs of
whitespace, and removes hidden characters first, so a phrase split by a zero-width character is still
found. If a listing has none of the three text fields, AMS-008 does not run.

**Not a sign (false-positive guards):** running the project's own tests or scripts (`pytest`,
`npm test`, `python3 verify.py`, "make the tests pass"); a negated warning ("never share your private
key", "you will never be asked to send your recovery phrase"); using an API key locally ("paste your API
key into .env", "send your API key in the Authorization header"); piping data into local code
(`| jq`, `| python3 -m json.tool`, `| python3 script.py`); one escrow link; a payout promise next to an
escrow link or address that can be checked; a byte-order mark at the start of a field; zero-width
joiners inside emoji; joiners between letters of Arabic-script or Indic-script words; and HTML
comments not aimed at an AI reader, such as issue-template leftovers (`<!-- Describe the bug -->`,
`<!-- Browser and user agent -->`, "if you are an existing customer …").

**Rationale:** on 2026-11-06 a GitHub account created that day posted the same two "escrowed" USDC
bounties in six new repositories. Each said manual pull requests from human engineers would not be
reviewed, listed three escrow services at once, promised payment automatically on merge via `/attempt`
or `/claim`, and set the task as making a bundled verification script pass. 51 pull requests from 10
accounts arrived within about 30 hours, and none was merged
([write-up](https://github.com/Echolonius/the-penniless-agent/blob/main/skills/safe-agent-commerce/SKILL.md#8-bounty-bait-written-for-agents)).
A published analysis of a "bounty verifier" skill
([Knostic, 2026-11-07](https://www.knostic.ai/blog/doomsday-escrow-when-a-bounty-verifier-certifies-its-own-claims))
found that it told agents to pipe a remote script into `python3`, and that its sponsor-funding command
sends the wallet private key to the operator. No real escrow, sponsor or verifier step needs a private
key, seed phrase or API token, and a maintainer who wants working code takes it from anyone. Hidden text
is the same move in a quieter form: instructions that a person reviewing the rendered page never sees,
but that an agent reading the raw text does.
**Known false positives:** official installer one-liners quoted in a listing (`curl … | sh` for a
language toolchain); wallet-development bounties that tell the reader to paste their own key into a
local file; a listing that quotes a scam request in order to warn about it; template comments that
mention AI for another reason (an AI-use disclosure question, a "GPT" disk partition); right-to-left
text with explicit direction marks; HTML comments inside code samples. **Known misses:** reworded
requests, escrow services named without a web address, hidden comments that address an AI without
naming one, and anything outside the listing text.

## Threshold defaults, provenance, and tuning

Every numeric cutoff has a single authoritative definition — in the reference implementation,
`agent_market_signals/thresholds.py`; the browser port mirrors it and a parity test fails if the two
ever diverge. The defaults are **field-informed engineering choices, not statistically fitted
cutoffs**; this specification deliberately claims no measured false-positive rate it has not
established.

| Indicator | Knob | Default | Rationale for the default |
|---|---|---|---|
| AMS-002 | window / min cluster | 1 s / 3 | three listings sharing one second is already past plausible independent arrival |
| AMS-003 | self-advertisement ratio | 0.80 | three live boards measured ~95% self-advertisement; 0.80 sits well under that yet clears ordinary mixed boards |
| AMS-005 | budget multiple | 3× median | the point where an above-norm budget starts reading as bait in observed seeded listings |

All cutoffs are tunable per platform. A conforming implementation SHOULD document any non-default
values it uses. Changing a *default* is a minor-version event (see Evolution).

## Conformance

An implementation conforms to v0.2 if it: (1) accepts listings in the data model above,
treating absent fields as unknown (except that AMS-007 counts an absent `has_escrow` as no
escrow); (2) emits findings tagged with these stable indicator IDs
(the reference implementation tags each finding with both the id, e.g. `AMS-001`, and a
human-readable detector name) and preserves the severity ordering; (3) performs the
`views_tracked` suppression; and (4) presents findings as advisory signals, not verdicts.
Implementations MAY add their own indicators under a distinct namespace.

## Related work

This specification is complementary to, not competitive with, agent **identity and reputation**
standards such as ERC-8004 (which score the trustworthiness of counterparties). Those ask "is this
agent trustworthy?"; this asks "are this marketplace's published signals honest?" The two compose:
integrity findings defined here can inform a reputation layer. Coordinated-listing / Sybil detection
also appears in academic frameworks (e.g. Agent Bazaar, Magentic Marketplace); this specification's
contribution is a deployable, implementation-neutral, dependency-free formalization grounded in field
observation. See the repository README for a fuller comparison.

## Evolution

Indicator IDs are stable and will not be reused. New indicators receive new IDs. Threshold and
wording changes are minor versions; removing or redefining an indicator is a major version. New
indicators must be grounded in real, describable observations, and counter-examples that show an
indicator is too aggressive are equally welcome — propose either via a repository issue or pull
request.
