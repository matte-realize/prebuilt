## tuning_knobs_seed16_slots6

bad trust: honest site's final trust in the bad sender (lower is better). honest trust: final trust between honest sites, in honest runs and from the bad site toward the honest one (higher is better); `<0.5` is the share of those links that ended below 0.5. net/iso under attack: honest site's networked over isolated mae_truth at the last round (1.0 = no harm). Gap closed: honest runs, pooled, last round. ora < net: share of seeds, honest runs, last round, where the oracle beats networked. Retired: agents retired per run, honest runs.

| config | bad trust (SE) | honest trust (SE) | honest <0.5 | net/iso under attack | iso - net honest, µm (SE) | gap closed [90% CI] | ora < net | retired |
|---|---|---|---|---|---|---|---|---|
| disc=0.2_bssd=0.1 | 0.007 (0.001) | 0.866 (0.016) | 0.08 | 0.94 (mean 1.03) | 1.97 (0.45) | 1.04 [0.73, 1.77] | 0.53 | 0.07 |
| disc=0.1_bssd=0.1 | 0.006 (0.001) | 0.872 (0.016) | 0.07 | 0.96 (mean 1.04) | 1.92 (0.46) | 1.00 [0.69, 1.61] | 0.50 | 0.05 |
| disc=0.0_bssd=0.1 | 0.007 (0.001) | 0.877 (0.015) | 0.07 | 1.00 (mean 1.07) | 1.28 (0.50) | 1.42 [0.46, 4.61] | 0.53 | 0.03 |
| disc=0.0_bssd=0.25 | 0.036 (0.009) | 0.905 (0.012) | 0.04 | 0.99 (mean 1.16) | 1.11 (0.47) | 1.23 [-1.07, 4.57] | 0.50 | 0.00 |
| disc=0.2_bssd=0.25 | 0.034 (0.009) | 0.886 (0.014) | 0.06 | 0.97 (mean 1.14) | 2.22 (0.47) | 0.99 [0.72, 1.44] | 0.60 | 0.00 |
| disc=0.1_bssd=0.25 | 0.034 (0.009) | 0.899 (0.013) | 0.04 | 0.98 (mean 1.20) | 1.83 (0.48) | 0.89 [0.60, 1.37] | 0.57 | 0.03 |
| disc=0.0_bssd=0.5 | 0.191 (0.027) | 0.916 (0.010) | 0.01 | 1.02 (mean 1.15) | 0.77 (0.55) | 1.89 [-7.31, 8.34] | 0.45 | 0.00 |
| disc=0.1_bssd=0.5 | 0.188 (0.027) | 0.922 (0.009) | 0.02 | 0.98 (mean 1.10) | 2.07 (0.45) | 0.96 [0.71, 1.49] | 0.47 | 0.03 |
| disc=0.2_bssd=0.5 | 0.187 (0.026) | 0.932 (0.009) | 0.02 | 0.98 (mean 1.11) | 2.35 (0.51) | 1.00 [0.75, 1.49] | 0.53 | 0.03 |
| disc=0.0_bssd=1.0 | 0.732 (0.027) | 0.927 (0.009) | 0.01 | 1.04 (mean 1.17) | 0.12 (0.57) | 1.98 [-5.65, 6.81] | 0.42 | 0.00 |
| disc=0.1_bssd=1.0 | 0.731 (0.030) | 0.922 (0.011) | 0.03 | 1.02 (mean 1.04) | 1.34 (0.46) | 1.07 [0.53, 2.66] | 0.50 | 0.03 |
| disc=0.4_bssd=0.5 | 0.185 (0.026) | 0.924 (0.010) | 0.03 | 0.95 (mean 1.08) | 1.99 (0.55) | 0.92 [0.63, 1.36] | 0.55 | 0.03 |
| disc=0.4_bssd=0.1 | 0.007 (0.001) | 0.872 (0.016) | 0.07 | 1.02 (mean 1.05) | 1.78 (0.45) | 0.78 [0.52, 1.17] | 0.55 | 0.07 |
| disc=0.4_bssd=0.25 | 0.033 (0.008) | 0.895 (0.014) | 0.05 | 1.03 (mean 1.11) | 2.20 (0.53) | 0.89 [0.63, 1.28] | 0.55 | 0.00 |
| disc=0.2_bssd=1.0 | 0.728 (0.029) | 0.934 (0.009) | 0.01 | 1.02 (mean 1.11) | 1.16 (0.53) | 1.39 [-2.15, 5.01] | 0.45 | 0.00 |
| disc=0.4_bssd=1.0 | 0.744 (0.029) | 0.941 (0.008) | 0.01 | 1.04 (mean 1.08) | 1.26 (0.60) | 1.01 [0.25, 2.54] | 0.50 | 0.00 |
