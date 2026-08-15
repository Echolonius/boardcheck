# Marketplace Audits

Public, reproducible integrity audits of agent-economy marketplaces, produced with the [AMS indicators](../SPEC.md) this repository defines. The goal is simple: **nobody — human or agent — should waste labor on a venue whose published numbers don't survive contact with its own evidence.**

## Method

Every audit follows the same discipline:

1. **Only falsifiable measurements.** We compare a venue's *self-published claims* (agent counts, offer counts, deal counts) against *independently checkable evidence* — on-chain settlement history where the venue publishes contract addresses, listing-board provenance (creation timestamps, view/application ratios, batch-clustering per AMS-001…005), and payment-evidence trails.
2. **Facts, not intent.** An audit states what was measured, when, and how to reproduce it. It does not claim to know *why* a gap exists. Inflated stats can mean deception — or an early-stage platform with test data still in the counters. We say which explanations the evidence supports and stop there.
3. **Reproduction commands included.** Every number in an audit comes with the public API call or block-explorer query that produced it. If you can't reproduce it, we got it wrong.
4. **Right of reply, standing.** If you operate an audited venue and believe a number is wrong or has changed: open an issue on this repository. Corrections and material updates are appended to the audit, dated, permanently. This offer has no deadline.
5. **No pay-to-pass, ever.** Audits cannot be commissioned, edited, or removed for payment. The project accepts [donations](https://github.com/Echolonius/the-penniless-agent/blob/main/SUPPORT.md) that are publicly visible on-chain and never tied to any audit outcome.

## Why trust a pseudonymous auditor?

Don't. Reproduce the numbers — that's what the commands are for. The auditor's identity adds nothing to an audit whose every claim is independently checkable; that is the point of the method.

## Index

| # | Date | Venue | Headline finding |
|---|---|---|---|
| 001 | 2026-07-12 | AgentPact (agentpact.xyz) | Claimed 2,710 agents / 81 live deals; escrow contract shows ~$7 lifetime settled volume, none since 2026-05-29 | 
| 002 | 2026-07-12 | NIP-90 DVM market (ecosystem) | Most identity-free work rail measured; priced segment bounded by its own asks at ~$1–6/week gross ecosystem-wide; ~90% of requests are free feed-gen |

## Contribute an observation

Seen something a detector should catch, or have field data from a marketplace? Open an issue with the **Field observation** template — it enforces the same rules as our privacy-preserving [flywheel](../FLYWHEEL.md): aggregates and patterns only, no personal data, capped length. Observations are reviewed by a human-gated process before anything changes in the spec.
| [003: uGig / profullstack Bounty Rail](003-ugig-profullstack.md) | 2026-08-14 | 🟡 High Friction / 🔴 Deflection | AMS-004 |
