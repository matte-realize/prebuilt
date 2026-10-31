# Spec: Speed, Verifiability, NVIDIA Stack

## 11. Speed and verifiability

### 11.1 Targets

- Agent decision cycle (receive → propose → challenge → clear): under one second per site.
- Language model off the critical path; explanations async.
- Posterior updates vectorized on GPU, one batched call for all agents.
- Piece library and printability checks precomputed and cached; no per-proposal API calls.

### 11.2 Physical loop

- Print time is part of each piece's bid cost (height and volume).
- Measurement in order of information value; held-out accuracy shown stabilizing before a plate is fully measured.

### 11.3 Receipts

Every decision and every cross-site message writes a hashed receipt: evidence snapshot, proposals, challenges, bids, clearing result, plate file hash, randomization seed hash, approval, measurement hashes, and outgoing/incoming messages. Each site keeps its own hash chain; cross-site messages reference both chains.

Anyone can replay a site's log to reproduce its numbers in seconds, and an auditor can verify from message receipts alone that nothing outside the allowed schema crossed a boundary (H4), without seeing any site's raw data.

## 12. NVIDIA stack

| Component | Use |
|---|---|
| Warp | Batched multi-site simulator; posterior updates |
| Nemotron | Hypothesis agent; async explanations |
| NeMo Agent Toolkit | Agent orchestration and cross-site messaging |
| Nebius H100s | Many-seed and site-scaling sweeps |
| DGX Spark | Local site loop next to the printers |

