# Future Work

What the simulations say about the current setup, what would make the agents and the network matter, and where this goes. The evidence is in [`hpc/sweeps/relevance/README.md`](../hpc/sweeps/relevance/README.md).

## What the simulations say about the current setup

All simulation, against printers whose true behavior is known (`hpc/sweeps/relevance/README.md`, section numbers below).

- **Sharing works, but at two sites the effect is small.** By round 3, networked beats isolated by 1.6 µm (12%) against true size, in 75 of 100 worlds, matching the pooled-data oracle. It comes from the messages: with messages cut, the same agents gain nothing (2.4%, 56/100). Section 1.
- **It's too small to see on real prints at two sites.** Model error is ~11–13 µm, scanner noise ~31 µm, the resin slip-fit band 100 µm. On measured diameters the gain is 1.5%. Section 1.
- **Many data-poor sites is the lever.** Sites that start with 4 test pieces and print 2 a round gain 11% / 28% / 35% at 2 / 4 / 8 sites (8 sites: 20 of 20 worlds). Sections 2 and 7.
- **The agent layer adds nothing measurable.** Learned credibility doesn't beat uniform credibility, the agents' piece choices don't beat random (section 8), and a saboteur agent inside a site does almost no harm and isn't caught (section 3). Likely causes: a small design space (pins and holes, 1–8 mm), ~8 parameters per site, agents that read the same posterior.
- **The gain isn't built into the simulator.** In a negative control where printers share no physics, sharing gains nothing (−13%). Section 6.
- **Liars and mismatched printers can be handled, as opt-in options.** The consistency check catches a blatant liar's notes on arrival (180/180, no honest note dropped) but only about half of subtle ones; adding adaptive spread caps the round-1 cost at 5% for every liar tried and removes the harm when printers share nothing (−13% → −0.4%). In a mixed fleet of 8 (half mismatched), the defences lift the matching printers from +16% to +25% and cut the harm to the others from −15% to −1%; predictive trust goes further (matching +33%, mismatched +7% at round 6, on held-out parts trust never saw). None of them cleanly identifies a mismatched printer (best AUC 0.77). Sections 5, 8, 10, 11.
- **Small features:** on a sub-millimetre plate the gain holds at 7–9% and doesn't grow; below about 0.5 mm the physics model stops being believable. Section 9.
- **Corrected designs work and their interval is calibrated:** size error 132 → 9 µm (median, 60 worlds), 90% interval covering 81–96% in cross-validation. Section 12.

So the honest pitch: a privacy-preserving learning network whose value grows with the number of sites, with trust and privacy you can verify. Not "multi-agent swarm intelligence" yet.

## What would make the agents and the network matter

Not built:

1. **Real-site validation.** No full real run exists: one Formlabs Form Studio 1 and micrometer readings of 3 pins only. The next step is many real printers with a few hand-measured pieces each, which is the regime where the simulator says the gain becomes measurable.
2. **Harder parts.** Multi-feature parts (holes, pins, slots, thin walls) whose errors interact; printability limits (overhangs, bridges, minimum wall) so tests can fail and cost something; assemblies that must fit, scored on fit or yield, not microns.
3. **More printer types.** Several resins, PLA, PETG, nylon, so sites differ more and there is more to transfer within and across families.
4. **A real swarm.** Many sites (8–32) that divide the labor of testing (a shared board of what each site is probing, so the network avoids redundant tests), each with specialist agents per feature or failure mode that actually see different evidence. Until then the agent layer has to earn its place against random selection.
5. **A model that scales.** The particle posterior handles ~8 parameters; multi-feature parts need 30–60. A model linear in its parameters with an exact Gaussian posterior (plus a logistic failure model) scales to many sites on CPU and makes messages exact summaries.
6. **Trust that identifies bad partners.** The defences make sharing safe but only nudge mismatched senders down. Next: make the consistency check and adaptive spread the default, test predictive trust in more fleet layouts, and check all of them against real-printer model mismatch.
7. **A micro-scale model.** Resin overcure, light scatter and nozzle limits dominate below 1 mm and aren't modelled; micro-scale stays a direction until they are.

## Long-term direction: agents that assist production of complex products

The aim is to evolve this into agents that help run production for complex products, bioprinting being the motivating example. The pin-and-hole testbed is the smallest version of that problem. What carries over, and why the harder setting suits the method better:

- **Tests are expensive and slow.** A bioprinted construct can cost far more than a PLA pin and take days to evaluate, so choosing what to test next (the agents' job) has real value, unlike here, where almost any test teaches the same thing.
- **Every site is different.** Bioinks, crosslinking, printheads, temperature and cell lines vary by lab, so no site can borrow another's settings, but they share underlying behavior worth transferring. That is the hierarchical, shared-plus-local structure the network already models.
- **Data can't be pooled.** Process recipes are IP, and patient-derived material brings privacy rules, so learning from summaries rather than raw data is a requirement, not a nicety.
- **Results must be checkable.** Regulated production needs an audit trail; the hash-chained receipts and replayable audit are the start of one.
- **Outcomes are many-dimensional and some fail.** Shape fidelity, viability, mechanical properties and outright print failure, which is the multi-feature, printability and assembly-fit work listed above, in a harder domain.

What the evidence so far implies for that path: the value will come from many sites and expensive tests, the agent layer has to earn its place against random and single-agent baselines, and a bad or miscalibrated site must be caught before it does damage, not one round after.
