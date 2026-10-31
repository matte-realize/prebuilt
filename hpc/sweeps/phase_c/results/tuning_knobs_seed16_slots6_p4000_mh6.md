## tuning_knobs_seed16_slots6_p4000_mh6

bad trust: honest site's final trust in the bad sender (lower is better). honest trust: final trust between honest sites, in honest runs and from the bad site toward the honest one (higher is better); `<0.5` is the share of those links that ended below 0.5. net/iso under attack: honest site's networked over isolated mae_truth at the last round (1.0 = no harm). Gap closed: honest runs, pooled, last round. ora < net: share of seeds, honest runs, last round, where the oracle beats networked. Retired: agents retired per run, honest runs.

| config | bad trust (SE) | honest trust (SE) | honest <0.5 | net/iso under attack | iso - net honest, µm (SE) | gap closed [90% CI] | ora < net | retired |
|---|---|---|---|---|---|---|---|---|
| disc=0.0_bssd=1.0 | 0.733 (0.028) | 0.956 (0.006) | 0.01 | 1.02 (mean 1.12) | 1.19 (0.60) | 2.15 [-5.18, 13.67] | 0.38 | 0.00 |
| disc=0.0_bssd=0.1 | 0.022 (0.013) | 0.861 (0.015) | 0.06 | 1.00 (mean 1.22) | 1.34 (0.62) | 1.10 [0.29, 3.01] | 0.50 | 0.00 |
| disc=0.2_bssd=0.1 | 0.033 (0.017) | 0.880 (0.014) | 0.06 | 1.04 (mean 1.29) | 1.84 (0.52) | 0.86 [0.56, 1.26] | 0.50 | 0.10 |
| disc=0.0_bssd=0.25 | 0.050 (0.017) | 0.886 (0.014) | 0.06 | 0.92 (mean 1.04) | 1.30 (0.58) | 0.93 [0.30, 2.20] | 0.47 | 0.00 |
| disc=0.1_bssd=0.25 | 0.052 (0.018) | 0.897 (0.013) | 0.06 | 1.02 (mean 1.12) | 1.71 (0.41) | 0.80 [0.55, 1.24] | 0.57 | 0.10 |
| disc=0.1_bssd=0.1 | 0.033 (0.017) | 0.881 (0.015) | 0.06 | 1.07 (mean 1.28) | 1.92 (0.49) | 0.86 [0.58, 1.28] | 0.55 | 0.10 |
| disc=0.2_bssd=0.25 | 0.052 (0.018) | 0.903 (0.013) | 0.05 | 1.03 (mean 1.16) | 1.44 (0.43) | 0.73 [0.46, 1.11] | 0.47 | 0.10 |
| disc=0.2_bssd=0.5 | 0.212 (0.025) | 0.938 (0.009) | 0.01 | 0.99 (mean 1.15) | 1.92 (0.53) | 0.97 [0.69, 1.39] | 0.47 | 0.07 |
| disc=0.1_bssd=0.5 | 0.217 (0.026) | 0.939 (0.008) | 0.00 | 0.99 (mean 1.14) | 1.91 (0.50) | 0.94 [0.70, 1.35] | 0.50 | 0.07 |
| disc=0.0_bssd=0.5 | 0.213 (0.028) | 0.923 (0.010) | 0.02 | 0.99 (mean 1.17) | 1.34 (0.58) | 1.76 [-1.58, 6.88] | 0.50 | 0.00 |
| disc=0.1_bssd=1.0 | 0.766 (0.028) | 0.966 (0.005) | 0.00 | 1.03 (mean 1.11) | 1.11 (0.48) | 1.35 [0.17, 4.50] | 0.40 | 0.03 |
| disc=0.2_bssd=1.0 | 0.770 (0.028) | 0.966 (0.005) | 0.00 | 1.05 (mean 1.12) | 1.02 (0.47) | 1.76 [-3.92, 6.68] | 0.42 | 0.03 |
| disc=0.4_bssd=0.1 | 0.030 (0.016) | 0.887 (0.014) | 0.04 | 1.06 (mean 1.27) | 1.45 (0.55) | 0.71 [0.38, 1.05] | 0.50 | 0.00 |
| disc=0.4_bssd=0.25 | 0.052 (0.018) | 0.904 (0.013) | 0.05 | 1.05 (mean 1.15) | 1.27 (0.50) | 0.61 [0.33, 0.93] | 0.53 | 0.10 |
| disc=0.4_bssd=0.5 | 0.218 (0.026) | 0.936 (0.009) | 0.00 | 1.00 (mean 1.17) | 1.44 (0.57) | 0.81 [0.43, 1.27] | 0.53 | 0.07 |
| disc=0.4_bssd=1.0 | 0.766 (0.028) | 0.965 (0.006) | 0.00 | 1.05 (mean 1.15) | 0.68 (0.51) | 1.34 [-4.33, 5.47] | 0.47 | 0.03 |
