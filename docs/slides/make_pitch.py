"""Generate docs/slides/prebuilt-pitch.html: the 3-minute pitch in a browser.

    python docs/slides/make_pitch.py

The same slides, story and numbers as the PowerPoint deck (make_pptx.js). Uses
deck_template.html for present mode and speaker notes, always in the dark theme. Every
figure is read from committed results: demo/tier-d/*.json (the three-round charts),
viewer/evidence.json (sites chart, consistency check) and plates/out/resin/resin-seed.json
(the plate); the rest is quoted from hpc/sweeps/relevance/README.md. Icons: icons.json
(react-icons Font Awesome, exported once).
"""
import json
import re
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


HONEST = curves(ROOT / "demo/tier-d/sim.json")
LIAR = curves(ROOT / "demo/tier-d/bad-site.json", site="resin")
CHECKED = curves(ROOT / "demo/tier-d/bad-site-check.json", site="resin")   # run.py --consistency-check
SEED = json.loads((ROOT / "plates/out/resin/resin-seed.json").read_text())
EV = json.loads((ROOT / "viewer/evidence.json").read_text())  # hpc/sweeps/relevance/evidence.py
SITES = EV["sites_needed"]["rows"]   # coldstart grid: warm-up 4, 2 pieces/round, round 3
CHECK = EV["consistency_check"]      # protocol sweep: Config.consistency_check, off in the frozen config
ICONS = json.loads((HERE / "icons.json").read_text())
LOGO_SVG = (ROOT / "assets/logo.svg").read_text()
LOGO_INNER = LOGO_SVG[LOGO_SVG.index(">") + 1:LOGO_SVG.rindex("</svg>")].strip()


def logo(cls: str = "logo") -> str:
    return f'<svg class="{cls}" viewBox="0 0 32 32" aria-hidden="true">{" ".join(LOGO_INNER.split())}</svg>'


def tile(name: str, tone: str = "") -> str:
    return f'<span class="tile {tone}">{ICONS[name]}</span>'


def plate_svg() -> str:
    parts = ['<svg viewBox="-6 -6 112 112" class="plate" role="img" aria-label="The test plate: pins and holes, 1 to 7 mm">',
             '<rect x="0" y="0" width="100" height="100" rx="1.2" class="pl"/>',
             '<rect x="47" y="97.5" width="6" height="2.6" class="cut"/>']
    for fx, fy in ((5, 95), (95, 95), (5, 5)):
        parts.append(f'<rect x="{fx - 2}" y="{100 - fy - 2}" width="4" height="4" class="cut"/>')
    for p in SEED["pieces"]:
        (r, c), d = p["slot"], p["nominal_d"]
        cls = ("pin" if p["kind"] == "pin" else "hole") + (" ho" if p["arm"] == "heldout" else "")
        parts.append(f'<circle cx="{15 + 10 * c}" cy="{15 + 10 * r}" r="{d / 2}" class="{cls}"/>')
    return "".join(parts) + "</svg>"


def line_svg(data: dict, title: str) -> str:
    """Static three-round chart: learning alone, network, pooled raw data."""
    W, H, X0, X1, Y0, Y1 = 440, 260, 50, 396, 210, 40
    top = max(20, -(-max(max(v) for v in data.values()) // 10) * 10)
    x = lambda k: X0 + (X1 - X0) * k / 2
    y = lambda v: Y0 - (Y0 - Y1) * v / top
    parts = [f'<svg viewBox="0 0 {W} {H}" class="lchart" role="img" aria-label="{title}">',
             f'<text x="{W / 2}" y="20" text-anchor="middle" class="ct">{title}</text>']
    for t in range(0, int(top) + 1, int(top // 4) or 1):
        parts.append(f'<line x1="{X0}" x2="{X1}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
                     f'<text x="{X0 - 8}" y="{y(t) + 4:.1f}" text-anchor="end" class="tick">{t}</text>')
    for k in range(3):
        parts.append(f'<text x="{x(k):.1f}" y="{Y0 + 22}" text-anchor="middle" class="tick">Round {k + 1}</text>')
    for arm, cls in (("isolated", "iso"), ("oracle", "ora"), ("networked", "net")):
        pts = " ".join(f"{x(k):.1f},{y(v):.1f}" for k, v in enumerate(data[arm]))
        parts.append(f'<polyline points="{pts}" class="ln {cls}"/>')
        parts += [f'<circle cx="{x(k):.1f}" cy="{y(v):.1f}" r="4.5" class="dot {cls}"/>' for k, v in enumerate(data[arm])]
    parts.append(f'<text x="14" y="{(Y0 + Y1) / 2}" transform="rotate(-90 14 {(Y0 + Y1) / 2})" text-anchor="middle" class="tick">model error, µm</text>')
    return "".join(parts) + "</svg>"


def sites_svg() -> str:
    """Bars: gain over learning alone at 2 / 4 / 8 data-poor sites (simulation)."""
    W, H, X0, Y0, Y1 = 360, 240, 24, 196, 44
    top = 42
    bw, gap = 76, (W - 2 * X0 - 3 * 76) / 2
    y = lambda v: Y0 - (Y0 - Y1) * v / top
    parts = [f'<svg viewBox="0 0 {W} {H}" class="sites-chart" role="img" aria-label="Lower error than learning alone: '
             + ", ".join(f'{r["sites"]} labs {round(r["pct"])}%' for r in SITES) + '">',
             f'<text x="{W / 2}" y="18" text-anchor="middle" class="ct">Value grows with every lab that joins (simulation)</text>',
             f'<line x1="{X0}" x2="{W - X0}" y1="{Y0}" y2="{Y0}" class="axis"/>']
    for i, r in enumerate(SITES):
        x = X0 + i * (bw + gap)
        parts.append(f'<rect x="{x:.1f}" y="{y(r["pct"]):.1f}" width="{bw}" height="{Y0 - y(r["pct"]):.1f}" rx="3" class="bar"/>'
                     f'<text x="{x + bw / 2:.1f}" y="{y(r["pct"]) - 10:.1f}" text-anchor="middle" class="val">{round(r["pct"])}%</text>'
                     f'<text x="{x + bw / 2:.1f}" y="{Y0 + 22}" text-anchor="middle" class="lab">{r["sites"]} labs</text>')
    return "".join(parts) + "</svg>"


def bars_svg(title: str, labels: list, values: list, unit: str, cls: str, top: float) -> str:
    W, H, X0, Y0, Y1 = 300, 220, 18, 180, 46
    n = len(values); bw = 64 if n == 2 else 58; gap = (W - 2 * X0 - n * bw) / max(n - 1, 1)
    y = lambda v: Y0 - (Y0 - Y1) * v / top
    parts = [f'<svg viewBox="0 0 {W} {H}" class="sites-chart" role="img" aria-label="{title}">',
             f'<text x="{W / 2}" y="18" text-anchor="middle" class="ct">{title}</text>',
             f'<line x1="{X0}" x2="{W - X0}" y1="{Y0}" y2="{Y0}" class="axis"/>']
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = X0 + i * (bw + gap)
        parts.append(f'<rect x="{x:.1f}" y="{y(v):.1f}" width="{bw}" height="{max(Y0 - y(v), 3):.1f}" rx="3" class="bar {cls}"/>'
                     f'<text x="{x + bw / 2:.1f}" y="{min(y(v), Y0 - 3) - 8:.1f}" text-anchor="middle" class="val">{v}{unit}</text>'
                     f'<text x="{x + bw / 2:.1f}" y="{Y0 + 20}" text-anchor="middle" class="lab">{lab}</text>')
    return "".join(parts) + "</svg>"


LEGEND = ('<p class="legend"><span class="k iso"></span>Learning alone<span class="k net"></span>Prebuilt network'
          '<span class="k ora"></span>Pooled raw data</p>')

SLIDES = [
    ("", "", "Prebuilt",
     f"""<div class="brandline small">{logo("logo-md")}<span>Prebuilt</span></div>
<p class="tag">Every printer learns from every other. No data leaves.</p>
<div class="two">
  <div class="rows">
    <div class="row">{tile("FaPrint")}<div><b>Every printer is wrong in its own way</b><span>Holes print up to 250 µm small and pins up to 195 µm large (desktop SLA, CMM; Tehnički vjesnik 2026).</span></div></div>
    <div class="row">{tile("FaTooth")}<div><b>In medicine, that decides the fit</b><span>Crowns, surgical guides and microfluidic chips must fit first time. A crown margin allows ~120 µm.</span></div></div>
    <div class="row">{tile("FaLock")}<div><b>And labs can't pool what they learn</b><span>Patient scans and process recipes can't leave, so every lab re-learns its printer from scratch.</span></div></div>
  </div>
  <figure class="card fig">{plate_svg()}<figcaption>Our test plate on a Formlabs Form Studio 1: a 1.50 mm pin printed at 1.44 mm.</figcaption></figure>
</div>""",
     ""),

    ("", "How it works", "Learn locally, share three numbers",
     f"""<div class="steps">
  <div class="card step">{tile("FaPrint")}<b>1&nbsp; Print a test plate</b><span>24 pins and holes, measured by micrometer or flatbed scanner.</span></div>
  <div class="card step">{tile("FaRulerCombined")}<b>2&nbsp; Learn your printer</b><span>A physics model of your machine, fit locally on your own data.</span></div>
  <div class="card step">{tile("FaExchangeAlt")}<b>3&nbsp; Share three numbers</b><span>Mean and spread of 3 parameters every printer shares, logged on a receipt.</span></div>
</div>
<div class="card banner">{tile("FaLock", "teal")}<p><b>Never leaves the lab:</b> patient scans, part geometry, measurements, machine settings. Every crossing is audited; claims were registered before the first print.</p></div>
<div class="card banner"><p><b class="gap">What's new:</b> correcting printer error (Huang et al. 2015) and learning across printers (Wei et al. 2023) are proven, but pool the data. Prebuilt does it privately.</p></div>""",
     ""),

    ("", "Results · simulation", "Parts that fit, and new labs get there faster",
     f"""<div class="charts three">
  <div class="card">{bars_svg("Size error per part, µm", ["Drawn as-is", "Corrected"], [132, 9], " µm", "net", 160)}</div>
  <div class="card">{bars_svg("Lower error than a lab alone", [f'{r["sites"]} labs' for r in SITES], [round(r["pct"]) for r in SITES], "%", "ora", 42)}</div>
  <div class="card">{line_svg({"isolated": LIAR["isolated"], "networked": LIAR["networked"], "oracle": CHECKED["networked"]}, "One lab lies: error, µm")}<p class="legend"><span class="k iso"></span>Lab alone<span class="k net"></span>Network, no check<span class="k ora"></span>Network + check</p></div>
</div>
<table class="bench"><thead><tr><th>Head to head, simulated fleets</th><th>Lower error</th><th>Fleets won</th><th>p</th></tr></thead><tbody>
<tr><td>Network vs a lab learning alone (2 labs)</td><td>12.3%</td><td>75 / 100</td><td>&lt;0.001</td></tr>
<tr><td>Pooling all raw data, the upper bound</td><td>12.2%</td><td>64 / 100</td><td></td></tr>
<tr><td>Eight data-poor labs vs alone</td><td>{SITES[2]["pct"]:.1f}%</td><td>{SITES[2]["wins"]} / {SITES[2]["n"]}</td><td>&lt;0.001</td></tr>
<tr><td>Control: printers that share no physics</td><td>no gain</td><td>19 / 60</td><td></td></tr>
</tbody></table>""",
     ""),

    ("", "Who it's for", "For anyone whose precision is a trade secret",
     f"""<div class="who2">
  <span class="glbl net">Now · medical and bio</span>
  <div class="grid3">
    <div class="card who chip">{tile("FaHospital")}<b>Hospital 3D-printing labs</b></div>
    <div class="card who chip">{tile("FaTooth")}<b>Dental labs</b></div>
    <div class="card who chip">{tile("FaMicroscope")}<b>Bio and microfluidics labs</b></div>
  </div>
  <span class="glbl amb">Next · high-precision industry</span>
  <div class="grid3">
    <div class="card who chip">{tile("FaMicrochip", "amb")}<b>Chip makers, GPU packaging</b></div>
    <div class="card who chip">{tile("FaShieldAlt", "amb")}<b>Defense and aerospace</b></div>
    <div class="card who chip">{tile("FaCogs", "amb")}<b>MEMS and nanotech</b></div>
  </div>
</div>
<div class="card banner"><p><b class="gap">Value grows with every member:</b> {round(SITES[0]["pct"])}% → {round(SITES[1]["pct"])}% → {round(SITES[2]["pct"])}% lower error at 2 / 4 / 8 labs. From microns today to nanometres next.</p></div>
<p class="endline">{logo("logo-sm")}<span>Print anywhere, trust the part.</span><span class="meta">github.com/matte-realize/prebuilt</span></p>""",
     ""),
]

EXTRA_CSS = """
/* Pitch: always dark, the same palette as the PowerPoint deck. */
:root, :root[data-theme="light"], :root[data-theme="dark"] {
  --bg: #0b121c; --sheet: #0b121c; --ink: #eef2f7; --muted: #9aa9bc; --line: #2a3a52; --plate: #3b4f5b;
  --card: #142030; --card2: #1b2a3e; --accent: #f07a48; --net: #f07a48; --ora: #2fc2b0; --iso: #8d9bad; --amber: #f0a43a; --teal: #2fc2b0;
}
@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) { --bg: #0b121c; --sheet: #0b121c; --ink: #eef2f7; --muted: #9aa9bc; --line: #2a3a52; } }
body { background: #05090f; }
.slide { background: var(--bg); grid-template-rows: auto auto 1fr; }
.slide header .kick { color: var(--accent); }
.slide h2 { font-size: 4.2cqw; }
.slide .body { font-size: 1.9cqw; align-content: center; gap: 1.6cqw; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 1cqw; }
.tile { display: inline-grid; place-items: center; width: 4.6cqw; height: 4.6cqw; border-radius: .9cqw; flex: none;
  color: var(--accent); background: color-mix(in srgb, var(--accent) 16%, transparent); border: 1px solid var(--accent); font-size: 2.3cqw; }
.tile svg { width: 55%; height: 55%; display: block; }
.slide .body p.foot, .slide .body p.legend, .slide .body p.q, .slide .body p.tag, .slide .body p.sub, .slide .body p.big-close { max-width: none; }
.tile.teal { color: var(--teal); background: color-mix(in srgb, var(--teal) 16%, transparent); border-color: var(--teal); }
.foot { font-size: 1.25cqw; color: var(--muted); border-top: 0; padding-top: 0; max-width: none; }
.muted { color: var(--muted); }
.two { display: grid; grid-template-columns: 1.6fr 1fr; gap: 3cqw; align-items: center; }
.two.wide { grid-template-columns: 1.8fr 1fr; }
.rows { display: grid; gap: 2cqw; }
.row { display: flex; gap: 2cqw; align-items: flex-start; }
.row b, .step b, .who b { display: block; font: 700 1.9cqw/1.25 var(--display); }
.row span, .step span, .who span { display: block; color: var(--muted); font-size: 1.6cqw; margin-top: .4cqw; }
.q { font: 700 1.8cqw/1.3 var(--display); color: var(--accent); margin: .4cqw 0 0; max-width: none; }
.fig { margin: 0; padding: 2cqw; display: grid; justify-items: center; gap: 1cqw; }
.fig figcaption { font-size: 1.2cqw; color: var(--muted); text-align: left; }
.plate { width: 100%; max-width: 26cqw; } .plate .pl { fill: var(--plate); } .plate .cut { fill: #d7dee3; }
.plate .pin { fill: #d7dee3; } .plate .hole { fill: var(--bg); stroke: #6e8290; stroke-width: .5; } .plate .ho { stroke: var(--amber); stroke-width: .9; }
.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2cqw; }
.step { padding: 2.2cqw; display: grid; gap: 1.2cqw; align-content: start; }
.banner { display: flex; gap: 2cqw; align-items: center; padding: 1.6cqw 2cqw; background: var(--card2); }
.step .lbl { font: 700 1.1cqw var(--mono); letter-spacing: .14em; text-transform: uppercase; color: var(--teal); }
.step .pn { font: 700 3.2cqw/1.1 var(--display); color: var(--ink); }
.step i { font-size: 1.15cqw; color: var(--muted); opacity: .8; }
.banner b.gap { color: var(--accent); }
.brandline.small { font-size: 4.6cqw; gap: 1.4cqw; } .logo-md { width: 5cqw; height: 5cqw; } .logo-sm { width: 3.4cqw; height: 3.4cqw; }
.step.rig { background: var(--card2); padding: 1.6cqw 2cqw; gap: .6cqw; } .step.rig b { color: var(--teal); }
.who.chip { grid-template-columns: auto 1fr; padding: 1.2cqw 1.4cqw; } 
.endline { display: flex; align-items: center; gap: 1.4cqw; font: 700 3cqw var(--display); margin: .6cqw 0 0; max-width: none; } .endline .meta { margin-left: auto; font: 400 1.3cqw var(--body); color: var(--muted); }
.who2 { display: grid; gap: 1cqw; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.6cqw; margin-bottom: .8cqw; }
.glbl { font: 700 1.1cqw var(--mono); letter-spacing: .14em; text-transform: uppercase; } .glbl.net { color: var(--accent); } .glbl.amb { color: var(--amber); }
.step .lbl.net { color: var(--accent); } .step .lbl.amb { color: var(--amber); }
.tile.amb { color: var(--amber); background: color-mix(in srgb, var(--amber) 16%, transparent); border-color: var(--amber); }
.banner p { margin: 0; font-size: 1.65cqw; max-width: none; } .banner b { color: var(--teal); }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 2cqw; }
.charts .card { padding: 1cqw 1.4cqw; }
.charts.three { grid-template-columns: repeat(3, 1fr); gap: 1.6cqw; } .charts.three .legend { font-size: 1.05cqw; gap: .4cqw 1.6cqw; }
.sites-chart .bar.net { fill: var(--accent); } .sites-chart .bar.ora { fill: var(--ora); }
.bench { font-size: 1.35cqw; } .bench th, .bench td { padding: .55cqw 1.2cqw; }
.lchart { width: 100%; height: auto; display: block; }
.lchart .ct, .sites-chart .ct { font: 600 15px var(--body); fill: var(--ink); }
.lchart .grid { stroke: var(--line); stroke-width: 1; } .lchart .tick { font: 12px var(--body); fill: var(--muted); }
.lchart .ln { fill: none; stroke-width: 3.5; stroke-linejoin: round; stroke-linecap: round; }
.lchart .iso { stroke: var(--iso); fill: var(--iso); } .lchart .net { stroke: var(--net); fill: var(--net); } .lchart .ora { stroke: var(--ora); fill: var(--ora); }
.lchart polyline.iso, .lchart polyline.net, .lchart polyline.ora { fill: none; }
.legend { display: flex; flex-wrap: wrap; gap: .8cqw 2.4cqw; align-items: center; justify-content: center; font-size: 1.4cqw; color: var(--muted); margin: 0; max-width: none; }
.legend .k { display: inline-block; width: 2cqw; height: .5cqw; border-radius: 1cqw; margin-right: -1.6cqw; }
.legend .k.iso { background: var(--iso); } .legend .k.net { background: var(--net); } .legend .k.ora { background: var(--ora); }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.8cqw; }
.stat { padding: 2.2cqw; display: grid; gap: 1.4cqw; align-content: start; min-height: 22cqw; }
.stat .n, .pin .n { font: 700 5.2cqw/1 var(--display); font-variant-numeric: tabular-nums; }
.stat .n.sm { font-size: 3.6cqw; line-height: 1.45; }
.stat .n.net { color: var(--net); } .stat .n.ora { color: var(--ora); } .stat .n.amb { color: var(--amber); }
.stat > span:last-child { color: var(--muted); font-size: 1.6cqw; }
.tl { list-style: none; margin: 0; padding: 0; display: grid; gap: 2.4cqw; }
.tl li { position: relative; padding-left: 4cqw; }
.tl li::before { content: ""; position: absolute; left: 0; top: .3cqw; width: 2cqw; height: 2cqw; border-radius: 50%; background: var(--accent); }
.tl li:not(:last-child)::after { content: ""; position: absolute; left: .95cqw; top: 2.6cqw; bottom: -2.2cqw; width: 2px; background: var(--line); }
.tl b { display: block; font: 700 2cqw var(--display); } .tl span { display: block; color: var(--muted); font-size: 1.65cqw; margin-top: .4cqw; }
.pin { padding: 2.4cqw; display: grid; gap: 1cqw; background: var(--card2); }
.pin .lbl { font: 700 1.15cqw var(--mono); letter-spacing: .14em; text-transform: uppercase; color: var(--teal); }
.pin .n small { font: 400 2cqw var(--body); color: var(--muted); }
.pin .muted { font-size: 1.5cqw; }
.pin ul { list-style: none; margin: .6cqw 0 0; padding: 0; display: grid; gap: .8cqw; font-size: 1.6cqw; }
.pin li::before { content: "●"; margin-right: 1cqw; color: var(--muted); } .pin li.ok::before { color: var(--teal); } .pin li.edge::before { color: var(--amber); }
.grid4 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.6cqw; }
.who { padding: 1.8cqw; display: grid; grid-template-columns: auto 1fr; gap: .6cqw 1.4cqw; align-items: center; }
.who .tile { width: 3.8cqw; height: 3.8cqw; font-size: 1.9cqw; }
.who span { grid-column: 1 / -1; font-size: 1.4cqw; }
.sites-chart { width: 100%; height: auto; display: block; }
.sites-chart .bar { fill: var(--accent); } .sites-chart .axis { stroke: var(--line); stroke-width: 1.5; }
.sites-chart .val { font: 700 22px var(--display); fill: var(--ink); } .sites-chart .lab { font: 600 14px var(--body); fill: var(--muted); }
.hero-title { display: grid; gap: 1.8cqw; align-content: center; }
.brandline { display: flex; align-items: center; gap: 2.4cqw; font: 700 9cqw/1 var(--display); }
.logo-xl { width: 10cqw; height: 10cqw; } .logo-lg { width: 7cqw; height: 7cqw; }
.tag { font: 700 2.8cqw/1.25 var(--display); color: var(--accent); margin: 0; max-width: none; }
.sub { font-size: 2cqw; color: var(--muted); margin: 0; max-width: 60ch; }
.hero-title .meta { font-size: 1.3cqw; color: var(--muted); margin-top: 3cqw; }
.big-close { font: 700 5.6cqw/1.1 var(--display); margin: 0; max-width: none; }
.slide.first header { visibility: hidden; } .slide.first h2 { display: none; } .slide.first .body { gap: 1.2cqw; }
.bench { width: 100%; border-collapse: collapse; font-size: 1.6cqw; }
.bench th { text-align: left; font: 600 1.25cqw var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); background: var(--card2); }
.bench th, .bench td { padding: 1cqw 1.4cqw; border: 1px solid var(--line); }
.bench tbody tr:nth-child(odd) td { background: var(--card); }
@media (max-width: 720px) {
  .slide h2 { font-size: 24px; } .slide .body { font-size: 14px; }
  .two, .two.wide, .steps, .charts, .stats, .grid4, .grid3 { grid-template-columns: 1fr; }
  .row b, .step b, .who b, .tl b { font-size: 16px; } .row span, .step span, .who span, .tl span, .stat > span:last-child, .banner p, .pin ul, .pin .muted { font-size: 14px; }
  .tile, .who .tile { width: 36px; height: 36px; font-size: 18px; } .q { font-size: 16px; } .foot, .legend { font-size: 12px; }
  .stat .n, .pin .n { font-size: 36px; } .stat .n.sm { font-size: 28px; } .brandline { font-size: 44px; } .logo-xl { width: 48px; height: 48px; }
  .tag { font-size: 18px; } .sub { font-size: 15px; } .big-close { font-size: 28px; } .bench { font-size: 12px; } .bench th { font-size: 10px; }
  .tl li { padding-left: 28px; } .tl li::before { width: 14px; height: 14px; } .tl li:not(:last-child)::after { left: 6px; top: 18px; }
  .legend .k { width: 14px; height: 4px; margin-right: -8px; }
}
"""


def render() -> str:
    sections = []
    for i, (kind, kicker, title, body, note) in enumerate(SLIDES, 1):
        cls = "slide first" if i == 1 else "slide"
        sections.append(f"""<section class="{cls}" id="s{i}" aria-label="Slide {i}: {title}">
  <header><span class="kick">{logo()}{kicker}</span><span class="num">{i} / {len(SLIDES)}</span></header>
  <h2>{title}</h2>
  <div class="body">{body}</div>
</section>""")
    html = (HERE / "deck_template.html").read_text()
    html = html.replace("<title>Prebuilt Deck</title>", "<title>Prebuilt Pitch</title>")
    html = html.replace("</style>", EXTRA_CSS + "</style>", 1)
    html = re.sub(r'<button id="notes"[^>]*>.*?</button>', "", html)
    return html.replace("%%SLIDES%%", "\n".join(sections))


out = HERE / "prebuilt-pitch.html"
out.write_text(render())
print(out, out.stat().st_size)
