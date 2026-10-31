# Spec: Overview

## 1. One-line pitch

A decentralized collective of scientist agents that designs and runs its own experiments on real 3D printers to learn how a fabrication process actually behaves. Each printer is a site with its own agents and private data. Sites share only beliefs and hypotheses, yet the network learns nearly as fast as if all data were pooled, and far faster than any site alone.

**The scientific question:** can autonomous agents that cannot pool their evidence still do experimental science together efficiently? Fabrication is the testbed because the experiments are real, cheap, fast, and measurable within a weekend.

## 2. Problem

Every fabrication process has to be characterized before its parts can be trusted. Today that work is manual, machine-specific, and repeated for every printer, material, and site.

Manufacturing is increasingly distributed: marketplaces and networks route jobs to machines they don't own, and regulated buyers (aerospace, medical, defense) need evidence that a part from a given machine will meet spec. The knowledge that would make characterization fast already exists, spread across thousands of machines, but it can't be pooled. Shops won't hand over raw process data: it's proprietary and exposes their capabilities and failure rates.

So every site re-learns from scratch. Prebuilt lets sites learn from each other without sharing data.

We use two processes, resin (SLA) and PLA (FDM), as two sites. They fail in opposite ways: resin holes close up from light bleed and over-cure while pins grow; FDM holes shrink from polygonization and extrusion width, and the first layer flares. Same test vocabulary (pin/hole pairs), different physics, which makes them a hard test of what can be shared.

## 3. Why decentralization is required, not chosen

The constraint defines the system: **raw measurements, plate files, and site-specific parameters never leave a site.** Only messages cross the boundary (Section 5.3). A centralized optimizer is therefore impossible in the real setting. We still build one, the pooled-data oracle, as an upper bound that no real network can reach.

