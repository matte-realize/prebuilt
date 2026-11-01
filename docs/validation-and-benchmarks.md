# Validation and Benchmarks

The evidence behind every claim, in one place: accuracy against single sites, scaling, robustness and controls, calibration, speed, measurement, and the real printer. Each number links to the sweep that produced it.

## Benchmark setup

- **Hidden-truth simulator** (`sim/reference.py`): each world draws its own printers, with shared physics that varies slightly between sites and effects the model doesn't know about (a radial plate term, small-feature print failures). The true printed size of every piece is known.
- **Metric:** held-out model error against the true size (`mae_truth`, µm), averaged over sites, at round 3 unless stated. Held-out pieces are never fitted.
- **Registered config:** the frozen config from `prereg/prereg.yaml` (4000 particles, 6 MH steps, η 5, challenge and spawn off). Anything else is labelled as an opt-in option.
- **Paired worlds:** every comparison changes one thing within the same world seed. p is an exact two-sided sign test over worlds.

## 1. Multi-site vs. single site

Two sites (resin + PLA), 16 seed pieces, 6 slots a round, 100 worlds ([relevance §1](../hpc/sweeps/relevance/README.md#1-current-setup-2-sites-16-piece-seed-6-slots-100-worlds-8-rounds)). Error at round 3: alone 12.6 µm, networked 11.0 µm, pooled raw data 11.3 µm.

| Comparison, round 3 | Gain | Worlds better | p |
|---|---|---|---|
| **Networked vs. single site alone (isolated)** | 1.6 µm, 12.3% (CI 9.1–17.9%) | 75/100 | <0.001 |
| Pooled raw data (oracle, the upper bound) vs. alone | 12.2% | 64/100 | |
| Networked vs. same agents with messages cut | 1.1 µm, 9.9% | 66/100 | 0.002 |
| Messages cut vs. alone (agent layer only) | 2.4% | 56/100 | 0.27 |

Agents vs. random piece selection, 60 worlds ([relevance §8](../hpc/sweeps/relevance/README.md#8-adaptive-spread-subtle-liars-random-selection-frozen-config-60-worlds-3-rounds)):

| Comparison, round 3 | Gain | Worlds better | p |
|---|---|---|---|
| Agent auction vs. random, isolated arm | +1.0% | 31/60 | 0.90 |
| Agent auction vs. random, networked arm | +7.0% | 33/60 | 0.52 |
| Networked vs. alone, random selection | +14.0% | 37/60 | 0.09 |
| Networked vs. alone, agent auction | +10.0% | 44/60 | <0.001 |

Sharing between sites matches pooling the raw data without moving any. The agent layer adds nothing measurable on top.

## 2. Scaling with the number of sites

Data-poor sites (4 warm-up pieces, 2 a round), round 3 ([relevance §7](../hpc/sweeps/relevance/README.md#7-how-many-sites-it-takes-from-hpcsweepscoldstartresultsgridjsonl-no-rerun), [coldstart](../hpc/sweeps/coldstart/README.md)):

| Sites | Worlds | Alone → together (µm) | Gain | Worlds better | p |
|---|---|---|---|---|---|
| 2 | 60 | 26.2 → 23.4 | 10.6% | 39/60 | 0.03 |
| 4 | 40 | 26.5 → 19.0 | 28.5% | 35/40 | <0.001 |
| 8 | 20 | 26.9 → 17.6 | 34.7% | 20/20 | <0.001 |

## 3. Robustness and controls

**Lying site** (confident beliefs 3 prior std off), 60 worlds ([relevance §5](../hpc/sweeps/relevance/README.md#5-consistency-check-as-a-protocol-option-frozen-config--consistency_checktrue-60-worlds-3-rounds)). The site lied to, round 1: 64.0 µm with no defence, 11.6 µm with the consistency check, 11.6 µm with no notes at all. The check caught 180 of 180 lying notes and dropped 0 of 540 honest ones.

**Subtle liars**, resin's round-1 change vs. learning alone ([relevance §8](../hpc/sweeps/relevance/README.md#8-adaptive-spread-subtle-liars-random-selection-frozen-config-60-worlds-3-rounds)):

| Liar offset (prior std) | No defence | Consistency check (notes caught) | Check + adaptive spread |
|---|---|---|---|
| 0.5 | −72% | −17% (84/180) | −5% |
| 1 | −109% | −11% (129/180) | −4% |
| 2 | −279% | +2% (180/180) | +2% |
| 3 | −534% | +2% (180/180) | +2% |

**Negative control:** printers that share no physics, 60 paired worlds ([relevance §6](../hpc/sweeps/relevance/README.md#6-negative-control-printers-that-share-no-physics-frozen-config-60-worlds-3-rounds), [§8](../hpc/sweeps/relevance/README.md#8-adaptive-spread-subtle-liars-random-selection-frozen-config-60-worlds-3-rounds)). If the gain were built into the simulator or the scoring, it would show up here too. It doesn't:

| Together vs. alone, round 3 | Shared physics | Nothing shared |
|---|---|---|
| Fixed spread (registered) | +10.0%, 44/60, p<0.001 | −13.0%, 19/60, p=0.006 |
| Adaptive spread (opt-in) | +10.3%, 44/60, p<0.001 | −0.4%, 30/60, p=1.0 |

**Mixed fleet:** 8 data-poor sites, 4 sharing physics and 4 not, 20 worlds ([relevance §10](../hpc/sweeps/relevance/README.md#10-mixed-fleets-some-printers-share-physics-some-dont-frozen-config-data-poor-sites-3-rounds)). Matched sites gain +16.2% with the fixed spread and +24.7% with both defences. Unmatched sites go from −14.6% to −1.2%.

**Predictive trust** (opt-in), same fleet, 30 worlds ([relevance §11](../hpc/sweeps/relevance/README.md#11-sharper-trust-in-mixed-fleets-longer-runs-and-predictive-trust-frozen-config-data-poor-sites-8-sites-30-worlds)). Scored on the half of the held-out pieces the trust step never saw, round 6: matched sites +32.6% (fixed: +19.5%), unmatched sites +6.8%, 20/30, p=0.10 (fixed: −21.5%). Separation of mismatched senders: AUC 0.76. It doesn't cleanly identify them.

## 4. Calibration

- **Predictive intervals:** 90% intervals cover 90–91% of true sizes in every arm ([relevance §1](../hpc/sweeps/relevance/README.md#1-current-setup-2-sites-16-piece-seed-6-slots-100-worlds-8-rounds)).
- **Corrected designs** (`model/compensate.py`), 60 worlds, 960 cases ([relevance §12](../hpc/sweeps/relevance/README.md#12-corrected-designs-a-calibrated-interval-60-worlds-seed-plate-fit-simulation)): median |true printed − target| goes from 132 µm drawn as-is to 9 µm corrected (90th percentile 305 → 21 µm), and the corrected design is closer in 97% of cases. With the 8.6 µm model-discrepancy term, the 90% interval covers 81% and 96% in two-fold cross-validation (69% without the term).

## 5. Speed

Warp GPU posterior vs. the NumPy reference ([gpu-posterior.md](gpu-posterior.md)):

| Workload | Laptop RTX 5060 | H100 80GB |
|---|---|---|
| One update, 200k particles | 9.9× | 60× |
| 64 posteriors in one batch, 2k particles | 8.6× | 39× |
| 64 posteriors in one batch, 20k particles | 62× | 84× |

A full two-site, 3-round simulated experiment at 2000 particles takes about 1.3 s on a laptop CPU ([spec 11](spec/07-speed-verifiability.md)). The 60–100-world sweeps take minutes on 18 cores.

## 6. Measurement

Flatbed scanner pipeline on synthetic 400 dpi scans, RMS / max error in µm ([design notes](design-notes.md#scanner-stress-test-synthetic), `hpc/scanner_stress/`):

| Condition | Holes | Pins |
|---|---|---|
| Clean | 1.9 / 8.7 | 4.7 / 15 |
| Lighting gradient 30% | 4.2 / 13 | 13 / 39 |
| 150 dust specks | 5.8 / 22 | 9.1 / 57 |
| Blur 3 px | 15 / 76 | 14 / 34 |
| Pin shadow 0.3 mm | | 51 / 65 (bias −50; removed by the caliper offset) |

The scanner has not been tested on real scans.

## 7. Real printer (Formlabs Form Studio 1)

One printer and a micrometer; no scanner and no full real run. The only piece measured is the 1.5 mm calibration pin on the fast test plate (`plates/out/test/resin-test.stl`): 1.411 and 1.476 mm, two readings 65 µm apart. That is too little to fit the model, so it is a sanity check, not a result.

| Check | Value | Verdict |
|---|---|---|
| Vendor spec (±0.08 mm on 1–30 mm features) | 24–89 µm small | inside |
| Simulator: true size of this pin over 500 simulated printers | 1.384–1.79 mm; the mean reading (1.443) is at the 1.8th percentile, the low reading at the 0.4th | inside, at the small edge |
| Model prior, before any data: 90% / 99% predictive interval | 1.460–1.730 / 1.394–1.836 mm (mean 1.586) | below the 90%, inside the 99% |

What it says: the real printer makes this pin smaller than the resin prior expects, and the prior's centre is about 0.14 mm too large for it. That is the error a site's seed plate corrects (the 16 calibration pieces), and the reason the model is fit per site; with one piece, we can't say whether the whole prior is off or only small pins. For a micrometer-only site, the fit-and-predict check is built: put pin readings on a hand sheet (`measure.real.write_manual_sheet` format; µm values and repeated readings are accepted) and run

```
python -m measure.testprint plates/out/test/resin-test.json --manual <sheet.csv>
```

It fits the 8 calibration pins and scores the 4 held-out pins (4.1, 5.8, 7.0, 7.3 mm) the fit never saw, prior error against fitted error. It has not been run on real readings.

## 8. Reproduce

```
.venv/bin/python -m pytest -q                                   # tests; Warp tests skip without warp-lang and a CUDA GPU

# Multi-site vs. single site, regimes (sections 1, 2)
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/worlds.py 100 hpc/sweeps/relevance/results/worlds.jsonl
.venv/bin/python hpc/sweeps/relevance/analyze_worlds.py hpc/sweeps/relevance/results/worlds.jsonl.gz
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/regimes.py hpc/sweeps/relevance/results/regimes.jsonl
.venv/bin/python hpc/sweeps/relevance/analyze_regimes.py hpc/sweeps/relevance/results/regimes.jsonl.gz

# Scaling (section 2)
PYTHONPATH=. .venv/bin/python hpc/sweeps/coldstart/ceiling.py hpc/sweeps/coldstart/results/grid.jsonl grid
.venv/bin/python hpc/sweeps/coldstart/analyze.py hpc/sweeps/coldstart/results/grid.jsonl 3,5

# Robustness and controls (section 3)
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/consistency_protocol.py 60 hpc/sweeps/relevance/results/consistency_protocol.jsonl
.venv/bin/python hpc/sweeps/relevance/analyze_consistency.py hpc/sweeps/relevance/results/consistency_protocol.jsonl.gz
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/negative_control.py 60 hpc/sweeps/relevance/results/negative_control.jsonl
.venv/bin/python hpc/sweeps/relevance/analyze_negative_control.py hpc/sweeps/relevance/results/negative_control.jsonl.gz
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/technical.py 60 hpc/sweeps/relevance/results/technical.jsonl
.venv/bin/python hpc/sweeps/relevance/analyze_technical.py hpc/sweeps/relevance/results/technical.jsonl.gz
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/mixed_fleet.py 20 hpc/sweeps/relevance/results/mixed_fleet.jsonl --sites 8
.venv/bin/python hpc/sweeps/relevance/analyze_mixed_fleet.py hpc/sweeps/relevance/results/mixed_fleet.jsonl.gz
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/sharper_trust.py 20 hpc/sweeps/relevance/results/sharper_trust_split.jsonl --rounds 6 --split --only alone,fixed,predictive,pred_check
.venv/bin/python hpc/sweeps/relevance/analyze_sharper_trust.py --split hpc/sweeps/relevance/results/sharper_trust_split.jsonl.gz

# Calibration (section 4)
PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/compensate_calibration.py 60 hpc/sweeps/relevance/results/compensate_calibration.jsonl
.venv/bin/python hpc/sweeps/relevance/analyze_compensate_calibration.py hpc/sweeps/relevance/results/compensate_calibration.jsonl.gz

# Speed (section 5)
PYTHONPATH=. .venv/bin/python hpc/bench_posterior.py --batch 64
```

The committed results (`results/*.jsonl.gz`) are what the analyzers read, so every table can be re-derived without rerunning a sweep.

## Limits

- **The sharing results are simulation only.** No full real-printer run took place; the real evidence is a sanity check of error size on one printer.
- **At two sites the gain is tiny:** 1.6 µm, against roughly 31 µm of scanner noise. It can't be seen on real parts; it grows with the number of data-poor sites.
- **The agents don't beat random piece selection.** The gain comes from sharing between sites, not from the agent layer.
- **Trust doesn't cleanly identify mismatched printers.** The defences make sharing safe on average; the best separation is AUC 0.77.
- **The simulator's physics is the model's physics plus a few extra effects.** The negative control shows the gain isn't built in, but a real printer can differ in ways neither has.

## Prior work this builds on

The pitch's "built on proven science" slide cites these. Numbers are from each paper's abstract; check the full text before quoting details.

- **The error is real.** Desktop SLA, 54 CMM-measured specimens (5, 10, 20 mm; 25–100 µm layers): pins oversized up to about +195 µm, holes undersized up to about −250 µm. *Tehnički vjesnik* (2026), [hrcak.srce.hr/345003](https://hrcak.srce.hr/345003).
- **Correcting it works.** Q. Huang, J. Zhang, A. Sabbaghi, T. Dasgupta, "Optimal offline compensation of shape shrinkage for three-dimensional printing processes," *IISE Transactions* 47(5):431–441, 2015, [ideas.repec.org](https://ideas.repec.org/a/taf/uiiexx/v47y2015i5p431-441.html).
- **Transfer across processes.** A. Sabbaghi, Q. Huang, "Model transfer across additive manufacturing processes via mean effect equivalence of lurking variables," *Annals of Applied Statistics* 12(4):2409–2429, 2018, [projecteuclid.org](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-12/issue-4/Model-transfer-across-additive-manufacturing-processes-via-mean-effect-equivalence/10.1214/18-AOAS1158.full).
- **Sharing helps data-poor printers.** A.-T. Wei, H. Wang, T. Dickens, H. Chi, "Co-learning of extrusion deposition quality for supporting interconnected additive manufacturing systems," *IISE Transactions* 55(4):405–418, 2023, [ideas.repec.org](https://ideas.repec.org/a/taf/uiiexx/v55y2023i4p405-418.html). Shares covariance structure across printers; data is pooled.
- **Federated learning in printing so far targets defect images.** Tang et al., federated transfer learning for AM defect identification, *Robotics and Computer-Integrated Manufacturing*, 2024, doi:10.1016/j.rcim.2024.102779.
- **Fit thresholds in dentistry.** Printed crowns are typically judged against a marginal gap of 120 µm or less (stricter work uses 50 µm); e.g. [explorationpub.com/uploads/Article/A101320/101320.pdf](https://explorationpub.com/uploads/Article/A101320/101320.pdf).
- **Point-of-care printing and patient data.** Accuracy and in-house workflows for 3D-printed surgical guides: systematic review, [PMC11317891](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11317891/).
- **Semiconductor fabs keep tool data in silos.** imec's privacy-preserving amalgamated machine learning (PAML) trains across fab and tool-vendor silos and reports performance close to a pooled model (T. Ashby, imec, SEMI 2021, [slides](https://semi.org/sites/semi.org/files/2021-11/06%20Tom%20Ashby%20IMEC_0.pdf)); the 2025 VLSI Symposium workshop on federated digital twins covers the same need ([workshop](https://www.vlsisymposium.org/workshop/workshop2025_8)). This is the direction for Prebuilt, not a result.
