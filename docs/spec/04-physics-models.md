# Spec: Physics Models

## 7. Physics models

`model/physics.py`. Same model and priors for every arm. Bayesian updating with a particle posterior (resample-move SMC with adaptive tempering; NumPy reference `model/posterior.py`, GPU port `model/posterior_warp.py`). Each parameter is tagged process-agnostic (`shared`) or site-specific (`site`), which decides what may be shared. Priors are generic and deliberately wide: the seed plate learns each printer, and `eval/prior_check.py` checks after the seed plate whether a real printer sits inside them.

### 7.1 Resin (SLA)

- Jacobs working curve: Cd = Dp · ln(E / Ec)
- Light bleed: lateral over-cure, scaling with cure depth, that shrinks holes and grows pins
- Cure shrinkage: isotropic scale factor
- Site parameters: Dp, Ec, k_bleed, shrink, sigma_meas (measurement noise)

### 7.2 PLA (FDM)

- Extrusion width offset per wall
- Small-hole polygon shrinkage (holes shrink by poly_k / d)
- First-layer flare on pins
- Site parameters: w_off, poly_k, flare, sigma_meas

### 7.3 Shared structure

Three process-agnostic terms, identical across processes so summaries are comparable: feature-size dependence (`size_coef / d`) and linear plate-position gradients across columns and rows (`pos_gx`, `pos_gy`). Orientation effects and a learned residual correction are not modeled. Below about 0.5 mm the models stop being believable (the PLA hole model predicts negative sizes), so micro-scale results are direction only.

### 7.4 Fit definition

Clearance = hole diameter − pin diameter. Fit classes (press / slip / loose) use registered clearance thresholds per process (resin: press < 0 mm, slip 0.05–0.15, loose > 0.2; PLA: press < 0, slip 0.10–0.25, loose > 0.35). Hand fit checks (`eval/fitcheck.py`) compare pushed-together pins and holes with each arm's predicted class.

### 7.5 Corrected designs

`model/compensate.py` inverts the learned model: for a wanted pin or hole size, it finds the size to draw so the part prints at the target, with a 90% interval that includes a model-discrepancy term (8.6 µm). In simulation, median size error falls from 132 µm drawn as-is to 9 µm corrected (60 worlds), and the interval's cross-validated coverage is 81–96%. Shown per site in the console.
