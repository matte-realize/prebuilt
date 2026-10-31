# Phase D sweeps: robustness, ablation, scaling

Batched Warp simulator (`sim.batch.run_batch`, orient_std 0 = the world `run.py --source sim` uses) on the laptop RTX 5060. Config from `prereg/prereg.yaml` (sha256 `e59b618f…0528`) through `prereg.check.sim_config`: 16 seed pieces, 6 slots, 3 rounds, 4000 particles, 6 MH steps, eta 5, trust_init 1.0, cred_floor 0.05, discount 0.2, between_site_sd 0.25. Nothing retuned. Seeds 3000-3199. Code at base 04eed15 plus this directory.

    .venv/bin/python hpc/sweeps/phase_d/sweep.py robustness --seeds 200   # ~25 min on the laptop GPU
    .venv/bin/python hpc/sweeps/phase_d/sweep.py ablation --seeds 200     # reuses the honest runs
    .venv/bin/python hpc/sweeps/phase_d/sweep.py scaling --seeds 100
    .venv/bin/python hpc/sweeps/phase_d/analyze.py robustness             # writes results/robustness.md
    .venv/bin/python hpc/sweeps/phase_d/figures.py                        # eval/figures/*.png, *.pdf

`--cpu` runs the same sweeps on the NumPy reference sim with a process pool, for a machine without a GPU.

Errors are `mae_truth` in µm: model error against noise-free held-out diameters. ± is 1.96 SE over seeds. Raw rows are committed as `results/*.jsonl.gz`; `sweep.py` resumes from them and `analyze.py` reads them directly.

## 1. Robustness (claim 3)

**Claim 3 holds for "loses influence" and only partly for "the network recovers."** The lying site's trust falls from 1.0 to 0.03-0.04 by round 3 (below 0.5 in 397/400 attacked runs), and honest trust stays at 0.91-0.95, the same as in honest runs. But by round 3 the honest site is back to about its isolated error on average, not to what networking gives it without the attack, and a tail of seeds stays clearly hurt.

Full table: [`results/robustness.md`](results/robustness.md). Honest site, both directions, 200 seeds each:

| round | lying sender's trust | honest net, attack | honest net, no attack | honest isolated |
|---|---|---|---|---|
| pla lies, resin honest | | | | |
| 1 | 1.00 | 73.6 ± 4.9 | 12.5 ± 0.9 | 13.1 ± 0.9 |
| 2 | 0.050 | 15.2 ± 1.9 | 11.5 ± 0.8 | 11.8 ± 0.8 |
| 3 | 0.027 | 11.5 ± 0.8 | 10.5 ± 0.7 | 11.1 ± 0.7 |
| resin lies, pla honest | | | | |
| 1 | 1.00 | 92.7 ± 8.3 | 14.2 ± 0.9 | 17.2 ± 1.1 |
| 2 | 0.081 | 20.9 ± 2.4 | 12.8 ± 0.8 | 15.8 ± 1.1 |
| 3 | 0.039 | 17.6 ± 3.1 | 11.7 ± 0.8 | 14.6 ± 1.0 |

How many seeds fail, at round 3, over 400 attacked runs:

- Strict test (lying trust < 0.5, honest trust ≥ 0.5, honest site's networked ≤ isolated): **217/400 fail**. Most of that is noise: without any attack, networked is already worse than isolated at that site in 152/400 of the same seeds.
- Accounting for noise (networked under attack vs the same seed's networked without attack, with the tolerance set by mirroring the lower tail, 4.1 µm): **112/400 fail**. 103 of those are harm beyond noise: 28 when pla lies, 75 when resin lies. Median harm is 0.9 µm, 90th percentile 9.2 µm, 99th 26 µm.
- Recovery round (first round from which networked stays ≤ isolated): round 2 in 118 runs, round 3 in 71, never within 3 rounds in 211.

Why the tail: leftover trust. Harm correlates with the liar's final trust at 0.66. A message is a Gaussian factor tempered by trust, and the lie is very confident (SD 0.1 prior SD, plus between_site_sd 0.25), so trust of 0.05-0.2 still pulls the shared parameters. Trust falls by exp(eta · dLPD) once per round, so a site with smaller held-out dLPD against the liar keeps it longer. pla is hurt more than resin, consistent with pla's predictions leaning harder on the shared parameters (inference, not tested).

Side effect: the round 1 lie also distorts the honest site's agent credibility. The top agent holds 0.76-0.78 at rounds 2-3 against 0.26-0.27 without the attack (which agent varies by seed). It doesn't correlate with the harm (0.03-0.08), but it doesn't recover within 3 rounds either. The lying site's own credibility is unchanged, as expected, because only its outgoing message is corrupted.

Tier D said the honest site was "not harmed by round 3" from 10 seeds (resin, −0.9 ± 1.3 µm vs isolated). At 200 seeds that direction gives +0.4 ± 0.6 µm, consistent with it; the other direction (pla honest), which tier D didn't run, is +3.1 ± 2.9 µm.

## 2. Ablation

**All of the networking gain comes from the messages.** Cutting the network (`--no-messages`) leaves the networked arm within 0.1-0.3 µm of isolated (CI includes 0), while networked beats isolated by 1.6-1.8 µm in every round. The agent auction on its own adds nothing measurable. Two sites, the same 200 seeds as the honest robustness runs. Full table: [`results/ablation.md`](results/ablation.md).

| round | isolated | no messages | networked | oracle (reference) | iso − net | iso − no messages | oracle − net |
|---|---|---|---|---|---|---|---|
| 1 | 15.12 | 14.85 | 13.38 | 13.70 | 1.75 ± 0.45 | 0.27 ± 0.37 | 0.33 ± 0.41 |
| 2 | 13.77 | 13.64 | 12.12 | 12.48 | 1.64 ± 0.51 | 0.13 ± 0.46 | 0.36 ± 0.43 |
| 3 | 12.82 | 12.62 | 11.12 | 11.53 | 1.70 ± 0.48 | 0.20 ± 0.41 | 0.41 ± 0.45 |

The oracle stays a reference, not an upper bound: it trails networked by 0.3-0.4 µm (CI includes 0), as in the Phase C oracle stage.
