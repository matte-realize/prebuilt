# Spec: Overview

## 1. One-line pitch

Every 3D printer prints parts slightly the wrong size, in its own way. Prebuilt is a network of sites, each with its own agents and private data, that learn their printers' errors from each other while sharing only summaries of three process-agnostic parameters. In simulation, sharing those summaries matches pooling the raw data, and the gain grows with the number of data-poor sites.

**The scientific question:** can sites that cannot pool their evidence still do experimental science together efficiently? Fabrication is the testbed because the experiments are real, cheap and measurable, and a simulator with hidden truth can score what real measurements are too noisy to show.

## 2. Problem

Every fabrication process has to be characterized before its parts can be trusted. Today that work is manual, machine-specific, and repeated for every printer, material and site.

Manufacturing is increasingly distributed: marketplaces and networks route jobs to machines they don't own, and fleets where fit decides (dental labs, print farms, service bureaus) run many printers with little data each. The knowledge that would make characterization fast exists, spread across machines, but it can't be pooled. Shops won't hand over raw process data: it's proprietary, it exposes capabilities and failure rates, and customer geometry belongs to the customer.

So every site re-learns from scratch. Prebuilt lets sites learn from each other without sharing data.

Two processes, resin (SLA) and PLA (FDM), are the two sites. They fail in opposite ways: resin holes close up from light bleed and over-cure while pins grow; FDM holes shrink from polygonization and extrusion width, and the first layer flares. Same test vocabulary (pin/hole pairs), different physics, which makes them a hard test of what can be shared.

## 3. Why decentralization is required, not chosen

The constraint defines the system: **raw measurements, plate files and site-specific parameters never leave a site.** Only messages cross the boundary (Section 6.3). A centralized optimizer is therefore impossible in the real setting. The pooled-data oracle is built anyway, as a reference that no real network can reach.
