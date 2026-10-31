# Build: Kickoff, Layout, Contracts

## 1. Kickoff (Fri 9:00–9:30 PM, together)

Do not split up until these are written down and committed.

1. Create the repo with the layout in Section 2.
2. Agree on the interfaces in Section 3 and commit them as code.
3. Fill in the pre-registration values in Section 9 (thresholds, η, metrics). Commit; record the commit hash.
4. Confirm Saturday printer logistics: opening time, printer models, resin type, whether a print started before 10 PM can be collected Sunday morning.
5. Assign measurement duty: who scans each round on Saturday.

## 2. Repo layout

```
prebuilt/
  contracts.py        # shared dataclasses (Section 3) — change only together
  prereg/             # pre-registration file + hashes
  receipts/           # hash-chained logs, one chain per site
  plates/             # generator, piece library, plate files
  sim/                # Warp simulator, domain randomization
  measure/            # scanner pipeline, caliper entry
  model/              # physics models + posterior
  agents/             # agents, auction, credibility
  network/            # message schema + boundary enforcement
  arms/               # isolated, networked, oracle
  eval/               # held-out scoring, metrics, figures
  run.py              # one entry point: --source sim|real
```

## 3. Interfaces (the contract)

Everything downstream sees only these. The simulator and the real scanner both implement `Printer`, so nothing can tell them apart.

```python
@dataclass
class Piece:
    piece_id: str
    kind: str              # "pin" | "hole"
    nominal_d: float       # mm
    slot: tuple[int, int]  # grid position on plate
    arm: str               # "isolated" | "networked" | "oracle" | "heldout" | "seed"

@dataclass
class Plate:
    plate_id: str
    site: str              # "resin" | "pla"
    pieces: list[Piece]
    seed: int              # placement shuffle seed

@dataclass
class Measurement:
    piece_id: str
    plate_id: str
    site: str
    measured_d: float | None   # None if failed
    status: str                # "ok" | "failed"
    method: str                # "scanner" | "caliper" | "sim"

class Printer(Protocol):
    def print_and_measure(self, plate: Plate) -> list[Measurement]: ...

class Model(Protocol):
    def update(self, ms: list[Measurement]) -> None: ...
    def predict(self, piece: Piece) -> tuple[float, float]: ...  # mean, std

@dataclass
class Message:                 # the ONLY thing that crosses a site boundary
    sender_site: str
    round: int
    shared_params: dict[str, tuple[float, float]]  # process-agnostic only
    credibility: dict[str, float]
    hypotheses: list[str]
```

The message serializer rejects any field not in `Message`. That rejection is the privacy guarantee, and it's logged.

