"use strict";
/* Boardcheck detectors — the single browser-side implementation.
 *
 * This is a faithful port of agent_market_signals/detectors.py (the reference
 * implementation), except that it does not run AMS-007. Same semantics:
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
    text: [item.title, item.description, item.instructions].filter(Boolean).join(" ").toLowerCase()
  };
}

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
