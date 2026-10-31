# Spec: System Architecture

## 6. System architecture

### 6.1 Topology

Each printer is a **site** running its own collective: agents, auction, plates, measurements, and posterior. Sites talk only through the message protocol. Each agent decides which incoming messages to use and how much to trust their senders. No node decides what transfers.

Real event: two sites (resin, PLA). Simulation: up to dozens of sites across both processes, each with its own hidden machine parameters.

### 6.2 Agents (within each site)

| Agent | Evidence | Shares beliefs across sites? |
|---|---|---|
| Physics | Datasheet priors, working-curve or extrusion model | Same-process sites only |
| Printability | PreForm / slicer checks, observed print failures | Same-process sites only |
| Calibration | Site's own seed-plate measurements | Never |
| Geometry | Feature size, aspect ratio, orientation | Yes |
| Empirical | Residual patterns across the site's measurements | Yes (as summaries) |
| Plate position (dormant) | Location on build plate | Yes |
| Orientation (dormant) | Feature orientation relative to build direction | Yes |
| Hypothesis (language model) | Residuals summaries + unmet-needs log | Yes |

The **hypothesis agent** (Nemotron) proposes candidate effects and new piece types when residuals or the unmet-needs log show something unexplained ("is the position-dependent error seen at the resin site also present at PLA?"). Its proposals enter the auction like any other and earn or lose credibility the same way. It never sets parameters or allocates space.

### 6.3 Message protocol

**May cross a site boundary:**
- Posterior summaries for process-agnostic parameters (mean and covariance)
- Agent and site credibility scores
- Hypotheses and proposed piece types
- Unmet-needs entries (question and anonymized residual summary)
- Challenge outcomes

**Never crosses:**
- Raw measurements
- Plate files and randomization seeds
- Site-specific parameters (calibration agent state)
- Held-out data

The boundary is enforced in code: messages are typed, and the serializer rejects anything outside the allowed schema. Every message is written to the receipt chain, so H4 is checkable by replay.

Known limitation: posterior summaries can leak some information about a site's data. Adding calibrated noise to shared summaries (differential privacy) is an aim goal, not core.

### 6.4 Incoming-message trust

Each receiving agent weights incoming posterior summaries by the sending site's credibility, as earned on the receiving site's own held-out data. A site whose shared beliefs hurt others' predictions loses influence everywhere it broadcasts.

### 6.5 Decision cycle (per plate, per site)

1. **Receive.** Agents ingest messages from other sites, weighted by sender credibility.
2. **Propose.** Each agent proposes the pieces it is least certain about, ranked by expected information gain.
3. **Challenge.** One round. Each agent may flag one other proposal with a reason ("redundant with mine," "already predictable from my evidence"). Flagged pieces lose bid weight. The flagger gains or loses credibility depending on whether the flag holds up on held-out data.
4. **Bid and clear.** Fixed clearing rule: each arm's slot pool is divided among agents in proportion to credibility (largest-remainder rounding); each agent fills its slots with its top surviving proposals. The rule allocates space only and never chooses content.
5. **Approve.** Human checks printability and safety only. Approvals logged; any edit or veto recorded and reported.
6. **Print, measure, update.** Posteriors update piece by piece as measurements arrive, in order of information value.
7. **Credit.** Agent and sender credibility update from held-out improvement (Section 6.6).
8. **Broadcast.** Allowed messages go out to other sites.
9. **Explain (async).** Nemotron writes explanations after the plate is locked, off the critical path.

### 6.6 Credibility

After each round, for each agent *a*, compute the change in held-out log predictive density when *a*'s contributed pieces are removed (leave-one-agent-out). Update multiplicatively:

c_a ← c_a · exp(η · ΔLPD_a), then normalize.

Sender credibility uses the same rule, with ΔLPD measured by removing that sender's messages. η is fixed and pre-registered. Held-out data is escrowed per site; agents see only scalar credit.

### 6.7 Spawn and retire

- **Retire:** an agent below a pre-registered credibility floor for two consecutive rounds stops bidding.
- **Spawn:** when a site's unmet-needs log, or incoming unmet-needs messages from other sites, reach a threshold matching a dormant template, that agent wakes with uniform credibility. A question raised at one site can wake an agent at another.
- Best-effort on real printers; always exercised in simulation.

