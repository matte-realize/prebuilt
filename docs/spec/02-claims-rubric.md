# Spec: Claims and Rubric

## 4. Pre-registered claims

Committed to the repository with a hash and timestamp before the first print.

- **H1 (privacy-preserving performance).** At equal print budgets, the networked collective reaches held-out error closer to the pooled-data oracle than to isolated sites, while no raw data crosses a site boundary.
- **H2 (transfer).** A site joining the network (PLA, one round behind) reaches target held-out error with fewer pieces than an isolated site, because process-agnostic knowledge arrives as messages.
- **H3 (robustness).** A deliberately miscalibrated agent, or a site broadcasting bad beliefs, loses credibility and the network recovers without intervention.
- **H4 (privacy, verified).** Receipts prove that no raw measurement, plate file, or site-specific parameter crossed a site boundary.
- **H5 (baseline).** The calibrated model predicts fit better than generic vendor clearance guidance. Expected; reported, not the headline.
- **H6 (discovery, exploratory).** The network surfaces at least one effect absent from the physics model (candidate: build-plate position dependence). Labeled exploratory in advance.

## 5. Rubric mapping

| Criterion | Weight | What earns it |
|---|---|---|
| Problem significance | 20 | Distributed manufacturing can't pool data; characterization repeated at every site |
| Scientific/technical impact | 25 | Near-oracle learning under privacy (H1), cross-process transfer (H2), discovered effect (H6), pre-registration, held-out escrow |
| Decentralized agency | 20 | Decentralization is a hard constraint; per-site collectives, message-only exchange, credibility auction, challenges, spawn/retire, hypothesis agent |
| Collective capability | 25 | Network vs. isolated sites vs. oracle (H1), transfer (H2), recovery (H3), scaling with number of sites |
| Execution and validation | 10 | Real held-out fits, verifiable receipts including privacy proof (H4), end-to-end loop, honest reporting |
| Reuse bonus | +10 | Test-plate spec, scanner tool, hidden-truth multi-site benchmark, clearing-rule and message-protocol library |

