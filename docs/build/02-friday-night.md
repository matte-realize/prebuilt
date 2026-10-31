# Build: Friday Night

## 4. Friday night build (software only)

### Phase A — Fri 9:30 PM to 1 AM

**M**
1. **Receipts.** Append-only log per site; each entry hashes the previous one. Log every plate, measurement, bid, clearing result, and message.
2. **Physics models.** Resin: Dp, Ec, lateral bleed, shrinkage. PLA: extrusion width, hole polygon shrinkage, first-layer flare. Plus process-agnostic terms: feature-size coefficient and plate-position gradient. Tag every parameter `shared` or `site`.
3. **Posterior.** Particle posterior (a few thousand particles), Gaussian measurement likelihood, importance reweighting with resampling. Implements `Model`. Vectorized in PyTorch or Warp so all agents update in one call.

**T**
1. **Piece library.** Pins and holes from about 1 to 8 mm nominal diameter, in steps fine enough to bracket expected fit transitions. Precompute every candidate once.
2. **Plate generator.** Roughly 100 × 100 mm plate, 3 mm thick, regular grid of slots. Holes go through the plate; pins are short standing cylinders. Three corner fiducials plus an orientation notch for the scanner. Piece identity comes from grid position, not printed text. Output STL for both printers.
3. **Seed plate files.** A fixed calibration grid plus held-out pieces, for both printers. These print first thing Saturday, so they must be finished tonight.

**Done when:** seed plate STLs exist and slice cleanly for both printers; the posterior updates on fake measurements and predicts with intervals.

### Phase B — Fri 1 AM to 4 AM

**M**
1. **Agents.** Each agent = an evidence filter + a prior + a proposal rule. Physics (datasheet priors), calibration (seed measurements only), printability (failure history), geometry and empirical (all site measurements, different features). Each proposes the library pieces with the highest predictive std under its own posterior, discounted by print height.
2. **Auction.** Arm slot pool split across agents in proportion to credibility, largest-remainder rounding. Agents fill slots with their top proposals. The rule never picks content.
3. **Credibility.** After each round: leave-one-agent-out change in held-out log predictive density; c ← c · exp(η · ΔLPD), normalize.
4. **Message boundary.** Typed `Message`, rejecting serializer, logged to both sites' receipt chains. Receiving site applies shared-parameter posteriors as a tempered prior, with the tempering weight set by sender credibility.
5. **Three arms.** Isolated (one agent, own site's data, max predictive std). Networked (auction + messages). Oracle (one agent, both sites' raw data, max predictive std). All three are scored by the same site model, so they differ only in which pieces they chose and, for networked, what they received.

**T**
1. **Simulator.** Implements `Printer`. Each simulated site draws true parameters from wide ranges around the datasheet values, adds measurement noise, and adds two effects the agents don't model: a plate-position gradient and an orientation-dependent error.
2. **Domain randomization + batching.** Thousands of simulated sites in one Warp launch.
3. **Scanner pipeline, first pass.** Detect fiducials, rectify, fit circles to holes (backlit) and pin tops (dark background). Test on a printed paper target with known circles to get a scale and error estimate.

**Done when:** `run.py --source sim` runs a full multi-round experiment for all three arms and prints held-out error per arm.

### Phase C — Fri 4 AM to 8 AM (stagger sleep)

One of you sleeps roughly 4–7:30 while the other runs Phase C; whoever slept takes the first printer shift.

1. **Run the sim experiment across many seeds.** Confirm networked lands between isolated and oracle. If it doesn't, debug before anything else; this is the whole project.
2. **Tune and freeze** η, credibility floor, slot split, and proposal discount in simulation only. Commit the frozen config with a hash.
3. **Draft the predicted range** for oracle-gap-closed on a two-site real setup. It gets recomputed after seed calibration (Phase D) and committed then.

**Done when:** frozen config committed; one figure showing the three arms across seeds.

