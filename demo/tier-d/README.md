# Tier D demo: pure simulation

The fallback if no printer is usable (prereg `fallback_tiers.D`): everything here comes from the hidden-truth simulator, and is labeled that way wherever it's shown. It's also the backup demo for any tier.

Generated at commit `3559da5` from a clean checkout, with the **frozen config** from `prereg/prereg.yaml` (eta 5, trust_init 1.0, cred_floor 0.05, discount 0.2, 4000 particles, 6 MH steps). `run.py --source sim` and `viewer.export` read that config from the prereg, so the commands below reproduce it.

| File | What |
|---|---|
| `headline-truth.png/.pdf` | Slide 6 on noise-free held-out error (what the models actually learned) |
| `headline-measured.png/.pdf` | The same chart on measured error (what real rounds would show) |
| `run-seed0.html` | Viewer page for one run: plates, intervals, credibility, messages, audit, receipts. Open in any browser, offline |
| `run-bad-site.html` | The same run with the PLA site broadcasting corrupted beliefs |
| `sim.json`, `bad-site.json` | Score rows (20 and 10 seeds) |

## Results (two sites, 16 seed pieces, 6 slots per arm, challenge and spawn off)

Held-out MAE in µm, mean over 20 seeds, ± SE of the paired difference:

| Round | Isolated | Networked | Oracle | Isolated − networked | Oracle − networked |
|---|---|---|---|---|---|
| 1 | 16.6 | 14.9 | 14.9 | 1.6 ± 0.5 | −0.1 ± 0.7 |
| 2 | 15.3 | 12.6 | 13.1 | 2.7 ± 0.6 | 0.5 ± 0.9 |
| 3 | 14.0 | 12.1 | 13.0 | 1.9 ± 0.6 | 0.9 ± 1.1 |

Noise-free error. The networked arm closes essentially the whole gap to the oracle without pooling any raw data; the round 3 oracle − networked difference is within noise. On measured error isolated − networked is 1.2 ± 0.5, 1.3 ± 0.4 and 0.5 ± 0.4 µm: measurement noise (~35 µm MAE) hides most of the effect, which is why the real-printer claim is sim-to-real (prereg). Privacy audit: PASS in every run.

**Bad-faith site (10 seeds), PLA lying:** at the honest resin site, networked error jumps to 82 µm in round 1 (isolated 15) because trust starts at 1.0 and credit only acts after a round of held-out data. The bad sender's trust then collapses, and networked recovers to 16.8 µm in round 2 (isolated 13.2) and 12.7 µm in round 3 (isolated 11.8, difference −0.9 ± 1.3, within noise). So the honest site is not harmed by round 3 but gains nothing over isolated. Averaged over both sites, networked is 49.9, 16.1 and 13.6 µm against isolated 16.5, 16.3 and 15.0; that average looks better because the lying site still learns from the honest one. The frozen config keeps `trust_init = 1.0`, so that first round is the price of trusting by default.

## Regenerate

```
python run.py --source sim --seeds 20 --out demo/tier-d/sim.json
python run.py --source sim --seeds 10 --bad-site pla --out demo/tier-d/bad-site.json
python -m eval.figures.headline demo/tier-d/sim.json --truth --out demo/tier-d/headline-truth.png
python -m eval.figures.headline demo/tier-d/sim.json --out demo/tier-d/headline-measured.png
python -m viewer.export --source sim --rounds 3 --seed 0 --out demo/tier-d/run-seed0.html
python -m viewer.export --source sim --rounds 3 --seed 0 --bad-site pla --out demo/tier-d/run-bad-site.html
```
