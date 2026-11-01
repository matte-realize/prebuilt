# Spec: Measurement and Simulator

## 9. Measurement

- **Scanner pipeline:** flatbed scanner, backlit thin plates, computer-vision extraction of hole and pin diameters.
- **Spot checks:** calipers and pin gauges on a random sample; report agreement with the scanner.
- Process-agnostic: works at any site that can print the test-plate spec.
- Measurements stream into the site's posterior piece by piece and never leave the site.

## 10. Hidden-truth multi-site simulator

- Built first. Shares the exact code path with real data.
- Each simulated site draws its own perturbed machine parameters, measurement noise, and deliberately unmodeled effects (plate-position gradient, orientation-dependent error), with some effects shared across sites and some local.
- Calibrated to real measurements as they arrive; residuals reported.
- Implemented in NVIDIA Warp, batched across thousands of simulated sites on Nebius H100s.
- Released as a public multi-site benchmark.

