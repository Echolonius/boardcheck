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

import re
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
# AMS-008: agent-bait listing (text written for an AI agent, not a person)
# --------------------------------------------------------------------------
# The phrase patterns run on _flatten()ed text: hidden characters removed,
# ASCII letters lower-cased, curly apostrophes straightened, Markdown * and `
# dropped, and every run of whitespace turned into one space. The browser port
# (docs/boardcheck.js) builds the same patterns from the same text, and
# tests/test_parity.py checks that both give the same findings. re.ASCII keeps
# \b on ASCII word characters, as in JavaScript.

_HIDDEN_ALL_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069]")
_APOSTROPHE_RE = re.compile("[\u2018\u2019\u02bc]")
_EMPHASIS_RE = re.compile("[*`]")
_SPACES_RE = re.compile(
    "[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)
_ASCII_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
)


def _flatten(text: str) -> str:
    text = _HIDDEN_ALL_RE.sub("", text)
    text = _APOSTROPHE_RE.sub("'", text)
    text = _EMPHASIS_RE.sub("", text)
    return _SPACES_RE.sub(" ", text.translate(_ASCII_LOWER))


_W = r"[^ .;!?]+"  # one word that does not cross the end of a sentence
_Q = "[\"']"
# A negation right before the verb ("never share", "you will never be asked to
# send") is captured in group 1; a match with group 1 set does not count.
_NEG = (
    r"(\b(?:never|not|don't|dont|doesn't|won't|wont|shouldn't|mustn't|can't|cannot|no one|nobody) "
    r"(?:(?:ever|be|been|asked|ask|asks|required|told|need|needs|have|has|to|you|anyone|anybody|we"
    r"|will|would|should|must|under|any|circumstances,?) )*)?"
)
_YOUR = r" (?:" + _W + r" ){0,2}?your (?:" + _W + r" ){0,2}?"
_WALLET_SECRET = (
    r"(?:private keys?|priv keys?|seed phrases?|seed words|recovery phrases?|recovery words"
    r"|secret phrases?|mnemonic(?: phrases?| words)?|(?:12|24)[- ]word (?:seed |recovery |secret )?phrases?"
    r"|wallet keys?|keystore(?: files?)?)"
)
_API_SECRET = (
    r"(?:api keys?|api tokens?|access tokens?|auth tokens?|authentication tokens?|bearer tokens?"
    r"|session tokens?|oauth tokens?|refresh tokens?|secret keys?|personal access tokens?"
    r"|(?:github|gh|gitlab|npm|pypi|openai|anthropic) (?:api )?(?:tokens?|keys?))"
)
_SEND = (
    r"(?:send(?:ing)?|shar(?:e|ing)|submit(?:ting)?|past(?:e|ing)|post(?:ing)?|upload(?:ing)?"
    r"|reveal(?:ing)?|disclos(?:e|ing)|forward(?:ing)?|hand(?:ing)? over|dm|e-?mail(?:ing)?"
    r"|repl(?:y|ying) with|respond(?:ing)? with|comment(?:ing)? with)"
)
_SEND_TO_THREAD = (
    r"(?:dm|e-?mail(?:ing)?|repl(?:y|ying) with|respond(?:ing)? with|comment(?:ing)? with)"
)
_SOFT = r"(?:provid(?:e|ing)|enter(?:ing)?|input(?:ting)?|typ(?:e|ing)|includ(?:e|ing))"
_DEST = (
    r"(?: " + _W + r"){0,4}? (?:to us|to me|with us|with me"
    r"|to the (?:operator|maintainers?|sponsors?|escrow|verifier|bot|team|organizers?|admins?|poster)"
    r"|to (?:this|our|that|the following) (?:address|email|form|link|bot|account)"
    r"|here|below"
    r"|in (?:this|the|a|your|our) (?:issue|comment|thread|pr|pull request|form|reply|discussion|chat|dm|message|ticket)"
    r"|(?:via|by|over|through|on) (?:dm|email|e-mail|telegram|discord|whatsapp|signal|the form|our form|the bot))\b"
)
# A wallet secret (private key, seed or recovery phrase) is flagged whenever it
# is to be sent, shared or pasted; an API or access token only when it is to be
# sent to the poster or posted in public, since using one locally is ordinary.
_SECRET_RE = re.compile(
    _NEG + r"\b(?:"
    + _SEND + _YOUR + _WALLET_SECRET + r"\b"
    + r"|(?:giv(?:e|ing)|tell(?:ing)?) (?:us|me|them|the " + _W + r") your (?:" + _W + r" ){0,2}?"
    + r"(?:" + _WALLET_SECRET + r"|" + _API_SECRET + r")\b"
    + r"|" + _SEND_TO_THREAD + _YOUR + _API_SECRET + r"\b"
    + r"|(?:" + _SEND + r"|" + _SOFT + r")" + _YOUR + r"(?:" + _WALLET_SECRET + r"|" + _API_SECRET + r")\b"
    + _DEST
    + r")",
    re.A,
)

_FETCH = r"(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)"
_RUNNER = r"(?:(?:ba|z|da|k)?sh|python[0-9.]*|py|node|nodejs|deno|bun|perl|ruby|php|pwsh|powershell)"
_CODE_FILE = r"\.(?:py|sh|bash|js|mjs|cjs|pl|rb|ps1|php|exe|bin|appimage)\b"
_CODE_OBJECT = (
    r"(?:[^ ]+" + _CODE_FILE
    + r"|scripts?\b|binary\b|binaries\b|installers?\b|verifiers?\b|executables?\b)"
)
# Remote code piped or substituted straight into a shell or interpreter. Piping
# into "python -m json.tool", "node -e ..." or "python3 script.py" feeds data to
# local code, so it does not count.
_REMOTE_EXEC_RES = (
    re.compile(
        r"\b" + _FETCH + r"\b(?: [^ |;&]+)+ ?\| ?(?:sudo(?: -[a-z]+)* )?(?:" + _RUNNER
        + r"|iex|invoke-expression)\b(?! -[mce]\b)(?! [^ ]+\.(?:py|js|mjs|cjs|ts|sh|pl|rb|php)\b)",
        re.A,
    ),
    re.compile(
        r"(?:\b(?:" + _RUNNER + r"|source) <\( ?|\beval " + _Q + r"?\$\( ?|\b" + _RUNNER
        + r" -c " + _Q + r"?\$\( ?)" + _FETCH + r"\b",
        re.A,
    ),
    re.compile(
        r"\b(?:iex|invoke-expression) ?\(? ?(?:iwr|irm|invoke-webrequest|invoke-restmethod"
        r"|\(?new-object (?:system\.)?net\.webclient\)?\.downloadstring)\b",
        re.A,
    ),
    re.compile(
        r"\b(?:curl|wget)\b[^|;&]{0,200}?" + _CODE_FILE + r"[^|;&]{0,200}?(?:&&|;) ?"
        r"(?:sudo(?: -[a-z]+)* )?(?:" + _RUNNER + r" |chmod \+x |\./)",
        re.A,
    ),
)
# "Download verify.py and run it" in words. Negations count here too.
_DOWNLOAD_RUN_RES = (
    re.compile(
        _NEG + r"\bdownload(?:ing)? (?:" + _W + r" ){0,4}?" + _CODE_OBJECT
        + r"(?: [^ ;!?]+){0,8}?(?:,? (?:and|then|&&)(?: then)?|,(?: then)?) "
        r"(?:run|execute|exec|launch|invoke)(?: it\b| this\b| that\b| them\b"
        r"| the (?:script|file|verifier|binary|installer|executable|tool)\b"
        r"| [^ ]+" + _CODE_FILE + r"|(?= ?[.;!?,)]|(?![\s\S])))",
        re.A,
    ),
    re.compile(
        _NEG + r"\bdownload(?: and|,| &| \+) ?(?:then )?(?:run|execute|exec)\b (?:" + _W + r" ){0,3}?"
        + _CODE_OBJECT,
        re.A,
    ),
)

_SUBMITTERS = (
    r"(?:pull requests?|prs?|submissions?|contributions?|solutions?|entries|applications?|patches"
    r"|commits|engineers?|developers?|contributors?|solvers?|applicants?|participants?|attempts?)"
)
_NOT_REVIEWED = (
    r"(?:(?:(?:are|is|will|would|shall|do|does|can|get|gets)(?: not| never) (?:be |get )?"
    r"|(?:aren't|isn't|won't|wont|don't|doesn't|can't|cannot) (?:be |get )?)"
    r"(?:reviewed|accepted|considered|merged|evaluated|eligible|paid|read|looked at|welcome)"
    r"|(?:are|is|will be|get|gets) (?:automatically |silently )?"
    r"(?:ignored|rejected|discarded|auto-?closed|closed without review))"
)
_NO_HUMANS_RE = re.compile(
    r"\b(?:human|manual)(?:ly)?(?:[- ](?:written|made|authored|created|submitted|opened))? (?:"
    + _W + r" ){0,3}?" + _SUBMITTERS + r"\b(?: " + _W + r"){0,4}? " + _NOT_REVIEWED
    + r"|\b(?:pull requests?|prs?|submissions?|contributions?|solutions?|patches|entries)"
    r" (?:from|by|made by|written by|opened by|submitted by) (?:a |the )?(?:humans?|people|persons?"
    r"|human (?:engineers?|developers?|contributors?|beings?|authors?)|manual (?:contributors?|solvers?))\b"
    r"(?: " + _W + r"){0,3}? " + _NOT_REVIEWED
    + r"|\bhumans? (?:need not|should not|shouldn't|must not|mustn't|may not|cannot|can't|do not|don't)"
    r" (?:apply|submit|contribute|bother|open)\b"
    r"|\bno (?:human|manual) (?:pull requests?|prs?|submissions?|contributions?|solutions?|applications?"
    r"|entries|patches|applicants?|solvers?)\b"
    r"|\bonly (?:(?:accepts?|accepting|for|from|by|via) )?(?:(?:submissions|pull requests|prs|solutions) )?"
    r"(?:(?:from|by|via) )?(?:fully )?automated (?:agents?|runners?|solvers?|bots?|submissions?|pipelines?"
    r"|pull requests?|prs?|contributions?|solutions?)\b"
    r"|\bautomated (?:agents?|runners?|solvers?|bots?|submissions?) only\b",
    re.A,
)

_AUTO_PAYOUT_RE = re.compile(
    r"(?:^|[^a-z0-9/])/(?:claim|attempt)\b"
    r"|\b(?:paid|pays?|paying|payouts?|payments?|released?|disbursed|rewards?|rewarded|transferred)\b"
    r"(?: " + _W + r"){0,3}? (?:automatically|instantly|auto-?magically)\b(?: " + _W + r"){0,3}?"
    r" (?:on|upon|after|at|when|once)\b(?: " + _W + r"){0,3}? merg(?:e|ed|es|ing)\b"
    r"|\b(?:automatic(?:ally)?|auto|instant(?:ly)?)[- ]?(?:paid|payouts?|payments?|released?|disbursed"
    r"|rewarded|transferred)\b(?: " + _W + r"){0,4}? (?:on|upon|after|at|when|once)\b(?: " + _W
    + r"){0,3}? merg(?:e|ed|es|ing)\b",
    re.A,
)
# Something a reader can look up for this exact bounty: a link with a path on a
# named host (a bare home page or an IP address does not count), or an on-chain
# address or transaction hash.
_CHECKABLE_RE = re.compile(
    r"https?://(?![0-9.]+(?::[0-9]+)?/)[a-z0-9-]+(?:\.[a-z0-9-]+)+(?::[0-9]+)?/[^ ]*[a-z0-9]"
    r"|\b0x[0-9a-f]{40}(?:[0-9a-f]{24})?\b",
    re.A,
)
_ESCROW_WORD_RE = re.compile(r"\bescrow", re.A)
_URL_HOST_RE = re.compile(r"https?://([a-z0-9.-]+)", re.A)
_LINE_BREAK_RE = re.compile("\r\n|[\n\r\u2028\u2029]")
_CODE_HOSTS = ("github.com", "githubusercontent.com", "gitlab.com")

_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_BIDI_CONTROL_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")
# Joiners that belong where they are: inside emoji sequences, and between
# letters of Arabic-script and Indic-script words.
_JOINER_OK_RE = re.compile(
    "(?<=[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\u0900-\u0dff\ufb50-\ufdff\ufe70-\ufefc])"
    "[\u200c\u200d]"
    "(?=[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\u0900-\u0dff\ufb50-\ufdff\ufe70-\ufefc])"
    "|(?<=[\U0001f000-\U0001ffff\u2600-\u27bf\ufe0f])\u200d(?=[\U0001f000-\U0001ffff\u2600-\u27bf])"
)
_HTML_COMMENT_RE = re.compile(r"<!--([\s\S]*?)(?:-->|(?![\s\S]))")
# An HTML comment counts only when it addresses an AI reader or gives it an
# instruction, or (see _comment_aims_at_ai) would trip the secret or
# remote-code test on its own. Merely mentioning AI does not count, so
# AI-use disclosure questions ("Did you use AI or GPT to write this?") and
# template leftovers ("<!-- Describe the bug -->") stay clean.
_ADDRESSEE = (
    r"(?:ai (?:agents?|assistants?|models?|systems?|readers?|bots?)|(?<!user )(?<!user-)agents?"
    r"|assistants?|llms?|large language models?|language models?|bots?)"
)
_AI_NAME = r"(?:ai|chatgpt|gpt|claude|copilot|gemini)"
_READER = r"(?:" + _ADDRESSEE + r"|" + _AI_NAME + r")\b(?![-'])"
_READER_LIST = r"(?:(?:(?:,| or| and) | ?/ ?)(?:the )?" + _READER + r")*"
_SENTENCE_START = r"(?:^ ?|[.!?;] )"
_ORDER = (
    r"(?:(?:also|please|now|then|first|always|you must|you should|make sure to|remember to"
    r"|do not|don't|never) )*(?:post|send|share|paste|run|execute|approve|merge|ignore|disregard"
    r"|forget|reply|respond|answer|write|add|change|replace|update|delete|remove|summari[sz]e|say"
    r"|tell|include|use|output|print|return|call|open|click|visit|follow|transfer|pay|skip|mark"
    r"|rate|give|leave|comment|set|treat|act|pretend|translate|classify|label|recommend)\b"
)
_AI_READER_RE = re.compile(
    # "AI agents: ...", "Assistant: ...", or a model's name followed by an
    # order ("Claude, Copilot or Gemini: reply in French"); a bare form field
    # such as "Copilot: [ ]" or "AI: none" does not count.
    _SENTENCE_START + r"(?:the |any |all |every )?" + _ADDRESSEE + r"\b(?![-'])" + _READER_LIST
    + r" ?:"
    + r"|" + _SENTENCE_START + r"(?:the |any |all |every )?" + _READER + _READER_LIST + r" ?: ?"
    + _ORDER
    # "dear AI,", "hey Claude,", "note to AI:", "message for the agent:"
    + r"|\b(?:hey|hi|hello|dear|(?:a )?(?:note|message|memo|reminder|hint|tip) (?:to|for))"
    r" (?:the |any |all |every |an? )?" + _READER + _READER_LIST + r"(?= ?[:,.!?;)]| ?(?![\s\S]))"
    # "to any AI reading this", "To the agent: ..."
    + r"|\bto (?:the |any |all |every |an? )?" + _READER + r"(?: (?:that is|who is|that's|who's))?"
    r" (?:reading|processing|reviewing|parsing|scanning|summari[sz]ing|seeing|viewing)"
    r" (?:this|these|it|the)\b"
    + r"|" + _SENTENCE_START + r"to (?:the |any |all |every )?" + _READER + _READER_LIST + r" ?[:,]"
    # "if you are an AI / a bot / an LLM / an agent"
    + r"|\bif you(?: are|'re| re) (?:an? |the )?(?:ai (?:model|agent|assistant)|ai|llm|bot|agent"
    r"|assistant|automated|autonomous|large language model|language model|model)\b(?![-'])"
    r"(?= ?[:,.!?;)]| ?(?![\s\S])| (?:reading|processing|reviewing|parsing|scanning|summari[sz]ing"
    r"|and you|you must|you should|please|agents?|assistants?|bots?|systems?|models?)\b)"
    # injected-instruction phrasing
    r"|\b(?:ignore|disregard) (?:all |any |the )?(?:previous|above|prior|earlier|preceding)\b"
    r"|\bsystem prompt\b"
    r"|\binstructions? (?:to|for) (?:the |any |all |every |an? )?(?:ai|agents?|assistants?|llms?"
    r"|models?|bots?|language models?)\b(?![-'])",
    re.A,
)

_BAIT_SECRET = "asks for a private key, seed phrase or API/access token to be sent or pasted"
_BAIT_REMOTE_CODE = "tells the solver to download and run remote code"
_BAIT_NO_HUMANS = (
    "says human submissions will not be reviewed or that only automated solvers are accepted"
)
_BAIT_ESCROWS = "names several escrow services for one bounty"
_BAIT_AUTO_PAYOUT = (
    "promises automatic payout on merge or claim with no escrow link or on-chain address to check"
)


def _affirmed(pattern: "re.Pattern[str]", text: str) -> bool:
    """True if ``pattern`` matches somewhere without its negation group (1)."""
    return any(m.group(1) is None for m in pattern.finditer(text))


def _asks_for_secret(flat: str) -> bool:
    return _affirmed(_SECRET_RE, flat)


def _runs_remote_code(flat: str) -> bool:
    return any(p.search(flat) for p in _REMOTE_EXEC_RES) or any(
        _affirmed(p, flat) for p in _DOWNLOAD_RUN_RES
    )


def _comment_aims_at_ai(body: str) -> bool:
    flat = _flatten(body)
    return bool(
        _AI_READER_RE.search(flat) or _asks_for_secret(flat) or _runs_remote_code(flat)
    )


def _several_escrows(parts: list[str]) -> bool:
    """A line that mentions escrow and links two or more different hosts
    (code hosts such as github.com are not counted)."""
    for part in parts:
        for line in _LINE_BREAK_RE.split(part):
            line = _flatten(line)
            if not _ESCROW_WORD_RE.search(line):
                continue
            hosts = set()
            for m in _URL_HOST_RE.finditer(line):
                host = m.group(1).rstrip(".")
                if host.startswith("www."):
                    host = host[4:]
                if not host or any(
                    host == h or host.endswith("." + h) for h in _CODE_HOSTS
                ):
                    continue
                hosts.add(host)
            if len(hosts) >= 2:
                return True
    return False


def _hidden_text_kinds(raw: str) -> list[str]:
    kinds = []
    if _ZERO_WIDTH_RE.search(_JOINER_OK_RE.sub("", raw)):
        kinds.append("zero-width characters")
    if _BIDI_CONTROL_RE.search(raw):
        kinds.append("bidirectional control characters")
    if any(_comment_aims_at_ai(m.group(1)) for m in _HTML_COMMENT_RE.finditer(raw)):
        kinds.append("HTML comment aimed at an AI reader")
    return kinds


def agent_bait_listing(listing: Listing) -> Optional[Finding]:
    """Listing text written to bait an AI agent rather than to hire anyone.
    (Indicator AMS-008.)

    ``high`` when the text asks for a private key, seed phrase or API/access
    token to be sent or pasted, or tells the solver to download and run remote
    code (``curl ... | python3``, "download verify.py and run it"). ``warn``
    when it says human submissions will not be reviewed, names several escrow
    services for one bounty, promises automatic payout on merge or ``/claim``
    with nothing to check, or carries hidden text an agent would read but a
    person would not see (zero-width or bidirectional control characters, or an
    HTML comment that addresses an AI reader or gives it an instruction;
    merely mentioning AI does not count, so disclosure questions and template
    leftovers such as ``<!-- Describe the bug -->`` stay clean). At most one
    finding per listing, naming every sign found. Running the project's own tests
    (``pytest``, ``npm test``, "make the tests pass") is not a sign. Silent
    when the listing has no text.
    """
    parts = [
        p
        for p in (listing.title, listing.description, listing.instructions)
        if isinstance(p, str) and p
    ]
    if not parts:
        return None
    # A byte-order mark at the very start of a field is an encoding artifact,
    # not hidden text.
    parts = [p[1:] if p.startswith("\ufeff") else p for p in parts]
    raw = " ".join(parts)
    flat = _flatten(raw)

    signs = []
    high = False
    if _asks_for_secret(flat):
        signs.append(_BAIT_SECRET)
        high = True
    if _runs_remote_code(flat):
        signs.append(_BAIT_REMOTE_CODE)
        high = True
    if _NO_HUMANS_RE.search(flat):
        signs.append(_BAIT_NO_HUMANS)
    if _several_escrows(parts):
        signs.append(_BAIT_ESCROWS)
    if _AUTO_PAYOUT_RE.search(flat) and not _CHECKABLE_RE.search(flat):
        signs.append(_BAIT_AUTO_PAYOUT)
    kinds = _hidden_text_kinds(raw)
    if kinds:
        signs.append(
            "hidden text an agent would read but a person wouldn't see ("
            + ", ".join(kinds)
            + ")"
        )
    if not signs:
        return None
    return Finding(
        "agent_bait_listing",
        "high" if high else "warn",
        "listing text aimed at AI agents: " + "; ".join(signs),
        listing.id,
    )


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
        result = agent_bait_listing(listing)
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
