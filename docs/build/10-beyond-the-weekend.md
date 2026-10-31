# Build: Beyond the Weekend

Not a build target. Notes for the closing slide ([spec 19](../spec/08-scope-and-logistics.md)) and for after the hackathon. The evidence is in [`hpc/sweeps/relevance/README.md`](../../hpc/sweeps/relevance/README.md).

## What the simulations say about the current setup

- **Sharing works, but the effect is small here.** By round 3, networked beats isolated by 1.6 µm (12%) against true size, in 75 of 100 worlds, at or below the pooled-data oracle. It comes from the messages: with messages cut, the same agents gain nothing (2.4%, 56/100).
- **It's too small to matter for fit or to see on real prints.** Model error is ~11–13 µm, scanner noise ~31 µm, the resin slip-fit band 100 µm. On measured diameters the gain is 1.5%.
- **Learned credibility adds nothing measurable to accuracy.** With messages cut, the agents at learned credibility don't beat the same agents at uniform credibility. Challenge and spawn were off in these sweeps (as in the frozen config), so this says nothing about them. Likely causes: a small design space (pins and holes, 1–8 mm), ~8 parameters per site, agents that read the same posterior.
- **Many data-poor sites is the lever.** Neither four sites (2.3 µm) nor less data with two sites (2.7 µm, not significant) helps much alone; four data-poor sites give 6.9 µm (27%, 51/60) and show through scanner noise (11% measured).
- **A bad site is cut off after one round, but round 1 is costly** (40 vs 14 µm), and afterwards the network is only back to where it would be with no messages. Lower `trust_init` only trims round 1. A prototype consistency check (receiver compares each note with its own data) caught every lying note, dropped no honest ones, and removed both problems in simulation.
- **A saboteur agent inside a site does almost no harm and isn't caught.** Piece choice barely matters here, so the agent market has nothing to protect; its credibility stays level with an honest agent's.

So the honest pitch: a privacy-preserving learning network whose value grows with the number of sites, with trust and privacy you can verify. Not "multi-agent swarm intelligence" yet.

## What would make the agents and the network matter

Considered on Oct 31 and deliberately left out of hackathon scope:

1. **Harder parts.** Multi-feature parts (holes, pins, slots, thin walls) whose errors interact; printability limits (overhangs, bridges, minimum wall) so tests can fail and cost something; assemblies that must fit, scored on fit or yield, not microns.
2. **More printer types.** Several resins, PLA, PETG, nylon, so sites differ more and there is more to transfer within and across families.
3. **A real swarm.** Many sites (8–32) that divide the labor of testing (a shared board of what each site is probing, so the network avoids redundant tests), each with specialist agents per feature or failure mode that actually see different evidence.
4. **A model that scales.** The particle posterior handles ~8 parameters; multi-feature parts need 30–60. A model linear in its parameters with an exact Gaussian posterior (plus a logistic failure model) scales to many sites on CPU and makes messages exact summaries.
5. **Catching liars in round 1.** Prototyped and it works in simulation (`hpc/sweeps/relevance/consistency.py`): adopt it as a protocol step after the weekend, then test it against subtle liars and real-printer model mismatch.
6. **Guard against building a sim that confirms itself.** Fix the world and experiments before running, include a negative control with no shared structure, and always compare against random test selection.

## Long-term direction: agents that assist production of complex products

The aim is to evolve this into agents that help run production for complex products, bioprinting being the motivating example. The pin-and-hole testbed is the smallest version of that problem. What carries over, and why the harder setting suits the method better:

- **Tests are expensive and slow.** A bioprinted construct can cost far more than a PLA pin and take days to evaluate, so choosing what to test next (the agents' job) has real value, unlike here, where almost any test teaches the same thing.
- **Every site is different.** Bioinks, crosslinking, printheads, temperature and cell lines vary by lab, so no site can borrow another's settings, but they share underlying behavior worth transferring. That is the hierarchical, shared-plus-local structure the network already models.
- **Data can't be pooled.** Process recipes are IP, and patient-derived material brings privacy rules, so learning from summaries rather than raw data is a requirement, not a nicety.
- **Results must be checkable.** Regulated production needs an audit trail; the hash-chained receipts and replayable audit are the start of one.
- **Outcomes are many-dimensional and some fail.** Shape fidelity, viability, mechanical properties and outright print failure, which is the multi-feature, printability and assembly-fit work listed above, in a harder domain.

What the weekend's evidence implies for that path: the value will come from many sites and expensive tests, the agent layer has to earn its place against random and single-agent baselines, and a bad or miscalibrated site must be caught before it does damage, not one round after.
