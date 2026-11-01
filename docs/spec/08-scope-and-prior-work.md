# Spec: Scope, Reuse and Prior Work

## 13. Beyond the hackathon

The build, claims and results stand on their own. This is the direction, not a result; the evidence-based version is [future-work.md](../future-work.md).

**Where it could go:** a trust layer for distributed manufacturing. Networks that route jobs to machines they don't own, and regulated buyers (aerospace, medical, defense) who need qualification evidence, both need to know what a machine can do without the owner handing over raw data. Every site that joins improves priors for the next, across vendors and processes, and the receipt chain doubles as qualification evidence.

**Open questions we'd name, not hide:** whether networks adopt a cross-vendor layer, whether printer makers lock out third-party characterization, and how much shared summaries leak.

**Out of scope for the hackathon build:** pricing, go-to-market, customer interviews, product UI.

## 14. Fallback tiers

| Tier | Situation | Claim |
|---|---|---|
| A | Both printers, all rounds | Full claims, real two-site network |
| B | One printer works | Real site plus simulated sites, anchored to real data |
| C | One or two plates succeed | Simulator calibrated to real data; network results in simulation |
| D | No usable prints | Pure multi-site simulation, reported honestly |

The registered tiers and which claims each keeps are in `prereg/prereg.yaml` (`fallback_tiers`). The project reports tier D for the sharing results: no full real-printer run took place.

## 15. Scope

**Built:** two sites, three arms, message protocol with enforced boundary, held-out escrow, scanner pipeline and hand-measurement sheet, multi-site simulator (NumPy and Warp), GPU posterior, receipts and privacy audit, many-world sweeps, real-printer path with checkpoint and resume, operator console, corrected designs.
**Built, off in the registered config:** challenge round, spawn of the position agent, consistency check, adaptive spread, predictive trust.
**Built, exploratory:** hypothesis agent (not run against a live model).
**Not built:** human-grid arm, orientation agent, demo assembly, noise on shared summaries, a site joining a round behind, a full real two-printer run.

## 16. Reuse deliverables

Built for reuse outside this project (usage in the [README](../../README.md#reusable-tools)):

- Process-agnostic test-plate spec and generator
- Scanner measurement tool
- Hidden-truth multi-site simulator benchmark
- Clearing rule and typed message protocol (`agents/auction.py`, `network/protocol.py`), usable on their own but not packaged separately

## 17. Prior work and competitors

- Query by committee (early 1990s): model disagreement as a guide to what to label next. Prebuilt extends it to agents with distinct evidence, earned credibility, market allocation, and sites that can't pool data.
- Federated learning: training across sites without sharing raw data. Prebuilt differs in that sites also choose their own experiments; it's federated active learning on physical processes.
- Single-part print preparation: 1000 Kelvin (AMAIZE), Formlabs PreForm, Markforged Blacksmith, Siemens Simcenter. These optimize individual parts on known machines; Prebuilt characterizes the machines themselves, across vendors and processes.
