# Robustness (claim 3)

One site broadcasts confident beliefs 3 prior SD off (`--bad-site`). Two sites, config from the prereg. Paired by seed against the same seed's honest run. ± is 1.96 SE over seeds. Errors are the honest site's `mae_truth`, µm.

## pla lies, resin honest (200 seeds)

| round | bad sender's trust | honest sender's trust (attack / honest run) | bad site's top agent credibility (attack / honest run) | honest site's top agent credibility (attack / honest run) | honest net, attack | honest net, no attack | honest iso, attack | net − iso, attack | seeds with net ≤ iso |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.000 ± 0.000 | 1.000 ± 0.000 / 1.000 ± 0.000 | 0.242 ± 0.007 / 0.242 ± 0.007 | 0.249 ± 0.008 / 0.249 ± 0.008 | 73.61 ± 4.88 | 12.52 ± 0.87 | 13.09 ± 0.90 | 60.52 ± 4.94 | 0/200 |
| 2 | 0.050 ± 0.015 | 0.938 ± 0.016 / 0.938 ± 0.016 | 0.260 ± 0.010 / 0.260 ± 0.010 | 0.755 ± 0.030 / 0.260 ± 0.009 | 15.17 ± 1.91 | 11.47 ± 0.76 | 11.78 ± 0.75 | 3.39 ± 1.72 | 74/200 |
| 3 | 0.027 ± 0.006 | 0.910 ± 0.022 / 0.908 ± 0.023 | 0.268 ± 0.010 / 0.268 ± 0.010 | 0.775 ± 0.030 / 0.268 ± 0.009 | 11.53 ± 0.75 | 10.54 ± 0.65 | 11.10 ± 0.70 | 0.43 ± 0.59 | 94/200 |

Recovery round (first round from which networked stays ≤ isolated): round 1: 0, round 2: 59, round 3: 35, never: 106.

## resin lies, pla honest (200 seeds)

| round | bad sender's trust | honest sender's trust (attack / honest run) | bad site's top agent credibility (attack / honest run) | honest site's top agent credibility (attack / honest run) | honest net, attack | honest net, no attack | honest iso, attack | net − iso, attack | seeds with net ≤ iso |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.000 ± 0.000 | 1.000 ± 0.000 / 1.000 ± 0.000 | 0.249 ± 0.008 / 0.249 ± 0.008 | 0.242 ± 0.007 / 0.242 ± 0.007 | 92.67 ± 8.33 | 14.23 ± 0.87 | 17.16 ± 1.13 | 75.51 ± 8.34 | 0/200 |
| 2 | 0.081 ± 0.027 | 0.963 ± 0.010 / 0.963 ± 0.010 | 0.260 ± 0.009 / 0.260 ± 0.009 | 0.761 ± 0.033 / 0.260 ± 0.010 | 20.87 ± 2.43 | 12.77 ± 0.80 | 15.76 ± 1.09 | 5.11 ± 2.07 | 76/200 |
| 3 | 0.039 ± 0.013 | 0.946 ± 0.014 / 0.947 ± 0.014 | 0.269 ± 0.009 / 0.268 ± 0.009 | 0.784 ± 0.034 / 0.268 ± 0.010 | 17.63 ± 3.09 | 11.70 ± 0.76 | 14.55 ± 1.02 | 3.08 ± 2.94 | 95/200 |

Recovery round (first round from which networked stays ≤ isolated): round 1: 0, round 2: 59, round 3: 36, never: 105.

## Claim 3, per seed, both directions

At round 3, over 400 attacked runs (200 seeds × 2 directions):

- bad sender's trust < 0.5: 397/400
- honest sender's trust ≥ 0.5: 389/400
- honest site's networked ≤ isolated: 189/400 (same site, same seeds, no attack: networked > isolated in 152/400, so part of this is noise, not the attack)
- all three: 183/400; fail: 217

Noise-aware version: networked under attack minus the same seed's networked without attack, round 3. Its 5th percentile is -4.11 µm; seeds above +4.11 µm count as harmed beyond noise.

- harmed beyond noise: 103/400 (pla lies: 28), (resin lies: 75)
- median difference 0.94 µm, 90th percentile 9.19, 99th 26.26
- correlation of that difference with the bad sender's final trust: 0.66
- trust lost, honest trust kept, and not harmed beyond noise: 288/400; fail: 112

