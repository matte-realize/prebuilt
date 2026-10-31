# Spec: Physics Models

## 7. Physics models

Same model and priors for every arm. Bayesian updating via a GPU particle or grid posterior, optional learned correction on residuals. Parameters are tagged process-agnostic or site-specific, which determines what may be shared.

### 7.1 Resin (SLA)

- Jacobs working curve: Cd = Dp · ln(E / Ec)
- Light bleed: lateral over-cure that shrinks holes and grows pins
- Cure shrinkage: isotropic scale factor
- Parameters: Dp, Ec, lateral bleed coefficient, shrinkage, (optional) orientation offset
- Priors from the resin datasheet

### 7.2 PLA (FDM)

- Effective extrusion width
- Hole polygon shrinkage (small holes print undersized)
- First-layer flare
- Priors from slicer settings

### 7.3 Shared structure

Process-agnostic terms shared across sites: feature-size dependence of error, orientation effects, plate-position effects, and the residual correction's geometry features.

### 7.4 Fit definition

Clearance = hole diameter − pin diameter. Fit classes (press / slip / loose) are defined by pre-registered clearance thresholds per process. Physical go/no-go checks on a random sample validate the derived classes.

