# Cold start: how far can sharing cut model error?

Exploratory, simulation only (`sim/reference.py`), frozen config from `prereg/prereg.yaml` except the cell's settings. Errors are `mae_truth` (held-out model error against noise-free sizes, µm, mean over sites). Gains are isolated − arm, as % of isolated, paired per world. Wins = worlds where networked < isolated; p is an exact two-sided sign test. 5 rounds; 60 / 40 / 20 worlds at 2 / 4 / 8 sites (cost grows ~n² per run).

    PYTHONPATH=. .venv/bin/python hpc/sweeps/coldstart/ceiling.py hpc/sweeps/coldstart/results/grid.jsonl grid         # ~50 min, 18 cores
    PYTHONPATH=. .venv/bin/python hpc/sweeps/coldstart/ceiling.py hpc/sweeps/coldstart/results/knobs.jsonl knobs 0.5   # ~8 min
    .venv/bin/python hpc/sweeps/coldstart/analyze.py hpc/sweeps/coldstart/results/grid.jsonl 3,5
    cd hpc/sweeps/coldstart && ../../../.venv/bin/python analyze_knobs.py results/grid.jsonl results/knobs.jsonl

Two diagnostic predictors are scored next to the arms (they pick no pieces):

- `known_shared`: the isolated arm's data plus the site's **true** shared parameters (a tight Gaussian, 0.1 prior std). Roughly the most that sharing shared-parameter summaries can give. Not a strict bound at cold start: there, networked beats it, because the network also changes which pieces get printed.
- `true θ`: the site's true parameters. What's left is the unmodeled radial plate term (~8 µm). Not a strict floor either: fitted parameters absorb part of it.

## 1. Why 12% is about the ceiling in the current setup

| 2 sites, seed 16, 6/round (current) | Round 3 | Round 5 |
|---|---|---|
| isolated → networked | 13.5 → 12.0 µm (11.2%, 43/60) | 12.4 → 10.2 µm (17.8%, 46/60) |
| isolated → known shared params | 24.2% | 27.0% |
| share of that available gain networked gets | 46% | 66% |

Only 3 of the 7–8 parameters (`size_coef`, `pos_gx`, `pos_gy`) are shared. The site parameters (cure depth, bleed, shrink, extrusion width, flare) can't be learned from another site, and ~8 µm is unmodeled. So even perfect knowledge of the shared physics cuts error by only ~25%, and networked already gets about half of that by round 3. Tuning the messages can't move 12% far.

## 2. Cold start and network size: the levers

Round 3, networked vs isolated:

| | seed 16, 6/rd | seed 4, 2/rd | seed 0, 2/rd (no data) |
|---|---|---|---|
| 2 sites | 11.2% (43/60) | 10.6% (39/60) | 23.9% (41/60), 41.4 → 31.5 µm |
| 4 sites | 18.7% (30/40) | 28.5% (35/40) | 26.7% (30/40) |
| 8 sites | — | **34.7% (20/20)**, 26.9 → 17.6 µm | **38.1% (18/20)**, 40.3 → 24.9 µm |

- **Network size is the lever that holds up.** At a seed of 4 pieces and 2 per round, gain goes 11% → 29% → 35% from 2 → 4 → 8 sites, and 8 sites wins in every world. Each extra site is another independent estimate of the same shared physics.
- **Coming in with no data roughly doubles the relative gain at 2 sites** (11% → 24%). But that is partly because isolated is so bad (41 µm): the absolute errors are 2–3× the current setup's. Relative gain at cold start is a fair headline only alongside the absolute numbers.
- **At 8 sites the oracle stops being an upper bound** (35.9 vs 24.9 µm at seed 0). Its pooled posterior has 3 + 8×(5–8) dimensions, and 15 MH steps don't mix it. Networked passes summaries and keeps each fit small, so it scales where pooling raw data does not.

## 3. Method knobs (2/4 sites, seed 4, 2/round; 8 sites for msg_proposal)

Paired against the same worlds' baseline networked arm (`analyze_knobs.py`). None helps reliably:

| Knob | Effect on networked error |
|---|---|
| `between_site_sd` 0.0 / 0.1 / 0.5 (default 0.25) | within ±1 µm, no consistent sign (best p=0.36 in favor) |
| `discount` 0.0 / 0.5 (default 0.2) | ±1 µm; also moves isolated, no consistent direction |
| `msg_proposal`: draw shared columns from prior × messages instead of reweighting | +0.9 µm at 2 sites round 3 (21/30, p=0.04), nothing at round 5 or at 4 and 8 sites |

About 36 comparisons, so one p≈0.04 is what chance gives. Particle collapse from many tight messages is not hurting networked at 8 sites (`msg_proposal` doesn't help there). The frozen settings are fine; the gain is set by the world and the network size, not the tuning.

## 4. What would raise the ceiling (not tested)

Sharing can only remove error from parameters that are actually shared. In `make_world`, two resin printers draw their site parameters independently, so a second resin site helps a resin site no more than a PLA site does. That is a modeling choice, not a measured fact. If same-model printers on the same material really share most of their cure or extrusion behavior, then passing **process-family parameters** between same-process sites would make most of the remaining error shareable. Test that on real data (two printers of one model) before building it into the sim; otherwise the sim just confirms itself (`docs/build/10-beyond-the-weekend.md`, point 6).
