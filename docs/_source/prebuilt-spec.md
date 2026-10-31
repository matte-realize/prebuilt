# Prebuilt — Technical Spec

**ScienceClaw Hackathon, MIT Media Lab · Oct 30 – Nov 1, 2026 · Area A·03 Manufacturing & Materials**
Team of two · Goal: first place · Slides due Sun ~2:30 PM, presentations 4 PM

---

## 1. One-line pitch

A decentralized collective of scientist agents that designs and runs its own experiments on real 3D printers to learn how a fabrication process actually behaves. Each printer is a site with its own agents and private data. Sites share only beliefs and hypotheses, yet the network learns nearly as fast as if all data were pooled, and far faster than any site alone.

**The scientific question:** can autonomous agents that cannot pool their evidence still do experimental science together efficiently? Fabrication is the testbed because the experiments are real, cheap, fast, and measurable within a weekend.

## 2. Problem

Every fabrication process has to be characterized before its parts can be trusted. Today that work is manual, machine-specific, and repeated for every printer, material, and site.

Manufacturing is increasingly distributed: marketplaces and networks route jobs to machines they don't own, and regulated buyers (aerospace, medical, defense) need evidence that a part from a given machine will meet spec. The knowledge that would make characterization fast already exists, spread across thousands of machines, but it can't be pooled. Shops won't hand over raw process data: it's proprietary and exposes their capabilities and failure rates.

So every site re-learns from scratch. Prebuilt lets sites learn from each other without sharing data.

We use two processes, resin (SLA) and PLA (FDM), as two sites. They fail in opposite ways: resin holes close up from light bleed and over-cure while pins grow; FDM holes shrink from polygonization and extrusion width, and the first layer flares. Same test vocabulary (pin/hole pairs), different physics, which makes them a hard test of what can be shared.

## 3. Why decentralization is required, not chosen

The constraint defines the system: **raw measurements, plate files, and site-specific parameters never leave a site.** Only messages cross the boundary (Section 5.3). A centralized optimizer is therefore impossible in the real setting. We still build one, the pooled-data oracle, as an upper bound that no real network can reach.

## 4. Pre-registered claims

Committed to the repository with a hash and timestamp before the first print.

- **H1 (privacy-preserving performance).** At equal print budgets, the networked collective reaches held-out error closer to the pooled-data oracle than to isolated sites, while no raw data crosses a site boundary.
- **H2 (transfer).** A site joining the network (PLA, one round behind) reaches target held-out error with fewer pieces than an isolated site, because process-agnostic knowledge arrives as messages.
- **H3 (robustness).** A deliberately miscalibrated agent, or a site broadcasting bad beliefs, loses credibility and the network recovers without intervention.
- **H4 (privacy, verified).** Receipts prove that no raw measurement, plate file, or site-specific parameter crossed a site boundary.
- **H5 (baseline).** The calibrated model predicts fit better than generic vendor clearance guidance. Expected; reported, not the headline.
- **H6 (discovery, exploratory).** The network surfaces at least one effect absent from the physics model (candidate: build-plate position dependence). Labeled exploratory in advance.

## 5. Rubric mapping

| Criterion | Weight | What earns it |
|---|---|---|
| Problem significance | 20 | Distributed manufacturing can't pool data; characterization repeated at every site |
| Scientific/technical impact | 25 | Near-oracle learning under privacy (H1), cross-process transfer (H2), discovered effect (H6), pre-registration, held-out escrow |
| Decentralized agency | 20 | Decentralization is a hard constraint; per-site collectives, message-only exchange, credibility auction, challenges, spawn/retire, hypothesis agent |
| Collective capability | 25 | Network vs. isolated sites vs. oracle (H1), transfer (H2), recovery (H3), scaling with number of sites |
| Execution and validation | 10 | Real held-out fits, verifiable receipts including privacy proof (H4), end-to-end loop, honest reporting |
| Reuse bonus | +10 | Test-plate spec, scanner tool, hidden-truth multi-site benchmark, clearing-rule and message-protocol library |

## 6. System architecture

### 6.1 Topology

Each printer is a **site** running its own collective: agents, auction, plates, measurements, and posterior. Sites talk only through the message protocol. Each agent decides which incoming messages to use and how much to trust their senders. No node decides what transfers.

Real event: two sites (resin, PLA). Simulation: up to dozens of sites across both processes, each with its own hidden machine parameters.

### 6.2 Agents (within each site)

| Agent | Evidence | Shares beliefs across sites? |
|---|---|---|
| Physics | Datasheet priors, working-curve or extrusion model | Same-process sites only |
| Printability | PreForm / slicer checks, observed print failures | Same-process sites only |
| Calibration | Site's own seed-plate measurements | Never |
| Geometry | Feature size, aspect ratio, orientation | Yes |
| Empirical | Residual patterns across the site's measurements | Yes (as summaries) |
| Plate position (dormant) | Location on build plate | Yes |
| Orientation (dormant) | Feature orientation relative to build direction | Yes |
| Hypothesis (language model) | Residuals summaries + unmet-needs log | Yes |

The **hypothesis agent** (Nemotron) proposes candidate effects and new piece types when residuals or the unmet-needs log show something unexplained ("is the position-dependent error seen at the resin site also present at PLA?"). Its proposals enter the auction like any other and earn or lose credibility the same way. It never sets parameters or allocates space.

### 6.3 Message protocol

**May cross a site boundary:**
- Posterior summaries for process-agnostic parameters (mean and covariance)
- Agent and site credibility scores
- Hypotheses and proposed piece types
- Unmet-needs entries (question and anonymized residual summary)
- Challenge outcomes

**Never crosses:**
- Raw measurements
- Plate files and randomization seeds
- Site-specific parameters (calibration agent state)
- Held-out data

The boundary is enforced in code: messages are typed, and the serializer rejects anything outside the allowed schema. Every message is written to the receipt chain, so H4 is checkable by replay.

Known limitation: posterior summaries can leak some information about a site's data. Adding calibrated noise to shared summaries (differential privacy) is an aim goal, not core.

### 6.4 Incoming-message trust

Each receiving agent weights incoming posterior summaries by the sending site's credibility, as earned on the receiving site's own held-out data. A site whose shared beliefs hurt others' predictions loses influence everywhere it broadcasts.

### 6.5 Decision cycle (per plate, per site)

1. **Receive.** Agents ingest messages from other sites, weighted by sender credibility.
2. **Propose.** Each agent proposes the pieces it is least certain about, ranked by expected information gain.
3. **Challenge.** One round. Each agent may flag one other proposal with a reason ("redundant with mine," "already predictable from my evidence"). Flagged pieces lose bid weight. The flagger gains or loses credibility depending on whether the flag holds up on held-out data.
4. **Bid and clear.** Fixed clearing rule: each arm's slot pool is divided among agents in proportion to credibility (largest-remainder rounding); each agent fills its slots with its top surviving proposals. The rule allocates space only and never chooses content.
5. **Approve.** Human checks printability and safety only. Approvals logged; any edit or veto recorded and reported.
6. **Print, measure, update.** Posteriors update piece by piece as measurements arrive, in order of information value.
7. **Credit.** Agent and sender credibility update from held-out improvement (Section 6.6).
8. **Broadcast.** Allowed messages go out to other sites.
9. **Explain (async).** Nemotron writes explanations after the plate is locked, off the critical path.

### 6.6 Credibility

After each round, for each agent *a*, compute the change in held-out log predictive density when *a*'s contributed pieces are removed (leave-one-agent-out). Update multiplicatively:

c_a ← c_a · exp(η · ΔLPD_a), then normalize.

Sender credibility uses the same rule, with ΔLPD measured by removing that sender's messages. η is fixed and pre-registered. Held-out data is escrowed per site; agents see only scalar credit.

### 6.7 Spawn and retire

- **Retire:** an agent below a pre-registered credibility floor for two consecutive rounds stops bidding.
- **Spawn:** when a site's unmet-needs log, or incoming unmet-needs messages from other sites, reach a threshold matching a dormant template, that agent wakes with uniform credibility. A question raised at one site can wake an agent at another.
- Best-effort on real printers; always exercised in simulation.

## 7. Physics models

Same model and priors for every arm. Bayesian updating via a GPU particle or grid posterior, optional learned correction on residuals. Parameters are tagged process-agnostic or site-specific, which determines what may be shared.

### 7.1 Resin (SLA)

- Jacobs working curve: Cd = Dp · ln(E / Ec)
- Light bleed: lateral over-cure that shrinks holes and grows pins
- Cure shrinkage: isotropic scale factor
- Parameters: Dp, Ec, lateral bleed coefficient, shrinkage, (optional) orientation offset
- Priors from the resin datasheet

### 7.2 PLA (FDM)

- Effective extrusion width
- Hole polygon shrinkage (small holes print undersized)
- First-layer flare
- Priors from slicer settings

### 7.3 Shared structure

Process-agnostic terms shared across sites: feature-size dependence of error, orientation effects, plate-position effects, and the residual correction's geometry features.

### 7.4 Fit definition

Clearance = hole diameter − pin diameter. Fit classes (press / slip / loose) are defined by pre-registered clearance thresholds per process. Physical go/no-go checks on a random sample validate the derived classes.

## 8. Experimental design

### 8.1 Arms

All arms share every plate, with equal slot budgets and randomized placement.

| Arm | Data access | Selection policy |
|---|---|---|
| Human grid | Own site | Uniform sweep over nominal clearance and feature size |
| Isolated site | Own site only | Single agent, all of its site's evidence, maximum-uncertainty selection |
| Networked collective | Own site + messages | Full system (Section 6) |
| Pooled-data oracle | All sites' raw data | Single agent, maximum-uncertainty selection. Upper bound; not realizable in practice |

Each plate's slots split equally across the four arms; positions randomized by a seeded shuffle recorded in the receipt.

### 8.2 Held-out set

- Fixed before the first print, hashed and committed.
- Spread across plates to capture drift.
- Measured but escrowed per site: used only for scoring and credibility.
- Includes geometries outside the training distribution for the "new geometries" claim.

### 8.3 Plate sequence

| Plate | Resin site | PLA site |
|---|---|---|
| Seed calibration | Fri night | Sat morning (one round behind) |
| Round 1 | Sat morning | Sat midday |
| Round 2 | Sat afternoon | Sat evening |
| Demo assembly + audit | Sat night (optional) | Sat night (preferred; faster) |

PLA joins one round behind so H2 tests a genuine new site joining the network.

Every plate carries duplicate pieces. Plates are small, flat, and well supported.

### 8.4 Metrics

- Held-out mean absolute error in clearance
- Held-out log predictive density
- Fit-class accuracy
- Calibration: coverage of 90% predictive intervals
- **Oracle gap closed:** (isolated − networked) / (isolated − oracle) on each metric
- Learning curves per arm vs. pieces printed
- Transfer: pieces needed to reach target error at the joining site, networked vs. isolated

Uncertainty on real data via bootstrap over pieces; in simulation via many seeds.

### 8.5 Print-failure rules (pre-registered)

- A piece that fails to print, fuses, warps, or breaks is a **printability outcome**, not dropped data; the printability agent is scored on predicting it.
- If a held-out piece fails, it is reported, and fit metrics are computed on survivors with the failure count shown.
- A plate is "failed" if fewer than a pre-registered fraction of pieces are measurable; otherwise "partial" and used.

### 8.6 Ablations

- Remove each agent type; report held-out degradation.
- Cut the network (no messages): networked collective should fall to isolated performance.
- Inject a miscalibrated agent and a bad-faith site; track credibility and recovery.
- Scaling in simulation: number of sites (2, 5, 10, 25) and agents per site; plot oracle gap closed.
- Share only same-process vs. all messages; measure what cross-process transfer actually contributes.

## 9. Measurement

- **Scanner pipeline:** flatbed scanner, backlit thin plates, computer-vision extraction of hole and pin diameters.
- **Spot checks:** calipers and pin gauges on a random sample; report agreement with the scanner.
- Process-agnostic: works at any site that can print the test-plate spec.
- Measurements stream into the site's posterior piece by piece and never leave the site.

## 10. Hidden-truth multi-site simulator

- Built first (Friday night). Shares the exact code path with real data.
- Each simulated site draws its own perturbed machine parameters, measurement noise, and deliberately unmodeled effects (plate-position gradient, orientation-dependent error), with some effects shared across sites and some local.
- Calibrated to real measurements as they arrive; residuals reported.
- Implemented in NVIDIA Warp, batched across thousands of simulated sites on Nebius H100s.
- Released as a public multi-site benchmark.

## 11. Speed and verifiability

### 11.1 Targets

- Agent decision cycle (receive → propose → challenge → clear): under one second per site.
- Language model off the critical path; explanations async.
- Posterior updates vectorized on GPU, one batched call for all agents.
- Piece library and printability checks precomputed and cached; no per-proposal API calls.

### 11.2 Physical loop

- Print time is part of each piece's bid cost (height and volume).
- Measurement in order of information value; held-out accuracy shown stabilizing before a plate is fully measured.

### 11.3 Receipts

Every decision and every cross-site message writes a hashed receipt: evidence snapshot, proposals, challenges, bids, clearing result, plate file hash, randomization seed hash, approval, measurement hashes, and outgoing/incoming messages. Each site keeps its own hash chain; cross-site messages reference both chains.

Anyone can replay a site's log to reproduce its numbers in seconds, and an auditor can verify from message receipts alone that nothing outside the allowed schema crossed a boundary (H4), without seeing any site's raw data.

## 12. NVIDIA stack

| Component | Use |
|---|---|
| Warp | Batched multi-site simulator; posterior updates |
| Nemotron | Hypothesis agent; async explanations |
| NeMo Agent Toolkit | Agent orchestration and cross-site messaging |
| Nebius H100s | Many-seed and site-scaling sweeps |
| DGX Spark | Local site loop next to the printers |

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
