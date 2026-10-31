"""Generate docs/slides/prebuilt-deck.html, the self-contained 10-slide deck.

    python docs/slides/make_deck.py [--chart demo/tier-d/headline-truth.png]

Edit slide text below; styles live in deck_template.html. On Sunday, point --chart at the
headline chart with real rounds and update slides 6, 7 and 9.
"""
import argparse
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
_ap = argparse.ArgumentParser()
_ap.add_argument("--chart", default=str(ROOT / "demo/tier-d/headline-truth.png"))
_args = _ap.parse_args()
_seed = json.loads((ROOT / "plates/out/resin/resin-seed.json").read_text())
PLATE = [[p["slot"][0], p["slot"][1], p["kind"], p["nominal_d"], p["arm"]] for p in _seed["pieces"]]
CHART = base64.b64encode(Path(_args.chart).read_bytes()).decode()


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
    <p>Agents at each site choose test pieces to characterize a resin printer and a PLA printer from printed plates. Sites exchange beliefs, never data, and every exchange is on a receipt.</p>
    <p class="meta">Matthew Shi and team · MIT Media Lab · Nov 1, 2026</p>
  </div>
  <figure class="fig">{plate_svg()}</figure>
</div>""",
      "Open on the plate: this is the real seed plate both printers print first. Pins and holes, 1.1 to 7.3 mm.")

slide("The problem", "Every site re-learns its own printer",
      """<div class="cols3">
  <div class="cell"><span class="big">0.05–0.15<small> mm</small></span><p>A resin slip fit. The printer's own bias is often larger than the whole band.</p></div>
  <div class="cell"><span class="big">Dozens<small> of plates</small></span><p>Characterizing one machine for one material takes many prints, and it's repeated at every site.</p></div>
  <div class="cell"><span class="big">No pooling</span><p>Measurements reveal process know-how and customer parts. Sites won't hand over raw data.</p></div>
</div>
<p class="foot">Much of what a printer gets wrong is shared across machines and even processes: small features shrink, error grows toward plate edges. That part is learnable together.</p>""",
      "The ask: can sites get most of the benefit of pooling without pooling?")

slide("The setup", "Two sites, one boundary",
      """<div class="boundary">
  <div class="site"><h3>Resin site · SLA</h3><ul><li>Scans and calipers</li><li>Every measurement</li><li>Resin parameters: penetration depth, critical energy, bleed, shrink</li></ul></div>
  <div class="wall"><span>schema-checked boundary</span>
    <ul class="cross"><li>Posterior mean and covariance of 3 shared parameters</li><li>Agent credibility</li><li>Unmet-needs questions with a z-score</li></ul>
  </div>
  <div class="site"><h3>PLA site · FDM</h3><ul><li>Scans and calipers</li><li>Every measurement</li><li>PLA parameters: extrusion offset, polygon shrink, flare</li></ul></div>
</div>
<p class="foot">Three arms print side by side on every plate: <b class="a-iso">isolated</b> (own data), <b class="a-net">networked</b> (own data plus messages), <b class="a-ora">oracle</b> (all raw data pooled, the upper bound).</p>""",
      "Shared parameters: size dependence and the plate-position gradient. Anything else is rejected at the boundary and logged.")

slide("How the collective decides", "Agents bid for plate slots",
      """<ol class="flow">
  <li><b>Propose.</b> Five agents rank pieces by what they'd learn: physics, calibration, geometry, empirical residuals, printability.</li>
  <li><b>Auction.</b> Slots split in proportion to credibility, largest remainder. The rule allocates space and never picks content.</li>
  <li><b>Print and measure.</b> Each plate carries 8 held-out pieces at fixed slots, escrowed from every model.</li>
  <li><b>Credit.</b> An agent's credibility moves with how much its pieces improved held-out prediction (leave-one-agent-out, in nats).</li>
  <li><b>Exchange.</b> Sites send belief summaries. Trust in each sender moves the same way, so a bad source fades out.</li>
</ol>
<p class="foot">What does the work, in simulation: the exchange. With messages cut, the same agents with learned credibility do no better than at equal credibility (2.4%, 56 of 100 worlds), and a planted saboteur agent does almost no harm and isn't caught: which pieces print barely matters here. <span class="flag">Simulation only.</span></p>""",
      "Be upfront: the auction is how slots get shared fairly, not where the gain comes from. The gain is in step 5.")

slide("Sim-to-real", "We wrote the prediction down first",
      """<div class="timeline">
  <div><span class="t">Fri night</span><p>Simulator with hidden truth and unmodeled effects. Config tuned there, then frozen.</p></div>
  <div><span class="t">Before printing</span><p>Pre-registration committed with its sha256: claims, metric, fit classes, failure rules, fallback tiers.</p></div>
  <div><span class="t">After seed plates</span><p>Simulator calibrated to the real seed data. Predicted range for isolated − networked committed before round 1.</p></div>
  <div><span class="t">Rounds 1–3</span><p>Real printers. Does the measured value land in the committed range?</p></div>
</div>
<p class="foot mono">prereg sha256 recorded on both receipt chains before every set of rounds</p>""",
      "Measurement noise (~35 µm MAE) hides a few-µm effect on 8 held-out pieces, so the real claim is sim-to-real, not detection on real data alone.")

slide("Result · simulation", "Networked matches the oracle",
      f"""<figure class="chart"><img src="data:image/png;base64,{CHART}" alt="Held-out error falls with pieces printed; networked tracks the oracle below isolated in every round."></figure>
<table class="nums"><thead><tr><th>Round</th><th class="a-iso">Isolated</th><th class="a-net">Networked</th><th class="a-ora">Oracle</th></tr></thead>
<tbody><tr><td>1</td><td>16.6</td><td>14.9</td><td>14.9</td></tr><tr><td>2</td><td>15.3</td><td>12.6</td><td>13.1</td></tr><tr><td>3</td><td>14.0</td><td>12.1</td><td>13.0</td></tr></tbody></table>
<p class="foot">Noise-free held-out MAE, µm, 20 seeds × 2 sites. Over 100 worlds, by round 3: networked 1.6 µm (12%) below isolated, better in 75 of 100, at or below the oracle. To scale: scanner noise ~31 µm, resin slip-fit band 100 µm, so on measured diameters the gain is 1.5%. <span class="flag">Frozen config, simulation only.</span> Real rounds and the committed range go here.</p>""",
      "Say the size out loud: real, matches pooling, and far too small to change whether a part fits or to detect in three real rounds. Swap in the real-round markers and the committed prediction box on Sunday (eval.figures.headline --real). Source: hpc/sweeps/relevance/README.md.")

slide("Robustness · simulation", "A lying site loses the room in one round",
      """<div class="cols2">
  <div class="cell"><span class="big">82<small> µm</small></span><p>Networked error at the honest site in round 1 when the PLA site broadcasts confident, wrong beliefs (isolated: 15 µm).</p></div>
  <div class="cell"><span class="big">12.7<small> µm</small></span><p>Round 3: the bad sender's trust has collapsed and the honest site is back level with isolated (11.8 µm, within noise).</p></div>
</div>
<p class="foot">10 seeds. Trust starts at 1.0, so the first round is the price of trusting by default; starting at 0.3 only trims it (39 → 30 µm), but a prototype consistency check that sets aside notes contradicting a site's own data caught 300 of 300 lying notes, dropped 0 of 900 honest ones, and removed the damage. Scaling, 60 worlds each, round 3: more sites alone (2.3 µm) or less data alone (2.7 µm, not significant) help little; four sites that each have little data reach 6.9 µm (27%, 51 of 60), visible through scanner noise. <span class="flag">Simulation only.</span></p>""",
      "Many sites that each know little is where sharing pays; that's the honest case for a bigger network. Source: hpc/sweeps/relevance/README.md section 2; replace with the teammate's 2–25-site sweep if it lands.")

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
  <div class="stack"><p>Each site keeps a hash chain of plates, measurements, bids, credit and messages. The receipt above is a real one from a simulated run. The audit replays both chains and checks that every boundary crossing matches the schema and that nothing else left.</p><p class="big-ok">PASS<small> in every run</small></p></div>
</div>""",
      "Live demo: python -m eval.audit on the real chains, then the viewer page.")

slide("What reality taught the simulator", "Residuals from the real plates",
      """<div class="placeholder"><p>Filled after the real rounds: which calibrated parameters moved, which unmodeled effects showed up, and what the hypothesis agent proposed from the residuals.</p></div>""",
      "Sat night: recalibrate with all real data (teammate) plus hypothesis agent output.")

slide("Next", "Print anywhere, trust the part",
      f"""<div class="split">
  <div class="stack"><p class="lede">Any shop that can print a flat plate can join and keep its data. It's worth most when many sites each know little.</p>
  <p>This weekend's problem is the smallest version: two printers, pins and holes, a few-micron gain. The method matters where tests are expensive, sites can't pool data and results must be auditable: many-machine networks and complex products such as bioprinting.</p>
  <p>Released for reuse: the process-agnostic test plate and generator, the flatbed scanner tool, and the hidden-truth multi-site simulator.</p>
  <p class="meta mono">github.com/matte-realize/prebuilt</p></div>
  <figure class="fig small">{plate_svg(label=False)}</figure>
</div>""",
      "Close on the plate again. Direction, not a result: see docs/build/10-beyond-the-weekend.md.")


def render() -> str:
    sections = []
    for i, (kicker, title, body, note) in enumerate(SLIDES, 1):
        sections.append(f"""<section class="slide" id="s{i}" aria-label="Slide {i}: {title}">
  <header><span class="kick">{kicker}</span><span class="num">{i:02d} / {len(SLIDES):02d}</span></header>
  <h2>{title}</h2>
  <div class="body">{body}</div>
  <aside class="note">{note}</aside>
</section>""")
    return TEMPLATE.replace("%%SLIDES%%", "\n".join(sections))


TEMPLATE = (HERE / "deck_template.html").read_text()
out = ROOT / "docs/slides/prebuilt-deck.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(render())
print(out, out.stat().st_size)
