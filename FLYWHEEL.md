# How this improves over time — safely (the "flywheel")

The goal: as more people run these checks, the checks get better — thresholds tuned to
reality, new deceptive patterns discovered — **without** anyone having to babysit it and
**without** leaking anyone's data. This document is the honest design for that, including
the things we deliberately refuse to build.

## Non-negotiable principles

1. **Local-first. No phone-home, ever.** Running a scan sends nothing anywhere. The tool works
   fully offline and always will. A security tool that secretly uploads your data is worthless,
   and we will not ship one.
2. **Contribution is opt-in and explicit.** Improvement data is produced only when a user calls
   the contribution primitive on purpose, and shared only when they choose to. Off by default.
3. **Privacy by construction, not by promise.** The only shareable artifact is the *observation*
   (see `observation.py`): coarse buckets and boolean flags. It contains no platform name (the
   data model has none), no listing ids or text, no budgets, no timestamps, no user identity. A
   k-anonymity floor refuses to emit for samples too small to be safe. You can read the whole
   thing before you share it.
4. **Human-gated, so it can't be poisoned.** Contributions arrive as ordinary pull requests or
   issues to a public repository and are reviewed by a human before anything is accepted. There
   is no server ingesting untrusted data automatically, because an auto-ingesting, auto-tuning
   system is a data-poisoning target — an attacker could flood it with fake observations to blind
   the very detectors it powers. Review at human pace is slower and vastly safer.
5. **The spec changes at open-source pace, not by live self-mutation.** Accumulated observations
   inform *proposals* to tune a threshold or add an indicator; those land as a new, versioned
   `SPEC.md`. The rules never silently rewrite themselves on your machine.

## What actually spins the wheel

1. Someone runs a scan locally.
2. If they opt in, `to_observation()` produces a minimal, non-reversible summary.
3. They (optionally) contribute it to the public observations file via a pull request.
4. As real observations accumulate across many contributors, base rates become visible — e.g.
   "how often does the zero-view inversion actually fire on real boards?" — which lets thresholds
   be tuned empirically instead of hand-guessed, and surfaces new patterns worth an indicator ID.
5. Those improvements ship as a new spec version. Everyone's next scan is a little sharper.

## What we will NOT build, and why

- **No telemetry server / hosted database.** It would be a privacy liability, a maintenance and
  security burden, and a single point of failure — the opposite of "robust and unmanaged."
- **No automatic threshold tuning from untrusted input.** Poisoning risk; see principle 4.
- **No per-user or per-platform tracking.** Not collected, so it cannot leak.

## Honest status

This is a *mechanism for later*. A flywheel needs motion to spin, and motion means adoption — with
zero users there is no data to learn from. So the near-term priority is making the tool genuinely
useful and easy to reach (a clean spec, a one-command install, and an MCP server so agents can call
it at decision time), **not** an elaborate contribution pipeline before anyone is using it.
The safe primitive exists now (`to_observation`) so that when adoption comes, the improvement path is
already private-by-construction rather than bolted on under pressure.
