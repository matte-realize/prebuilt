## tuning_trustcheck_p4000_mh6

bad trust: honest site's final trust in the bad sender (lower is better). honest trust: final trust between honest sites, in honest runs and from the bad site toward the honest one (higher is better); `<0.5` is the share of those links that ended below 0.5. net/iso under attack: honest site's networked over isolated mae_truth at the last round (1.0 = no harm). Gap closed: honest runs, pooled, last round. ora < net: share of seeds, honest runs, last round, where the oracle beats networked. Retired: agents retired per run, honest runs.

| config | bad trust (SE) | honest trust (SE) | honest <0.5 | net/iso under attack | iso - net honest, µm (SE) | gap closed [90% CI] | ora < net | retired |
|---|---|---|---|---|---|---|---|---|
| eta=2.0_ti=1.0_floor=0.05 | 0.139 (0.019) | 0.948 (0.008) | 0.01 | 1.27 (mean 1.61) | 1.22 (0.45) | 0.62 [0.33, 0.97] | 0.53 | 0.07 |
| eta=10.0_ti=1.0_floor=0.05 | 0.030 (0.018) | 0.843 (0.019) | 0.11 | 1.00 (mean 1.07) | 1.24 (0.42) | 0.63 [0.32, 1.01] | 0.53 | 0.20 |
| eta=5.0_ti=1.0_floor=0.05 | 0.052 (0.018) | 0.903 (0.013) | 0.05 | 1.03 (mean 1.16) | 1.44 (0.43) | 0.73 [0.46, 1.12] | 0.47 | 0.10 |
