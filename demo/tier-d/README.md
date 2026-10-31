# Tier D demo: pure simulation

The fallback if no printer is usable (prereg `fallback_tiers.D`): everything here comes from the hidden-truth simulator, and is labeled that way wherever it's shown. It's also the backup demo for any tier.

Generated at commit `3822c6e` from a clean checkout. **DRAFT config:** the five tuning values (`eta`, `cred_floor`, `trust_init`, `discount`, `oracle_particles`) are still at `Config` defaults until T's sweep freezes them. Regenerate after that with the commands below.

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
| 2 | 15.3 | 12.7 | 12.9 | 2.6 ± 0.6 | 0.2 ± 0.7 |
| 3 | 13.3 | 11.8 | 11.8 | 1.5 ± 0.7 | 0.0 ± 0.7 |

Noise-free error. The networked arm closes essentially the whole gap to the oracle without pooling any raw data. On measured error the same differences are 1.4 ± 0.6, 1.5 ± 0.4 and 0.9 ± 0.5 µm: measurement noise (~35 µm MAE) hides most of the effect, which is why the real-printer claim is sim-to-real (prereg). Privacy audit: PASS in every run.

**Bad-faith site (10 seeds):** in round 1, networked error jumps to 46 µm (isolated 16) because trust starts at 1.0 and credit only acts after a round of held-out data. From round 2 the bad sender's trust has collapsed and networked is back below isolated (13.6 vs 15.5 µm). One round of damage at `trust_init = 1.0` is the case for a lower initial trust in the tuning sweep.

## Regenerate

```
python run.py --source sim --seeds 20 --out demo/tier-d/sim.json
python run.py --source sim --seeds 10 --bad-site pla --out demo/tier-d/bad-site.json
python -m eval.figures.headline demo/tier-d/sim.json --truth --out demo/tier-d/headline-truth.png
python -m eval.figures.headline demo/tier-d/sim.json --out demo/tier-d/headline-measured.png
python -m viewer.export --source sim --rounds 3 --seed 0 --out demo/tier-d/run-seed0.html
python -m viewer.export --source sim --rounds 3 --seed 0 --bad-site pla --out demo/tier-d/run-bad-site.html
```
