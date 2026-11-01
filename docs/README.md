# Prebuilt docs

ScienceClaw Hackathon, MIT Media Lab · Oct 30 – Nov 1, 2026 · Area A·03 Manufacturing & Materials.

Start with the [project README](../README.md) for what we found and how to run it.

## Results and design

- [Design notes](design-notes.md): why the experiment is set up the way it is (seed plate size, same agents in every arm, the oracle's MH steps, the primary metric, LPD clipping, held-out count), prereg choices, challenge and spawn, the hypothesis agent, real-path hardening, the scanner stress test, known limits
- Sweep results: [`hpc/sweeps/relevance/`](../hpc/sweeps/relevance/README.md) (does sharing matter, where, and how to make it safe), [`hpc/sweeps/coldstart/`](../hpc/sweeps/coldstart/README.md) (how many sites it takes), [`hpc/sweeps/phase_c/`](../hpc/sweeps/phase_c/README.md) (config tuning), [`hpc/sweeps/phase_d/`](../hpc/sweeps/phase_d/README.md) (robustness and ablation)
- [Warp GPU posterior](gpu-posterior.md): design, tests and benchmarks (laptop GPU and H100)
- [Future work](future-work.md): what the simulations say about the current setup, what would make the agents matter, and the long-term direction (production agents for complex products such as bioprinting)

## Guides

- [Console](guides/console.md): the browser UI for practice runs, hand measurements and corrected designs
- [Running at real sites](guides/real-site-run.md): the registered real-printer run, step by step
- [Formlabs test print](guides/test-print.md): one fast off-the-books resin print to check printing and scanning

## Spec

The full design. Where the build differs from it, the build and the pre-registration win:

| Topic | Spec | Built and registered |
|---|---|---|
| Arms | 4: human grid, isolated, networked, oracle | 3: isolated, networked, oracle |
| Claims | H1–H6 | 3: network vs. isolated, sim-to-real range, robustness (sim only) |
| Primary metric | Oracle gap closed | Isolated − networked held-out MAE, µm ([design notes](design-notes.md), point 5) |

1. [Overview](spec/01-overview.md): pitch, problem, why decentralization is required
2. [Claims and rubric](spec/02-claims-rubric.md): H1–H6, rubric mapping
3. [System architecture](spec/03-architecture.md): topology, agents, message protocol, trust, decision cycle, credibility, spawn/retire
4. [Physics models](spec/04-physics-models.md): resin, PLA, shared structure, fit definition
5. [Experimental design](spec/05-experimental-design.md): arms, held-out set, plates, metrics, failure rules, ablations
6. [Measurement and simulator](spec/06-measurement-simulator.md)
7. [Speed, verifiability, NVIDIA stack](spec/07-speed-verifiability.md): targets, receipts
8. [Scope, reuse and prior work](spec/08-scope-and-prior-work.md): direction, fallback tiers, scope, reuse deliverables, prior work

## Also

- Pre-registration: [`prereg/prereg.yaml`](../prereg/prereg.yaml) (its sha256 is recorded in [`eval/figures/README.md`](../eval/figures/README.md))
- Slides: [`slides/prebuilt-pitch.html`](slides/prebuilt-pitch.html) (3-minute pitch), [`slides/pitch-notes.md`](slides/pitch-notes.md) (script and Q&A), [`slides/prebuilt-deck.html`](slides/prebuilt-deck.html) (full deck)
- Backup demo, pure simulation: [`demo/tier-d/`](../demo/tier-d/)
