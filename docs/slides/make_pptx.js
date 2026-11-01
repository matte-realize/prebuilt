// Generate docs/slides/prebuilt-pitch.pptx: the pitch as a PowerPoint deck.
//
//   npm install pptxgenjs@3.12.0 sharp@0.33.5 react-icons@5.3.0 react@18.3.1 react-dom@18.3.1   (once, on NODE_PATH)
//   node docs/slides/make_pptx.js
//
// Every figure is read from committed results (demo/tier-d/*.json, viewer/evidence.json,
// plates/out/resin/resin-seed.json) or quoted from hpc/sweeps/relevance/README.md and
// docs/validation-and-benchmarks.md. Speaker notes carry the script timing.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const fa = require("react-icons/fa");

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
      return Math.round(((1000 * v.reduce((a, b) => a + b, 0)) / v.length) * 10) / 10;
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
const C = {
  bg: "0B121C", card: "142030", card2: "1B2A3E", line: "2A3A52",
  ink: "EEF2F7", muted: "9AA9BC", faint: "6B7A8F",
  accent: "F07A48", teal: "2FC2B0", slate: "8D9BAD", amber: "F0A43A",
};
const HEAD = "Arial", BODY = "Calibri";
const W = 10, M = 0.55;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "Prebuilt";
pres.company = "Prebuilt";
pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };

async function png(svg, px) {
  const buf = await sharp(Buffer.from(svg), { density: 600 }).resize(px, px).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
const icon = (name, hex) =>
  png(renderToStaticMarkup(React.createElement(fa[name], { color: "#" + hex, size: 256 })), 256);

function T(slide, t, o) {
  slide.addText(t, { isTextBox: true, fontFace: BODY, color: C.ink, margin: 0, valign: "top", ...o });
}
function card(slide, x, y, w, h, fill = C.card) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: fill }, line: { color: C.line, width: 0.75 } });
}
async function tile(slide, name, x, y, s = 0.5, hex = C.accent) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: s, h: s, rectRadius: 0.1, fill: { color: hex, transparency: 82 }, line: { color: hex, width: 0.75 } });
  slide.addImage({ data: await icon(name, hex), x: x + s * 0.24, y: y + s * 0.24, w: s * 0.52, h: s * 0.52, altText: name });
}

let LOGO;
pres.defineSlideMaster({
  title: "DARK",
  background: { color: C.bg },
  objects: [{ text: { text: "Prebuilt", options: { x: M, y: 5.2, w: 3, h: 0.25, fontFace: BODY, fontSize: 9, color: C.faint, margin: 0 } } }],
  slideNumber: { x: W - M - 0.5, y: 5.2, w: 0.5, h: 0.25, fontFace: BODY, fontSize: 9, color: C.faint, align: "right" },
});

function head(slide, kicker, title) {
  slide.addImage({ data: LOGO, x: M, y: 0.38, w: 0.22, h: 0.22, altText: "Prebuilt logo" });
  T(slide, kicker.toUpperCase(), { x: M + 0.32, y: 0.38, w: 7, h: 0.22, fontSize: 10, bold: true, charSpacing: 3, color: C.accent, valign: "middle" });
  T(slide, title, { x: M, y: 0.72, w: W - 2 * M, h: 0.6, fontFace: HEAD, fontSize: 26, bold: true });
}
const foot = (slide, t) => T(slide, t, { x: M, y: 4.82, w: W - 2 * M, h: 0.34, fontSize: 9.5, color: C.faint });

function plate(slide, x, y, s) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: s, h: s, rectRadius: 0.05, fill: { color: "3B4F5B" }, line: { color: "56707F", width: 0.75 } });
  const u = s / 100;
  for (const [fx, fy] of [[5, 5], [95, 5], [5, 95]])
    slide.addShape(pres.shapes.RECTANGLE, { x: x + (fx - 2) * u, y: y + (fy - 2) * u, w: 4 * u, h: 4 * u, fill: { color: "D7DEE3" }, line: { color: "D7DEE3" } });
  for (const p of SEED.pieces) {
    const [r, c] = p.slot, d = p.nominal_d, pin = p.kind === "pin", ho = p.arm === "heldout";
    const cx = x + (15 + 10 * c) * u, cy = y + (15 + 10 * r) * u, rr = (d / 2) * u;
    slide.addShape(pres.shapes.OVAL, { x: cx - rr, y: cy - rr, w: 2 * rr, h: 2 * rr,
      fill: { color: pin ? "D7DEE3" : "0B121C" }, line: { color: ho ? C.amber : pin ? "D7DEE3" : "6E8290", width: ho ? 1.5 : 0.75 } });
  }
}

function lineChart(slide, data, x, y, w, h, title) {
  card(slide, x, y, w, h);
  const labels = ["Round 1", "Round 2", "Round 3"];
  slide.addChart(pres.charts.LINE, [
    { name: "Learning alone", labels, values: data.isolated },
    { name: "Prebuilt network", labels, values: data.networked },
    { name: "Pooled raw data", labels, values: data.oracle },
  ], {
    x: x + 0.1, y: y + 0.1, w: w - 0.2, h: h - 0.2, chartColors: [C.slate, C.accent, C.teal], lineSize: 3, lineDataSymbol: "circle", lineDataSymbolSize: 7,
    showTitle: true, title, titleFontSize: 13, titleColor: C.ink, titleFontFace: "+mn-lt",
    showLegend: true, legendPos: "b", legendFontSize: 10, legendColor: C.muted, legendFontFace: "+mn-lt",
    catAxisLabelColor: C.muted, valAxisLabelColor: C.muted, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLineShow: false, valAxisLineShow: false,
    valAxisTitle: "model error, µm", showValAxisTitle: true, valAxisTitleFontSize: 10, valAxisTitleColor: C.muted, valAxisTitleFontFace: "+mn-lt",
    valGridLine: { color: C.line, size: 0.5 }, catGridLine: { style: "none" }, valAxisMinVal: 0,
  });
}

async function main() {
  LOGO = await png(fs.readFileSync(path.join(ROOT, "assets/logo.svg"), "utf8"), 512);
  let s;

  // 1 · title
  s = pres.addSlide({ masterName: "DARK" });
  s.addImage({ data: LOGO, x: M, y: 1.25, w: 1.05, h: 1.05, altText: "Prebuilt logo" });
  T(s, "Prebuilt", { x: M + 1.3, y: 1.25, w: 6, h: 1.05, fontFace: HEAD, fontSize: 60, bold: true, valign: "middle" });
  T(s, "Precision printing for labs that can't share their data", { x: M, y: 2.65, w: 8.6, h: 0.6, fontFace: HEAD, fontSize: 24, bold: true, color: C.accent });
  T(s, "Printers learn their errors from each other. Patient scans, part geometry and measurements never leave the lab.",
    { x: M, y: 3.35, w: 8.2, h: 0.7, fontSize: 16, color: C.muted });
  T(s, "ScienceClaw · Manufacturing & Materials · MIT Media Lab", { x: M, y: 4.6, w: 8, h: 0.3, fontSize: 11, color: C.faint });
  s.addNotes("Open on the one-liner and hold up the printed plate.");

  // 2 · problem
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "The problem", "Labs that print can't share what they learn");
  const prob = [
    ["FaTooth", "Guides, crowns and implants from patient scans", "They must seat on the first print, and the scans are protected health data."],
    ["FaFlask", "Microfluidic chips and bioprinted scaffolds", "Sub-millimetre features, and every test print costs days and material."],
    ["FaPrint", "Every printer is wrong in its own way", "Holes print small and pins fat, by tens to hundreds of µm. Only printing reveals it."],
  ];
  for (const [i, [ic, h, d]] of prob.entries()) {
    const y = 1.6 + i * 0.98;
    await tile(s, ic, M, y, 0.56);
    T(s, h, { x: M + 0.8, y: y - 0.02, w: 5.0, h: 0.34, fontFace: HEAD, fontSize: 15, bold: true });
    T(s, d, { x: M + 0.8, y: y + 0.33, w: 5.0, h: 0.5, fontSize: 13, color: C.muted });
  }
  card(s, 6.55, 1.5, 2.9, 3.2, C.card);
  plate(s, 6.8, 1.72, 2.4);
  T(s, "The test plate: 24 pins and holes, 1–7 mm. Print it, measure it, know your printer.", { x: 6.8, y: 4.2, w: 2.45, h: 0.45, fontSize: 9.5, color: C.muted });
  T(s, "Can printers learn from each other without sharing a single measurement?", { x: M, y: 4.62, w: 5.9, h: 0.5, fontFace: HEAD, fontSize: 14, bold: true, color: C.accent });
  s.addNotes("0:00–0:25. Hold up a printed plate. Hospitals, dental and bio labs print parts that must fit. The error belongs to each machine, you learn it by printing, and these labs can't pool what they learn: patient scans and process recipes can't leave.");

  // 3 · how it works
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "How it works", "Learn locally, share three numbers");
  const steps = [
    ["FaPrint", "1  Print a test plate", "24 pins and holes. Measure them by micrometer or flatbed scanner."],
    ["FaRulerCombined", "2  Learn your printer", "A physics model of your machine, fit locally on your own data."],
    ["FaExchangeAlt", "3  Share three numbers", "Mean and spread of 3 parameters every printer shares. Schema-checked, logged on a receipt."],
  ];
  for (const [i, [ic, h, d]] of steps.entries()) {
    const x = M + i * 3.0;
    card(s, x, 1.55, 2.8, 2.1);
    await tile(s, ic, x + 0.25, 1.78, 0.5);
    T(s, h, { x: x + 0.25, y: 2.45, w: 2.35, h: 0.35, fontFace: HEAD, fontSize: 14, bold: true });
    T(s, d, { x: x + 0.25, y: 2.82, w: 2.35, h: 0.8, fontSize: 12, color: C.muted });
  }
  card(s, M, 3.88, W - 2 * M, 0.82, C.card2);
  await tile(s, "FaLock", M + 0.2, 4.04, 0.5, C.teal);
  T(s, [{ text: "Never leaves the lab: ", options: { bold: true, color: C.teal } },
        { text: "patient scans, part geometry, measurements, machine settings. A replayable privacy audit checks every crossing: 0 measurements crossed.", options: { color: C.ink } }],
    { x: M + 0.9, y: 3.88, w: 7.8, h: 0.82, fontSize: 13, valign: "middle" });
  s.addNotes("0:25–0:50. That's the whole interface: three numbers out, nothing else. Errors every printer shares (small features shrink, edges drift) are learned together; everything else stays local. Results are scored on simulated printers whose true behavior we know.");

  // 4 · live run
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Three rounds · simulation", "The network learns faster, and shrugs off a liar");
  lineChart(s, HONEST, M, 1.5, 4.35, 3.2, "All sites honest");
  lineChart(s, LIAR, M + 4.55, 1.5, 4.35, 3.2, "One site lies (the honest site's error)");
  foot(s, `20 simulated worlds, registered config, error on held-out pieces. A liar spikes the honest site to ${LIAR.networked[0]} µm in round 1; trust collapses and it is back to ${LIAR.networked[2]} µm by round 3. With the consistency check on, round 1 stays at ${CHECKED.networked[0]} µm.`);
  s.addNotes("0:50–1:10. Twenty seconds, two points. Left: the network tracks the pooled-data line and beats learning alone every round. Right: a site that lies costs one round, then trust cuts it off; the consistency check removes even that round. Don't walk through it; the 3D view (viewer/demo.html) is for Q&A.");

  // 5 · results
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Results · simulation", "The win is many sites, not many agents");
  const stats = [
    ["12%", "lower error than learning alone, in 75 of 100 worlds. Pooling all raw data: also 12%.", C.accent],
    [`${Math.round(SITES[2].pct)}%`, `with eight data-poor sites, better in ${SITES[2].wins} of ${SITES[2].n} worlds.`, C.teal],
    ["0 rounds", `lost to a liar with the consistency check: ${CHECK.liar_caught} of ${CHECK.liar_notes} lies caught, ${CHECK.honest_dropped} honest notes dropped.`, C.amber],
    ["9 µm", "size error from a corrected design, against 132 µm drawn as-is (median, 60 worlds).", C.ink],
  ];
  stats.forEach(([big, sub, col], i) => {
    const x = M + i * 2.25;
    card(s, x, 1.55, 2.08, 2.7);
    T(s, big, { x: x + 0.2, y: 1.8, w: 1.8, h: 0.75, fontFace: HEAD, fontSize: big.length > 4 ? 26 : 36, bold: true, color: col, valign: "middle" });
    T(s, sub, { x: x + 0.2, y: 2.75, w: 1.72, h: 1.7, fontSize: 12.5, color: C.muted });
  });
  foot(s, "Hidden-truth simulation, registered config, paired per world. The consistency check is an added option, off in the registered config. The agent layer adds nothing measurable. At two sites the gain is 1.6 µm, below what a real part can show.");
  s.addNotes("1:10–1:40. Simulation numbers, said plainly. The gain comes from sharing between sites, not from the agents. It grows with the number of data-poor sites. And what a lab actually gets is a corrected design: 9 µm off instead of 132.");

  // 6 · rigor
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Rigor", "A real printer for scale, simulation to score");
  const tl = [
    ["Registered first", "Claims and the prediction that two printers can't show the gain were committed before printing."],
    ["Negative control", "When printers share no physics, sharing gains nothing. The gain isn't built into the scoring."],
    ["Why simulation", "The two-site gain is 1.6 µm; two readings of one pin differ by 65 µm. Only hidden truth can score it."],
  ];
  tl.forEach(([h, d], i) => {
    const y = 1.6 + i * 1.0;
    s.addShape(pres.shapes.OVAL, { x: M, y: y + 0.04, w: 0.22, h: 0.22, fill: { color: C.accent }, line: { color: C.accent } });
    if (i < 2) s.addShape(pres.shapes.LINE, { x: M + 0.11, y: y + 0.3, w: 0, h: 0.72, line: { color: C.line, width: 1.5 } });
    T(s, h, { x: M + 0.45, y, w: 4.4, h: 0.32, fontFace: HEAD, fontSize: 15, bold: true });
    T(s, d, { x: M + 0.45, y: y + 0.33, w: 4.4, h: 0.6, fontSize: 12.5, color: C.muted });
  });
  card(s, 5.7, 1.5, 3.75, 3.2, C.card2);
  T(s, "REAL PRINTER · FORM STUDIO 1", { x: 5.95, y: 1.7, w: 3.3, h: 0.25, fontSize: 9.5, bold: true, charSpacing: 2, color: C.teal });
  T(s, [{ text: "1.44", options: { fontSize: 48, bold: true, color: C.ink } }, { text: " mm", options: { fontSize: 20, color: C.muted } }],
    { x: 5.95, y: 2.0, w: 3.3, h: 0.85, fontFace: HEAD, valign: "middle" });
  T(s, "a 1.50 mm pin, by micrometer (two readings: 1.41 and 1.48)", { x: 5.95, y: 2.85, w: 3.3, h: 0.45, fontSize: 12, color: C.muted });
  const checks = [["Inside the vendor's ±0.08 mm spec", C.teal], ["Inside the simulator, at its small edge", C.amber], ["One pin: a sanity check, not a model fit", C.muted]];
  checks.forEach(([t, col], i) => T(s, [{ text: "●  ", options: { color: col } }, { text: t, options: { color: C.ink } }],
    { x: 5.95, y: 3.45 + i * 0.36, w: 3.35, h: 0.32, fontSize: 12 }));
  s.addNotes("1:40–2:05. Hold up the printed plate. The real printer tells us the simulator is the right size: this pin is inside its range, at the small edge (1.8th percentile), so say 'edge', not 'middle'. The negative control shows the simulator doesn't hand us the result. Don't claim a fit on the real printer.");

  // 7 · who it's for
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Who it's for", "Medical and bio labs that print and can't pool data");
  const who = [
    ["FaHospital", "Hospital 3D-printing labs", "Surgical guides and anatomical models from patient scans. The scans stay in-house."],
    ["FaTooth", "Dental labs", "Crowns, models and aligners must seat first time. Patient data can't be pooled."],
    ["FaMicroscope", "Bio and microfluidics labs", "Lab-on-chip and organ-on-chip parts with sub-mm features. Recipes are IP."],
    ["FaIndustry", "Medical device makers", "One part, many contract printers. Receipts double as an audit trail."],
  ];
  for (const [i, [ic, h, d]] of who.entries()) {
    const x = M + (i % 2) * 2.85, y = 1.5 + Math.floor(i / 2) * 1.62;
    card(s, x, y, 2.7, 1.47);
    await tile(s, ic, x + 0.2, y + 0.2, 0.44);
    T(s, h, { x: x + 0.78, y: y + 0.2, w: 1.8, h: 0.44, fontFace: HEAD, fontSize: 12.5, bold: true, valign: "middle" });
    T(s, d, { x: x + 0.2, y: y + 0.75, w: 2.35, h: 0.68, fontSize: 11, color: C.muted });
  }
  card(s, 6.35, 1.5, 3.1, 3.09);
  s.addChart(pres.charts.BAR, [{ name: "Lower error than alone", labels: SITES.map((r) => `${r.sites} labs`), values: SITES.map((r) => Math.round(r.pct)) }], {
    x: 6.45, y: 1.58, w: 2.9, h: 2.95, barDir: "col", chartColors: [C.accent], barGapWidthPct: 55,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelColor: C.ink, dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt",
    showTitle: true, title: "Value grows with every lab that joins", titleFontSize: 11, titleColor: C.ink, titleFontFace: "+mn-lt",
    showLegend: false, catAxisLabelColor: C.muted, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", catAxisLineShow: false,
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 42,
  });
  foot(s, "Buyers are our hypothesis, not yet validated with customers. Chart: lower error than learning alone at 2 / 4 / 8 data-poor sites, simulation. On sub-millimetre features the gain holds at 7–9% in simulation; bioprinting is direction, not a result.");
  s.addNotes("2:05–2:45. Name the buyer and why pooling is off the table: patient data and process IP. Then the bars: value grows with every lab that joins, a network effect. If asked about bioprinting: the gain holds on sub-mm features in simulation; real bioprinting is the direction, not a result.");

  // 8 · close
  s = pres.addSlide({ masterName: "DARK" });
  s.addImage({ data: LOGO, x: M, y: 1.2, w: 0.75, h: 0.75, altText: "Prebuilt logo" });
  T(s, "Print anywhere, trust the part", { x: M, y: 2.15, w: 9, h: 0.8, fontFace: HEAD, fontSize: 38, bold: true });
  T(s, "Labs learn their printers together. Their data stays home.", { x: M, y: 2.95, w: 9, h: 0.5, fontSize: 18, color: C.accent });
  T(s, "github.com/matte-realize/prebuilt  ·  all sharing results in simulation", { x: M, y: 4.55, w: 9, h: 0.3, fontSize: 11, color: C.faint });
  s.addNotes("2:45–3:00. End on the line. Stop talking.");

  // 9 · appendix
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Appendix · validation and benchmarks", "Many sites beat one; agents don't beat random");
  const H = (t) => ({ text: t, options: { bold: true, color: C.muted, fontSize: 10, fill: { color: C.card2 } } });
  const rows = [
    [H("Round 3, paired simulated worlds"), H("Gain"), H("Worlds better"), H("p")],
    ["Network vs single site alone", "12.3% (1.6 µm)", "75 / 100", "<0.001"],
    ["Pooled raw data (upper bound) vs alone", "12.2%", "64 / 100", ""],
    ["Agents only, messages cut, vs alone", "2.4%", "56 / 100", "0.27"],
    ["Agent auction vs random pieces", "+1.0%", "31 / 60", "0.90"],
    ["4 / 8 data-poor sites vs alone", `${SITES[1].pct.toFixed(1)}% / ${SITES[2].pct.toFixed(1)}%`, `${SITES[1].wins}/${SITES[1].n} · ${SITES[2].wins}/${SITES[2].n}`, "<0.001"],
    ["Negative control: nothing shared", "−13.0% (adaptive spread −0.4%)", "19 / 60", "0.006"],
  ];
  s.addTable(rows.map((r, i) => r.map((c) => (typeof c === "string" ? { text: c, options: { fill: { color: i % 2 ? C.card : C.bg } } } : c))), {
    x: M, y: 1.5, w: W - 2 * M, colW: [3.5, 2.7, 1.6, 1.1], fontFace: BODY, fontSize: 12, color: C.ink,
    border: { type: "solid", pt: 0.5, color: C.line }, rowH: 0.37, valign: "middle", margin: [0.03, 0.1, 0.03, 0.1] });
  foot(s, "Hidden-truth simulator, registered config, error against true size on held-out pieces, sign test over worlds. 90% intervals cover 90–91%. GPU posterior up to 84× NumPy on an H100. Reproduce: docs/validation-and-benchmarks.md.");
  s.addNotes("Backup for Q&A: the multi-agent vs single-agent comparison. Many sites beat one site; many agents inside a site don't beat random. Say both.");

  const out = path.join(__dirname, "prebuilt-pitch.pptx");
  await pres.writeFile({ fileName: out });
  console.log(out);
}

main().catch((e) => { console.error(e); process.exit(1); });
