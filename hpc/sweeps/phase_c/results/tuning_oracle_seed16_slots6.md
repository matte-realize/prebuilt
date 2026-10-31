## tuning_oracle_seed16_slots6

bad trust: honest site's final trust in the bad sender (lower is better). honest trust: final trust between honest sites, in honest runs and from the bad site toward the honest one (higher is better); `<0.5` is the share of those links that ended below 0.5. net/iso under attack: honest site's networked over isolated mae_truth at the last round (1.0 = no harm). Gap closed: honest runs, pooled, last round. ora < net: share of seeds, honest runs, last round, where the oracle beats networked. Retired: agents retired per run, honest runs.

| config | bad trust (SE) | honest trust (SE) | honest <0.5 | net/iso under attack | iso - net honest, µm (SE) | gap closed [90% CI] | ora < net | retired |
|---|---|---|---|---|---|---|---|---|
| oracle_particles=2000 | - | 0.922 (0.011) | 0.04 | - | 1.59 (0.31) | 0.84 [0.66, 1.07] | 0.52 | 0.08 |
| oracle_particles=4000 | - | 0.922 (0.010) | 0.04 | - | 1.52 (0.31) | 0.87 [0.66, 1.13] | 0.50 | 0.07 |
| oracle_particles=8000 | - | 0.922 (0.010) | 0.03 | - | 1.58 (0.32) | 0.84 [0.65, 1.07] | 0.53 | 0.03 |
| oracle_particles=16000 | - | 0.921 (0.011) | 0.04 | - | 1.49 (0.31) | 0.83 [0.64, 1.07] | 0.52 | 0.08 |
| oracle_particles=32000 | - | 0.920 (0.011) | 0.04 | - | 1.51 (0.31) | 0.89 [0.69, 1.18] | 0.50 | 0.08 |

Per round, honest runs:

| config | round | n | isolated | networked | oracle | iso - net (SE) | gap closed, pooled [90% CI] | gap closed, per-seed median [IQR] |
|---|---|---|---|---|---|---|---|---|
| oracle_particles=2000 | 1 | 100 | 15.13 ± 0.52 | 13.48 ± 0.49 | 13.29 ± 0.48 | 1.65 (0.32) | 0.89 [0.68, 1.12] | 0.79 [-0.08, 1.68] |
| oracle_particles=2000 | 2 | 100 | 14.26 ± 0.51 | 12.20 ± 0.44 | 12.23 ± 0.44 | 2.06 (0.35) | 1.02 [0.79, 1.28] | 0.71 [-0.20, 1.60] |
| oracle_particles=2000 | 3 | 100 | 13.03 ± 0.49 | 11.45 ± 0.38 | 11.15 ± 0.37 | 1.59 (0.31) | 0.84 [0.66, 1.08] | 0.66 [-0.01, 1.42] |
| oracle_particles=4000 | 1 | 100 | 15.14 ± 0.53 | 13.46 ± 0.49 | 13.39 ± 0.47 | 1.67 (0.33) | 0.96 [0.73, 1.22] | 0.83 [-0.01, 1.85] |
| oracle_particles=4000 | 2 | 100 | 14.31 ± 0.52 | 12.27 ± 0.44 | 12.27 ± 0.43 | 2.04 (0.35) | 1.00 [0.77, 1.25] | 0.62 [-0.39, 1.55] |
| oracle_particles=4000 | 3 | 100 | 13.04 ± 0.49 | 11.52 ± 0.39 | 11.30 ± 0.37 | 1.52 (0.31) | 0.87 [0.67, 1.13] | 0.68 [-0.03, 1.52] |
| oracle_particles=8000 | 1 | 100 | 15.17 ± 0.52 | 13.47 ± 0.49 | 13.29 ± 0.46 | 1.70 (0.32) | 0.90 [0.69, 1.13] | 0.85 [0.03, 1.83] |
| oracle_particles=8000 | 2 | 100 | 14.28 ± 0.52 | 12.26 ± 0.45 | 12.19 ± 0.43 | 2.03 (0.35) | 0.97 [0.74, 1.23] | 0.62 [-0.34, 1.54] |
| oracle_particles=8000 | 3 | 100 | 13.06 ± 0.49 | 11.48 ± 0.40 | 11.17 ± 0.39 | 1.58 (0.32) | 0.84 [0.66, 1.07] | 0.81 [0.15, 1.62] |
| oracle_particles=16000 | 1 | 100 | 15.14 ± 0.52 | 13.48 ± 0.49 | 13.15 ± 0.47 | 1.67 (0.33) | 0.83 [0.63, 1.06] | 0.76 [-0.15, 1.36] |
| oracle_particles=16000 | 2 | 100 | 14.22 ± 0.52 | 12.23 ± 0.44 | 12.24 ± 0.44 | 2.00 (0.35) | 1.01 [0.77, 1.29] | 0.64 [-0.34, 1.58] |
| oracle_particles=16000 | 3 | 100 | 13.02 ± 0.50 | 11.53 ± 0.39 | 11.23 ± 0.38 | 1.49 (0.31) | 0.83 [0.64, 1.08] | 0.70 [0.03, 1.26] |
| oracle_particles=32000 | 1 | 100 | 15.16 ± 0.52 | 13.49 ± 0.49 | 13.31 ± 0.47 | 1.67 (0.33) | 0.91 [0.69, 1.13] | 0.81 [-0.03, 1.69] |
| oracle_particles=32000 | 2 | 100 | 14.23 ± 0.52 | 12.20 ± 0.44 | 12.38 ± 0.44 | 2.04 (0.35) | 1.10 [0.84, 1.39] | 0.59 [-0.39, 1.60] |
| oracle_particles=32000 | 3 | 100 | 13.04 ± 0.50 | 11.53 ± 0.40 | 11.35 ± 0.38 | 1.51 (0.31) | 0.89 [0.70, 1.15] | 0.79 [0.21, 1.60] |

Share of seeds where the oracle wins:

| config | round | ora < net | ora < iso |
|---|---|---|---|
| oracle_particles=2000 | 1 | 0.47 | 0.73 |
| oracle_particles=2000 | 2 | 0.52 | 0.75 |
| oracle_particles=2000 | 3 | 0.52 | 0.69 |
| oracle_particles=4000 | 1 | 0.48 | 0.74 |
| oracle_particles=4000 | 2 | 0.52 | 0.79 |
| oracle_particles=4000 | 3 | 0.50 | 0.62 |
| oracle_particles=8000 | 1 | 0.51 | 0.76 |
| oracle_particles=8000 | 2 | 0.57 | 0.78 |
| oracle_particles=8000 | 3 | 0.53 | 0.65 |
| oracle_particles=16000 | 1 | 0.51 | 0.74 |
| oracle_particles=16000 | 2 | 0.53 | 0.77 |
| oracle_particles=16000 | 3 | 0.52 | 0.65 |
| oracle_particles=32000 | 1 | 0.50 | 0.74 |
| oracle_particles=32000 | 2 | 0.51 | 0.76 |
| oracle_particles=32000 | 3 | 0.50 | 0.65 |
