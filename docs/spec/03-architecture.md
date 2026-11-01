# Spec: System Architecture

## 6. System architecture

### 6.1 Topology

Each printer is a **site** running its own collective: agents, auction, plates, measurements and posterior. Sites talk only through the message protocol. Each site decides how much to trust each sender, from that sender's effect on its own held-out data. No node decides what transfers.

Registered setup: two sites (resin, PLA). Simulation: 2–8 sites in the sweeps, each with its own hidden machine parameters (`sim/warp_sim.py` can draw thousands).

### 6.2 Agents (within each site)

Defined in `agents/agents.py`. Agents that share an evidence filter share one posterior.

| Agent | Evidence | Uses incoming messages? | Proposal rule |
|---|---|---|---|
| Physics | All site measurements | Yes | Information gain on site parameters |
| Calibration | Seed plate only | No | Total information gain |
| Geometry | All site measurements | Yes | Information gain on `size_coef` |
| Empirical | All site measurements | Yes | Information gain × residual size by bin |
| Printability | Print outcomes (ok / failed) | No | Uncertainty about failing to print |
| Position (dormant) | All site measurements | Yes | Information gain on `pos_gx`, `pos_gy` |

There is no orientation agent: `Piece` carries no orientation. The **hypothesis agent** (`agents/hypothesis.py`, a Nemotron endpoint) is separate from the auction: between rounds it reads residual summaries and the unmet-needs log, proposes up to 3 candidate effects with test pieces, and writes them to its own receipt chain. It never sets parameters or allocates space.

### 6.3 Message protocol

`contracts.Message` is the only thing that crosses a site boundary. `network/protocol.py` validates every message against a closed schema on both serialize and deserialize and raises `BoundaryViolation` on anything else.

**Crosses:**
- Posterior mean and covariance of the three process-agnostic parameters (`size_coef`, `pos_gx`, `pos_gy`)
- Agent credibility scores
- Unmet-needs entries (template, short question, one z-score)
- A hypotheses field (schema-checked; empty in the current build)

**Never crosses:** raw measurements, plate files and randomization seeds, site-specific parameters, held-out data.

Every crossing is written to both sites' receipt chains and every rejection to the sender's, so the privacy claim is checkable by replay (`eval/audit.py`). Known limitation: posterior summaries can leak some information about a site's data; noise on shared summaries (differential privacy) is not built.

### 6.4 Incoming-message trust

Each receiver folds an incoming summary into its prior, widened by a registered between-site spread (`between_site_sd`, 0.25 prior std) and weighted by its trust in the sender. Trust starts at `trust_init` (1.0) and updates from leave-one-sender-out held-out improvement on the receiver's own escrowed data (Section 6.6), capped at 1.

Opt-in defences, **off in the registered config**, evaluated in simulation (`hpc/sweeps/relevance/README.md`):
- **Consistency check** (`consistency_check`): drop a note whose summary contradicts the receiver's own local fit (Σz² above the chi-square 0.999 quantile). Caught 180 of 180 lying notes and dropped 0 of 540 honest ones.
- **Adaptive spread** (`adaptive_spread`): scale a sender's spread by its running disagreement with the receiver. Removes the harm when printers share no physics (−13% → −0.4%) and keeps the gain when they do.
- **Predictive trust** (`predictive_trust`): score each sender's note on the receiver's newly measured held-out pieces and widen it by the likelihood ratio against it. In an 8-site mixed fleet it lifts matched sites to about a third better than alone; it ranks senders better but doesn't cleanly separate them.

### 6.5 Decision cycle (per round, per site)

1. **Receive.** Fold in messages from other sites, weighted by trust.
2. **Propose.** Each agent ranks candidate pieces by its proposal rule (Section 6.2), discounting near-duplicates.
3. **Challenge** (designed, off in the registered config, `challenge=True` to enable). Each agent may flag one other proposal ("redundant with mine", "already predictable from my evidence"); flagged pieces move to the end of their owner's list, and the flagger is credited on held-out data.
4. **Bid and clear.** Each arm's slot pool is divided among agents in proportion to credibility (largest-remainder rounding); each agent fills its slots with its top proposals. The rule allocates space only. `selection="random"` replaces the auction with uniform choice as a baseline.
5. **Approve.** A human checks printability and safety only (approve, approve with an edit note, or veto); every decision goes on the receipt chain.
6. **Print, measure, update.** Scanner, caliper or hand-sheet measurements update the site's posteriors.
7. **Credit.** Agent credibility and sender trust update from held-out improvement (Section 6.6).
8. **Broadcast.** Allowed messages go out to other sites.

### 6.6 Credibility

After each round, for each agent *a*, compute the change in held-out log predictive density when *a*'s contributed pieces are removed (leave-one-agent-out), averaging per-piece differences clipped to ±2 nats (`lpd_clip`). Update multiplicatively in log space:

c_a ← c_a · exp(η · ΔLPD_a), then normalize over active agents.

Sender trust uses the same rule with ΔLPD from removing that sender's messages, without normalization and capped at 1. η = 5 is registered. Held-out data is escrowed per site; agents see only scalar credit.

### 6.7 Spawn and retire

- **Retire:** an agent below the registered credibility floor (`cred_floor`, 0.05) for two rounds in a row stops bidding.
- **Spawn** (designed, off in the registered config, `dormant=("position",)` to enable): each site correlates its residuals with squared distance from the plate center; a trend with |z| ≥ 2 goes in the unmet-needs log and is broadcast. When own plus incoming entries reach the threshold (2), the position agent wakes with uniform credibility, so a question raised at one site can wake an agent at another. Exercised in simulation only.
