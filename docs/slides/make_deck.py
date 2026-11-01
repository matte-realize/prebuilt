"""Generate docs/slides/prebuilt-deck.html, the self-contained 10-slide backup deck for Q&A.

    python docs/slides/make_deck.py [--chart demo/tier-d/headline-truth.png]

Edit slide text below; styles live in deck_template.html. The 6-slide pitch (make_pitch.py) and
docs/slides/pitch-notes.md are the source of truth; this deck goes deeper on the same claims.
Every result is simulation. Headline, check, negative-control and sites numbers read
viewer/evidence.json (hpc/sweeps/relevance/evidence.py); the round table and the lying-site
cells read demo/tier-d (frozen config); the rest is from hpc/sweeps/relevance/README.md.
"""
import argparse
import base64
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
_ap = argparse.ArgumentParser()
_ap.add_argument("--chart", default=str(ROOT / "demo/tier-d/headline-truth.png"))
_args = _ap.parse_args()
_seed = json.loads((ROOT / "plates/out/resin/resin-seed.json").read_text())
PLATE = [[p["slot"][0], p["slot"][1], p["kind"], p["nominal_d"], p["arm"]] for p in _seed["pieces"]]
CHART = base64.b64encode(Path(_args.chart).read_bytes()).decode()
EV = json.loads((ROOT / "viewer/evidence.json").read_text())
HEAD, POOL, CUT = EV["together_vs_alone"], EV["pooled_vs_alone"], EV["team_without_notes_vs_alone"]
ERR = EV["error_um"]
CHECK = EV["consistency_check"]
NEG = EV["negative_control"]
SITES = EV["sites_needed"]["rows"]
TRUST = EV["trust_start"]
_RES = ROOT / "hpc/sweeps/relevance/results"
TECH = json.loads((_RES / "technical-summary.json").read_text())
ADAPT = TECH["spread"]["control"]["adaptive"]["vs_alone"]
MIXED = json.loads((_RES / "mixed-fleet-summary.json").read_text())["8"]


def curves(path: Path, site: str | None = None) -> dict:
    """arm -> [round 1, 2, 3] mean noise-free held-out MAE in µm (same as make_pitch.py)."""
    acc = defaultdict(list)
    for r in json.loads(path.read_text()):
        if site is None or r["site"] == site:
            acc[(r["arm"], r["round"])].append(r["mae_truth"])
    return {arm: [round(1000 * sum(acc[(arm, k)]) / len(acc[(arm, k)]), 1) for k in (1, 2, 3)]
            for arm in ("isolated", "networked", "oracle")}


DEMO = curves(ROOT / "demo/tier-d/sim.json")
pct = lambda v: f"{round(v)}%"
um1 = lambda v: f"{v:.1f}"
ROWS = "".join(f"<tr><td>{k + 1}</td><td>{DEMO['isolated'][k]}</td><td>{DEMO['networked'][k]}</td>"
               f"<td>{DEMO['oracle'][k]}</td></tr>" for k in range(3))
SITES_TXT = " / ".join(pct(r["pct"]) for r in SITES) + " at " + " / ".join(str(r["sites"]) for r in SITES) + " sites"


def plate_svg(label: bool = True) -> str:
    """The real resin seed plate, drawn from plates/out/resin/resin-seed.json (plate mm -> svg units)."""
    parts = ['<svg viewBox="-6 -6 112 118" class="plate" role="img" aria-label="Resin seed plate: 8 by 8 grid, '
             '16 calibration pieces and 8 held-out pieces">',
             '<rect x="0" y="0" width="100" height="100" rx="1.2" class="pl"/>',
             '<rect x="47" y="97.5" width="6" height="2.6" class="cut"/>']
    for fx, fy in ((5, 95), (95, 95), (5, 5)):
        parts.append(f'<rect x="{fx - 2}" y="{100 - fy - 2}" width="4" height="4" class="cut"/>')
    for r in range(8):
        for c in range(8):
            parts.append(f'<circle cx="{15 + 10 * c}" cy="{15 + 10 * r}" r="0.5" class="dot"/>')
    for r, c, kind, d, arm in PLATE:
        x, y = 15 + 10 * c, 15 + 10 * r
        cls = ("pin" if kind == "pin" else "hole") + (" ho" if arm == "heldout" else "")
        parts.append(f'<circle cx="{x}" cy="{y}" r="{d / 2}" class="{cls}"><title>{kind} {d:.1f} mm'
                     f'{" (held out)" if arm == "heldout" else ""}</title></circle>')
    if label:
        parts.append('<text x="0" y="108.5" class="lab">100 × 100 × 3 mm · 16 calibration + 8 held-out (ringed)</text>')
    parts.append("</svg>")
    return "".join(parts)


SLIDES = []


def slide(kicker, title, body, note):
    SLIDES.append((kicker, title, body, note))


slide("ScienceClaw · Manufacturing & Materials", "Prebuilt",
      f"""<div class="split">
  <div class="stack">
    <p class="lede">Printers at different sites learn each other's lessons without ever sharing a measurement.</p>
    <p>Two simulated printer sites, resin SLA and PLA FDM, each print a test plate, measure it and fit a model of their own machine. Only the mean and uncertainty of three shared parameters cross between them, schema-checked and on a hash chain. <span class="flag">Every result here is simulation.</span></p>
    <p class="meta">Matthew Shi and team · MIT Media Lab · Nov 1, 2026</p>
  </div>
  <figure class="fig">{plate_svg()}</figure>
</div>""",
      "Open on the plate: the seed test plate, pins and holes 1.1 to 7.3 mm. We printed it for real on one Formlabs Form Studio 1; the two sites in every result are simulated printers with known truth.")

slide("The problem", "Every site re-learns its own printer",
      """<div class="cols3">
  <div class="cell"><span class="big">24–89<small> µm</small></span><p>How small a 1.5 mm pin came out on our Form Studio 1, by micrometer. A resin slip fit is a ~100 µm band.</p></div>
  <div class="cell"><span class="big">By printing</span><p>That error belongs to one machine, resin, settings and wear. No datasheet knows it; every site learns it from scratch.</p></div>
  <div class="cell"><span class="big">No pooling</span><p>Measurements reveal process know-how and customer parts. Sites won't hand over raw data.</p></div>
</div>
<p class="foot">Some of what a printer gets wrong is shared across machines and even processes: small features shrink, error drifts across the plate. That part can be learned together. Vendor spec for the Form Studio 1: ±0.08 mm on 1–30 mm features.</p>""",
      "The ask: can sites get the benefit of pooling without pooling? The 24–89 µm is two micrometer readings of one pin (1.411 and 1.476 mm), inside the vendor spec.")

slide("The setup", "Two simulated sites, one boundary",
      """<div class="boundary">
  <div class="site"><h3>Resin site · SLA (simulated)</h3><ul><li>Every measurement stays here</li><li>Own parameters: penetration depth, critical energy, bleed, shrink</li></ul></div>
  <div class="wall"><span>schema-checked boundary</span>
    <ul class="cross"><li>Mean and uncertainty of 3 shared parameters: size dependence and the two plate-position gradients</li><li>That is all the receiver's model uses. Anything off-schema is rejected and logged</li></ul>
  </div>
  <div class="site"><h3>PLA site · FDM (simulated)</h3><ul><li>Every measurement stays here</li><li>Own parameters: extrusion offset, polygon shrink, flare</li></ul></div>
</div>
<p class="foot">Three arms, scored per world against the simulator's hidden truth: <b class="a-iso">isolated</b> (own data only), <b class="a-net">networked</b> (own data plus the summaries), <b class="a-ora">pooled</b> (all raw data in one model, the "oracle").</p>""",
      "Both sites are simulated printers whose true behavior we know; that is how every result is scored. The note also carries round, sender and agent-credibility fields as bookkeeping (see the receipt on slide 8); the receiving model reads only the three summaries.")

slide("Inside a site", "Agents pick pieces; sharing does the work",
      f"""<ol class="flow">
  <li><b>Propose.</b> Five agents rank pieces by what they'd learn: physics, calibration, geometry, empirical residuals, printability.</li>
  <li><b>Auction.</b> Plate slots split in proportion to credibility. The rule allocates space and never picks content.</li>
  <li><b>Print and measure.</b> Each plate carries 8 held-out pieces at fixed slots, escrowed from every model.</li>
  <li><b>Credit.</b> Credibility moves with how much an agent's pieces improved held-out prediction.</li>
  <li><b>Exchange.</b> Sites send the three summaries. Trust in each sender moves the same way, so a bad source fades out.</li>
</ol>
<p class="foot">The agent layer adds nothing measurable. With messages cut, learned credibility ties equal votes ({pct(CUT["pct"])}, {CUT["wins"]} of {CUT["n"]} worlds, p={CUT["p"]:.2f}). A saboteur agent that always picks the least informative pieces barely hurts and isn't caught, and the agents' piece choices don't beat random: which pieces print hardly matters here. The gain is step 5, between sites. <span class="flag">Simulation only.</span></p>""",
      "Say it before they ask: the win is many sites, not many agents. Agents vs random piece choice: +1%, 31 of 60 worlds (isolated arm). Source: hpc/sweeps/relevance/README.md sections 1, 3 and 8.")

slide("Sim-to-real", "Grounded in a real printer, scored in simulation",
      """<div class="timeline">
  <div><span class="t">Simulator</span><p>Multi-site simulator with hidden truth and unmodeled effects. Config tuned there, then frozen.</p></div>
  <div><span class="t">Before printing</span><p>Pre-registration committed with its sha256, including the prediction that two printers can't show the sharing gain on real parts.</p></div>
  <div><span class="t">Real printer</span><p>One Formlabs Form Studio 1, Alpha Fast resin. The 1.5 mm pin measured 1.41–1.48 mm by micrometer: inside the simulator's range, at its small edge (1.8th percentile).</p></div>
  <div><span class="t">Why not real</span><p>The two-site gain is 1.6 µm; two readings of one pin differed by 65 µm. Only hidden truth can score it.</p></div>
</div>
<p class="foot">The real printer checks the simulator's scale. No model was fit on the real printer (three pieces aren't enough) and no sharing gain is claimed there. The plate, a hand-measurement sheet and the scanner pipeline are ready for real sites.</p>""",
      "Simulated resin pins miss by −0.1 to +0.27 mm and holes by up to −0.35 mm; the real pin sits inside. Don't claim a real fit or real rounds.")

slide("Result · simulation", "Sharing matches pooling the raw data",
      f"""<figure class="chart"><img src="data:image/png;base64,{CHART}" alt="Held-out error falls with pieces printed; networked tracks the pooled-data oracle below isolated in every round."></figure>
<table class="nums"><thead><tr><th>Round</th><th class="a-iso">Isolated</th><th class="a-net">Networked</th><th class="a-ora">Pooled</th></tr></thead>
<tbody>{ROWS}</tbody></table>
<p class="foot">Chart and table: noise-free held-out MAE, µm, 20 worlds × 2 sites. Over {EV["worlds"]} worlds, round 3: networked {HEAD["um"]:.1f} µm ({pct(HEAD["pct"])}) below isolated, better in {HEAD["wins"]} of {HEAD["n"]}; pooling the raw data gains {pct(POOL["pct"])} ({um1(ERR["networked"])} vs {um1(ERR["oracle"])} µm). At two sites that is too small to see on a real part, and we registered that before printing. <span class="flag">Frozen config, simulation only.</span></p>""",
      "Say the size out loud: real in simulation, matches pooling, far too small to see on a part at two sites. Source: viewer/evidence.json, hpc/sweeps/relevance/README.md section 1.")

slide("Robustness · simulation", "A liar costs one round; with the check, none",
      f"""<div class="cols3">
  <div class="cell"><span class="big">{CHECK["resin_round1_um"]["liar_no_check"]:.0f}<small> µm</small></span><p>Round 1 at the honest site when PLA broadcasts confident, wrong beliefs ({CHECK["resin_round1_um"]["no_notes"]:.1f} with no notes). Its held-out pieces expose the lie: trust in PLA falls to ~1% and resin recovers.</p></div>
  <div class="cell"><span class="big">{CHECK["liar_caught"]}/{CHECK["liar_notes"]}</span><p>lying notes caught on arrival by the consistency check, {CHECK["honest_dropped"]} of {CHECK["honest_notes"]} honest notes dropped. Round 1 at the lied-to site: {CHECK["resin_round1_um"]["liar_no_check"]:.0f} → {CHECK["resin_round1_um"]["liar_check"]:.1f} µm.</p></div>
  <div class="cell"><span class="big">{pct(SITES[-1]["pct"])}</span><p>lower error at {SITES[-1]["sites"]} data-poor sites, better in {SITES[-1]["wins"]} of {SITES[-1]["n"]} worlds: {SITES_TXT} (4 seed pieces, 2 a round, round 3). Many sites that each know little is where sharing pays.</p></div>
</div>
<p class="foot">Both cells: the same {CHECK["worlds"]} worlds, round 1. The check compares each incoming summary with the receiver's own fit (chi-square 0.999) and is an added protocol option, off in the registered config, tested in {CHECK["worlds"]} worlds; this liar is easy to catch. A subtle one (0.5–1 prior std off) slips past the check a quarter to half the time; adding adaptive spread caps the round-1 cost at 5% for every liar tried. Starting trust at 0.3 instead only trims round 1 ({TRUST["trust 1.0 | liar"][0]:.0f} → {TRUST["trust 0.3 | liar"][0]:.0f} µm). <span class="flag">Simulation only.</span></p>""",
      "Sources: viewer/evidence.json (consistency_check, sites_needed), hpc/sweeps/coldstart/README.md, hpc/sweeps/relevance/README.md section 8 (subtle liars).")

slide("Verifiability", "Every crossing is on a receipt",
      """<div class="split">
  <pre class="receipt">{ "seq": 13, "site": "resin", "kind": "message_out",
  "payload": { "to": "pla", "wire": {
    "sender_site": "resin", "round": 2,
    "shared_params": {
      "size_coef": [0.0226, 0.00028],
      "pos_gx":    [-0.0249, 0.00011],
      "pos_gy":    [0.0070, 0.00011] },
    "credibility": { "physics": 0.49, "calibration": 0.26, … },
    "hypotheses": [], "unmet_needs": [] } },
  "prev_hash": "61de94d1…231a",
  "hash":      "e646e784…06d0" }</pre>
  <div class="stack"><p>Each site keeps a hash chain of plates, measurements, bids, credit and messages. The receipt above is a real one from a simulated run. The audit replays both chains and checks that every boundary crossing matches the schema and that nothing else left.</p><p class="big-ok">PASS<small> in every run</small></p>
  <p class="meta mono">python -m console: the full pipeline as a practice run, simulated or real sites, hand measurements</p></div>
</div>""",
      "shared_params is [mean, variance] per parameter; credibility is bookkeeping the receiving model doesn't read. Live: python -m eval.audit on the chains, or the local console.")

slide("Is the simulator built to confirm itself?", "Negative control: share nothing, gain nothing",
      f"""<div class="cols3">
  <div class="cell"><span class="big">+{pct(NEG["normal"]["together_vs_alone"]["pct"])}</span><p>Normal worlds, physics really shared: together vs alone, better in {NEG["normal"]["together_vs_alone"]["wins"]} of {NEG["normal"]["together_vs_alone"]["n"]}.</p></div>
  <div class="cell"><span class="big">−{-NEG["control"]["together_vs_alone"]["pct"]:.0f}%</span><p>Same worlds, each printer's "shared" physics drawn independently: sharing hurts, better in only {NEG["control"]["together_vs_alone"]["wins"]} of {NEG["control"]["together_vs_alone"]["n"]}.</p></div>
  <div class="cell"><span class="big">{f'{ADAPT["pct"]:+.1f}'.replace("-", "−")}%</span><p>With adaptive spread (each receiver learns how far to trust a sender from how much they agree): printers that share nothing lose nothing, {ADAPT["wins"]} of {ADAPT["n"]}. In normal worlds it keeps the full gain.</p></div>
</div>
<p class="foot">{NEG["worlds"]} worlds, round 3, paired per world. The gain isn't built into the scoring: it comes from physics the printers share. The flip side: with the registered fixed spread, printers that share less than the model assumes are hurt. The consistency check alone cuts that to −{-NEG["control"]["check"]["together_vs_alone"]["pct"]:.0f}% (drops {NEG["control"]["check"]["dropped"]} of {NEG["control"]["check"]["notes"]} notes); adaptive spread removes it. Both are added options, off in the registered config. <span class="flag">Simulation only.</span></p>""",
      "Sources: viewer/evidence.json negative_control, hpc/sweeps/relevance/README.md sections 6 and 8.")

slide("Next", "Print anywhere, trust the part",
      f"""<div class="split">
  <div class="stack"><p class="lede">Any shop that can print a flat plate can join, learn its machine faster, and keep its data.</p>
  <p>Two printers is the smallest network, and there the gain is a couple of microns. The simulator says when it pays: many sites that each know little ({SITES_TXT}).</p>
  <p><b>Parts that fit the first time:</b> corrected designs cut size error from 132 to 9 µm (median, 60 worlds), with a calibrated 90% interval. <b>Safe when printers differ:</b> with half of eight printers sharing no physics, the defences lift the matching ones to {MIXED["matched"]["both"]["vs_alone"]["pct"]:.0f}% better and cut the harm to the others from −{-MIXED["unmatched"]["fixed"]["vs_alone"]["pct"]:.0f}% to −{-MIXED["unmatched"]["both"]["vs_alone"]["pct"]:.0f}%.</p>
  <p>Released: the process-agnostic test plate and generator, a hand-measurement sheet and scanner pipeline, the local console, and the hidden-truth multi-site simulator. Next: real sites.</p>
  <p class="meta mono">github.com/matte-realize/prebuilt</p></div>
  <figure class="fig small">{plate_svg(label=False)}</figure>
</div>""",
      "Close on the plate. Buyers: dental labs, print farms and service bureaus, distributed manufacturing (pitch slide 6). Corrected designs: hpc/sweeps/relevance/README.md section 12. Mixed fleets: section 10; predictive trust (section 11) is newer and opt-in, and neither rule identifies bad partners. Many-machine networks and complex products are direction, not results: see docs/future-work.md.")


def render() -> str:
    sections = []
    for i, (kicker, title, body, note) in enumerate(SLIDES, 1):
        sections.append(f"""<section class="slide" id="s{i}" aria-label="Slide {i}: {title}">
  <header><span class="kick">{kicker}</span><span class="num">{i:02d} / {len(SLIDES):02d}</span></header>
  <h2>{title}</h2>
  <div class="body">{body}</div>
  <aside class="note">{note}</aside>
</section>""")
    return (TEMPLATE.replace("Prebuilt · draft deck · 10 slides", f"Prebuilt · backup deck · {len(SLIDES)} slides")
            .replace("%%SLIDES%%", "\n".join(sections)))


TEMPLATE = (HERE / "deck_template.html").read_text()
out = ROOT / "docs/slides/prebuilt-deck.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(render())
print(out, out.stat().st_size)
