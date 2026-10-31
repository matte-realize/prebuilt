# Build: Saturday

## 5. Saturday printer day (about 8–9 AM to 10 PM)

Print and measurement times below are placeholders; adjust once you see real durations. Resin needs wash and cure time on top of printing.

| Approx. time | Printers | Software |
|---|---|---|
| 8:30 | Tiny test piece on each printer to confirm the pipeline end to end | Final checks on the scanner |
| 9:00 | **Seed plates** on both printers | Sim sweeps running on Nebius |
| ~11:00 | Collect, wash/cure resin, scan both | Ingest seed data |
| ~11:30 | — | **Phase D:** calibrate the simulator to seed data only; recompute the predicted range; commit it with a hash. Collective settings stay frozen. |
| ~12:00 | **Round 1** (all three arms + held-out) | Auction runs in seconds; messages exchanged after measurement |
| ~2:30 | Scan round 1 | Update posteriors, credibility, messages |
| ~3:00 | **Round 2** | — |
| ~5:30 | Scan round 2 | Update |
| ~6:00 | **Round 3** | Start figures with rounds 1–2 |
| ~8:30 | Scan round 3 | Update |
| 9:00–10:00 | Reprint any failed plate, or a short round 4 if time allows | — |

**Every real plate:** human approves for printability only; any change is logged. Duplicates on every plate. Held-out pieces at fixed, pre-registered slots spread across plates.

**Measurement routine (per plate):**
1. Scan with backlight for holes; scan on a dark background for pins.
2. Pipeline outputs a `Measurement` per piece; failed pieces get `status="failed"`.
3. Caliper-check a random sample of about 10 pieces; log agreement.
4. Physically test a few pin/hole pairs for fit; log against predicted fit class.

**Saturday checkpoints:**
- **Seed plates fail:** fix the obvious cause once (adhesion, supports, orientation) and reprint. A second failure on the same printer → drop to one real site plus simulated sites.
- **5 PM, behind schedule:** stop adding rounds; measure what exists.
- **10 PM:** printers done. Everything after is software.

## 6. Saturday night (software only)

**M**
1. Score real rounds: held-out error per arm, oracle-gap-closed, comparison to the committed predicted range.
2. Privacy audit: replay message receipts and show every crossing matched the schema.
3. Hypothesis agent (Nemotron), async: feed residual summaries and the unmet-needs log; record what it proposes. Exploratory only.

**T**
1. Recalibrate the simulator with all real data; report which parameters and unmodeled effects it got wrong.
2. Robustness sweep: inject a bad-faith site; plot its credibility and network recovery.
3. Scaling sweep: 2, 5, 10, 25 sites; plot oracle-gap-closed vs. number of sites.

**Done when:** all figures exist from real data plus sweeps.

