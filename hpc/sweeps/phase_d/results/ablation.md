# Ablation

Two sites, 200 seeds, same seeds in every column. `mae_truth`, µm, both sites averaged, mean ± 1.96 SE. No-messages is the networked arm with the network cut (`--no-messages`).

| round | isolated | no messages | networked | oracle (reference) |
|---|---|---|---|---|
| 1 | 15.12 ± 0.75 | 14.85 ± 0.71 | 13.38 ± 0.67 | 13.70 ± 0.69 |
| 2 | 13.77 ± 0.66 | 13.64 ± 0.67 | 12.12 ± 0.60 | 12.48 ± 0.61 |
| 3 | 12.82 ± 0.63 | 12.62 ± 0.62 | 11.12 ± 0.54 | 11.53 ± 0.57 |

Paired differences, µm:

| round | iso − net | iso − no-messages | no-messages − net | oracle − net |
|---|---|---|---|---|
| 1 | 1.75 ± 0.45 | 0.27 ± 0.37 | 1.47 ± 0.34 | 0.33 ± 0.41 |
| 2 | 1.64 ± 0.51 | 0.13 ± 0.46 | 1.52 ± 0.46 | 0.36 ± 0.43 |
| 3 | 1.70 ± 0.48 | 0.20 ± 0.41 | 1.50 ± 0.43 | 0.41 ± 0.45 |
