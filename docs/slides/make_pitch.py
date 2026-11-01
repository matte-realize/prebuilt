"""Generate docs/slides/prebuilt-pitch.html: the 3-minute pitch, six slides, demo built in.

    python docs/slides/make_pitch.py

Shares deck_template.html's styles with the full deck (make_deck.py). Slide 3 is the demo:
an animation driven by real simulation numbers (demo/tier-d, frozen config), so the pitch
never leaves the deck. Numbers on slide 4 come from hpc/sweeps/relevance/README.md (100
worlds, frozen config); the consistency-check cell and the slide-6 chart read viewer/evidence.json
(hpc/sweeps/relevance/evidence.py). Script and Q&A: docs/slides/pitch-notes.md.
"""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def curves(path: Path, site: str | None = None) -> dict:
    """arm -> [round 1, 2, 3] mean noise-free held-out MAE in µm."""
    acc = defaultdict(list)
    for r in json.loads(path.read_text()):
        if site is None or r["site"] == site:
            acc[(r["arm"], r["round"])].append(r["mae_truth"])
    return {arm: [round(1000 * sum(acc[(arm, k)]) / len(acc[(arm, k)]), 1) for k in (1, 2, 3)]
            for arm in ("isolated", "networked", "oracle")}


DATA = {"honest": curves(ROOT / "demo/tier-d/sim.json"),
        "liar": curves(ROOT / "demo/tier-d/bad-site.json", site="resin"),
        "check": curves(ROOT / "demo/tier-d/bad-site-check.json", site="resin")}   # run.py --consistency-check
SEED = json.loads((ROOT / "plates/out/resin/resin-seed.json").read_text())
EV = json.loads((ROOT / "viewer/evidence.json").read_text())  # hpc/sweeps/relevance/evidence.py
SITES_NEEDED = EV["sites_needed"]   # coldstart grid: warm-up 4, 2 pieces/round, round 3
CHECK = EV["consistency_check"]     # protocol sweep: Config.consistency_check, off in the frozen config


def sites_svg() -> str:
    """Bars: gain over learning alone at 2 / 4 / 8 data-poor sites (simulation)."""
    rows = SITES_NEEDED["rows"]
    W, H, X0, Y0, Y1 = 360, 230, 20, 186, 34
    top = max(40, -(-max(r["pct"] for r in rows) // 10) * 10)
    bw, gap = 74, (W - 2 * X0 - 3 * 74) / 2
    y = lambda v: Y0 - (Y0 - Y1) * v / top
    parts = [f'<svg viewBox="0 0 {W} {H}" class="sites-chart" role="img" aria-label="Lower error than learning alone: '
             + ", ".join(f'{r["sites"]} sites {round(r["pct"])}%' for r in rows) + '">',
             f'<line x1="{X0}" x2="{W - X0}" y1="{Y0}" y2="{Y0}" class="axis"/>']
    for i, r in enumerate(rows):
        x = X0 + i * (bw + gap)
        parts.append(f'<rect x="{x:.1f}" y="{y(r["pct"]):.1f}" width="{bw}" height="{Y0 - y(r["pct"]):.1f}" rx="3" class="bar"/>'
                     f'<text x="{x + bw / 2:.1f}" y="{y(r["pct"]) - 10:.1f}" text-anchor="middle" class="val">{round(r["pct"])}%</text>'
                     f'<text x="{x + bw / 2:.1f}" y="{Y0 + 20}" text-anchor="middle" class="lab">{r["sites"]} sites</text>'
                     f'<text x="{x + bw / 2:.1f}" y="{Y0 + 37}" text-anchor="middle" class="sub">{r["wins"]}/{r["n"]} worlds</text>')
    return "".join(parts) + "</svg>"


def plate_svg() -> str:
    parts = ['<svg viewBox="-6 -6 112 112" class="plate" role="img" aria-label="The seed test plate: pins and holes, 1 to 7 mm">',
             '<rect x="0" y="0" width="100" height="100" rx="1.2" class="pl"/>',
             '<rect x="47" y="97.5" width="6" height="2.6" class="cut"/>']
    for fx, fy in ((5, 95), (95, 95), (5, 5)):
        parts.append(f'<rect x="{fx - 2}" y="{100 - fy - 2}" width="4" height="4" class="cut"/>')
    for p in SEED["pieces"]:
        (r, c), d = p["slot"], p["nominal_d"]
        cls = ("pin" if p["kind"] == "pin" else "hole") + (" ho" if p["arm"] == "heldout" else "")
        parts.append(f'<circle cx="{15 + 10 * c}" cy="{15 + 10 * r}" r="{d / 2}" class="{cls}"/>')
    return "".join(parts) + "</svg>"


SLIDES = [
    ("0:00–0:25 · The problem", "Every shop re-learns its own printer",
     f"""<div class="split">
  <div class="stack">
    <p class="lede">No printed part matches its file. Holes come out small, pins come out fat, by tens to hundreds of microns, and that decides whether parts fit.</p>
    <p>The error belongs to your machine today: its resin, settings and wear. No datasheet knows it; you learn it by printing. Every site does that from scratch, and can't pool the data, because measurements expose process know-how and customer parts.</p>
    <p class="big-q">Can printers learn from each other without sharing a single measurement?</p>
  </div>
  <figure class="fig">{plate_svg()}<figcaption>The test plate: pins and holes, 1–7 mm. Print it, measure it, and you know your printer.</figcaption></figure>
</div>""",
     "Hold up a printed plate. The point: precision is a property of your machine, and the only way to learn it is to print."),

    ("0:25–0:45 · What we built", "Two printer sites, one boundary, only beliefs cross",
     """<div class="arch">
  <div class="node"><span class="proc">SLA · simulated</span><h3>Resin site</h3><p>prints, measures, learns its own model</p></div>
  <div class="link"><span class="msg">μ, σ of 3 shared parameters</span><span class="arrow" aria-hidden="true">⇄</span><span class="wall-tag">schema-checked · on a receipt</span></div>
  <div class="node"><span class="proc">FDM · simulated</span><h3>PLA site</h3><p>different machine, different physics</p></div>
</div>
<div class="stays"><b>Stays home:</b> every measurement, every machine-specific parameter.</div>""",
     "Point at the middle: that's the whole interface. Errors that every printer shares (small features shrink, edges drift) are learned together; everything else stays local. Both sites are simulated printers whose true behavior we know, which is how every result is scored."),

    ("0:45–1:30 · Demo", "Watch the network learn",
     """<div class="demo" id="demo">
  <svg class="sites" viewBox="0 0 440 300" aria-label="Two sites exchanging belief summaries across a boundary">
    <g id="trustG"><text x="220" y="22" text-anchor="middle" class="tiny">resin's trust in PLA</text>
      <rect x="150" y="32" width="140" height="10" rx="5" class="track"/><rect x="150" y="32" width="140" height="10" rx="5" class="trust" id="trustBar"/>
      <text x="298" y="42" class="tiny" id="trustTxt">1.00</text></g>
    <line x1="220" y1="60" x2="220" y2="246" class="wall-line"/>
    <text x="220" y="262" class="tiny" text-anchor="middle">site boundary</text>
    <rect x="12" y="74" width="168" height="150" rx="8" class="box"/>
    <text x="96" y="104" text-anchor="middle" class="lbl">Resin</text>
    <text x="96" y="134" text-anchor="middle" class="count" id="measA">24</text>
    <text x="96" y="154" text-anchor="middle" class="tiny">measurements here</text>
    <text x="96" y="204" text-anchor="middle" class="tiny" id="platesA">seed plate</text>
    <rect x="260" y="74" width="168" height="150" rx="8" class="box"/>
    <text x="344" y="104" text-anchor="middle" class="lbl" id="nameB">PLA</text>
    <text x="344" y="134" text-anchor="middle" class="count" id="measB">24</text>
    <text x="344" y="154" text-anchor="middle" class="tiny">measurements here</text>
    <text x="344" y="204" text-anchor="middle" class="tiny" id="platesB">seed plate</text>
    <g id="pktAB" class="pkt"><rect x="-44" y="-14" width="88" height="28" rx="14"/><text y="5" text-anchor="middle">μ, σ ×3</text></g>
    <g id="pktBA" class="pkt"><rect x="-44" y="-14" width="88" height="28" rx="14"/><text y="5" text-anchor="middle">μ, σ ×3</text></g>
    <text x="220" y="292" text-anchor="middle" class="crossed" id="crossed">crossed: 0 measurements · 0 numbers</text>
  </svg>
  <svg class="chart" id="chart" viewBox="0 0 480 300" aria-label="Held-out error by round for isolated, networked and oracle"></svg>
  <p class="say" id="say">Two sites, each starting from one seed plate. Press Play.</p>
  <div class="ctl">
    <button type="button" id="play">▶ Play (P)</button>
    <button type="button" id="liar" aria-pressed="false">Make PLA lie (L)</button>
    <button type="button" id="check" aria-pressed="false" disabled>Check notes (C)</button>
    <span class="tiny" id="cap">Simulation with hidden truth, frozen config, 20 worlds. Model error on held-out pieces, µm.</span>
  </div>
</div>""",
     "In Present mode it plays by itself. Narrate the caption line. Then L: resin's error spikes in round 1, trust collapses to 0.01 once held-out pieces expose the lie, and by round 3 resin is back level with learning alone. Without a check, a liar costs one round. Then C: the consistency check sets PLA's note aside at the boundary, no spike. With the check, none (slide 4)."),

    ("1:30–2:00 · Results, in simulation", "The win is many sites, not many agents",
     f"""<div class="cols3 hero">
  <div class="cell"><span class="big">12%</span><p>lower error than learning alone, in 75 of 100 worlds. Pooling all the raw data: also 12%.</p></div>
  <div class="cell"><span class="big">35%</span><p>with eight sites that each know little, better in 20 of 20 worlds. Many data-poor sites is where sharing pays.</p></div>
  <div class="cell"><span class="big">0 rounds</span><p>for a liar: a consistency check catches its notes on arrival ({CHECK["liar_caught"]} of {CHECK["liar_notes"]}, {CHECK["honest_dropped"]} honest notes dropped). Without it, a liar costs one round.</p></div>
</div>
<p class="foot">Simulation with hidden truth, frozen config, paired per world. The consistency check is an added protocol option, off in the registered config, tested in {CHECK["worlds"]} worlds. The agent layer adds nothing measurable: with messages cut, learned credibility ties equal votes. At two sites the gain is 1.6 µm, below what you can measure on a real part, so we don't claim it there.</p>""",
     "Say it plainly: these are simulation numbers, the gain comes from sharing between sites, not from the agents, and at two sites it is a couple of microns. It grows with the number of data-poor sites."),

    ("2:00–2:25 · Science, not a demo", "Grounded in a real printer, scored in simulation",
     """<div class="timeline">
  <div><span class="t">Real printer</span><p>Formlabs Form Studio 1: a 1.5 mm pin measured 1.41–1.48 mm by micrometer, 24–89 µm small.</p></div>
  <div><span class="t">Vendor spec</span><p>±0.08 mm on 1–30 mm features. Real error is tens of µm, as the spec says.</p></div>
  <div><span class="t">Simulator</span><p>Simulated resin pins miss by −0.1 to +0.27 mm. The real pin is inside, at the small edge: each printer must learn its own error.</p></div>
  <div><span class="t">Why not real</span><p>The sharing gain is 1.6 µm. Two readings of one pin differed by 65 µm. Only hidden truth can score it.</p></div>
</div>
<p class="foot">Registered before printing: two printers can't show the sharing gain on real parts. Negative control: when printers share no physics, sharing gains nothing, so the gain isn't built into the scoring. The simulator says when the gain becomes measurable: many sites, each with little data.</p>""",
     "Judge beat: this is the rigor slide. Hold up the printed plate. The real printer tells us the simulator is the right size (this pin sits at its small edge, 1.8th percentile, so say 'edge', not 'middle'); the simulator is the only place a 1.6 µm gain can be scored; the negative control shows the simulator doesn't hand us the result. Don't claim the model was fit on the real printer: one pin, two readings, isn't enough."),

    ("2:25–3:00 · Who it's for", "Fleets where fit decides and data can't leave",
     f"""<div class="split">
  <div class="who">
    <div class="who-h"><span>Who</span><span>Why they can't pool data</span></div>
    <div><b>Dental labs</b><span>Patient scans. Crowns, models and guides must seat on the first print.</span></div>
    <div><b>Print farms, service bureaus</b><span>Customer geometry is the customer's IP. Many machines, every job must fit.</span></div>
    <div><b>Distributed manufacturing</b><span>One part, many vendors. Each vendor's process is its edge.</span></div>
    <div class="next"><b>Next: microfluidics, bioprinting</b><span>Smaller features, costlier tests, stricter data rules. Direction, not a result.</span></div>
    <p class="get"><b>What they get:</b> parts that fit the first time (corrected designs: size error 132 → 9 µm), and sharing that stays safe when printers differ.</p>
  </div>
  <figure class="fig">{sites_svg()}<figcaption>Where it pays: lower error than learning alone, by number of data-poor sites. Round 3, simulation.</figcaption></figure>
</div>
<p class="close">Print anywhere, trust the part. <span class="meta mono">github.com/matte-realize/prebuilt · all numbers simulation</span></p>""",
     "Investor beat: name the buyer and why pooling is off the table for them, then the bars: value grows with the number of sites, which is a network effect. Mixed fleets answers 'what if printers differ': trust makes sharing safe, it doesn't yet identify bad partners. Bioprinting is direction. End on the line. Stop talking."),
]

EXTRA_CSS = """
/* Pitch: projected, so bigger type and content centred in the frame. */
.slide { grid-template-rows: auto auto 1fr; }
.slide h2 { font-size: 4.8cqw; }
.slide .body { font-size: 2.1cqw; align-content: center; }
.lede { font-size: 2.9cqw; }
.foot { font-size: 1.6cqw; }
.big-q { font: 600 2.6cqw/1.25 var(--display); color: var(--amber); max-width: 34ch; }
.fig figcaption { font: 1.3cqw var(--mono); color: var(--muted); margin-top: .8cqw; text-align: center; }
.plate { max-width: 34cqw; }
.timeline > div { font-size: 2cqw; } .t { font-size: 1.5cqw; }
.hero .big { font-size: 8cqw; } .hero .cell p { font-size: 2cqw; }
.sites-chart { width: 100%; max-width: 38cqw; height: auto; display: block; }
.sites-chart .bar { fill: var(--net); } .sites-chart .axis { stroke: var(--line); stroke-width: 1.5; }
.sites-chart .val { font: 700 26px var(--display); fill: var(--ink); }
.sites-chart .lab { font: 600 15px var(--body); fill: var(--ink); } .sites-chart .sub { font: 12px var(--mono); fill: var(--muted); }

.arch { display: grid; grid-template-columns: 1fr 1.25fr 1fr; gap: 2cqw; align-items: center; }
.node { border: 2px solid var(--ink); border-radius: 8px; padding: 2cqw; display: grid; gap: .6cqw; text-align: center; }
.node h3 { font: 700 3cqw var(--display); margin: 0; }
.node p { font-size: 1.8cqw; color: var(--muted); max-width: none; }
.proc { font: 600 1.4cqw var(--mono); letter-spacing: .1em; color: var(--muted); }
.link { display: grid; justify-items: center; gap: .8cqw; border-left: 3px dashed var(--amber); border-right: 3px dashed var(--amber); padding: 1.5cqw 1cqw; }
.msg { font: 600 1.9cqw var(--mono); background: var(--net); color: #fff; border-radius: 999px; padding: .7cqw 1.6cqw; text-align: center; }
.arrow { font-size: 5cqw; line-height: 1; color: var(--net); }
.wall-tag { font: 600 1.3cqw var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--amber); text-align: center; }
.stays { font-size: 2cqw; border-top: 1px dashed var(--line); padding-top: 1.2cqw; }

.slide:has(.demo) .body { grid-template-columns: 1fr; }   /* the template splits slides that hold a .chart */
.demo { display: grid; grid-template-columns: 1fr 1.1fr; gap: 1.2cqw 2cqw; align-items: center; }
.demo svg { width: 100%; height: auto; display: block; }
.demo .chart { background: none; padding: 0; }   /* the template's .chart is a light card for a PNG */
.demo .say { grid-column: 1 / -1; font: 600 2.2cqw/1.3 var(--display); margin: 0; min-height: 2.9cqw; max-width: none; }
.demo .ctl { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 1cqw; align-items: center; }
.demo button { font: 600 1.4cqw var(--body); color: var(--ink); background: var(--sheet); border: 1px solid var(--line);
  border-radius: 6px; padding: .6cqw 1.3cqw; cursor: pointer; }
.demo button[aria-pressed="true"] { border-color: var(--amber); color: var(--amber); }
.demo button:disabled { opacity: .4; cursor: not-allowed; }
.demo .tiny { font: 13px var(--mono); fill: var(--muted); color: var(--muted); }
.demo .ctl .tiny { font-size: 1.2cqw; }
.demo .lbl { font: 700 22px var(--display); fill: var(--ink); }
.demo .count { font: 700 30px var(--display); fill: var(--ink); font-variant-numeric: tabular-nums; }
.demo .crossed { font: 600 15px var(--mono); fill: var(--ora); }
.demo .box { fill: var(--bg); stroke: var(--line); stroke-width: 1.5; }
.demo .wall-line { stroke: var(--amber); stroke-width: 3; stroke-dasharray: 7 6; }
.demo .pkt rect { fill: var(--net); } .demo .pkt text { font: 600 14px var(--mono); fill: #fff; }
.demo .pkt { opacity: 0; } .demo .pkt.bad rect { fill: #c2342b; }
.demo .track { fill: var(--line); } .demo .trust { fill: var(--ora); transition: width .6s ease; }
.demo .trust.low { fill: #c2342b; }
.demo .grid { stroke: var(--line); stroke-dasharray: 2 4; }
.demo .ln { fill: none; stroke-width: 3.5; stroke-linecap: round; stroke-linejoin: round; }
.demo .ln.oracle { stroke-dasharray: 8 6; }
.demo .tick { font: 13px var(--mono); fill: var(--muted); }
.demo .end { font: 600 15px var(--body); }
.demo .spike { font: 700 15px var(--body); fill: var(--net); }
.who { display: grid; gap: 0; align-content: start; }
.who > div { display: grid; grid-template-columns: 1fr 1.5fr; gap: 1.6cqw; padding: 1cqw 0; border-top: 1px solid var(--line); }
.who > div b { font: 700 2cqw/1.2 var(--display); }
.who > div span { font-size: 1.7cqw; color: var(--muted); }
.who .who-h { border-top: 0; padding-top: 0; }
.who .who-h span { font: 600 1.2cqw var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.who .next b { color: var(--amber); }
.who .get { font-size: 1.8cqw; margin: 1.2cqw 0 0; border-top: 3px solid var(--net); padding-top: 1cqw; max-width: none; }
.close { font: 700 3cqw var(--display); margin: 0; display: flex; flex-wrap: wrap; gap: 2cqw; align-items: baseline; max-width: none; }
.close .meta { font-size: 1.3cqw; font-weight: 400; }
@media (max-width: 720px) {
  .slide h2 { font-size: 28px; } .slide .body { font-size: 15px; } .lede { font-size: 19px; } .foot { font-size: 13px; }
  .sites-chart { max-width: 100%; }
  .who > div { grid-template-columns: 1fr; gap: 4px; } .who > div b { font-size: 16px; } .who > div span, .who .get { font-size: 14px; }
  .who .who-h span { font-size: 11px; } .close { font-size: 20px; } .close .meta { font-size: 11px; }
  .arch, .demo { grid-template-columns: 1fr; } .node h3 { font-size: 20px; } .node p, .stays, .timeline > div { font-size: 14px; }
  .msg { font-size: 13px; padding: 6px 12px; } .arrow { font-size: 28px; } .wall-tag, .proc, .t { font-size: 11px; }
  .link { border-left: 0; border-right: 0; border-top: 3px dashed var(--amber); border-bottom: 3px dashed var(--amber); }
  .demo .say { font-size: 16px; } .demo button, .demo .ctl .tiny { font-size: 14px; }
  .hero .big { font-size: 40px; } .hero .cell p { font-size: 14px; } .big-q { font-size: 18px; } .fig figcaption { font-size: 11px; }
}
"""

DEMO_JS = """
<script>
(() => {
  const DATA = %%DATA%%;
  const COL = { isolated: 'var(--iso)', networked: 'var(--net)', oracle: 'var(--ora)' };
  const PER_ROUND = 26, SEED = 24, NUMBERS = 6;   // pieces per round plate, seed plate; numbers per message
  const chart = document.getElementById('chart'), NS = 'http://www.w3.org/2000/svg';
  const $ = id => document.getElementById(id);
  const el = (tag, attrs, text) => { const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; };
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let mode = 'honest', shown = 3, timer = null, run = 0;
  const SAY = {
    honest: ['Each round both sites print and measure a plate. Only belief summaries cross.',
      'Round 1: networked (orange) already beats learning alone (blue).',
      'Round 2: it matches pooling all the raw data (green), which never moved.',
      'Round 3: 12% lower error than alone, and still zero measurements crossed.'],
    liar: ['PLA now sends confident, wrong beliefs. Resin trusts it by default.',
      `Round 1: resin is misled, ${DATA.liar.networked[0].toFixed(0)} µm. Its held-out pieces expose the lie.`,
      'Round 2: trust in PLA drops from 1.00 to 0.01. Resin recovers.',
      'Round 3: back level with learning alone. A liar costs one round.'],
    check: ['PLA lies again. Now resin checks each note against its own plate first.',
      `Round 1: PLA's note contradicts resin's data, so it's set aside. No spike: ${DATA.check.networked[0].toFixed(1)} µm.`,
      'Round 2: set aside again. Every note is re-checked, every round.',
      'Round 3: the liar never got through. With the check, a liar costs zero rounds.'],
  };
  function draw() {
    const d = DATA[mode], X0 = 54, X1 = 330, Y0 = 254, Y1 = 30, bad = mode !== 'honest';
    const lo = 10, hi = mode === 'liar' ? 30 : 18, step = mode === 'liar' ? 5 : 2;
    const x = i => X0 + (X1 - X0) * i / 2, y = v => Y0 - (Y0 - Y1) * (Math.min(v, hi) - lo) / (hi - lo);
    chart.replaceChildren();
    for (let v = lo; v <= hi; v += step) {
      chart.append(el('line', { x1: X0, x2: X1, y1: y(v), y2: y(v), class: 'grid' }));
      chart.append(el('text', { x: X0 - 10, y: y(v) + 4, 'text-anchor': 'end', class: 'tick' }, v));
    }
    [1, 2, 3].forEach((r, i) => chart.append(el('text', { x: x(i), y: Y0 + 24, 'text-anchor': 'middle', class: 'tick' }, 'round ' + r)));
    chart.append(el('text', { x: X0 - 44, y: 16, class: 'tick' }, bad ? 'µm, resin site' : 'µm, both sites'));
    const ends = [];
    for (const arm of ['isolated', 'oracle', 'networked']) {
      const v = d[arm].slice(0, shown);
      if (v.length > 1) chart.append(el('polyline', { points: v.map((a, i) => `${x(i)},${y(a)}`).join(' '), class: 'ln ' + arm, stroke: COL[arm] }));
      v.forEach((a, i) => {
        chart.append(el('circle', { cx: x(i), cy: y(a), r: 6, fill: COL[arm], stroke: 'var(--sheet)', 'stroke-width': 2 }));
        if (a > hi) chart.append(el('text', { x: x(i) + 12, y: y(a) + 5, class: 'spike' }, `↑ ${Math.round(a)} µm`));
      });
      if (shown) ends.push([arm, y(v[v.length - 1]), v[v.length - 1]]);
    }
    ends.sort((a, b) => a[1] - b[1]);
    const ys = [];   // direct labels at the line ends: pushed apart, then lifted to stay above the axis
    for (const [, yy] of ends) ys.push(ys.length ? Math.max(yy, ys[ys.length - 1] + 19) : yy);
    const lift = Math.max(0, ys[ys.length - 1] - (Y0 - 4));
    ends.forEach(([arm, , v], i) => chart.append(el('text', { x: x(shown - 1) + 14, y: ys[i] - lift + 5,
      class: 'end', fill: 'var(--ink)' }, `${arm} ${v.toFixed(1)}`)));
    const t = mode === 'liar' && shown >= 2 ? 0.01 : 1.0;
    $('trustBar').setAttribute('width', 140 * t); $('trustBar').classList.toggle('low', t < 0.5);
    $('trustTxt').textContent = mode === 'check' && shown ? `${t.toFixed(2)} · note set aside` : t.toFixed(2);
    $('trustG').style.opacity = bad ? 1 : 0.3;
    $('nameB').textContent = bad ? 'PLA (lying)' : 'PLA';
    const label = shown ? `round ${shown} plate measured` : 'seed plate measured';
    $('platesA').textContent = $('platesB').textContent = label;
    $('measA').textContent = $('measB').textContent = SEED + PER_ROUND * shown;
    $('crossed').textContent = `crossed: 0 measurements · ${2 * NUMBERS * shown} numbers`;
    $('say').textContent = SAY[mode][shown];
  }
  function packets(onDone) {
    const a = $('pktAB'), b = $('pktBA');
    b.classList.toggle('bad', mode !== 'honest');
    const stop = mode === 'check' ? 0.5 : 1;   // with the check, PLA's note halts at the boundary
    if (reduce) return onDone();
    const t0 = performance.now(), dur = 1100;
    (function frame(now) {
      const k = Math.min(1, (now - t0) / dur), e = k < .5 ? 2 * k * k : 1 - 2 * (1 - k) * (1 - k);
      a.setAttribute('transform', `translate(${96 + 248 * e},178)`); a.style.opacity = k < 1 ? 1 : 0;
      b.setAttribute('transform', `translate(${344 - 248 * stop * e},120)`); b.style.opacity = k < 1 ? (stop < 1 ? 1 - 0.6 * k : 1) : 0;
      k < 1 ? requestAnimationFrame(frame) : onDone();
    })(t0);
  }
  function play() {
    const me = ++run; clearTimeout(timer); shown = 0; draw();
    const next = () => { if (me !== run || shown >= 3) return;
      packets(() => { if (me !== run) return; shown += 1; draw(); timer = setTimeout(next, 1600); }); };
    timer = setTimeout(next, 1200);
  }
  function toggleCheck() {
    if (mode === 'honest') return;
    mode = mode === 'check' ? 'liar' : 'check';
    $('check').setAttribute('aria-pressed', String(mode === 'check'));
    $('cap').textContent = mode === 'check'
      ? 'Consistency check on (an added option, off in the registered config). Resin site, 10 worlds, µm.'
      : 'PLA broadcasts confident, wrong beliefs. Resin site, 10 worlds, model error on held-out pieces, µm.';
    play();
  }
  function toggleLiar() {
    mode = mode === 'honest' ? 'liar' : 'honest';
    $('check').disabled = mode === 'honest'; $('check').setAttribute('aria-pressed', 'false');
    $('liar').setAttribute('aria-pressed', String(mode === 'liar'));
    $('liar').textContent = mode === 'liar' ? 'Make PLA honest (L)' : 'Make PLA lie (L)';
    $('cap').textContent = mode === 'liar'
      ? 'PLA broadcasts confident, wrong beliefs. Resin site, 10 worlds, model error on held-out pieces, µm.'
      : 'Simulation with hidden truth, frozen config, 20 worlds. Model error on held-out pieces, µm.';
    play();
  }
  $('play').addEventListener('click', play);
  $('liar').addEventListener('click', toggleLiar);
  $('check').addEventListener('click', toggleCheck);
  $('demo').addEventListener('click', e => e.stopPropagation());   // clicks here don't advance slides
  const s3 = $('demo').closest('.slide');
  const onScreen = () => !document.body.classList.contains('present') || s3.classList.contains('on');
  document.addEventListener('keydown', e => {
    if (!onScreen() || e.metaKey || e.ctrlKey) return;
    if (e.key === 'p' || e.key === 'P') play();
    if (e.key === 'l' || e.key === 'L') toggleLiar();
    if (e.key === 'c' || e.key === 'C') toggleCheck();
  });
  new MutationObserver(() => {   // Present mode: play when the demo slide comes up
    if (document.body.classList.contains('present') && s3.classList.contains('on')) play();
  }).observe(s3, { attributes: true, attributeFilter: ['class'] });
  draw();
})();
</script>
"""


def render() -> str:
    sections = []
    for i, (kicker, title, body, note) in enumerate(SLIDES, 1):
        sections.append(f"""<section class="slide" id="s{i}" aria-label="Slide {i}: {title}">
  <header><span class="kick">{kicker}</span><span class="num">{i} / {len(SLIDES)}</span></header>
  <h2>{title}</h2>
  <div class="body">{body}</div>
  <aside class="note">{note}</aside>
</section>""")
    html = (HERE / "deck_template.html").read_text()
    html = html.replace("<title>Prebuilt Deck</title>", "<title>Prebuilt Pitch</title>")
    html = html.replace("Prebuilt · draft deck · 10 slides", "Prebuilt · 3-minute pitch · 6 slides")
    html = html.replace("</style>", EXTRA_CSS + "</style>", 1)
    html = html.replace("%%SLIDES%%", "\n".join(sections))
    return html + DEMO_JS.replace("%%DATA%%", json.dumps(DATA))


out = HERE / "prebuilt-pitch.html"
out.write_text(render())
print(out, out.stat().st_size, DATA)
