// Generate docs/slides/prebuilt-pitch.pptx: the 3-minute pitch as a PowerPoint deck.
//
//   npm install pptxgenjs@3.12.0 sharp@0.33.5      (once, anywhere on NODE_PATH)
//   node docs/slides/make_pptx.js
//
// Same content and numbers as make_pitch.py: every figure is read from committed results
// (demo/tier-d/*.json, viewer/evidence.json, plates/out/resin/resin-seed.json), never typed in.
// Speaker notes carry the script timing. The live 3D run is viewer/demo.html.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));

// ---- data ---------------------------------------------------------------------------
function curves(file, site) {
  const acc = {};
  for (const r of read(file)) {
    if (site && r.site !== site) continue;
    (acc[`${r.arm}|${r.round}`] ??= []).push(r.mae_truth);
  }
  const out = {};
  for (const arm of ["isolated", "networked", "oracle"])
    out[arm] = [1, 2, 3].map((k) => {
      const v = acc[`${arm}|${k}`];
      return Math.round((1000 * v.reduce((a, b) => a + b, 0)) / v.length * 10) / 10;
    });
  return out;
}
const HONEST = curves("demo/tier-d/sim.json");
const LIAR = curves("demo/tier-d/bad-site.json", "resin");
const CHECKED = curves("demo/tier-d/bad-site-check.json", "resin");
const EV = read("viewer/evidence.json");
const SITES = EV.sites_needed.rows;
const CHECK = EV.consistency_check;
const SEED = read("plates/out/resin/resin-seed.json");

// ---- look ---------------------------------------------------------------------------
const COL = {
  ink: "111A20", steel: "E9EEF1", sheet: "FFFFFF", muted: "5B6B75", line: "C9D3D9",
  net: "EB6834", iso: "2A78D6", ora: "12936A", amber: "B86B00", slate: "4F6070", mist: "8D9BAD",
  night: "0D1316", nightInk: "E6ECEF", nightMuted: "9BABB5",
};
const HEAD = "Arial", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "Prebuilt";
pres.company = "Prebuilt";
pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };

async function logoPng(px) {
  const svg = fs.readFileSync(path.join(ROOT, "assets/logo.svg"));
  const buf = await sharp(svg, { density: 600 }).resize(px, px).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

function text(slide, t, o) {
  slide.addText(t, { isTextBox: true, fontFace: BODY, margin: 0, valign: "top", ...o });
}

function header(slide, LOGO, kicker, title, dark = false) {
  slide.addImage({ data: LOGO, x: 0.5, y: 0.36, w: 0.24, h: 0.24, altText: "Prebuilt logo" });
  text(slide, kicker.toUpperCase(), { x: 0.84, y: 0.36, w: 6, h: 0.24, fontSize: 10, bold: true, charSpacing: 2,
    color: dark ? COL.nightMuted : COL.muted, valign: "middle" });
  text(slide, title, { x: 0.5, y: 0.72, w: 9, h: 0.62, fontFace: HEAD, fontSize: 26, bold: true,
    color: dark ? COL.nightInk : COL.ink });
}

function footnote(slide, t, dark = false) {
  text(slide, t, { x: 0.5, y: 5.0, w: 9, h: 0.4, fontSize: 10, color: dark ? COL.nightMuted : COL.muted });
}

function plate(slide, x, y, s) {
  // the seed test plate, top view: steel square, fiducials, pins filled, holes outlined, held-out ringed amber
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: s, h: s, rectRadius: 0.04,
    fill: { color: "3B4F5B" }, line: { color: "3B4F5B" } });
  const u = s / 100;
  for (const [fx, fy] of [[5, 5], [95, 5], [5, 95]])
    slide.addShape(pres.shapes.RECTANGLE, { x: x + (fx - 2) * u, y: y + (fy - 2) * u, w: 4 * u, h: 4 * u,
      fill: { color: COL.steel }, line: { color: COL.steel } });
  for (const p of SEED.pieces) {
    const [r, c] = p.slot, d = p.nominal_d;
    const cx = x + (15 + 10 * c) * u, cy = y + (15 + 10 * r) * u, rr = (d / 2) * u;
    const pin = p.kind === "pin", ho = p.arm === "heldout";
    slide.addShape(pres.shapes.OVAL, { x: cx - rr, y: cy - rr, w: 2 * rr, h: 2 * rr,
      fill: pin ? { color: "D7DEE3" } : { color: COL.ink },
      line: { color: ho ? "F0A43A" : pin ? "D7DEE3" : "6E8290", width: ho ? 1.5 : 0.75 } });
  }
}

function lineChart(slide, data, x, y, w, h, title) {
  slide.addChart(pres.charts.LINE, [
    { name: "Learning alone", labels: ["Round 1", "Round 2", "Round 3"], values: data.isolated },
    { name: "Prebuilt network", labels: ["Round 1", "Round 2", "Round 3"], values: data.networked },
    { name: "Pooled raw data", labels: ["Round 1", "Round 2", "Round 3"], values: data.oracle },
  ], {
    x, y, w, h, chartColors: [COL.iso, COL.net, COL.ora], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 7,
    showTitle: true, title, titleFontSize: 12, titleColor: COL.ink, titleFontFace: "+mj-lt",
    showLegend: true, legendPos: "b", legendFontSize: 10, legendColor: COL.muted, legendFontFace: "+mn-lt",
    catAxisLabelColor: COL.muted, valAxisLabelColor: COL.muted, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valAxisTitle: "error, µm", showValAxisTitle: true, valAxisTitleFontSize: 10, valAxisTitleColor: COL.muted,
    valGridLine: { color: COL.line, size: 0.5 }, catGridLine: { style: "none" }, valAxisMinVal: 0,
  });
}

const pct = (v) => `${Math.round(v)}%`;

async function main() {
  const LOGO = await logoPng(512);

  // 1 · title (dark)
  let s = pres.addSlide();
  s.background = { color: COL.night };
  s.addImage({ data: LOGO, x: 0.5, y: 1.55, w: 0.9, h: 0.9, altText: "Prebuilt logo" });
  text(s, "Prebuilt", { x: 1.6, y: 1.55, w: 7, h: 0.9, fontFace: HEAD, fontSize: 54, bold: true, color: COL.nightInk, valign: "middle" });
  text(s, "Printers that learn their errors from each other, without sharing a single measurement.",
    { x: 0.5, y: 2.75, w: 8.4, h: 0.9, fontSize: 22, color: COL.nightInk });
  text(s, "ScienceClaw · Manufacturing & Materials · MIT Media Lab", { x: 0.5, y: 4.75, w: 8, h: 0.3, fontSize: 12, color: COL.nightMuted });
  s.addNotes("Open on the one-liner. Hold the printed plate.");

  // 2 · problem
  s = pres.addSlide();
  s.background = { color: COL.sheet };
  header(s, LOGO, "The problem", "Every shop re-learns its own printer");
  text(s, "No printed part matches its file. Holes come out small, pins come out fat, by tens to hundreds of microns, and that decides whether parts fit.",
    { x: 0.5, y: 1.55, w: 5.3, h: 1.1, fontSize: 16, bold: true, color: COL.ink });
  text(s, "The error belongs to your machine today: its resin, settings and wear. No datasheet knows it; you learn it by printing. Every site does that from scratch, and can't pool the data, because measurements expose process know-how and customer parts.",
    { x: 0.5, y: 2.75, w: 5.3, h: 1.2, fontSize: 14, color: COL.muted });
  text(s, "Can printers learn from each other without sharing a single measurement?",
    { x: 0.5, y: 4.0, w: 5.3, h: 0.8, fontFace: HEAD, fontSize: 17, bold: true, color: COL.net });
  plate(s, 6.35, 1.5, 3.15);
  text(s, "The test plate: pins and holes, 1–7 mm. Print it, measure it, and you know your printer.",
    { x: 6.35, y: 4.72, w: 3.15, h: 0.5, fontSize: 10, color: COL.muted });
  s.addNotes("0:00–0:25. Hold up a printed plate. The point: precision is a property of your machine, and the only way to learn it is to print.");

  // 3 · what we built
  s = pres.addSlide();
  s.background = { color: COL.steel };
  header(s, LOGO, "What we built", "Two sites, one boundary, only beliefs cross");
  for (const [x, proc, name, sub] of [[0.5, "SLA", "Resin site", "prints, measures, learns its own model"],
                                      [6.5, "FDM", "PLA site", "different machine, different physics"]]) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.75, w: 3.0, h: 2.0, rectRadius: 0.12,
      fill: { color: COL.sheet }, line: { color: COL.line, width: 1 },
      shadow: { type: "outer", color: "000000", opacity: 0.12, blur: 6, offset: 2, angle: 90 } });
    text(s, proc, { x: x + 0.3, y: 1.98, w: 2.4, h: 0.3, fontSize: 11, bold: true, color: COL.muted, charSpacing: 2 });
    text(s, name, { x: x + 0.3, y: 2.35, w: 2.4, h: 0.5, fontFace: HEAD, fontSize: 22, bold: true, color: COL.ink });
    text(s, sub, { x: x + 0.3, y: 2.95, w: 2.4, h: 0.6, fontSize: 13, color: COL.muted });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 3.85, y: 2.3, w: 2.3, h: 0.55, rectRadius: 0.27,
    fill: { color: COL.net }, line: { color: COL.net } });
  text(s, "μ, σ of 3 shared parameters", { x: 3.85, y: 2.3, w: 2.3, h: 0.55, fontSize: 12, bold: true, color: COL.sheet, align: "center", valign: "middle" });
  text(s, "⇄", { x: 3.85, y: 1.7, w: 2.3, h: 0.55, fontSize: 26, color: COL.net, align: "center", valign: "middle" });
  text(s, "schema-checked · on a receipt", { x: 3.85, y: 2.98, w: 2.3, h: 0.3, fontSize: 10, color: COL.amber, align: "center", bold: true });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y: 4.1, w: 9.0, h: 0.6, rectRadius: 0.08,
    fill: { color: COL.sheet }, line: { color: COL.line, width: 1 } });
  text(s, [{ text: "Stays home: ", options: { bold: true, color: COL.ink } },
           { text: "every measurement, every machine-specific parameter, every customer part.", options: { color: COL.muted } }],
    { x: 0.75, y: 4.1, w: 8.5, h: 0.6, fontSize: 14, valign: "middle" });
  s.addNotes("0:25–0:45. Point at the middle: that's the whole interface. Errors every printer shares (small features shrink, edges drift) are learned together; everything else stays local. Both sites here are simulated printers whose true behavior we know, which is how every result is scored.");

  // 4 · live run (charts of the same run the live view plays)
  s = pres.addSlide();
  s.background = { color: COL.sheet };
  header(s, LOGO, "Live run", "Watch the network learn and shrug off a liar");
  lineChart(s, HONEST, 0.4, 1.45, 4.5, 3.3, "Honest network");
  lineChart(s, LIAR, 5.1, 1.45, 4.5, 3.3, "PLA site lies (resin's error)");
  const spike = LIAR.networked[0], back = LIAR.networked[2];
  footnote(s, `Held-out model error, µm, 20 simulated worlds, registered config. With a liar, resin's error spikes to ${spike} µm in round 1, trust collapses, and it is back to ${back} µm by round 3. With the consistency check on, round 1 stays at ${CHECKED.networked[0]} µm. Live view: viewer/demo.html.`);
  s.addNotes("0:45–1:30. Left: the network tracks the pooled-data line, below learning alone, every round. Right: the PLA site broadcasts lies. Resin's error spikes in round 1, trust collapses to 0.01 once held-out pieces expose the lie, and by round 3 resin is level again. With the consistency check, the lie is set aside at the boundary and there is no spike. If there's time, switch to the live 3D view.");

  // 5 · results (stat callouts)
  s = pres.addSlide();
  s.background = { color: COL.steel };
  header(s, LOGO, "Results, in simulation", "The win is many sites, not many agents");
  const stats = [
    ["12%", "lower error than learning alone, in 75 of 100 worlds. Pooling all the raw data: also 12%.", COL.net],
    [pct(SITES[2].pct), `with eight sites that each know little, better in ${SITES[2].wins} of ${SITES[2].n} worlds. Many data-poor sites is where sharing pays.`, COL.ora],
    ["0 rounds", `for a liar: a consistency check catches its notes on arrival (${CHECK.liar_caught} of ${CHECK.liar_notes}, ${CHECK.honest_dropped} honest notes dropped).`, COL.amber],
  ];
  stats.forEach(([big, sub, c], i) => {
    const x = 0.5 + i * 3.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.6, w: 2.8, h: 2.75, rectRadius: 0.12,
      fill: { color: COL.sheet }, line: { color: COL.line, width: 1 } });
    text(s, big, { x: x + 0.25, y: 1.85, w: 2.3, h: 0.95, fontFace: HEAD, fontSize: 36, bold: true, color: c });
    text(s, sub, { x: x + 0.25, y: 2.75, w: 2.3, h: 1.5, fontSize: 14, color: COL.ink });
  });
  footnote(s, "Hidden-truth simulation, registered config, paired per world. The consistency check is an added option, off in the registered config. The agent layer adds nothing measurable. At two sites the gain is 1.6 µm, below what a real part can show, so we claim it in simulation only.");
  s.addNotes("1:30–2:00. Say it plainly: these are simulation numbers, the gain comes from sharing between sites, not from the agents, and at two sites it is a couple of microns. It grows with the number of data-poor sites.");

  // 6 · rigor (timeline)
  s = pres.addSlide();
  s.background = { color: COL.sheet };
  header(s, LOGO, "Rigor", "A real printer for scale, simulation to score");
  const steps = [
    ["Real printer", "Formlabs Form Studio 1: a 1.5 mm pin measured 1.41–1.48 mm by micrometer, 24\u201189\u00A0µm small."],
    ["Vendor spec", "±0.08 mm on 1–30 mm features. Real error is tens of µm, as the spec says."],
    ["Simulator", "Simulated resin pins miss by −0.1 to +0.27 mm. The real pin is inside, at the small edge: each printer must learn its own error."],
    ["Why not real", "The sharing gain is 1.6 µm. Two readings of one pin differed by 65 µm. Only hidden truth can score it."],
  ];
  s.addShape(pres.shapes.LINE, { x: 0.65, y: 1.83, w: 8.7, h: 0, line: { color: COL.line, width: 1.5 } });
  steps.forEach(([t, d], i) => {
    const x = 0.5 + i * 2.3;
    s.addShape(pres.shapes.OVAL, { x: x + 0.03, y: 1.71, w: 0.24, h: 0.24, fill: { color: i === 2 ? COL.net : COL.ink }, line: { color: COL.sheet, width: 2 } });
    text(s, t, { x, y: 2.1, w: 2.05, h: 0.35, fontFace: HEAD, fontSize: 15, bold: true, color: COL.ink });
    text(s, d, { x, y: 2.5, w: 2.05, h: 1.9, fontSize: 13, color: COL.muted });
  });
  footnote(s, "Registered before printing: two printers can't show the sharing gain on real parts. Negative control: when printers share no physics, sharing gains nothing, so the gain isn't built into the scoring.");
  s.addNotes("2:00–2:25. Rigor slide. Hold up the printed plate. The real printer tells us the simulator is the right size; this pin sits at its small edge (1.8th percentile), so say 'edge', not 'middle'. The simulator is the only place a 1.6 µm gain can be scored; the negative control shows the simulator doesn't hand us the result. Don't claim the model was fit on the real printer: one pin, two readings, isn't enough.");

  // 7 · who it's for (dark close)
  s = pres.addSlide();
  s.background = { color: COL.night };
  header(s, LOGO, "Who it's for", "Fleets where fit decides and data can't leave", true);
  const who = [
    ["Dental labs", "Patient scans. Crowns, models and guides must seat on the first print.", COL.nightInk],
    ["Print farms, service bureaus", "Customer geometry is the customer's IP. Many machines, every job must fit.", COL.nightInk],
    ["Distributed manufacturing", "One part, many vendors. Each vendor's process is its edge.", COL.nightInk],
    ["Next: microfluidics, bioprinting", "Smaller features, costlier tests, stricter data rules.", "F0A43A"],
  ];
  who.forEach(([b, d, c], i) => {
    const y = 1.55 + i * 0.68;
    text(s, b, { x: 0.5, y, w: 2.5, h: 0.6, fontFace: HEAD, fontSize: 13, bold: true, color: c });
    text(s, d, { x: 3.05, y, w: 2.9, h: 0.6, fontSize: 12, color: COL.nightMuted });
  });
  text(s, [{ text: "What they get: ", options: { bold: true, color: COL.nightInk } },
           { text: "parts that fit the first time (corrected designs: size error 132\u00A0→\u00A09\u00A0µm), and sharing that stays safe when printers differ.", options: { color: COL.nightMuted } }],
    { x: 0.5, y: 4.3, w: 5.45, h: 0.6, fontSize: 12 });
  s.addChart(pres.charts.BAR, [{ name: "Lower error than alone", labels: SITES.map((r) => `${r.sites} sites`), values: SITES.map((r) => Math.round(r.pct)) }], {
    x: 6.2, y: 1.45, w: 3.4, h: 3.3, barDir: "col", chartColors: [COL.net], barGapWidthPct: 60,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelColor: COL.nightInk, dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt",
    showTitle: true, title: "Gain vs learning alone, by data-poor sites", titleFontSize: 11, titleColor: COL.nightInk, titleFontFace: "+mn-lt",
    showLegend: false, catAxisLabelColor: COL.nightMuted, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt",
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 40,
  });
  text(s, "Print anywhere, trust the part.", { x: 0.5, y: 4.95, w: 6, h: 0.45, fontFace: HEAD, fontSize: 20, bold: true, color: COL.net });
  text(s, "github.com/matte-realize/prebuilt · all numbers simulation", { x: 6.2, y: 5.05, w: 3.4, h: 0.3, fontSize: 10, color: COL.nightMuted, align: "right" });
  s.addNotes("2:25–3:00. Name the buyer and why pooling is off the table for them, then the bars: value grows with every printer that joins. Mixed fleets answers 'what if printers differ': trust makes sharing safe, it doesn't yet identify bad partners. Bioprinting is direction. End on the line. Stop talking.");

  // 8 · appendix: validation and benchmarks
  s = pres.addSlide();
  s.background = { color: COL.sheet };
  header(s, LOGO, "Appendix · validation and benchmarks", "Many sites beat one; agents don't beat random");
  const hdr = (t) => ({ text: t, options: { bold: true, color: COL.muted, fontSize: 10, fill: { color: COL.steel } } });
  const rows = [
    [hdr("Round 3, paired simulated worlds"), hdr("Gain"), hdr("Worlds better"), hdr("p")],
    ["Network vs single site alone", "12.3% (1.6 µm)", "75 / 100", "<0.001"],
    ["Pooled raw data (upper bound) vs alone", "12.2%", "64 / 100", ""],
    ["Agents only, messages cut, vs alone", "2.4%", "56 / 100", "0.27"],
    ["Agent auction vs random pieces", "+1.0%", "31 / 60", "0.90"],
    ["4 / 8 data-poor sites vs alone", `${SITES[1].pct.toFixed(1)}% / ${SITES[2].pct.toFixed(1)}%`, `${SITES[1].wins} / ${SITES[1].n} · ${SITES[2].wins} / ${SITES[2].n}`, "<0.001"],
    ["Negative control: nothing shared", "−13.0% (adaptive spread: −0.4%)", "19 / 60", "0.006"],
  ];
  s.addTable(rows, { x: 0.5, y: 1.5, w: 9.0, colW: [3.6, 2.6, 1.7, 1.1], fontFace: BODY, fontSize: 12, color: COL.ink,
    border: { type: "solid", pt: 0.5, color: COL.line }, rowH: 0.38, valign: "middle", margin: [0.03, 0.08, 0.03, 0.08] });
  footnote(s, "Hidden-truth simulator, registered config, error against true size on held-out pieces, sign test over worlds. 90% intervals cover 90–91%. GPU posterior up to 84× NumPy on an H100. Reproduce every row: docs/validation-and-benchmarks.md.");
  s.addNotes("Backup for Q&A: the multi-agent vs single-agent comparison. Many sites beat one site; many agents inside a site don't beat random. Say both.");

  const out = path.join(__dirname, "prebuilt-pitch.pptx");
  await pres.writeFile({ fileName: out });
  console.log(out);
}

main().catch((e) => { console.error(e); process.exit(1); });
