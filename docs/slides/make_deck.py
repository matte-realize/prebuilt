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
    <p>A collective of scientist agents characterizes a resin printer and a PLA printer from printed test plates. Sites exchange beliefs, never data, and every exchange is on a receipt.</p>
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
</ol>""",
      "This is a sequence, so the numbers mean something. The whole cycle runs in seconds; printing takes hours.")

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
<tbody><tr><td>1</td><td>16.5</td><td>14.9</td><td>14.8</td></tr><tr><td>2</td><td>15.5</td><td>12.9</td><td>12.9</td></tr><tr><td>3</td><td>13.9</td><td>11.7</td><td>12.7</td></tr></tbody></table>
<p class="foot">Noise-free held-out MAE, µm, 20 seeds × 2 sites. <span class="flag">Frozen config, simulation only.</span> Real rounds and the committed range go here.</p>""",
      "Swap in the real-round markers and the committed prediction box on Sunday (eval.figures.headline --real).")

slide("Robustness · simulation", "A lying site loses the room in one round",
      """<div class="cols2">
  <div class="cell"><span class="big">46<small> µm</small></span><p>Networked error in round 1 when the PLA site broadcasts confident, wrong beliefs (isolated: 16 µm).</p></div>
  <div class="cell"><span class="big">13.9<small> µm</small></span><p>Round 2: the bad sender's trust has collapsed and networked is back below isolated (15.6 µm).</p></div>
</div>
<p class="foot">10 seeds. Trust starts at 1.0, so the first round is the price of trusting by default; the frozen config sets where trust starts. <span class="flag">Scaling sweep (2–25 sites) goes here.</span></p>""",
      "Placeholder for the teammate's robustness and scaling figures.")

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
  <div class="stack"><p class="lede">Any shop that can print a flat plate can join, learn faster, and keep its data.</p>
  <p>Released for reuse: the process-agnostic test plate and generator, the flatbed scanner tool, and the hidden-truth multi-site simulator.</p>
  <p class="meta mono">github.com/matte-realize/prebuilt</p></div>
  <figure class="fig small">{plate_svg(label=False)}</figure>
</div>""",
      "Close on the plate again.")


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
