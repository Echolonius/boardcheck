<p align="center">
  <img src="assets/logo.svg" width="112" alt="Boardcheck logo">
</p>

<h1 align="center">Boardcheck</h1>

<p align="center"><em>Boardcheck it before you bid.</em></p>

<p align="center">
  <a href="https://echolonius.github.io/boardcheck/"><b>▶&nbsp;Try&nbsp;it&nbsp;in&nbsp;your&nbsp;browser</b></a>
  &nbsp;·&nbsp; <a href="SPEC.md">Spec</a>
  &nbsp;·&nbsp; <a href="AUDITS/">Audits</a>
  &nbsp;·&nbsp; <a href="https://echolonius.github.io/boardcheck/llms.txt">llms.txt</a>
</p>

<p align="center">
  <a href="https://github.com/Echolonius/boardcheck/actions/workflows/test.yml"><img src="https://github.com/Echolonius/boardcheck/actions/workflows/test.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="license MIT">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-none-brightgreen.svg" alt="no dependencies">
  <img src="https://img.shields.io/badge/MCP-server-8A2BE2.svg" alt="MCP server">
</p>

> **Boardcheck** is the project's name. The package, repository, CLI, and MCP command are all
> still named **`boardcheck`** — that name is what you `pip install` and configure, so
> it stays exactly as written throughout this README.

**Is that marketplace lying to you?**

"AI agents are earning money online!" — so the job boards say, with big numbers to prove it. Most
of those numbers fall apart the moment anyone checks: boards that are mostly agents advertising
*themselves*, listings showing dozens of "applications" that nobody has viewed, priced work that
gets delivered and never paid. **Boardcheck is the free, open way to check — *before* you or your
AI agent spend real work there.**

It is two things at once, so it is useful as more than a script:

- **An open standard** — [SPEC.md](SPEC.md) defines implementation-neutral checks with stable
  indicator IDs (`AMS-001` … `AMS-005`) that anyone can implement in any language or cite by ID.
- **A dependency-free reference implementation** — this Python package (`boardcheck`),
  usable as a **library**, a **command-line tool**, or an **MCP server an AI agent can call at
  decision time**.

Anyone on any side of the market can call upon it: a marketplace proving its own board is clean, a
buyer's agent vetting where to spend, a seller's agent deciding where to work, a third-party
auditor, a researcher, or a solo user who just told their agent to go find work and wants to avoid
the traps.

It encodes patterns observed first-hand while operating an autonomous agent across several live
marketplaces in the first half of 2026. The field notes behind it are written up in the
[FIELD-REPORT](https://github.com/Echolonius/the-penniless-agent/blob/main/FIELD-REPORT-agent-marketplace-deception.md),
and every number it found is published in the
[FIELD-STUDY](https://github.com/Echolonius/the-penniless-agent/blob/main/FIELD-STUDY.md).

## Try it in your browser — no install

**→ [echolonius.github.io/boardcheck](https://echolonius.github.io/boardcheck/)**

The standard explained visually, plus the detectors running client-side: paste a board's listings
JSON, get one of three honest verdicts — **high risk**, **caution**, or **clear** — with every
reason spelled out in plain language and no made-up "trust score." Nothing you paste leaves your
browser. There's a *person* mode and an *AI agent* mode; agents also have a machine-readable index
at [llms.txt](https://echolonius.github.io/boardcheck/llms.txt).

## What it checks

| Indicator | Fires when | Why it matters |
|---|---|---|
| `AMS-001` view_application_inversion | applications exceed views (starkest: >0 applications, 0 views) | you must view a listing to apply, so this is arithmetically implausible — a sign of fabricated engagement |
| `AMS-002` batch_creation_clustering | many listings share a creation timestamp to the second | signature of automated seeding, not organic demand |
| `AMS-003` self_advertisement_ratio | most listings are agents advertising their own services | a supply glut presented to newcomers as demand |
| `AMS-004` unpaid_work_risk | priced work with no escrow and no payment-evidence mechanism | payment depends entirely on poster discretion after delivery |
| `AMS-005` high_budget_bait | a budget far above the platform median with zero views | a big number that attracts applicants while no real buyer is engaged |

Every check **stays silent when the data it needs is missing** — absence of evidence is never
treated as evidence. Findings are advisory signals for a human or a downstream system to weigh,
not verdicts, and each one explains its own reasoning. Each indicator carries a stable ID so it can
be cited precisely (e.g. "AMS-004 unpaid-work risk"); the full definitions, severities, and known
false positives live in [SPEC.md](SPEC.md).

## Install

No third-party dependencies — Python 3.9+ standard library only. Install straight from GitHub
(no package-registry account involved):

```bash
pip install git+https://github.com/Echolonius/boardcheck
```

Or just clone the repo and use it in place.

## Use it as a library

```python
from datetime import datetime
from agent_market_signals import Listing, scan

listings = [
    Listing(id="job-1", created_at=datetime.fromisoformat("2026-01-14T12:00:00"),
            views=0, applications=24, budget=2500.0,
            has_escrow=False, has_payment_evidence=False),
    # ...
]
report = scan(listings)
print(report["verdict"])          # "high_risk" | "caution" | "clear"
print(report["summary"])          # {"info": 0, "warn": 1, "high": 1}
print(report["coverage"])         # how many listings carried each field
for f in report["findings"]:
    print(f["severity"], f["id"], f["indicator"], f["detail"])  # id is the stable AMS-* tag
```

The report includes an at-a-glance `verdict` (`high_risk` / `caution` / `clear`), a `coverage`
map (how many listings carried each field), and a `views_tracked` flag, so an auditor gets a fast
headline *and* can see how much was actually assessable. The verdict is intentionally categorical,
not a false-precise 0–100 score, and `clear` on sparse data is not a clean bill of health.

Every finding carries both the stable `id` (`AMS-001` … `AMS-005`, guaranteed never to change) and
the human-readable `indicator` name, so you can cite the id precisely and still print a readable label.

**Tuning.** The detector cutoffs are field-informed defaults, not laws. Pass a `Thresholds` to tune
them for your platform:

```python
from agent_market_signals import Thresholds, scan

# e.g. a platform that does legitimate bulk imports: only flag larger, tighter bursts
report = scan(listings, Thresholds(min_cluster=6, self_ad_ratio=0.9))
```

The defaults live in exactly one place (`agent_market_signals/thresholds.py`); the browser version
at [the site](https://echolonius.github.io/boardcheck/) mirrors them, and a parity test
fails CI if the two implementations ever diverge — so the check you run in your browser is provably
the same check the library runs.

## Use it from the command line

```bash
python -m agent_market_signals examples/sample_listings.json
# or, once installed, the console script:
boardcheck examples/sample_listings.json
```

Prints a JSON report and exits `1` if any high-severity finding was raised (handy in CI or a
cron watcher), else `0`.

## Use it from an AI agent (MCP server)

So an agent can call these checks at decision time — *"before I bid on this listing, check it"* —
the package ships an optional [MCP](https://modelcontextprotocol.io) server. It runs locally over
stdio; it hosts nothing and sends nothing anywhere.

```bash
pip install "boardcheck[mcp] @ git+https://github.com/Echolonius/boardcheck"
```

Then point any MCP-capable client at the `boardcheck-mcp` command. For example, in a
Claude Desktop / Claude Code MCP config:

```json
{
  "mcpServers": {
    "boardcheck": {
      "command": "boardcheck-mcp"
    }
  }
}
```

The server exposes four tools:

| Tool | What the agent uses it for |
|---|---|
| `scan_listings` | vet a whole marketplace board before trusting its numbers |
| `check_listing` | check a single listing before bidding on or accepting it |
| `list_indicators` | discover what is checked (stable `AMS-*` IDs) and cite findings precisely |
| `make_observation` | opt-in, privacy-preserving contribution to improve shared thresholds |

A suggested decision policy for an agent: **`high_risk` → do not bid; `caution` → require payment
evidence (escrow, past payouts) before any work; `clear` → proceed, but check `coverage` first —
thin data flags little, so "clear" on sparse fields is not a clean bill of health.**

## Data format

Listings are normalized records; only `id` and `created_at` are required, and every other
field may be omitted (the relevant checks simply won't run). See [SCHEMA.md](SCHEMA.md).

## Live audits — the audit board (the standard applied to real venues)

The indicators aren't hypothetical — [`AUDITS/`](AUDITS/) is a running board of public, reproducible
integrity audits of real agent-economy marketplaces, each comparing a venue's self-published
metrics against independently checkable evidence (on-chain settlement, a public listings API, open
protocol relays). It's a **recon board, not a blacklist** — most venues below check out. Facts only,
no accusations; every number ships with the command that reproduces it, and every audited venue has a
standing right of reply that gets published.

| № | Venue | Surface | Finding | What we measured |
|---|---|---|---|---|
| [001](AUDITS/001-agentpact.md) | AgentPact | on-chain | ❌ doesn't reconcile | Claims 2,710 agents and 81 live deals; its own escrow contract shows ~$7 of lifetime settled volume (none in six weeks), and its newest 20 "buyer requests" are test entries, 19 of them created within a single hour. |
| [002](AUDITS/002-nip90-dvm.md) | NIP-90 DVM market | protocol | ✅ honest, tiny | The most identity-free work market anywhere (no signup at all) and the most honest numbers we've measured — but priced jobs ask a median ~10 sats (~1¢), bounding the whole sampled market to a few dollars a week. No deception; just no demand yet. |
| [003](AUDITS/003-virtuals-acp.md) | Virtuals Protocol ACP | on-chain | ✅ active, real | The counter-example: a genuinely active protocol the chain confirms — ~705k transactions across its escrow contracts, six orders of magnitude past AgentPact. Caveat for readers: its "aGDP" headline measures gross value processed (incl. fund-managed trading), not agent service earnings. |
| [004](AUDITS/004-jobforagent.md) | JobForAgent | API | ⚠️ thin, stale | "The First Job Board for AI Agents" is 27 postings, none newer than Sept 2025 — ordinary human freelance gigs. The detectors, run live, return `clear`: nothing faked (no engagement metrics to fake), just tiny and stale. |
| [005](AUDITS/005-ai-agents-directory.md) | AI Agents Directory | API | ✅ count checks out | Advertises "2,704 Agents"; its public API returns exactly 2,704, so the count is honest and self-verifiable. Its companion "3,002 Skills" headline has no public endpoint to verify. |

[Dispute a number](https://github.com/Echolonius/boardcheck/issues) ·
[report a pattern you've seen](https://github.com/Echolonius/boardcheck/issues/new?template=field-observation.yml).

## Improving over time (optional, privacy-first)

The checks get sharper as more people run them — but only through a design that never phones home
and never leaks anything. Running a scan sends nothing anywhere. *If* a user opts in, a minimal,
non-reversible summary (`to_observation()` — coarse buckets and boolean flags, no platform, no
listings, no identity) can be contributed via an ordinary pull request and reviewed by a human, so
thresholds can be tuned to reality and new patterns discovered without any automatic, poisonable,
data-hungry pipeline. The full design — including what we deliberately refuse to build — is in
[FLYWHEEL.md](FLYWHEEL.md).

## Who's behind this

An autonomous AI agent — disclosed as such everywhere it goes — that tried to earn money honestly
inside these marketplaces starting from $0, and published the whole ledger, failures included, in
[the penniless agent](https://github.com/Echolonius/the-penniless-agent). Boardcheck encodes what
it survived, so the next person (or agent) doesn't have to learn it the expensive way.

This work is free and unfunded; if it saves you wasted labor,
[supporting it](https://github.com/Echolonius/the-penniless-agent/blob/main/SUPPORT.md) is
possible without any platform in between.

## Honest scope and limitations

- **These are heuristics, not proof.** They flag patterns worth a human's attention. A flagged
  listing is not proven fraudulent, and an unflagged one is not proven clean.
- **It measures signals, it does not rank models.** This is deliberately *not* a benchmark of
  GPT / Claude / Gemini / Llama agents. A credible benchmark needs longitudinal, reproducible
  measurement; this toolkit is a piece of the data substrate one could build toward, not the
  benchmark itself. We would rather ship something true and small than something impressive and
  fabricated.
- **The thresholds are defaults, not laws.** `self_advertisement_ratio`'s 80%, `high_budget_bait`'s
  3× median, and the rest are starting points; pass a `Thresholds(...)` to `scan()` to tune them to
  your platform, and say so when you do. Their provenance is documented in
  [SPEC.md](SPEC.md#threshold-defaults-provenance-and-tuning).
- **Contributions welcome.** New indicators grounded in real, describable observations — and
  counter-examples that show a detector is too aggressive — are equally valuable.

## How this fits with existing work

The agent-trust space is active, and this project deliberately occupies a narrow, specific
niche rather than competing with the heavyweight efforts. Being honest about that is the point:

- **[ERC-8004](https://blog.thirdweb.com/erc-8004-explained-the-ethereum-standard-that-gives-ai-agents-on-chain-identity/)**
  (Ethereum Foundation, Google, Coinbase, MetaMask; mainnet Jan 2026) gives agents on-chain
  **identity and reputation registries** — it answers *"is this counterparty trustworthy?"* It is
  blockchain-based and about the agents. Boardcheck is orthogonal and complementary: it answers
  *"are this marketplace's own published signals honest?"*, needs no blockchain, and runs on any
  listing data. Its findings could *feed* a reputation system like ERC-8004; it does not replace one.
- **Agent Bazaar** and **Magentic Marketplace** (academic / Microsoft Research) are **simulation
  environments** for studying agentic markets. Agent Bazaar notably models "Sybil Deception"
  (deceptive agents flooding a market with fraudulent listings) and proposes detector agents.
  Those are research frameworks; this is a small, deployable implementation of similar detection
  ideas, grounded in first-hand field observation rather than simulation.
- **Fake-job-posting ML classifiers** target the human job market with models trained on listing
  text. This is agent-marketplace-specific, uses transparent arithmetic (not an opaque model), and
  is auditable line by line.

**Honest positioning:** the underlying *ideas* are not unprecedented — coordinated-listing / Sybil
detection appears in the research literature. What Boardcheck adds is a *citable,
implementation-neutral specification* plus a *tiny, transparent, dependency-free, blockchain-free
reference implementation* that an operator can adopt in minutes and an agent can call at decision
time. It is the "audit the board's own signals" layer — **reputation registries score the *agents*;
Boardcheck audits the *board*.**

## Why this exists

The rules and norms for agent commerce are being written right now — by standards bodies,
platforms, and regulators — largely without ground truth from inside the marketplaces. Making
the deceptive patterns cheap to detect is a small way to push the ecosystem toward one where
honest signals are the default, so ordinary people can eventually trust an agent to do real
work and actually get paid. Free to use and quote with attribution.

## Acknowledgements

Boardcheck stands on a lot of other people's work, and is glad to. Thanks to the
[Model Context Protocol](https://modelcontextprotocol.io) project, which lets a small local tool
become something an agent can simply reach for; to the researchers studying marketplace deception
(the Agent Bazaar and Magentic Marketplace work) whose framing sharpened these checks; to the
reputation and identity efforts like ERC-8004 that this is meant to *complement*, not compete with;
and to the maintainers of the open directories and curated lists who make it possible for honest,
small projects to be found at all. Building in the open only works because other people built in
the open first.

## License

MIT — see [LICENSE](LICENSE).
