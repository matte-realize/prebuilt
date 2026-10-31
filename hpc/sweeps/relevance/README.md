# Relevance sweeps: does sharing matter, and where?

Exploratory analyses on the frozen config unless stated. Simulation only (`sim/reference.py`), default `Config` unless stated. Errors are `mae_truth`: held-out model error against the noise-free sizes, in µm, averaged over sites. Results are committed gzipped (the sweep scripts write plain `.jsonl`; gzip them, or point the analyzers at either). Every gain is paired per world (same world seed, one thing changed). p is an exact two-sided sign test over worlds.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/worlds.py 100 hpc/sweeps/relevance/results/worlds.jsonl    # ~4 min on 18 cores
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/regimes.py hpc/sweeps/relevance/results/regimes.jsonl      # ~8 min
    .venv/bin/python hpc/sweeps/relevance/analyze_worlds.py hpc/sweeps/relevance/results/worlds.jsonl.gz
    .venv/bin/python hpc/sweeps/relevance/analyze_regimes.py hpc/sweeps/relevance/results/regimes.jsonl.gz
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/evidence.py    # writes viewer/evidence.json for the 3D demo

## 1. Current setup (2 sites, 16-piece seed, 6 slots), 100 worlds, 8 rounds

Frozen config from `prereg/prereg.yaml` via `frozen.py` (4000 particles, 6 MH steps, eta 5, challenge and spawn off). Round 3 is the headline because the real experiment prints 3 rounds.

| Paired gain | Round 3 | Round 8 |
|---|---|---|
| Networked vs isolated | 1.6 µm (12.3%, CI 9.1–17.9%), better in 75/100, p<0.001 | 1.3 µm (13.9%), 65/100 |
| Pooled raw data (oracle) vs isolated | 12.2%, 64/100 | 9.8%, 66/100 |
| Networked vs same arm with messages cut | 1.1 µm (9.9%), 66/100, p=0.002 | 0.7 µm (7.8%), 63/100 |
| Networked with messages cut vs isolated | 2.4%, 56/100, p=0.27 | 2.7%, 56/100, p=0.27 |
| Bad site present vs messages cut | 0.7%, 52/100, p=0.76 | −1.2%, 49/100, p=0.92 |

- Networked is at or below the pooled-data oracle (round 3: 11.0 vs 11.3 µm). The gain comes from the messages, not from learned credibility.
- Absolute size is small: 12.6 → 11.0 µm at round 3. Scanner noise is ~31 µm (median measured MAE), so on measured diameters networked vs isolated is 1.5% at round 8 (69/100). Three real rounds can't detect it.
- 90% intervals cover 90–91% of true sizes in every arm.
- Bad site (`bad_sites=pla`): resin's trust in pla goes 1.0 → 0.01 after round 1. Round 1 is costly (39.8 vs 14.3 µm with messages cut, worse in 100/100). After that the damage is contained, but the benefit of the honest site's messages is lost: the bad-site condition is level with no messages.
- Jake's particles stage found the same drop: at 2000 particles and 3 MH steps, poor mixing inflated isolated − networked (2.2 → 1.4 µm in his runs). Earlier versions of this README used 2000/3 and, before that, eta 20; their gains were larger for that reason.

## 2. Regimes, 60 worlds each, 5 rounds (frozen config)

| Setting | Gain, round 3 | Better in | Measured gain, round 3 | Wrong fit calls / 100 (iso → net, rounds 1–5) |
|---|---|---|---|---|
| 2 sites, seed 16, 6 slots (current) | 1.2 µm (10.0%) | 44/60 | 1.9% | 2.7 → 2.2 |
| 2 sites, seed 4, 2 slots | 2.7 µm (9.9%) | 35/60, p=0.25 | 7.5% | 6.3 → 5.4 |
| 2 sites, seed 8, 2 slots | 2.4 µm (15.3%) | 43/60 | 4.8% | 4.1 → 4.0 |
| 4 sites, seed 8, 6 slots | 2.3 µm (17.9%) | 45/60 | 1.5% | 3.4 → 3.0 |
| 4 sites, seed 4, 2 slots | 6.9 µm (27.4%) | 51/60 | 10.9% | 6.5 → 4.8 |

Full table (rounds 1, 3, 5, plus the messages-cut comparison) from `analyze_regimes.py`. Neither more sites nor less data per site raises the gain much on its own; the combination does. Many sites that each know little is where sharing pays, and there it shows through scanner noise. Fit pairs are pooled over worlds and rounds; they are sparse (2–3 scored pairs per site per round).

`trust_init` 0.3 instead of 1.0 (current setup, bad site): round-1 networked error 29.7 vs 38.8 µm, so it only partly limits the damage, and it costs a little with honest sites (round 1: 13.0 vs 12.6 µm). The consistency check in section 4 removes the damage instead. The bad site's beliefs are confident outliers (3 prior std off, 0.1 std wide), so a consistency check of incoming summaries against the receiver's own posterior would likely catch them in round 1. Not implemented: it changes the protocol and frozen config.

## 3. A saboteur agent, 100 worlds, 5 rounds (frozen config)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/saboteur.py 100 hpc/sweeps/relevance/results/saboteur.jsonl
    .venv/bin/python hpc/sweeps/relevance/analyze_saboteur.py hpc/sweeps/relevance/results/saboteur.jsonl.gz

The `geometry` agent is replaced by one that always proposes the least informative pieces (lowest expected information gain), in every arm. Isolated clears at equal credibility, networked at learned credibility; with messages cut they differ only in credibility.

| Round 5, saboteur minus honest | Equal votes | Learned credibility |
|---|---|---|
| Messages cut | +0.6 µm, worse in 60/100 | +0.1 µm, worse in 53/100 |
| Messages on | −0.1 µm, worse in 47/100 | +0.8 µm, worse in 61/100 |

- The saboteur barely hurts: which pieces get printed hardly matters in this design space.
- Learned credibility doesn't catch it: the saboteur's credibility stays at ~0.195, level with the honest agent's, and it keeps ~20% of networked slots every round. One slot per round moves held-out LPD too little to separate a bad agent from a good one through the noise.
- So the within-site agent market isn't justified here on accuracy or on robustness. The multi-agent behavior with evidence is between sites: trust drops a lying site to ~1% after one round.

An earlier run of this sweep was invalid: worker processes are reused, and a patch installed for one saboteur job leaked into later honest jobs (90 of 100 worlds came out identical). `saboteur.py` now sets the agent explicitly on every job.

## 4. Prototype: quarantine notes that contradict the receiver's own data (frozen config, 100 worlds, 3 rounds)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/consistency.py 100 hpc/sweeps/relevance/results/consistency.jsonl
    .venv/bin/python hpc/sweeps/relevance/analyze_consistency.py hpc/sweeps/relevance/results/consistency.jsonl.gz

After each broadcast, the receiver compares every incoming shared-parameter summary with its own local posterior (own data, no messages): per parameter z = (m_in − m_own) / sqrt(v_in + v_own + s_b²), with s_b = `between_site_sd` × prior std. A note whose Σz² exceeds the chi-square 0.999 quantile (16.3 for 3 parameters) is dropped for that round; trust is untouched, so the sender is re-checked next round. Monkeypatched onto `arms.experiment._broadcast`; no repo code changes.

| Networked, true-size error (µm), median | Round 1 | Round 2 | Round 3 |
|---|---|---|---|
| No notes | 14.3 | 12.6 | 11.9 |
| Honest notes | 12.6 | 11.5 | 11.0 |
| Honest notes + check | 12.6 | 11.5 | 11.0 |
| Bad site, no check | 39.8 | 12.9 | 11.8 |
| Bad site + check | 13.2 | 12.2 | 11.1 |

- Bad site's notes caught: 300 of 300 (lowest Σz² 58). Honest notes wrongly dropped: 0 of 900 (99th percentile Σz² 12.6).
- Round-1 damage is gone: resin, which receives the bad notes, goes from 65.9 to 11.4 µm (no notes: 11.5). Check vs no check under attack: 26.5 µm better in round 1, in 100/100 worlds.
- The honest benefit survives an attack: with the check, the bad-site condition beats no notes by 1.25 µm at round 3 (68/100) and is level with all-honest notes (11.1 vs 11.0), because the bad notes are dropped rather than left at ~1% trust.
- No cost with honest sites: nothing was dropped, so results are identical.
- Caveats: this bad site is easy to catch (3 prior std off, 0.1 std wide). A subtle one that stays within the allowed spread passes and is left to trust. On real printers, model mismatch may raise honest Σz² toward the threshold (simulated 99th percentile 12.6 vs 16.3). Adopting it changes the protocol and the frozen config, so it is a secondary analysis for this weekend, not part of the registered experiment.

Related: `hpc/sweeps/phase_c/README.md` section 1 found the same seed-plate effect on measured MAE (seed 4: 22% at round 3; seed 56: no separation).
