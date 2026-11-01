# Relevance sweeps: does sharing matter, and where?

Exploratory analyses on the frozen config unless stated. Simulation only (`sim/reference.py`), default `Config` unless stated. Errors are `mae_truth`: held-out model error against the noise-free sizes, in µm, averaged over sites. Results are committed gzipped (the sweep scripts write plain `.jsonl`; gzip them, or point the analyzers at either). Every gain is paired per world (same world seed, one thing changed). p is an exact two-sided sign test over worlds.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/worlds.py 100 hpc/sweeps/relevance/results/worlds.jsonl    # ~4 min on 18 cores
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/regimes.py hpc/sweeps/relevance/results/regimes.jsonl      # ~8 min
    .venv/bin/python hpc/sweeps/relevance/analyze_worlds.py hpc/sweeps/relevance/results/worlds.jsonl.gz
    .venv/bin/python hpc/sweeps/relevance/analyze_regimes.py hpc/sweeps/relevance/results/regimes.jsonl.gz
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/evidence.py    # writes viewer/evidence.json for the 3D demo (sections 1, 2, 4–7)

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

`trust_init` 0.3 instead of 1.0 (current setup, bad site): round-1 networked error 29.7 vs 38.8 µm, so it only partly limits the damage, and it costs a little with honest sites (round 1: 13.0 vs 12.6 µm). The consistency check in section 4 removes the damage instead. The bad site's beliefs are confident outliers (3 prior std off, 0.1 std wide), so a consistency check of incoming summaries against the receiver's own posterior catches them in round 1 (sections 4 and 5). It is now a protocol option, `Config.consistency_check`, off in the frozen config.

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

## 5. Consistency check as a protocol option (frozen config + `consistency_check=True`, 60 worlds, 3 rounds)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/consistency_protocol.py 60 hpc/sweeps/relevance/results/consistency_protocol.jsonl   # ~11 min
    .venv/bin/python hpc/sweeps/relevance/analyze_consistency.py hpc/sweeps/relevance/results/consistency_protocol.jsonl.gz

Section 4's check, built into `arms/experiment.py` (`Config.consistency_check`, default off) instead of monkeypatched. Same statistic and threshold; the receiver's own summary is the local fit it already makes for its outgoing note (no refit), and every check is a row in `Results.checks` and an entry on the receiver's receipt chain. Off in the frozen/registered config: this is an added option evaluated in simulation.

| Networked, true-size error (µm), median | Round 1 | Round 2 | Round 3 |
|---|---|---|---|
| No notes | 14.9 | 12.4 | 11.6 |
| Honest notes | 12.6 | 11.2 | 10.8 |
| Honest notes + check | 12.6 | 11.2 | 10.8 |
| Bad site, no check | 38.8 | 12.3 | 11.4 |
| Bad site + check | 13.2 | 12.2 | 10.6 |

- Bad site's notes caught: 180 of 180 (lowest Σz² 63). Honest notes wrongly dropped: 0 of 540 (360 in honest runs, 180 from the honest site in bad-site runs; 99th percentile Σz² 12.8, threshold 16.3). The prototype's 300/300 and 0/900 hold up.
- Resin, the site lied to, round 1: 64.0 µm without the check, 11.6 µm with it, 11.6 µm with no notes. Check vs no check under attack, round 1: 26.4 µm better, in 60/60 worlds.
- Honest gain preserved: nothing was dropped in honest runs, so results are identical (together vs alone 10.0%, 44/60, p<0.001, with or without the check). Under attack with the check, notes still beat no notes at round 3 by 1.2 µm (10.7%, 42/60, p=0.003); without the check that benefit was lost (section 1).
- Same caveats as section 4: this liar is easy to catch, and real-printer model mismatch may push honest Σz² toward the threshold.

## 6. Negative control: printers that share no physics (frozen config, 60 worlds, 3 rounds)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/negative_control.py 60 hpc/sweeps/relevance/results/negative_control.jsonl   # ~6 min
    .venv/bin/python hpc/sweeps/relevance/analyze_negative_control.py hpc/sweeps/relevance/results/negative_control.jsonl.gz

`make_world(..., independent_shared=True)` draws each site's "shared" parameters independently from the prior, with the same rng draws otherwise, so each control world is paired with the normal world of the same seed. If the gain were built into the simulator or the scoring, it would show up here too.

| Round 3, paired per world | Shared physics (normal) | Nothing shared (control) |
|---|---|---|
| Alone → together (µm) | 12.2 → 10.8 | 12.7 → 14.0 |
| Together vs alone | +1.2 µm (10.0%), 44/60, p<0.001 | −1.7 µm (−13.0%, CI −21 to −4%), 19/60, p=0.006 |
| Notes vs messages cut | +0.9 µm (7.7%), 39/60, p=0.03 | −1.8 µm (−13.7%), 13/60, p<0.001 |
| Pooled raw data vs alone | +0.6 µm (5.8%), 34/60, p=0.37 | −2.7 µm (−24.3%), 14/60, p<0.001 |
| With consistency check: notes dropped | 0 of 360 | 80 of 360 (16 of 60 worlds) |
| With consistency check: together vs alone | 10.0%, 44/60 (identical) | −3.0%, 26/60, p=0.37 |

- The gain is not built in: with nothing to share, sharing gains nothing.
- It is not harmless, though. Without shared physics the notes cost 13% and pooling the raw data costs 24%: the model assumes the shared parameters agree across sites to within `between_site_sd` (0.25 prior std), and here they differ by ~1.4 prior std, so the hierarchy pulls each site toward a common value that isn't there. Sharing pays only when the physics really is shared, and the model has no way of finding out that it isn't, beyond trust.
- The consistency check catches part of it: it drops the most contradictory notes (80 of 360) and the cost falls from −13% to −3% (not significant). Not a fix; a reason to keep the check on if real sites may differ more than the model allows.

## 7. How many sites it takes (from `hpc/sweeps/coldstart/results/grid.jsonl`, no rerun)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/evidence.py    # writes sites_needed into viewer/evidence.json

Warm-up 4 pieces, 2 per round, round 3; % = mean gain / mean isolated error, as in the coldstart README; wins are per world.

| Sites | Worlds | Alone → together (µm) | Gain | Better in | p | Paired median gain |
|---|---|---|---|---|---|---|
| 2 | 60 | 26.2 → 23.4 | 10.6% | 39/60 | 0.03 | 9.3% |
| 4 | 40 | 26.5 → 19.0 | 28.5% | 35/40 | <0.001 | 24.3% |
| 8 | 20 | 26.9 → 17.6 | 34.7% | 20/20 | <0.001 | 36.3% |

The deck's 11% / 29% / 35% (20 of 20 at eight sites) check out against the data.

Related: `hpc/sweeps/phase_c/README.md` section 1 found the same seed-plate effect on measured MAE (seed 4: 22% at round 3; seed 56: no separation).

## 8. Adaptive spread, subtle liars, random selection (frozen config, 60 worlds, 3 rounds)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/technical.py 60 hpc/sweeps/relevance/results/technical.jsonl
    .venv/bin/python hpc/sweeps/relevance/analyze_technical.py hpc/sweeps/relevance/results/technical.jsonl.gz

`Config.adaptive_spread`: each receiver scales a sender's message variance by the running mean, over rounds, of their per-parameter disagreement (z² against its own fit, floored at 1). Senders that agree keep full weight; senders that keep disagreeing fade out smoothly. `both` = adaptive spread plus the consistency check. Together vs alone is paired within each run (same world, same seed plate), as in sections 5–6. Round 3, true-size error.

| Together vs alone | Shared physics | Nothing shared (negative control) |
|---|---|---|
| Fixed spread (frozen config) | +10.0%, 44/60, p<0.001 | −13.0%, 19/60, p=0.006 |
| Consistency check | +10.0%, 44/60 | −3.0%, 26/60, p=0.37 |
| Adaptive spread | +10.3%, 44/60, p<0.001 | −0.4%, 30/60, p=1.0 |
| Both | +10.3%, 44/60, p<0.001 | +1.7%, 34/60, p=0.37 |

- **Adaptive spread removes the harm when printers share nothing and keeps the gain when they do.** Against the fixed spread in the control worlds it is 6.0% better, in 45/60 (p<0.001); in normal worlds it changes nothing that matters.

Lying site (pla), resin's error vs learning alone in the same run. Offset = how far the liar's confident beliefs sit from the prior mean, in prior std (the earlier sweeps used 3).

| Offset | No defence, round 1 | Check: round 1, notes caught | Adaptive: round 1 | Both: round 1 | Both: round 3 |
|---|---|---|---|---|---|
| 0.5 | −72% (6/60) | −17%, 84/180 | −9% | −5% (26/60) | −4% |
| 1 | −109% (2/60) | −11%, 129/180 | −8% | −4% (23/60) | −2% |
| 2 | −279% (0/60) | +2%, 180/180 | −6% | +2% (32/60) | −0.3% |
| 3 | −534% (0/60) | +2%, 180/180 | +4% | +2% (32/60) | −0.3% |

- **The check alone catches a liar 2+ prior std off every time but misses about half of subtle ones** (0.5–1 std), and those still cost 11–17% in round 1. Adaptive spread bounds the damage at every offset but recovers more slowly from a blatant liar (round 3: −6%). **Both together is the best defence everywhere:** worst round-1 cost 5%, against 72–534% with no defence.

Random piece selection (`Config.selection="random"`, every arm) vs the agent auction:

| | Result |
|---|---|
| Agents vs random, isolated arm | +1.0%, 31/60, p=0.90 |
| Agents vs random, networked arm | +7.0%, 33/60, p=0.52 |
| Together vs alone with random selection | +14.0%, 37/60, p=0.09 |
| Together vs alone with agents | +10.0%, 44/60, p<0.001 |

- **The agents' piece choices don't beat random** in either arm. The network gain survives without them (noisier with random pieces). Consistent with section 1: the win is sharing between sites, not the agent layer.

## 9. Micro-scale: does the gain grow on small features? (frozen config, 60 worlds, 3 rounds)

`microscale.py` / `analyze_microscale.py`, results in `results/microscale.jsonl.gz` and `results/microscale-summary.json`. Same frozen config and worlds; only the plate changes (patched per worker, defaults untouched): agents propose 0.4–1.0 mm instead of 1.5–7.0 mm, library 0.3–1.2 mm. "Fine" printers scale the simulator's 50% failure diameters by 0.2, a hypothetical finer process; "default" keeps them. Round 3, true-size error on held-out pieces that printed, paired per world.

| Pair, plate, printer | Held-out failed | Alone | Together | Gain (median) | Worlds better | Error / feature size |
|---|---|---|---|---|---|---|
| resin + PLA, normal | 8% | 12.9 µm | 11.1 µm | +10.0% | 44/60, p<0.001 | 0.37% → 0.32% |
| resin + PLA, small, fine | 9% | 12.6 µm | 11.3 µm | +9.1% | 38/60, p=0.05 | 2.0% → 1.9% |
| resin + PLA, small, default | 93% | 67.8 µm | 62.4 µm | +4.7% | 25/45, p=0.55 | 6.3% → 5.9% |
| resin + resin, normal | 3% | 10.6 µm | 9.5 µm | +8.9% | 37/60, p=0.09 | 0.34% → 0.30% |
| resin + resin, small, fine | 7% | 10.4 µm | 9.6 µm | +7.2% | 41/60, p=0.006 | 1.7% → 1.6% |
| resin + resin, small, default | 89% | 39.3 µm | 33.9 µm | +9.6% | 35/60, p=0.25 | 4.1% → 3.5% |

- **The sharing gain does not grow on small features.** It holds at 7–9% on a sub-millimetre plate (normal plate: 9–10%). The absolute error is about the same (~10–13 µm), so relative to the part it is about five times larger (2% of a 0.7 mm feature vs 0.4% of a 4.5 mm one). Likely why the gain doesn't grow: the shared `size_coef / d` term is easier for each site to learn alone when the pieces are small, so the other site's notes add less.
- **With the simulator's own failure model, these printers can't make the small plate.** 89–93% of held-out pieces fail, PLA scores no held-out piece in 15 of 60 worlds, and the comparison is noise. The "fine" rows assume a process that can print the features.
- **The physics doesn't extrapolate far below 1 mm.** Under the priors, the PLA hole model (`poly_k / d`) predicts a negative diameter for 95% of printers at 0.3 mm and 74% at 0.5 mm; resin holes go negative for 14% at 0.3 mm. The terms that dominate at micro scale (resin overcure and light scatter, nozzle limits) aren't modelled, and a real micro-scale process would also measure with less noise than 30–40 µm. Read the small-plate rows as "the method still works on the model as written", not as a micro-scale prediction.
- Consistency: the normal resin + PLA row reproduces section 8 (+10.0%, 44/60).

So for the pitch: the micro-scale angle stays a direction, not a result. What simulation supports is narrower: on sub-millimetre features the gain holds (7–9%) while the same error is a five times larger fraction of the part.

## 10. Mixed fleets: some printers share physics, some don't (frozen config, data-poor sites, 3 rounds)

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/mixed_fleet.py 40 results/mixed_fleet.jsonl --sites 4
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/mixed_fleet.py 20 results/mixed_fleet.jsonl --sites 8
    .venv/bin/python hpc/sweeps/relevance/analyze_mixed_fleet.py hpc/sweeps/relevance/results/mixed_fleet.jsonl.gz --json results/mixed-fleet-summary.json

Section 6 is all-or-nothing. Here half the sites share the common draw of the shared parameters ("matched") and half draw them on their own ("unmatched", `make_world(independent_sites=...)`; same draws otherwise, so worlds stay paired). Sites start data-poor as in section 7 (warm-up 4 pieces, 2 per round). Together vs alone is paired within each run; % is the paired median, round 3, true-size error.

**8 sites (4 matched, 4 unmatched), 20 worlds**

| Together vs alone | Matched sites | Unmatched sites |
|---|---|---|
| Fixed spread (frozen) | +16.2%, 17/20, p=0.003 | −14.6%, 8/20, p=0.50 |
| Consistency check | +16.5%, 17/20 | −4.1%, 9/20 |
| Adaptive spread | +24.7%, 17/20, p=0.003 | −5.2%, 8/20 |
| Both | +24.7%, 17/20, p=0.003 | −1.2%, 8/20 |

Against fixed spread, both is better for unmatched sites in 16/20 (p=0.01) and for matched sites in 14/20 (p=0.12).

**4 sites (2 matched, 2 unmatched), 40 worlds:** too few matched partners for a clear gain. Matched sites gain +2.4% fixed and +9.4% with both (25/40, p=0.15); unmatched −3.5% fixed, +0.8% with both. Adaptive beats fixed for both groups in 21/40 worlds (p=0.02), by small amounts.

**Does trust separate them?** Partly. The adaptive multiplier on a sender after round 3 (1 = full weight):

| Receiver ← sender | 4 sites: mean, >2× | 8 sites: mean, >2× |
|---|---|---|
| matched ← matched | 1.00, 0% | 1.05, 2% |
| matched ← unmatched | 1.23, 8% | 1.41, 12% |
| unmatched ← matched | 1.23, 8% | 1.41, 12% |
| unmatched ← unmatched | 1.06, 0% | 1.21, 7% |

Matched pairs keep full weight; mismatched pairs are down-weighted on average, but the median is still 1. Data-poor sites have wide fits, so most mismatches stay inside what the model allows after three rounds. The consistency check drops 0 of 720 matched-to-matched notes and 20 of 960 mismatched ones (8 sites).

- **What it shows:** in a mixed fleet, matched sites still gain, and the defences make the gain larger (+16% → +25% at 8 sites) while cutting the harm to unmatched sites (−15% → −1%). The fixed spread lets unmatched sites pull matched ones off; down-weighting them helps both sides.
- **What it doesn't:** trust doesn't yet cleanly sort senders into "listen" and "ignore" within three rounds; it nudges. Unmatched sites still don't gain (they have no one to learn from) and the 8-site run is 20 worlds. Simulation only; added options, off in the registered config.

## 11. Sharper trust in mixed fleets: longer runs and predictive trust (frozen config, data-poor sites, 8 sites, 30 worlds)

Section 10's fleet (8 sites, 4 share physics, 4 draw their shared parameters on their own), run for 8 rounds. Two ideas: (A) give adaptive spread more rounds; (B) **predictive trust** (`Config.predictive_trust`, off in the frozen config): each round, before a sender's note is used again, the receiver checks how well that note alone predicts its own newly measured held-out pieces, compared with its own data alone. That gives a score d in nats, and the receiver scales the note's spread by max(1, e^−d), the likelihood ratio against it, capped at 10⁴. `sharper_trust.py`, `analyze_sharper_trust.py`, `results/sharper_trust.jsonl.gz`, `sharper-trust-summary.json`. Together vs alone, paired median, true-size error:

| Round | Condition | Matched sites | Unmatched sites | Separation (AUC) |
|---|---|---|---|---|
| 3 | fixed (frozen) | +16.2% (26/30) | −20.3% (8/30) | |
| 3 | adaptive + check | +20.2% (26/30) | −11.4% (9/30) | 0.60 |
| 3 | predictive | +27.6% (29/30) | +14.5% (24/30) | 0.72 |
| 6 | fixed | +17.2% (26/30) | −25.7% (8/30) | |
| 6 | adaptive + check | +26.0% (28/30) | −7.4% (13/30) | 0.66 |
| 6 | predictive | +33.4% (30/30) | +14.8% (23/30) | 0.76 |
| 8 | fixed | +17.3% (26/30) | −26.6% (6/30) | |
| 8 | adaptive | +30.7% (26/30) | −10.6% (11/30) | 0.71 |
| 8 | adaptive + check | +14.3% (25/30) | −12.2% (13/30) | 0.71 |
| 8 | predictive | +32.1% (27/30) | +10.5% (19/30) | 0.77 |

AUC is the chance that a mismatched sender gets a larger spread multiplier than a matched sender, measured at matched receivers. 0.5 means no separation; 1 means perfect.

- **(A) Longer runs help adaptive spread, but slowly.** AUC rises from 0.60 to 0.66 to 0.71, and the share of mismatched senders down-weighted more than 2× rises from 12% to 22% to 32%. Matched pairs stay at full weight (1–2% above 2×). Unmatched sites are still hurt at round 8 (−11%).
  - Adaptive + check at round 8 (+14% matched) is lower than adaptive alone (+31%), and I haven't explained that.
- **(B) Predictive trust ranks senders better and changes the outcome.** Matched sites gain 28–33%, against 16–17% under fixed. Unmatched sites go from hurt (−20 to −27%) to helped (+11 to +15%).
  - A likely reason they're helped: some other site's independent draw happens to sit close to theirs, and predictive trust finds it.
  - Against fixed, predictive is better in 23–24 of 30 worlds for matched sites and 27–28 of 30 for unmatched.
  - Adding the check (`pred_check`) changes little.
- **Neither rule cleanly separates the groups.** Predictive trust's median multiplier for a mismatched sender at a matched receiver is 2.7× at round 3 and 22× at round 8, but 35% of mismatched senders still pass under 2×. It also down-weights 18–24% of matched senders more than 2×, a false-alarm rate adaptive spread doesn't have. Don't claim either rule "identifies" bad partners.
- **Leakage check (`--split`, `results/sharper_trust_split.jsonl.gz`, `sharper-trust-split-summary.json`).** Predictive trust scores notes on held-out pieces, and the evaluation uses those same pieces. So we reran with trust scoring only half of the held-out pieces (`predictive_half`) and measured error on each half separately (30 worlds, 6 rounds). On the half trust never saw:
  - Matched sites: +23.7% at round 3 and +32.6% at round 6, against +16.4% and +19.5% under fixed. The gain holds.
  - Unmatched sites: +2.8% and +6.8% (20/30, p=0.10), against −19.3% and −21.5% under fixed. Their gain shrinks: on the half trust saw it was +7.7% and +17.5%. Part of the unmatched gain in the table above is optimism from choosing notes on the test pieces.
  - What survives: predictive trust removes the harm to mismatched sites and lifts matched sites to about a third better than alone. It does not reliably make mismatched sites better off.
- Cost: one extra fit per sender, per receiver, per round (56 at 8 sites), about 15% more time per run here.

Caveats: simulation only, one fleet layout (8 sites, half mismatched). Trust uses the receiver's held-out pieces, as the existing sender trust already does, so a fair test needs pieces trust never sees; the split above is that test. The rounds 6 and 8 rows come from the same runs as round 3, read at a later round.

## 12. Corrected designs: a calibrated interval (60 worlds, seed plate fit, simulation)

`compensate_calibration.py` fits each site on its full seed plate (1000 particles), asks `model.compensate` for pins and holes at 2, 3, 5, 7 mm, and compares with the simulator's true printed size at the draw size. 960 cases. `analyze_compensate_calibration.py` writes `results/compensate-calibration-summary.json`.

- **Corrected designs work:** median |true printed − target| 132 µm drawn as-is → 9 µm corrected (90th percentile 305 → 21 µm), corrected closer in 97% of cases. The earlier 118 → 6 µm was the first 10 of these worlds.
- **The old interval was overconfident.** The 90% printer-mean interval (parameter uncertainty only) covered 69% of true sizes. The leftover error has no bias (within ±2 µm per site and kind) but is wider than the posterior thinks: residual sd 11–14 µm against a model sd of 7–9 µm. The simulator has effects the model lacks, so this is model discrepancy, not a bug.
- **Fix:** a pooled discrepancy term, 8.6 µm, added in quadrature to both intervals (`model.compensate.DISCREPANCY_MM`, `discrepancy=False` to turn it off). Two-fold cross-validation (fit on worlds 0–29, cover 30–59, and the reverse): 96% and 81%, mean 88%. Worlds differ in how heavy their tails are, so one half alone over- or under-states it. 90% half-width becomes about 16–24 µm.
- Per site and kind (fit on 0–29, test on 30–59) the term would be 7–11 µm; one pooled value is simpler and about as good.

Caveat: calibrated against this simulator. A real printer will have its own discrepancy; the hand-measurement sheet is how to estimate it.
