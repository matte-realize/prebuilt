# Spec: Experimental Design

## 8. Experimental design

### 8.1 Arms

`arms/experiment.py` (`run_experiment`). All arms share every plate, with equal slot budgets (6 per arm) and randomized placement recorded in the receipt.

| Arm | Data access | Selection policy |
|---|---|---|
| Isolated site | Own site only | The same agent auction, at uniform credibility |
| Networked collective | Own site + messages | The agent auction at learned credibility (Section 6) |
| Pooled-data oracle | All sites' raw data, hierarchical | The same agent auction, at uniform credibility. Reference; not realizable in practice |

Using the same agents in every arm (`same_agents=True`) means the arms differ only in the data each model sees. The human-grid arm in the original design was not built.

### 8.2 Held-out set

- Fixed before any print, hashed and committed (`prereg/heldout.json`): 8 pieces per plate.
- Measured but escrowed per site: used only for scoring and credibility.
- In simulation, scored against the noise-free sizes (`mae_truth`), which agents never see.

### 8.3 Plate sequence

1. Seed calibration plate at each site: 16 calibration pieces + 8 held-out.
2. Rounds 1–3 (registered): one plate per site per round, chosen by that site's agents.
3. Privacy audit over both receipt chains.

Both sites start together; a site joining a round behind and a demo assembly were designed but not run.

### 8.4 Metrics

- **Primary:** isolated − networked held-out MAE, in µm (diameter error against truth in simulation, measured MAE on real data)
- Held-out log predictive density
- Calibration: coverage of 90% predictive intervals (90–91% in every arm in simulation)
- Fit-class accuracy (reported, not headlined)
- Oracle gap closed, (isolated − networked) / (isolated − oracle), reported only as a reference: on measured MAE the denominator is near zero
- Learning curves per arm vs. pieces printed

In simulation, uncertainty comes from many paired worlds (same world seed, one thing changed) with an exact sign test.

### 8.5 Print-failure rules (registered)

- A piece that fails to print is a **printability outcome**, not dropped data; the printability agent learns from it.
- A failed held-out piece is reported, and metrics are computed on survivors.
- A plate is "failed" if more than the registered fraction (0.5) of its pieces fail; it is reprinted once, then dropped from the round.

### 8.6 Ablations and controls (simulation)

- Cut the network (`share_messages=False`): the gain comes from messages (with messages cut, the same agents gain 2.4%, not significant).
- Random piece selection (`selection="random"`): the agents' choices don't beat random.
- A saboteur agent inside a site, and a bad-faith site broadcasting corrupted beliefs (`bad_sites`, at offsets of 0.5–3 prior std).
- Negative control (`independent_shared=True`): printers that share no physics; sharing gains nothing (−13%).
- Scaling: 2, 4 and 8 data-poor sites; mixed fleets where half the sites share no physics; a sub-millimetre plate.

Results: `hpc/sweeps/relevance/README.md`, `hpc/sweeps/coldstart/README.md`, `hpc/sweeps/phase_d/`.
