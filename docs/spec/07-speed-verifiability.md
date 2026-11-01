# Spec: Speed, Verifiability, NVIDIA Stack

## 11. Speed and verifiability

### 11.1 Speed

- A 2000-particle, 3-round, two-site simulated experiment takes about 1.3 s on a laptop CPU; sweeps of 60–100 worlds take minutes.
- The language model is off the critical path: the hypothesis agent runs between rounds.
- The Warp posterior batches many posteriors into one kernel launch: 84× over a NumPy loop for 64 posteriors at 20k particles on an H100 (`docs/gpu-posterior.md`).
- The piece library and print costs are precomputed; no per-proposal API calls.

### 11.2 Physical loop

- Print cost (material volume above the plate) is part of each piece's proposal score.
- The real-printer path (`run.py --source real`, `measure/real.py`) checkpoints after every round and resumes after a crash; `measure.rehearsal` runs it end to end with simulated scans. The console (`python -m console`) drives the same loop from a browser.

### 11.3 Receipts

`receipts/chain.py`. Every decision and every cross-site message writes a hashed receipt: proposals, challenges, clearing result, plate file hash, approval, measurements, credit, and outgoing and incoming messages. Each site keeps its own hash chain; a real run also writes the prereg sha256 onto both chains.

Anyone can replay a site's log, and `eval/audit.py` verifies from the receipts alone that nothing outside the message schema crossed a boundary, without seeing any site's raw data. `run.py --source sim` audits every seed.

## 12. NVIDIA stack

| Component | Use | Status |
|---|---|---|
| Warp | Batched multi-site simulator; GPU particle posterior | Built, tested, benchmarked |
| Nebius H100 | Many-seed sweeps and the posterior benchmark (`hpc/nebius/`) | Used |
| Nemotron | Hypothesis agent (OpenAI-compatible endpoint, `agents/serve_nemotron.sh`) | Built; not run against a live model |
| NeMo Agent Toolkit | Agent orchestration | Not used; orchestration is plain Python |
| DGX Spark | Local site loop next to the printers | Not used |
