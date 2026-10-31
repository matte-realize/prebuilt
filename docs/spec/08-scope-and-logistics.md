# Spec: Scope and Logistics

## 13. Beyond the hackathon (closer only)

The build, claims, and results stand on their own as a hackathon project. This section is one closing slide, about 30 seconds, for an audience that includes a venture fund. It is not a build target, and no hacking time goes to it.

**Where it could go:** a trust layer for distributed manufacturing. Networks that route jobs to machines they don't own, and regulated buyers (aerospace, medical, defense) who need qualification evidence, both need to know what a machine can do without the owner handing over raw data. Every site that joins improves priors for the next, across vendors and processes, and the receipt chain doubles as qualification evidence.

**Open questions we'd name, not hide:** whether networks adopt a cross-vendor layer, whether printer makers lock out third-party characterization, and how much shared summaries leak.

**Deliberately out of scope this weekend:** pricing, go-to-market, customer interviews, product UI.

## 14. Fallback tiers

| Tier | Situation | Claim | Projected score |
|---|---|---|---|
| A | Both printers, all rounds | Full claims, real two-site network | ~80 |
| B | One printer works | Real site plus simulated sites, anchored to real data | ~70 |
| C | One or two plates succeed | Simulator calibrated to real data; network results in simulation | ~62 |
| D | No usable prints | Pure multi-site simulation, reported honestly | ~52 |

### Checkpoints

- **Fri ~11 PM:** Printer access confirmed? If not, ask organizers and nearby shops; start simulation-only track in parallel.
- **Sat ~8 AM:** Seed plates printed? On failure, fix the obvious cause once and reprint. Second failure on the same printer → drop it, Tier B.
- **Sat ~4 PM:** Last real round started? If not, stop new rounds; measure, calibrate simulator, polish results.
- **Sun ~9 AM:** Data freeze. No new prints.

## 15. Schedule

| When | Matthew | Teammate |
|---|---|---|
| Fri 9 PM – 1 AM | Agents, auction, challenge round, message protocol and boundary enforcement, receipts, pre-registration commit | Warp multi-site simulator, plate generator, test print on each printer |
| Fri overnight | — | Resin seed plate printing |
| Sat 6 – 10 AM | Measure resin seed, fit priors, run round 1 auction | Scanner pipeline, PLA seed plate |
| Sat 10 AM – 4 PM | Rounds 1–2 auctions, held-out escrow, credibility, cross-site messaging live | Simulation sweeps (many seeds, site scaling, ablations) |
| Sat 4 PM – midnight | Spawn/retire, hypothesis agent, transfer analysis, privacy audit replay | PLA rounds, demo assembly print |
| Sun 6 AM – 2:30 PM | Final measurements, results, slides | Figures, receipt replay demo |
| Sun 4 PM | Present | Present |

Measurement duty per round assigned in advance.

## 16. Scope

**Core:** two sites, four arms, message protocol with enforced boundary, held-out escrow, scanner pipeline, multi-site simulator, receipts, many-seed simulation.
**Aim (in order):** challenge round → site-scaling sweep → hypothesis agent → spawn/retire (simulation) → PLA demo assembly → noise on shared summaries → spawn/retire on real printers.
**Cut:** red-team critic, curing chemistry, separate centralized solver (the oracle covers it).
**Cut first if behind:** real-printer spawn/retire, then the demo assembly.

## 17. Reuse deliverables

Posted to the hackathon channel by Saturday morning:

- Process-agnostic test-plate spec and generator
- Scanner measurement tool
- Hidden-truth multi-site simulator benchmark
- Clearing rule and typed message protocol as a small library

## 18. Prior work and competitors

- Query by committee (early 1990s): model disagreement as a guide to what to label next. Prebuilt extends it to agents with distinct evidence, earned credibility, market allocation, and sites that can't pool data.
- Federated learning: training across sites without sharing raw data. Prebuilt differs in that sites also choose their own experiments; it's federated active learning on physical processes.
- Single-part print preparation: 1000 Kelvin (AMAIZE), Formlabs PreForm, Markforged Blacksmith, Siemens Simcenter. These optimize individual parts on known machines; Prebuilt characterizes the machines themselves, across vendors and processes.

## 19. Demo plan

Time split: roughly 85–90% problem, method, and results; one closing slide for where it goes next.

1. The problem: every site re-learns its machines from scratch because experimental data can't be pooled. Can agents do science together without sharing data?
2. Two sites, one boundary: what crosses and what never does.
3. A pre-printed plate through the scanner; the site's posterior updating live.
4. Challenge transcript: agents negotiating what goes on the plate.
5. Headline chart: networked collective vs. isolated site vs. oracle, with oracle gap closed.
6. PLA joining the network and learning faster than resin did alone.
7. A bad-faith site losing influence.
8. Privacy audit: replay the message receipts and show nothing raw crossed.
9. Demo assembly: predicted to fit, and it does.
10. Closer (one slide, ~30 seconds): what this could become beyond the weekend. Print anywhere, trust the part.

## 20. Open items to confirm (first hour)

- Printer models, resin type, PLA printer availability and queue
- Exact PreForm API capabilities
- Scanner availability (or phone-camera fallback with a calibration target)
- Organizer rules on simulated vs. real results
- Fit-class thresholds, failed-plate fraction, η, and credibility floor, set and committed before the first print

