"""Analyze negative_control.jsonl: does sharing gain anything when the printers share no physics?

    .venv/bin/python hpc/sweeps/relevance/analyze_negative_control.py hpc/sweeps/relevance/results/negative_control.jsonl.gz
"""
import os, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence import negative_control  # noqa: E402

r = negative_control(Path(sys.argv[1]))
print(f"{r['worlds']} worlds, round {r['rounds']}, true-size error (µm), paired per world (positive = first is better)\n")
fmt = lambda g: f"{g['um']:+5.2f} µm ({g['pct']:+5.1f}%, CI {g['pct_ci'][0]:+.1f} to {g['pct_ci'][1]:+.1f}), better in {g['wins']}/{g['n']}, p={g['p']:.4f}"
for w, nm in (("normal", "shared physics (normal world)"), ("control", "nothing shared (independent_shared=True)")):
    x = r[w]
    print(f"{nm}: alone {x['alone_um']:.1f} µm, together {x['together_um']:.1f} µm")
    print(f"  together vs alone          {fmt(x['together_vs_alone'])}")
    print(f"  notes vs messages cut      {fmt(x['notes_vs_no_notes'])}")
    print(f"  pooled raw data vs alone   {fmt(x['pooled_vs_alone'])}")
    if "check" in x:
        c = x["check"]
        print(f"  with consistency check: {c['dropped']} of {c['notes']} notes dropped; together vs alone {fmt(c['together_vs_alone'])}")
