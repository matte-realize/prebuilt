# Spec: Experimental Design

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

1. Seed calibration plate at each site.
2. Rounds 1, 2, … : one plate per site per round, chosen by that site's agents.
3. Optional: a demo assembly predicted to fit, and the privacy audit.

In the full design PLA joins one round behind, so H2 tests a genuine new site joining the network.

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

