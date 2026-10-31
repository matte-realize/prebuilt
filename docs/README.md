# Prebuilt docs

ScienceClaw Hackathon, MIT Media Lab · Oct 30 – Nov 1, 2026 · Area A·03 Manufacturing & Materials.

Originals, unedited: [`_source/prebuilt-spec.md`](_source/prebuilt-spec.md), [`_source/prebuilt-walkthrough.md`](_source/prebuilt-walkthrough.md).

## The build walkthrough is authoritative

The spec describes the full vision. The walkthrough is what we are building this weekend. Where they disagree, follow the walkthrough:

| Topic | Spec | Walkthrough (build this) |
|---|---|---|
| Arms | 4: human grid, isolated, networked, oracle | 3: isolated, networked, oracle |
| Claims | H1–H6 | 3: network vs. oracle, sim-to-real range, robustness (sim only) |
| Real rounds | Seed + 2 rounds | Seed + 3 rounds (+ optional 4th) |
| Sim-to-real | Simulator calibrated to real data | Predicted oracle-gap-closed range committed after seed calibration, before round 1 |
| Printer window | Fri overnight printing | Printers Saturday ~8–9 AM to 10 PM only |

## Spec

1. [Overview](spec/01-overview.md): pitch, problem, why decentralization is required
2. [Claims and rubric](spec/02-claims-rubric.md): H1–H6, rubric mapping
3. [System architecture](spec/03-architecture.md): topology, agents, message protocol, trust, decision cycle, credibility, spawn/retire
4. [Physics models](spec/04-physics-models.md): resin, PLA, shared structure, fit definition
5. [Experimental design](spec/05-experimental-design.md): arms, held-out set, plates, metrics, failure rules, ablations
6. [Measurement and simulator](spec/06-measurement-simulator.md)
7. [Speed, verifiability, NVIDIA stack](spec/07-speed-verifiability.md): targets, receipts
8. [Scope and logistics](spec/08-scope-and-logistics.md): beyond the hackathon, fallback tiers, schedule, scope, reuse, prior work, demo, open items

## Build walkthrough

0. [Definition of done](build/00-definition-of-done.md)
1. [Kickoff, repo layout, interfaces](build/01-kickoff-layout-contracts.md)
2. [Friday night: Phases A–C](build/02-friday-night.md)
3. [Saturday: printer day and night](build/03-saturday.md)
4. [Sunday and fallbacks](build/04-sunday-fallbacks.md)
5. [Pre-registration file and slide outline](build/05-prereg-and-slides.md)
6. [Task split](build/06-task-split.md): who owns what (Matthew: agents and the physical loop; teammate: HPC). Replaces the M/T assignments in 2 and 3
7. [Status and Phase C findings](build/07-status.md)
8. [Warp posterior build log](build/08-warp-posterior.md)
9. [Printer-day run sheet](build/09-run-sheet.md): step by step at the printers
