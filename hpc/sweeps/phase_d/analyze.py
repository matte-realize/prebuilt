"""Tables for the Phase D sweeps, from results/*.jsonl(.gz).

    .venv/bin/python hpc/sweeps/phase_d/analyze.py robustness   # writes results/robustness.md
    .venv/bin/python hpc/sweeps/phase_d/analyze.py ablation
    .venv/bin/python hpc/sweeps/phase_d/analyze.py scaling

Errors are `mae_truth` (model error against noise-free held-out diameters) in
µm. Intervals are mean ± 1.96 SE over seeds. Trust row r is the trust a
receiver applies to round r's messages (credit from round r - 1's held-out data).
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

RESULTS = Path(__file__).resolve().parent / "results"
ARMS = ("isolated", "networked", "oracle")
UM = 1000.0
# Claim 3 per seed, at the last round: the bad sender has lost influence, the honest
# sender kept it, and the honest site's networked model is no worse than its isolated one.
LOST, KEPT = 0.5, 0.5


def load(condition: str, k: int = 2) -> dict[int, dict]:
    """seed -> record, from results/<condition>_sites<k>.jsonl or its .gz."""
    p = RESULTS / f"{condition}_sites{k}.jsonl"
    if not p.exists():
        p = Path(f"{p}.gz")
    with (gzip.open(p, "rt") if p.suffix == ".gz" else open(p)) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["seed"]: r for r in rows}


def err(rec: dict, site: str | None = None) -> dict[int, dict[str, float]]:
    """round -> arm -> mae_truth in µm, one site or averaged over all sites."""
    acc = defaultdict(lambda: defaultdict(list))
    for s in rec["scores"]:
        if (site is None or s["site"] == site) and s["mae_truth"] is not None:
            acc[s["round"]][s["arm"]].append(s["mae_truth"] * UM)
    return {r: {a: float(np.mean(v)) for a, v in arms.items()} for r, arms in acc.items()}


def trust(rec: dict, receiver: str, sender: str) -> dict[int, float]:
    return {t["round"]: t["trust"] for t in rec["trust"] if t["receiver"] == receiver and t["sender"] == sender}


def max_cred(rec: dict, site: str) -> dict[int, float]:
    """round -> largest agent credibility at a site (0.2 = uniform over five agents)."""
    out = {}
    for c in rec["credibility"]:
        if c["site"] == site:
            out[c["round"]] = max(v for k, v in c.items() if k not in ("round", "site", "dlpd"))
    return out


def ci(x) -> str:
    x = np.asarray(x, float)
    h = 1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0
    return f"{x.mean():.2f} ± {h:.2f}"


def ci3(x) -> str:
    x = np.asarray(x, float)
    h = 1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0
    return f"{x.mean():.3f} ± {h:.3f}"


def recovery_round(rounds: list[int], harm: dict[int, float]) -> int | None:
    """First round from which networked stays at or below isolated (harm <= 0) for good; None = never."""
    for r in rounds:
        if all(harm[q] <= 0 for q in rounds if q >= r):
            return r
    return None


def robustness_seed(honest: dict, attacked: dict, bad: str, good: str) -> dict:
    rounds = sorted(err(attacked))
    e_att, e_hon = err(attacked, good), err(honest, good)
    harm = {r: e_att[r]["networked"] - e_att[r]["isolated"] for r in rounds}
    last = rounds[-1]
    bad_t, good_t = trust(attacked, good, bad), trust(attacked, bad, good)
    return {
        "rounds": rounds, "bad_trust": bad_t, "good_trust": good_t,
        "good_trust_honest": trust(honest, bad, good),
        "bad_cred": max_cred(attacked, bad), "bad_cred_honest": max_cred(honest, bad),
        "good_cred": max_cred(attacked, good), "good_cred_honest": max_cred(honest, good),
        "net_att": {r: e_att[r]["networked"] for r in rounds}, "iso_att": {r: e_att[r]["isolated"] for r in rounds},
        "net_hon": {r: e_hon[r]["networked"] for r in rounds}, "iso_hon": {r: e_hon[r]["isolated"] for r in rounds},
        "harm": harm, "recovery": recovery_round(rounds, harm),
        "lost": bad_t[last] < LOST, "kept": good_t[last] >= KEPT, "no_harm": harm[last] <= 0,
        "vs_honest": e_att[last]["networked"] - e_hon[last]["networked"],
    }


def robustness() -> str:
    honest = load("honest")
    out = ["# Robustness (claim 3)", "",
           "One site broadcasts confident beliefs 3 prior SD off (`--bad-site`). Two sites, config from the prereg. "
           "Paired by seed against the same seed's honest run. ± is 1.96 SE over seeds. Errors are the honest site's "
           "`mae_truth`, µm.", ""]
    per = {}
    for bad, good in (("pla", "resin"), ("resin", "pla")):
        att = load(f"bad_{bad}")
        seeds = sorted(set(att) & set(honest))
        per[bad] = [robustness_seed(honest[s], att[s], bad, good) | {"seed": s, "bad": bad} for s in seeds]
    for bad, rows in per.items():
        good = "resin" if bad == "pla" else "pla"
        rounds = rows[0]["rounds"]
        col = lambda key, r: [x[key][r] for x in rows]  # noqa: E731
        out += [f"## {bad} lies, {good} honest ({len(rows)} seeds)", "",
                "| round | bad sender's trust | honest sender's trust (attack / honest run) | bad site's top agent credibility (attack / honest run) "
                "| honest site's top agent credibility (attack / honest run) | honest net, attack | honest net, no attack | honest iso, attack "
                "| net − iso, attack | seeds with net ≤ iso |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for r in rounds:
            out.append(
                f"| {r} | {ci3(col('bad_trust', r))} | {ci3(col('good_trust', r))} / {ci3(col('good_trust_honest', r))} "
                f"| {ci3(col('bad_cred', r))} / {ci3(col('bad_cred_honest', r))} "
                f"| {ci3(col('good_cred', r))} / {ci3(col('good_cred_honest', r))} "
                f"| {ci(col('net_att', r))} | {ci(col('net_hon', r))} | {ci(col('iso_att', r))} "
                f"| {ci(col('harm', r))} | {sum(h <= 0 for h in col('harm', r))}/{len(rows)} |")
        rec = [x["recovery"] for x in rows]
        dist = ", ".join(f"round {r}: {rec.count(r)}" for r in rounds) + f", never: {rec.count(None)}"
        out += ["", f"Recovery round (first round from which networked stays ≤ isolated): {dist}.", ""]
    allrows = [x for rows in per.values() for x in rows]
    n = len(allrows)
    lost = sum(x["lost"] for x in allrows)
    kept = sum(x["kept"] for x in allrows)
    noharm = sum(x["no_harm"] for x in allrows)
    ok = sum(x["lost"] and x["kept"] and x["no_harm"] for x in allrows)
    last = allrows[0]["rounds"][-1]
    # Reference: how often networked is already worse than isolated in honest runs (no attack)
    hon_worse = sum(x["net_hon"][last] > x["iso_hon"][last] for x in allrows)
    # Attack harm beyond noise: networked under attack vs the same seed's honest networked run.
    # Piece choices diverge between the two runs, so the difference is noisy in both directions;
    # an attack can't help, so the lower tail is noise alone. Mirror its 5th percentile as the tolerance.
    d = np.array([x["vs_honest"] for x in allrows])
    tol = -np.percentile(d, 5)
    harmed = d > tol
    ok2 = sum(x["lost"] and x["kept"] and not h for x, h in zip(allrows, harmed))
    out += ["## Claim 3, per seed, both directions", "",
            f"At round {last}, over {n} attacked runs ({n // 2} seeds × 2 directions):", "",
            f"- bad sender's trust < {LOST}: {lost}/{n}",
            f"- honest sender's trust ≥ {KEPT}: {kept}/{n}",
            f"- honest site's networked ≤ isolated: {noharm}/{n} "
            f"(same site, same seeds, no attack: networked > isolated in {hon_worse}/{n}, so part of this is noise, not the attack)",
            f"- all three: {ok}/{n}; fail: {n - ok}", "",
            f"Noise-aware version: networked under attack minus the same seed's networked without attack, round {last}. "
            f"Its 5th percentile is {-tol:.2f} µm; seeds above +{tol:.2f} µm count as harmed beyond noise.", "",
            f"- harmed beyond noise: {harmed.sum()}/{n} "
            + ", ".join(f"({b} lies: {sum(h for x, h in zip(allrows, harmed) if x['bad'] == b)})" for b in per),
            f"- median difference {np.median(d):.2f} µm, 90th percentile {np.percentile(d, 90):.2f}, 99th {np.percentile(d, 99):.2f}",
            f"- correlation of that difference with the bad sender's final trust: {np.corrcoef(d, [x['bad_trust'][last] for x in allrows])[0, 1]:.2f}",
            f"- trust lost, honest trust kept, and not harmed beyond noise: {ok2}/{n}; fail: {n - ok2}", ""]
    return "\n".join(out)


def arm_table(recs: dict[int, dict], arms: dict[str, tuple[dict, str]]) -> list[str]:
    rounds = sorted(err(next(iter(recs.values()))))
    out = ["| round | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for r in rounds:
        cells = [ci([err(src[s])[r][arm] for s in sorted(src)]) for src, arm in arms.values()]
        out.append(f"| {r} | " + " | ".join(cells) + " |")
    return out


def ablation() -> str:
    honest, nomsg = load("honest"), load("no_messages")
    seeds = sorted(set(honest) & set(nomsg))
    honest, nomsg = {s: honest[s] for s in seeds}, {s: nomsg[s] for s in seeds}
    out = ["# Ablation", "", f"Two sites, {len(seeds)} seeds, same seeds in every column. `mae_truth`, µm, both sites averaged, "
           "mean ± 1.96 SE. No-messages is the networked arm with the network cut (`--no-messages`).", ""]
    out += arm_table(honest, {"isolated": (honest, "isolated"), "no messages": (nomsg, "networked"),
                              "networked": (honest, "networked"), "oracle (reference)": (honest, "oracle")})
    rounds = sorted(err(honest[seeds[0]]))
    out += ["", "Paired differences, µm:", "", "| round | iso − net | iso − no-messages | no-messages − net | oracle − net |",
            "|---|---|---|---|---|"]
    for r in rounds:
        e = {s: err(honest[s])[r] for s in seeds}
        m = {s: err(nomsg[s])[r]["networked"] for s in seeds}
        out.append(f"| {r} | {ci([e[s]['isolated'] - e[s]['networked'] for s in seeds])} "
                   f"| {ci([e[s]['isolated'] - m[s] for s in seeds])} | {ci([m[s] - e[s]['networked'] for s in seeds])} "
                   f"| {ci([e[s]['oracle'] - e[s]['networked'] for s in seeds])} |")
    return "\n".join(out)


def scaling() -> str:
    out = ["# Scaling", "", "Honest runs, config from the prereg, sites alternate resin and pla. `mae_truth`, µm, averaged over "
           "every site, mean ± 1.96 SE over seeds.", "",
           "| sites | seeds | round | isolated | networked | oracle (reference) | iso − net | oracle − net |",
           "|---|---|---|---|---|---|---|---|"]
    for k in (2, 5, 10, 25):
        try:
            recs = load("honest", k)
        except FileNotFoundError:
            continue
        seeds = sorted(recs)
        for r in sorted(err(recs[seeds[0]])):
            e = [err(recs[s])[r] for s in seeds]
            out.append(f"| {k} | {len(seeds)} | {r} | {ci([x['isolated'] for x in e])} | {ci([x['networked'] for x in e])} "
                       f"| {ci([x['oracle'] for x in e])} | {ci([x['isolated'] - x['networked'] for x in e])} "
                       f"| {ci([x['oracle'] - x['networked'] for x in e])} |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sweep", choices=["robustness", "ablation", "scaling"])
    a = ap.parse_args()
    text = {"robustness": robustness, "ablation": ablation, "scaling": scaling}[a.sweep]()
    (RESULTS / f"{a.sweep}.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
