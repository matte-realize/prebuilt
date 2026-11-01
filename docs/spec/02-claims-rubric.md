# Spec: Claims and Rubric

## 4. Claims

### 4.1 Registered claims

Committed in `prereg/prereg.yaml` before any print (its sha256 is recorded in `eval/figures/README.md`):

- **Network vs. isolated (`network_vs_oracle`).** At equal print budgets, the networked arm beats isolated sites on held-out error, near the pooled-data oracle, with no raw data crossing a site boundary. Primary metric: isolated − networked held-out MAE in µm. **Result, simulation only:** 1.6 µm (12%) at two sites, better in 75 of 100 worlds; the oracle also gains 12%.
- **Sim-to-real range (`sim_to_real_range`).** The measured value on real printers lands in a range predicted from simulation after seed calibration. **Not tested:** no full real-printer run took place (fallback tier D, Section 14). The only real-printer evidence is three micrometer readings on one Formlabs Form Studio 1 (a 1.5 mm pin measured 1.41–1.48 mm, within the vendor's ±0.08 mm spec and at the small edge of the simulator's range, 1.8th percentile for that pin).
- **Robustness (`robustness_sim`).** In simulation, a site broadcasting corrupted beliefs loses trust and the networked arm stays at least as good as isolated after round 1, while honest senders keep trust. **Result:** the liar's trust falls to ~0.01 after one round, but round 1 is costly; the opt-in consistency check removes that cost (Section 6.4).

### 4.2 Designed, not registered

From the full design, reported as exploratory or not built:

- **Transfer** (a site joining one round behind learns faster): not run; both sites start together.
- **Privacy, verified:** built. `eval/audit.py` replays the receipt chains and checks that nothing outside the message schema crossed.
- **Fit vs. vendor guidance:** fit-class accuracy is scored (`eval/fit.py`) but can't separate the arms (0.94–0.98 in every arm); not compared against vendor guidance.
- **Discovery** (an effect absent from the physics model): the hypothesis agent and the position-template spawn exist and are exploratory; the hypothesis agent has not been run against a live model.

### 4.3 Exploratory findings (simulation)

Many data-poor sites gain 11% / 28% / 35% at 2 / 4 / 8 sites; the agent layer adds nothing measurable and its piece choices don't beat random; a negative control with no shared physics gains nothing (−13%); corrected designs cut size error from 132 to 9 µm (median). Details: `hpc/sweeps/relevance/README.md`, `hpc/sweeps/coldstart/README.md`.

## 5. Rubric mapping

| Criterion | Weight | What earns it |
|---|---|---|
| Problem significance | 20 | Distributed manufacturing can't pool data; characterization is repeated at every site |
| Scientific/technical impact | 25 | Sharing matches pooling under privacy; claims registered before printing; held-out escrow; negative control; honest limits (sim only) |
| Decentralized agency | 20 | Decentralization is a hard constraint; per-site agents, message-only exchange, learned trust between sites, opt-in consistency check, adaptive spread and predictive trust |
| Collective capability | 25 | Network vs. isolated vs. oracle; gain grows with the number of data-poor sites; recovery from a lying site; mixed fleets |
| Execution and validation | 10 | End-to-end loop (console, real-printer path, rehearsal), verifiable receipts and privacy audit, real micrometer sanity check |
| Reuse bonus | +10 | Test-plate spec, scanner tool, hidden-truth multi-site benchmark, message-protocol library |
