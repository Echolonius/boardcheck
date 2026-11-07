"use strict";
/* Boardcheck detectors — the single browser-side implementation.
 *
 * This is a faithful port of agent_market_signals/detectors.py (the reference
 * implementation), except that it does not run AMS-007. It runs AMS-008 with
 * the same patterns as the reference (see agentBait below). Same semantics:
 * unknown (null/missing) is never treated as false; views_tracked is inferred
 * once per scan; the verdict is categorical, never a false-precise 0-100 score.
 * In the reference, AMS-007 is the one exception to the null rule: it counts a
 * missing has_escrow as no escrow.
 *
 * ONE source, two consumers: docs/index.html loads this in the browser, and
 * tests/parity_runner.js loads the very same file under Node so that
 * tests/test_parity.py can prove this port and the Python reference produce
 * identical findings on a shared fixture battery. Edit the algorithm here, not
 * inside index.html.
 *
 * THRESHOLDS mirrors agent_market_signals/thresholds.py — those Python defaults
 * are canonical, and the parity test fails CI if these numbers ever drift from
 * them. Change a threshold in BOTH places or the build goes red.
 */
var THRESHOLDS = {
  selfAdRatio: 0.80,   // AMS-003 fires at/above this share of self-ads
  budgetMultiple: 3.0, // AMS-005: budget >= this * median, with 0 views
  minCluster: 3,       // AMS-002: this many listings in one window
  windowSeconds: 1     // AMS-002: width of the batch-creation window (seconds)
};

function norm(item) {
  var s = String(item.created_at);
  // No timezone designator? Interpret as UTC — same rule as the Python
  // reference (parse_created_at) — so AMS-002 time buckets do not depend on the
  // viewer's local timezone.
  if (!/[Zz]$|[+-]\d\d:?\d\d$/.test(s)) s = (s.indexOf("T") === -1 ? s + "T00:00:00" : s) + "Z";
  var t = Date.parse(s);
  if (Number.isNaN(t)) throw new Error("bad created_at on listing " + String(item.id));
  return {
    id: String(item.id),
    ts: Math.floor(t / 1000),
    views: item.views ?? null,
    applications: item.applications ?? null,
    budget: item.budget ?? null,
    is_self_advertisement: item.is_self_advertisement ?? null,
    has_escrow: item.has_escrow ?? null,
    has_payment_evidence: item.has_payment_evidence ?? null,
    has_prompt_injection: item.has_prompt_injection ?? null,
    text: [item.title, item.description, item.instructions].filter(Boolean).join(" ").toLowerCase(),
    texts: [item.title, item.description, item.instructions].filter(p => typeof p === "string" && p !== "")
  };
}

// AMS-008 (agent-bait listing). The pattern text below is the same as in
// agent_market_signals/detectors.py, piece for piece; only the astral emoji
// range is written differently (\u{1F000} here, \U0001F000 in Python). The "u"
// flag makes JavaScript count code points, as Python does, and keeps \b on
// ASCII word characters, as Python's re.ASCII does. tests/test_parity.py checks
// that both ports give the same findings.
var agentBait = (function () {
  var R = String.raw;
  function flatten(s) {
    return s.replace(/[\u200B\u200C\u200D\u2060\uFEFF\u202A-\u202E\u2066-\u2069]/gu, "")
      .replace(/[\u2018\u2019\u02BC]/gu, "'")
      .replace(/[*`]/gu, "")
      .replace(/[A-Z]/gu, function (c) { return c.toLowerCase(); })
      .replace(/[\t\n\v\f\r \u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+/gu, " ");
  }
  var W = R`[^ .;!?]+`;
  var Q = "[\"']";
  var NEG = R`(\b(?:never|not|don't|dont|doesn't|won't|wont|shouldn't|mustn't|can't|cannot|no one|nobody) ` +
    R`(?:(?:ever|be|been|asked|ask|asks|required|told|need|needs|have|has|to|you|anyone|anybody|we` +
    R`|will|would|should|must|under|any|circumstances,?) )*)?`;
  var YOUR = R` (?:` + W + R` ){0,2}?your (?:` + W + R` ){0,2}?`;
  var WALLET_SECRET = R`(?:private keys?|priv keys?|seed phrases?|seed words|recovery phrases?|recovery words` +
    R`|secret phrases?|mnemonic(?: phrases?| words)?|(?:12|24)[- ]word (?:seed |recovery |secret )?phrases?` +
    R`|wallet keys?|keystore(?: files?)?)`;
  var API_SECRET = R`(?:api keys?|api tokens?|access tokens?|auth tokens?|authentication tokens?|bearer tokens?` +
    R`|session tokens?|oauth tokens?|refresh tokens?|secret keys?|personal access tokens?` +
    R`|(?:github|gh|gitlab|npm|pypi|openai|anthropic) (?:api )?(?:tokens?|keys?))`;
  var SEND = R`(?:send(?:ing)?|shar(?:e|ing)|submit(?:ting)?|past(?:e|ing)|post(?:ing)?|upload(?:ing)?` +
    R`|reveal(?:ing)?|disclos(?:e|ing)|forward(?:ing)?|hand(?:ing)? over|dm|e-?mail(?:ing)?` +
    R`|repl(?:y|ying) with|respond(?:ing)? with|comment(?:ing)? with)`;
  var SEND_TO_THREAD = R`(?:dm|e-?mail(?:ing)?|repl(?:y|ying) with|respond(?:ing)? with|comment(?:ing)? with)`;
  var SOFT = R`(?:provid(?:e|ing)|enter(?:ing)?|input(?:ting)?|typ(?:e|ing)|includ(?:e|ing))`;
  var DEST = R`(?: ` + W + R`){0,4}? (?:to us|to me|with us|with me` +
    R`|to the (?:operator|maintainers?|sponsors?|escrow|verifier|bot|team|organizers?|admins?|poster)` +
    R`|to (?:this|our|that|the following) (?:address|email|form|link|bot|account)` +
    R`|here|below` +
    R`|in (?:this|the|a|your|our) (?:issue|comment|thread|pr|pull request|form|reply|discussion|chat|dm|message|ticket)` +
    R`|(?:via|by|over|through|on) (?:dm|email|e-mail|telegram|discord|whatsapp|signal|the form|our form|the bot))\b`;
  var SECRET = new RegExp(NEG + R`\b(?:` +
    SEND + YOUR + WALLET_SECRET + R`\b` +
    R`|(?:giv(?:e|ing)|tell(?:ing)?) (?:us|me|them|the ` + W + R`) your (?:` + W + R` ){0,2}?` +
    R`(?:` + WALLET_SECRET + R`|` + API_SECRET + R`)\b` +
    R`|` + SEND_TO_THREAD + YOUR + API_SECRET + R`\b` +
    R`|(?:` + SEND + R`|` + SOFT + R`)` + YOUR + R`(?:` + WALLET_SECRET + R`|` + API_SECRET + R`)\b` +
    DEST + R`)`, "gu");

  var FETCH = R`(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)`;
  var RUNNER = R`(?:(?:ba|z|da|k)?sh|python[0-9.]*|py|node|nodejs|deno|bun|perl|ruby|php|pwsh|powershell)`;
  var CODE_FILE = R`\.(?:py|sh|bash|js|mjs|cjs|pl|rb|ps1|php|exe|bin|appimage)\b`;
  var CODE_OBJECT = R`(?:[^ ]+` + CODE_FILE +
    R`|scripts?\b|binary\b|binaries\b|installers?\b|verifiers?\b|executables?\b)`;
  var REMOTE_EXEC = [
    new RegExp(R`\b` + FETCH + R`\b(?: [^ |;&]+)+ ?\| ?(?:sudo(?: -[a-z]+)* )?(?:` + RUNNER +
      R`|iex|invoke-expression)\b(?! -[mce]\b)(?! [^ ]+\.(?:py|js|mjs|cjs|ts|sh|pl|rb|php)\b)`, "u"),
    new RegExp(R`(?:\b(?:` + RUNNER + R`|source) <\( ?|\beval ` + Q + R`?\$\( ?|\b` + RUNNER +
      R` -c ` + Q + R`?\$\( ?)` + FETCH + R`\b`, "u"),
    new RegExp(R`\b(?:iex|invoke-expression) ?\(? ?(?:iwr|irm|invoke-webrequest|invoke-restmethod` +
      R`|\(?new-object (?:system\.)?net\.webclient\)?\.downloadstring)\b`, "u"),
    new RegExp(R`\b(?:curl|wget)\b[^|;&]{0,200}?` + CODE_FILE + R`[^|;&]{0,200}?(?:&&|;) ?` +
      R`(?:sudo(?: -[a-z]+)* )?(?:` + RUNNER + R` |chmod \+x |\./)`, "u")
  ];
  var DOWNLOAD_RUN = [
    new RegExp(NEG + R`\bdownload(?:ing)? (?:` + W + R` ){0,4}?` + CODE_OBJECT +
      R`(?: [^ ;!?]+){0,8}?(?:,? (?:and|then|&&)(?: then)?|,(?: then)?) ` +
      R`(?:run|execute|exec|launch|invoke)(?: it\b| this\b| that\b| them\b` +
      R`| the (?:script|file|verifier|binary|installer|executable|tool)\b` +
      R`| [^ ]+` + CODE_FILE + R`|(?= ?[.;!?,)]|(?![\s\S])))`, "gu"),
    new RegExp(NEG + R`\bdownload(?: and|,| &| \+) ?(?:then )?(?:run|execute|exec)\b (?:` + W + R` ){0,3}?` +
      CODE_OBJECT, "gu")
  ];

  var SUBMITTERS = R`(?:pull requests?|prs?|submissions?|contributions?|solutions?|entries|applications?|patches` +
    R`|commits|engineers?|developers?|contributors?|solvers?|applicants?|participants?|attempts?)`;
  var NOT_REVIEWED = R`(?:(?:(?:are|is|will|would|shall|do|does|can|get|gets)(?: not| never) (?:be |get )?` +
    R`|(?:aren't|isn't|won't|wont|don't|doesn't|can't|cannot) (?:be |get )?)` +
    R`(?:reviewed|accepted|considered|merged|evaluated|eligible|paid|read|looked at|welcome)` +
    R`|(?:are|is|will be|get|gets) (?:automatically |silently )?` +
    R`(?:ignored|rejected|discarded|auto-?closed|closed without review))`;
  var NO_HUMANS = new RegExp(
    R`\b(?:human|manual)(?:ly)?(?:[- ](?:written|made|authored|created|submitted|opened))? (?:` +
    W + R` ){0,3}?` + SUBMITTERS + R`\b(?: ` + W + R`){0,4}? ` + NOT_REVIEWED +
    R`|\b(?:pull requests?|prs?|submissions?|contributions?|solutions?|patches|entries)` +
    R` (?:from|by|made by|written by|opened by|submitted by) (?:a |the )?(?:humans?|people|persons?` +
    R`|human (?:engineers?|developers?|contributors?|beings?|authors?)|manual (?:contributors?|solvers?))\b` +
    R`(?: ` + W + R`){0,3}? ` + NOT_REVIEWED +
    R`|\bhumans? (?:need not|should not|shouldn't|must not|mustn't|may not|cannot|can't|do not|don't)` +
    R` (?:apply|submit|contribute|bother|open)\b` +
    R`|\bno (?:human|manual) (?:pull requests?|prs?|submissions?|contributions?|solutions?|applications?` +
    R`|entries|patches|applicants?|solvers?)\b` +
    R`|\bonly (?:(?:accepts?|accepting|for|from|by|via) )?(?:(?:submissions|pull requests|prs|solutions) )?` +
    R`(?:(?:from|by|via) )?(?:fully )?automated (?:agents?|runners?|solvers?|bots?|submissions?|pipelines?` +
    R`|pull requests?|prs?|contributions?|solutions?)\b` +
    R`|\bautomated (?:agents?|runners?|solvers?|bots?|submissions?) only\b`, "u");

  var AUTO_PAYOUT = new RegExp(
    R`(?:^|[^a-z0-9/])/(?:claim|attempt)\b` +
    R`|\b(?:paid|pays?|paying|payouts?|payments?|released?|disbursed|rewards?|rewarded|transferred)\b` +
    R`(?: ` + W + R`){0,3}? (?:automatically|instantly|auto-?magically)\b(?: ` + W + R`){0,3}?` +
    R` (?:on|upon|after|at|when|once)\b(?: ` + W + R`){0,3}? merg(?:e|ed|es|ing)\b` +
    R`|\b(?:automatic(?:ally)?|auto|instant(?:ly)?)[- ]?(?:paid|payouts?|payments?|released?|disbursed` +
    R`|rewarded|transferred)\b(?: ` + W + R`){0,4}? (?:on|upon|after|at|when|once)\b(?: ` + W +
    R`){0,3}? merg(?:e|ed|es|ing)\b`, "u");
  var CHECKABLE = new RegExp(
    R`https?://(?![0-9.]+(?::[0-9]+)?/)[a-z0-9-]+(?:\.[a-z0-9-]+)+(?::[0-9]+)?/[^ ]*[a-z0-9]` +
    R`|\b0x[0-9a-f]{40}(?:[0-9a-f]{24})?\b`, "u");
  var ESCROW_WORD = new RegExp(R`\bescrow`, "u");
  var URL_HOST = new RegExp(R`https?://([a-z0-9.-]+)`, "gu");
  var LINE_BREAK = /\r\n|[\n\r\u2028\u2029]/u;
  var CODE_HOSTS = ["github.com", "githubusercontent.com", "gitlab.com"];

  var ZERO_WIDTH = /[\u200B\u200C\u200D\u2060\uFEFF]/u;
  var BIDI_CONTROL = /[\u202A-\u202E\u2066-\u2069]/u;
  var JOINER_OK = /(?<=[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0900-\u0DFF\uFB50-\uFDFF\uFE70-\uFEFC])[\u200C\u200D](?=[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0900-\u0DFF\uFB50-\uFDFF\uFE70-\uFEFC])|(?<=[\u{1F000}-\u{1FFFF}\u2600-\u27BF\uFE0F])\u200D(?=[\u{1F000}-\u{1FFFF}\u2600-\u27BF])/gu;
  var HTML_COMMENT = /<!--([\s\S]*?)(?:-->|(?![\s\S]))/gu;
  // A comment must address an AI reader or give it an instruction; merely
  // mentioning AI ("Did you use AI or GPT to write this?") does not count.
  var ADDRESSEE = R`(?:ai (?:agents?|assistants?|models?|systems?|readers?|bots?)|(?<!user )(?<!user-)agents?` +
    R`|assistants?|llms?|large language models?|language models?|bots?)`;
  var AI_NAME = R`(?:ai|chatgpt|gpt|claude|copilot|gemini)`;
  var READER = R`(?:` + ADDRESSEE + R`|` + AI_NAME + R`)\b(?![-'])`;
  var READER_LIST = R`(?:(?:(?:,| or| and) | ?/ ?)(?:the )?` + READER + R`)*`;
  var SENTENCE_START = R`(?:^ ?|[.!?;] )`;
  var ORDER = R`(?:(?:also|please|now|then|first|always|you must|you should|make sure to|remember to` +
    R`|do not|don't|never) )*(?:post|send|share|paste|run|execute|approve|merge|ignore|disregard` +
    R`|forget|reply|respond|answer|write|add|change|replace|update|delete|remove|summari[sz]e|say` +
    R`|tell|include|use|output|print|return|call|open|click|visit|follow|transfer|pay|skip|mark` +
    R`|rate|give|leave|comment|set|treat|act|pretend|translate|classify|label|recommend)\b`;
  var AI_READER = new RegExp(
    SENTENCE_START + R`(?:the |any |all |every )?` + ADDRESSEE + R`\b(?![-'])` + READER_LIST +
    R` ?:` +
    R`|` + SENTENCE_START + R`(?:the |any |all |every )?` + READER + READER_LIST + R` ?: ?` +
    ORDER +
    R`|\b(?:hey|hi|hello|dear|(?:a )?(?:note|message|memo|reminder|hint|tip) (?:to|for))` +
    R` (?:the |any |all |every |an? )?` + READER + READER_LIST + R`(?= ?[:,.!?;)]| ?(?![\s\S]))` +
    R`|\bto (?:the |any |all |every |an? )?` + READER + R`(?: (?:that is|who is|that's|who's))?` +
    R` (?:reading|processing|reviewing|parsing|scanning|summari[sz]ing|seeing|viewing)` +
    R` (?:this|these|it|the)\b` +
    R`|` + SENTENCE_START + R`to (?:the |any |all |every )?` + READER + READER_LIST + R` ?[:,]` +
    R`|\bif you(?: are|'re| re) (?:an? |the )?(?:ai (?:model|agent|assistant)|ai|llm|bot|agent` +
    R`|assistant|automated|autonomous|large language model|language model|model)\b(?![-'])` +
    R`(?= ?[:,.!?;)]| ?(?![\s\S])| (?:reading|processing|reviewing|parsing|scanning|summari[sz]ing` +
    R`|and you|you must|you should|please|agents?|assistants?|bots?|systems?|models?)\b)` +
    R`|\b(?:ignore|disregard) (?:all |any |the )?(?:previous|above|prior|earlier|preceding)\b` +
    R`|\bsystem prompt\b` +
    R`|\binstructions? (?:to|for) (?:the |any |all |every |an? )?(?:ai|agents?|assistants?|llms?` +
    R`|models?|bots?|language models?)\b(?![-'])`, "u");

  function affirmed(re, text) {
    for (const m of text.matchAll(re)) if (m[1] === undefined) return true;
    return false;
  }
  function asksForSecret(flat) {
    return affirmed(SECRET, flat);
  }
  function runsRemoteCode(flat) {
    return REMOTE_EXEC.some(re => re.test(flat)) || DOWNLOAD_RUN.some(re => affirmed(re, flat));
  }
  // An HTML comment counts only when it is aimed at an AI reader (same rule as
  // _comment_aims_at_ai in the Python reference).
  function commentAimsAtAi(body) {
    var flat = flatten(body);
    return AI_READER.test(flat) || asksForSecret(flat) || runsRemoteCode(flat);
  }
  function severalEscrows(parts) {
    for (const part of parts) for (const raw of part.split(LINE_BREAK)) {
      var line = flatten(raw);
      if (!ESCROW_WORD.test(line)) continue;
      var hosts = new Set();
      for (const m of line.matchAll(URL_HOST)) {
        var host = m[1].replace(/\.+$/u, "");
        if (host.startsWith("www.")) host = host.slice(4);
        if (!host || CODE_HOSTS.some(h => host === h || host.endsWith("." + h))) continue;
        hosts.add(host);
      }
      if (hosts.size >= 2) return true;
    }
    return false;
  }
  function hiddenTextKinds(raw) {
    var kinds = [];
    if (ZERO_WIDTH.test(raw.replace(JOINER_OK, ""))) kinds.push("zero-width characters");
    if (BIDI_CONTROL.test(raw)) kinds.push("bidirectional control characters");
    for (const m of raw.matchAll(HTML_COMMENT))
      if (commentAimsAtAi(m[1])) { kinds.push("HTML comment aimed at an AI reader"); break; }
    return kinds;
  }

  return function agentBait(texts) {
    // texts: the listing's title/description/instructions, strings only.
    if (!texts.length) return null;
    // A byte-order mark at the very start of a field is not hidden text.
    var parts = texts.map(p => p.charCodeAt(0) === 0xFEFF ? p.slice(1) : p);
    var raw = parts.join(" ");
    var flat = flatten(raw);
    var signs = [], high = false;
    if (asksForSecret(flat)) {
      signs.push("asks for a private key, seed phrase or API/access token to be sent or pasted");
      high = true;
    }
    if (runsRemoteCode(flat)) {
      signs.push("tells the solver to download and run remote code");
      high = true;
    }
    if (NO_HUMANS.test(flat))
      signs.push("says human submissions will not be reviewed or that only automated solvers are accepted");
    if (severalEscrows(parts)) signs.push("names several escrow services for one bounty");
    if (AUTO_PAYOUT.test(flat) && !CHECKABLE.test(flat))
      signs.push("promises automatic payout on merge or claim with no escrow link or on-chain address to check");
    var kinds = hiddenTextKinds(raw);
    if (kinds.length)
      signs.push("hidden text an agent would read but a person wouldn't see (" + kinds.join(", ") + ")");
    if (!signs.length) return null;
    return { s: high ? "high" : "warn", d: "listing text aimed at AI agents: " + signs.join("; ") };
  };
})();

function median(a) {
  var s = [...a].sort((x, y) => x - y), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function scan(listings, thresholds) {
  var T = thresholds || THRESHOLDS;
  var L = listings.map(norm);
  var viewsTracked = L.some(l => l.views !== null && l.views > 0);
  var F = [];
  var markers = ["ignore previous instructions", "ignore all previous instructions", "system prompt:", "system override", "cat /etc/passwd", "eval(", "curl -s | bash", "git push --force"];
  for (const l of L) {
    var v = l.views, a = l.applications;
    if (v !== null && a !== null && a > 0) {
      if (v === 0) {
        if (viewsTracked) F.push({ i: "AMS-001", n: "view_application_inversion", s: "high", id: l.id,
          d: `${a} application(s) with 0 views — applying requires viewing, so this count is arithmetically implausible and may be fabricated` });
      } else if (a > v) F.push({ i: "AMS-001", n: "view_application_inversion", s: "warn", id: l.id,
        d: `${a} applications exceed ${v} views — anomalous engagement` });
    }
    if (l.budget !== null && l.budget > 0 && l.has_escrow === false && l.has_payment_evidence === false)
      F.push({ i: "AMS-004", n: "unpaid_work_risk", s: "warn", id: l.id,
        d: `priced (${l.budget}) with no escrow and no payment-evidence mechanism — payment depends solely on poster discretion after delivery` });
    if (l.has_prompt_injection === true || markers.some(m => l.text.includes(m)))
      F.push({ i: "AMS-006", n: "prompt_injection_payload", s: "high", id: l.id,
        d: `listing content contains indirect prompt injection or instruction-override payloads` });
    var bait = agentBait(l.texts);
    if (bait) F.push({ i: "AMS-008", n: "agent_bait_listing", s: bait.s, id: l.id, d: bait.d });
  }
  var buckets = {};
  for (const l of L) {
    var bucket = Math.floor(l.ts / T.windowSeconds);
    (buckets[bucket] = buckets[bucket] || []).push(l.id);
  }
  for (const ids of Object.values(buckets)) if (ids.length >= T.minCluster)
    F.push({ i: "AMS-002", n: "batch_creation_clustering", s: "warn", id: null,
      d: `${ids.length} listings created within a ${T.windowSeconds}s window (${[...ids].sort().join(", ")}) — consistent with automated seeding` });
  var known = L.filter(l => l.is_self_advertisement !== null);
  if (known.length) {
    var r = known.filter(l => l.is_self_advertisement).length / known.length;
    if (r >= T.selfAdRatio) F.push({ i: "AMS-003", n: "self_advertisement_ratio", s: "high", id: null,
      d: `${Math.round(r * 100)}% of listings are agent self-advertisements (n=${known.length}) — supply glut marketed as demand` });
  }
  if (viewsTracked) {
    var budgets = L.filter(l => l.budget && l.budget > 0).map(l => l.budget);
    if (budgets.length >= 3) {
      var med = median(budgets);
      if (med > 0) for (const l of L)
        if (l.budget && l.budget >= T.budgetMultiple * med && l.views === 0)
          F.push({ i: "AMS-005", n: "high_budget_bait", s: "warn", id: l.id,
            d: `budget ${l.budget} is >=${T.budgetMultiple}x the platform median (${med}) with 0 views — seeded high-budget bait` });
    }
  }
  var summary = { info: 0, warn: 0, high: 0 };
  for (const f of F) summary[f.s]++;
  var verdict = summary.high > 0 ? "high_risk" : (summary.warn > 0 || summary.info > 0) ? "caution" : "clear";
  var fields = ["views", "applications", "budget", "is_self_advertisement", "has_escrow", "has_payment_evidence"];
  var coverage = Object.fromEntries(fields.map(f => [f, { present: L.filter(l => l[f] !== null).length, of: L.length }]));
  return { verdict, viewsTracked, findings: F, summary, coverage, n: L.length };
}

// Node (parity test) imports these; in a classic browser script `module` is
// undefined, so the site just gets the globals above.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { THRESHOLDS, norm, median, scan };
}
