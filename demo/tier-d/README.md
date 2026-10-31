# Tier D demo: pure simulation

The fallback if no printer is usable (prereg `fallback_tiers.D`): everything here comes from the hidden-truth simulator, and is labeled that way wherever it's shown. It's also the backup demo for any tier.

Generated at commit `f244e5e` from a clean checkout, with the **frozen config** from `prereg/prereg.yaml` (eta 5, trust_init 1.0, cred_floor 0.05, discount 0.2, 2000 particles).

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
| 1 | 16.5 | 14.9 | 14.8 | 1.6 ± 0.5 | −0.1 ± 0.6 |
| 2 | 15.5 | 12.9 | 12.9 | 2.6 ± 0.7 | 0.0 ± 0.8 |
| 3 | 13.9 | 11.7 | 12.7 | 2.2 ± 0.6 | 0.9 ± 1.0 |

Noise-free error. The networked arm closes essentially the whole gap to the oracle without pooling any raw data; the round 3 oracle − networked difference is within noise. On measured error isolated − networked is 1.4 ± 0.6, 1.3 ± 0.4 and 1.0 ± 0.4 µm: measurement noise (~35 µm MAE) hides most of the effect, which is why the real-printer claim is sim-to-real (prereg). Privacy audit: PASS in every run.

**Bad-faith site (10 seeds):** in round 1, networked error jumps to 46 µm (isolated 16) because trust starts at 1.0 and credit only acts after a round of held-out data. From round 2 the bad sender's trust has collapsed and networked is back below isolated (13.9 vs 15.6 µm). The frozen config keeps `trust_init = 1.0`, so that first round is the price of trusting by default.

## Regenerate

```
python run.py --source sim --seeds 20 --out demo/tier-d/sim.json
python run.py --source sim --seeds 10 --bad-site pla --out demo/tier-d/bad-site.json
python -m eval.figures.headline demo/tier-d/sim.json --truth --out demo/tier-d/headline-truth.png
python -m eval.figures.headline demo/tier-d/sim.json --out demo/tier-d/headline-measured.png
python -m viewer.export --source sim --rounds 3 --seed 0 --out demo/tier-d/run-seed0.html
python -m viewer.export --source sim --rounds 3 --seed 0 --bad-site pla --out demo/tier-d/run-bad-site.html
```
