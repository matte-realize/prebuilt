"""Generate docs/slides/prebuilt-pitch.html: the 3-minute pitch, six slides, demo built in.

    python docs/slides/make_pitch.py

Shares deck_template.html's styles with the full deck (make_deck.py). Slide 3 is the demo:
an animation driven by real simulation numbers (demo/tier-d, frozen config), so the pitch
never leaves the deck. Numbers on slide 4 come from hpc/sweeps/relevance/README.md (100
worlds, frozen config). Script and Q&A: docs/slides/pitch-notes.md.
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
        "liar": curves(ROOT / "demo/tier-d/bad-site.json", site="resin")}
SEED = json.loads((ROOT / "plates/out/resin/resin-seed.json").read_text())


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
    <p class="lede">A 3D printer is only useful once you know how it misses: holes come out small, pins come out fat, edges drift.</p>
    <p>Every site learns that from scratch, one test print at a time. Sites can't pool the data, because measurements expose process know-how and customer parts.</p>
    <p class="big-q">Can printers learn from each other without sharing a single measurement?</p>
  </div>
  <figure class="fig">{plate_svg()}<figcaption>The test plate: pins and holes, 1–7 mm, read by an ordinary flatbed scanner.</figcaption></figure>
</div>""",
     "Hold up a printed plate if you have one. One sentence on why pooling is off the table."),

    ("0:25–0:50 · What we built", "Two sites, one boundary, only beliefs cross",
     """<div class="boundary">
  <div class="site"><h3>Resin printer · SLA</h3><ul><li>Prints test plates, scans them</li><li>Agents choose which pieces to print next</li><li>Every measurement stays here</li></ul></div>
  <div class="wall"><span>what crosses</span>
    <ul class="cross"><li>Mean and uncertainty of 3 process-agnostic parameters</li><li>Nothing else: checked against a schema and hash-chained on a receipt</li></ul>
  </div>
  <div class="site"><h3>PLA printer · FDM</h3><ul><li>Different machine, different physics</li><li>Same test plate, same agents</li><li>Every measurement stays here</li></ul></div>
</div>
<p class="foot">Each site fits a physics model of its own printer. Some error terms are shared across machines and even processes (small features shrink, edges drift), and that part is learned together. A third arm pools all raw data as the upper bound.</p>""",
     "Point at the middle column: that's the whole interface. Three numbers and their uncertainty."),

    ("0:50–1:40 · Demo", "Watch the network learn",
     """<div class="demo" id="demo">
  <svg class="sites" viewBox="0 0 420 230" aria-label="Two sites exchanging belief summaries across a boundary">
    <line x1="210" y1="14" x2="210" y2="216" class="wall-line"/>
    <text x="210" y="226" class="tiny" text-anchor="middle">boundary</text>
    <g id="siteA"><rect x="14" y="60" width="150" height="104" rx="6" class="box"/>
      <text x="89" y="88" text-anchor="middle" class="lbl">Resin</text>
      <text x="89" y="110" text-anchor="middle" class="tiny" id="platesA">seed plate</text>
      <text x="89" y="146" text-anchor="middle" class="tiny">raw data stays</text></g>
    <g id="siteB"><rect x="256" y="60" width="150" height="104" rx="6" class="box"/>
      <text x="331" y="88" text-anchor="middle" class="lbl" id="nameB">PLA</text>
      <text x="331" y="110" text-anchor="middle" class="tiny" id="platesB">seed plate</text>
      <text x="331" y="146" text-anchor="middle" class="tiny">raw data stays</text></g>
    <g id="pktAB" class="pkt"><rect x="-34" y="-11" width="68" height="22" rx="11"/><text y="4" text-anchor="middle">μ, σ ×3</text></g>
    <g id="pktBA" class="pkt"><rect x="-34" y="-11" width="68" height="22" rx="11"/><text y="4" text-anchor="middle">μ, σ ×3</text></g>
    <g id="trustG"><text x="210" y="40" text-anchor="middle" class="tiny">resin's trust in PLA</text>
      <rect x="150" y="46" width="120" height="8" rx="4" class="track"/><rect x="150" y="46" width="120" height="8" rx="4" class="trust" id="trustBar"/>
      <text x="278" y="54" class="tiny" id="trustTxt">1.00</text></g>
  </svg>
  <svg class="chart" id="chart" viewBox="0 0 420 230" aria-label="Held-out error by round for isolated, networked and oracle"></svg>
  <div class="ctl">
    <button type="button" id="play">▶ Play 3 rounds</button>
    <button type="button" id="liar" aria-pressed="false">Make PLA lie</button>
    <span class="tiny" id="cap">Simulation, frozen config. Noise-free held-out error at the resin and PLA sites, µm.</span>
  </div>
</div>""",
     "Press Play: each round both sites print, then only the summaries cross; networked (orange) drops below isolated (blue) and lands on the oracle (green). Then press 'Make PLA lie': resin's error spikes in round 1, trust collapses to 0.01, and by round 3 it's back level with isolated. A liar costs one round."),

    ("1:40–2:15 · Results", "As good as pooling the data, without pooling it",
     """<div class="cols3">
  <div class="cell"><span class="big">12%</span><p>lower model error than learning alone by round 3, in 75 of 100 simulated worlds. Pooling all raw data does no better (12%).</p></div>
  <div class="cell"><span class="big">25%</span><p>when four sites each have little data: many sites that each know little is where sharing pays most.</p></div>
  <div class="cell"><span class="big">0.01</span><p>trust left in a lying site after one round. The receipt audit passes in every run: nothing but the schema ever crossed.</p></div>
</div>
<p class="foot">Simulation with hidden truth, frozen config, paired per world (hpc/sweeps/relevance). The gain comes from the shared beliefs, not the agent auction. In absolute terms it's 1.6 µm at two sites, small next to scanner noise, which is why the real-printer claim is a committed prediction (next).</p>""",
     "Say the honest size once: at two sites it's a couple of microns; the case for this grows with the number of sites."),

    ("2:15–2:40 · Science, not a demo", "We wrote the prediction down before printing",
     """<div class="timeline">
  <div><span class="t">Simulation</span><p>Hidden-truth printers. Config tuned, then frozen.</p></div>
  <div><span class="t">Pre-registered</span><p>Claims, metric, fit classes, failure rules and fallbacks, hashed onto both receipt chains.</p></div>
  <div><span class="t">Seed plates</span><p>Simulator calibrated to the real printers. Predicted range committed before round 1.</p></div>
  <div><span class="t">Real rounds</span><p>Does the real resin + PLA network land inside the prediction?</p></div>
</div>
<p class="foot">Every plate, measurement, bid and message is on a hash chain. Anyone can replay it and check that no raw data left a site.</p>""",
     "If real rounds are in, put the real point on screen here instead of the timeline."),

    ("2:40–3:00 · Next", "Print anywhere, trust the part",
     f"""<div class="split">
  <div class="stack"><p class="lede">Any shop that can print a flat plate can join, learn faster, and keep its data.</p>
  <p>Released today: the process-agnostic test plate, the flatbed scanner tool, and the hidden-truth multi-site printer simulator.</p>
  <p class="meta mono">github.com/matte-realize/prebuilt</p></div>
  <figure class="fig small">{plate_svg()}</figure>
</div>""",
     "End on the line. Stop talking."),
]

EXTRA_CSS = """
.big-q { font: 600 2.2cqw/1.25 var(--display); color: var(--amber); max-width: 40ch; }
.fig figcaption { font: 1.15cqw var(--mono); color: var(--muted); margin-top: .8cqw; text-align: center; }
.demo { display: grid; grid-template-columns: 1fr 1fr; gap: 2cqw; align-items: start; }
.demo svg { width: 100%; height: auto; display: block; }
.demo .ctl { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 1cqw; align-items: center; }
.demo button { font: 600 1.4cqw var(--body); color: var(--ink); background: var(--sheet); border: 1px solid var(--line);
  border-radius: 6px; padding: .7cqw 1.4cqw; cursor: pointer; }
.demo button[aria-pressed="true"] { border-color: var(--amber); color: var(--amber); }
.demo .tiny { font: 11px var(--mono); fill: var(--muted); color: var(--muted); }
.demo .ctl .tiny { font-size: 1.2cqw; }
.demo .lbl { font: 600 17px var(--display); fill: var(--ink); }
.demo .box { fill: var(--bg); stroke: var(--line); }
.demo .wall-line { stroke: var(--amber); stroke-width: 3; stroke-dasharray: 6 5; }
.demo .pkt rect { fill: var(--net); } .demo .pkt text { font: 600 11px var(--mono); fill: #fff; }
.demo .pkt { opacity: 0; } .demo .pkt.bad rect { fill: #c2342b; }
.demo .track { fill: var(--line); } .demo .trust { fill: var(--ora); transition: width .6s ease; }
.demo .trust.low { fill: #c2342b; }
.demo .axis { stroke: var(--line); } .demo .grid { stroke: var(--line); stroke-dasharray: 2 4; }
.demo .ln { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.demo .ln.oracle { stroke-dasharray: 7 5; }
.demo .tick { font: 11px var(--mono); fill: var(--muted); }
.demo .end { font: 600 12px var(--body); }
@media (max-width: 720px) { .demo { grid-template-columns: 1fr; } .demo button, .demo .ctl .tiny { font-size: 14px; } .big-q { font-size: 18px; } .fig figcaption { font-size: 11px; } }
"""

DEMO_JS = """
<script>
(() => {
  const DATA = %%DATA%%;
  const COL = { isolated: 'var(--iso)', networked: 'var(--net)', oracle: 'var(--ora)' };
  const chart = document.getElementById('chart'), NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs, text) => { const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; };
  let mode = 'honest', shown = 3, timer = null;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function draw() {
    const d = DATA[mode], X0 = 46, X1 = 330, Y0 = 200, Y1 = 22;
    const vals = Object.values(d).flat(), hi = mode === 'liar' ? 90 : 18, lo = mode === 'liar' ? 0 : 10;
    const x = i => X0 + (X1 - X0) * i / 2, y = v => Y0 - (Y0 - Y1) * (Math.min(v, hi) - lo) / (hi - lo);
    chart.replaceChildren();
    const step = mode === 'liar' ? 20 : 2;
    for (let v = lo; v <= hi; v += step) {
      chart.append(el('line', { x1: X0, x2: X1, y1: y(v), y2: y(v), class: 'grid' }));
      chart.append(el('text', { x: X0 - 8, y: y(v) + 4, 'text-anchor': 'end', class: 'tick' }, v));
    }
    [1, 2, 3].forEach((r, i) => chart.append(el('text', { x: x(i), y: Y0 + 18, 'text-anchor': 'middle', class: 'tick' }, 'round ' + r)));
    chart.append(el('text', { x: X0 - 36, y: 14, class: 'tick' }, mode === 'liar' ? 'µm, resin site' : 'µm, both sites'));
    const ends = [];
    for (const arm of ['isolated', 'oracle', 'networked']) {
      const pts = d[arm].slice(0, shown).map((v, i) => `${x(i)},${y(v)}`).join(' ');
      if (shown > 1) chart.append(el('polyline', { points: pts, class: 'ln ' + arm, stroke: COL[arm] }));
      d[arm].slice(0, shown).forEach((v, i) => chart.append(el('circle', { cx: x(i), cy: y(v), r: 5, fill: COL[arm], stroke: 'var(--sheet)', 'stroke-width': 2 })));
      if (shown) ends.push([arm, y(d[arm][shown - 1]), d[arm][shown - 1]]);
    }
    ends.sort((a, b) => a[1] - b[1]);
    let last = -1e9;
    for (const [arm, yy, v] of ends) {           // direct labels, pushed apart so they never overlap
      const yl = Math.max(yy, last + 15); last = yl;
      chart.append(el('text', { x: x(shown - 1) + 12, y: yl + 4, class: 'end', fill: 'var(--ink)' }, `${arm} ${v}`));
    }
    const t = mode === 'liar' && shown >= 1 ? (shown >= 2 ? 0.01 : 1.0) : 1.0;
    const bar = document.getElementById('trustBar');
    bar.setAttribute('width', 120 * t); bar.classList.toggle('low', t < 0.5);
    document.getElementById('trustTxt').textContent = t.toFixed(2);
    document.getElementById('trustG').style.opacity = mode === 'liar' ? 1 : 0.35;
    document.getElementById('nameB').textContent = mode === 'liar' ? 'PLA (lying)' : 'PLA';
    const label = shown ? `round ${shown} printed` : 'seed plate';
    document.getElementById('platesA').textContent = label;
    document.getElementById('platesB').textContent = label;
  }
  function packets(onDone) {
    const a = document.getElementById('pktAB'), b = document.getElementById('pktBA');
    b.classList.toggle('bad', mode === 'liar');
    if (reduce) return onDone();
    const t0 = performance.now(), dur = 900;
    (function frame(now) {
      const k = Math.min(1, (now - t0) / dur);
      a.setAttribute('transform', `translate(${100 + 220 * k},96)`); a.style.opacity = k < 1 ? 1 : 0;
      b.setAttribute('transform', `translate(${320 - 220 * k},128)`); b.style.opacity = k < 1 ? 1 : 0;
      k < 1 ? requestAnimationFrame(frame) : onDone();
    })(t0);
  }
  function play() {
    clearTimeout(timer); shown = 0; draw();
    const next = () => { if (shown >= 3) return; packets(() => { shown += 1; draw(); timer = setTimeout(next, 700); }); };
    timer = setTimeout(next, 400);
  }
  document.getElementById('play').addEventListener('click', play);
  document.getElementById('liar').addEventListener('click', e => {
    mode = mode === 'liar' ? 'honest' : 'liar';
    e.currentTarget.setAttribute('aria-pressed', String(mode === 'liar'));
    e.currentTarget.textContent = mode === 'liar' ? 'Make PLA honest' : 'Make PLA lie';
    document.getElementById('cap').textContent = mode === 'liar'
      ? 'PLA broadcasts confident, wrong beliefs. Resin site only, 10 worlds, noise-free held-out error, µm.'
      : 'Simulation, frozen config. Noise-free held-out error at the resin and PLA sites, µm.';
    play();
  });
  draw();
  document.getElementById('demo').addEventListener('click', e => e.stopPropagation());  // don't advance slides
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
