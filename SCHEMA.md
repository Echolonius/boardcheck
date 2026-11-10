# Listing schema

A listing is a JSON object. Only `id` and `created_at` are required; every other field is
optional, and any check that needs a missing field simply does not run for that listing
(one exception: AMS-007 treats a missing `has_escrow` as no escrow; see below).

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Stable identifier for the listing. |
| `created_at` | string (ISO 8601) | yes | When the listing was created. A trailing `Z` (UTC) is accepted. |
| `views` | integer | no | How many times the listing has been viewed. |
| `applications` | integer | no | How many applications/bids the listing has received. |
| `budget` | number | no | Advertised budget/price for the work. |
| `poster_type` | string | no | `"human"`, `"agent"`, or `"unknown"` (default). |
| `is_self_advertisement` | boolean | no | `true` if the listing is an agent advertising its own services rather than a buyer offering work. |
| `has_escrow` | boolean | no | Whether funds are escrowed before work begins. |
| `has_payment_evidence` | boolean | no | Whether the platform provides any verifiable record that priced work gets paid. |
| `requires_upfront_fee` | boolean | no | `true` if applying or bidding requires paying a fee or deposit first. Used by AMS-007. |
| `title` | string | no | The listing's title. Searched by AMS-006 and AMS-008. |
| `description` | string | no | The listing's description. Searched by AMS-006 and AMS-008. |
| `instructions` | string | no | Any instructions text on the listing. Searched by AMS-006 and AMS-008. |
| `has_prompt_injection` | boolean | no | `true` marks the listing as containing a prompt-injection payload (for example, one flagged by another tool); AMS-006 then fires without reading the text. |

**Unknown vs. false matters.** For boolean fields, `null`/omitted means *unknown* and is never
treated as `false`. For example, `unpaid_work_risk` fires only when escrow and payment-evidence
are both explicitly `false` — not when they are simply unrecorded. The one exception is
`has_escrow` in AMS-007 (below), where a missing value counts the same as `false`.

## AMS-006, AMS-007 and AMS-008

These checks were added after the first five and use the last five fields in the table.
AMS-006 and AMS-007 are severity `high`; AMS-008 is `high` or `warn`. Each gives at most one
finding per listing.

**AMS-006 `prompt_injection_payload`** fires when `has_prompt_injection` is `true`, or when the
listing's `title`, `description` and `instructions` (joined with spaces, letter case ignored)
contain any of these phrases:

`ignore previous instructions` · `ignore all previous instructions` · `system prompt:` ·
`system override` · `cat /etc/passwd` · `eval(` · `curl -s | bash` · `git push --force`

It is a plain text match on that fixed list: a reworded payload is not caught, and a harmless
listing that quotes one of these phrases is flagged. Missing or empty text fields are skipped,
and `has_prompt_injection: false` does not switch the text match off.

**AMS-007 `upfront_fee_gating`** fires when `requires_upfront_fee` is `true` and `has_escrow` is
anything other than `true` (`false`, `null` or missing). If `requires_upfront_fee` is anything
other than `true`, it stays silent.

**AMS-008 `agent_bait_listing`** reads the same three text fields as AMS-006 and flags text written
to bait an AI agent. Its one finding names every sign it found:

- `high`: the text asks for a private key, seed or recovery phrase, or an API/access token to be sent
  or pasted; or it tells the reader to download and run remote code (`curl … | python3`,
  `wget … && python3 v.py`, "download verify.py and run it").
- `warn`: it says human submissions will not be reviewed; links two or more escrow services on one
  line about escrow; promises automatic payout on merge or `/claim` with no escrow link or on-chain
  address to check; or hides text from people (zero-width characters, bidirectional control
  characters, or an HTML comment that addresses an AI reader or gives it an instruction, such as
  "AI agents: …", "if you are an LLM …", "ignore the above", or a hidden key request or
  download-and-run command). Merely mentioning AI does not count, so issue-template leftovers
  (`<!-- Describe the bug -->`) and AI-use disclosure questions (`<!-- Did you use AI to write
  this? -->`) stay clean.

Running the project's own tests (`pytest`, `npm test`, `python3 verify.py`) never counts, and if all
three text fields are missing or empty, AMS-008 stays silent. The full rules, guards and known false
positives are in [SPEC.md](SPEC.md#ams-008--agent-bait-listing).

**Where they run.** All three run in `scan()`, so in the library, the CLI and the `scan_listings`
MCP tool. The browser version on the site runs AMS-006 and AMS-008 but not AMS-007. The
single-listing `check_listing` MCP tool runs AMS-006, AMS-007 and AMS-008 as well, together with
AMS-001 and AMS-004 (the five checks that need only one listing). The report's `coverage` section
does not count these five fields.

## Example

```json
{
  "id": "job-1",
  "created_at": "2026-01-14T12:00:00Z",
  "views": 0,
  "applications": 24,
  "budget": 2500.0,
  "poster_type": "human",
  "is_self_advertisement": false,
  "has_escrow": false,
  "has_payment_evidence": false
}
```

See [`examples/sample_listings.json`](examples/sample_listings.json) for a full synthetic set.
