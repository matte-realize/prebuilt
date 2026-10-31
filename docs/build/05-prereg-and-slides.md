# Build: Pre-registration and Slides

## 9. Pre-registration file (fill in at kickoff)

> The live file is [`prereg/prereg.yaml`](../../prereg/prereg.yaml); it extends this template (deviations, config section, fallback tiers). The deck is in [`docs/slides/`](../slides/).

```
claims: [network_vs_oracle, sim_to_real_range, robustness_sim]
arms: [isolated, networked, oracle]
fit_classes_mm:  resin: {press: <_, slip: _–_, loose: >_}
                 pla:   {press: <_, slip: _–_, loose: >_}
failed_plate_fraction: _
eta: _          (frozen after Phase C)
credibility_floor: _
heldout_slots: [list per plate]
metrics: [heldout_MAE, heldout_LPD, fit_class_acc, interval_coverage_90, oracle_gap_closed]
predicted_range_oracle_gap_closed: _–_   (committed after Phase D, before round 1)
failure_rules: failed pieces are printability outcomes; held-out failures reported, scored on survivors
```

## 10. Slide outline

1. One-line pitch.
2. The problem: every site re-learns its machines; raw data can't be shared.
3. The setup: two sites, one boundary, what crosses and what doesn't.
4. How the collective decides: auction, credibility, messages.
5. Sim-to-real: frozen in simulation, prediction committed, then real printers.
6. **Headline chart:** isolated vs. networked vs. oracle, with the predicted range.
7. Robustness and scaling (simulation): bad site cut off after one round; more sites raises the gain.
8. Privacy audit replay.
9. What reality taught the simulator.
10. Closer: where this goes next. Print anywhere, trust the part; matters most for many-site networks and complex products such as bioprinting (direction, not a result).

