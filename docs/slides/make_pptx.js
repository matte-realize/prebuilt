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

  // 1 · title + problem
  s = pres.addSlide({ masterName: "DARK" });
  s.addImage({ data: LOGO, x: M, y: 0.5, w: 0.62, h: 0.62, altText: "Prebuilt logo" });
  T(s, "Prebuilt", { x: M + 0.8, y: 0.5, w: 4, h: 0.62, fontFace: HEAD, fontSize: 36, bold: true, valign: "middle" });
  T(s, "Every printer learns from every other. No data leaves.", { x: M, y: 1.3, w: 9, h: 0.5, fontFace: HEAD, fontSize: 22, bold: true, color: C.accent });
  const prob = [
    ["FaPrint", "Every printer is wrong in its own way", "Holes print up to 250 µm small and pins up to 195 µm large (desktop SLA, CMM; Tehnički vjesnik 2026)."],
    ["FaTooth", "In medicine, that decides the fit", "Crowns, surgical guides and microfluidic chips must fit first time. A crown margin allows ~120 µm."],
    ["FaLock", "And labs can't pool what they learn", "Patient scans and process recipes can't leave, so every lab re-learns its printer from scratch."],
  ];
  for (const [i, [ic, h, d]] of prob.entries()) {
    const y = 2.05 + i * 0.88;
    await tile(s, ic, M, y, 0.52);
    T(s, h, { x: M + 0.75, y: y - 0.02, w: 5.2, h: 0.32, fontFace: HEAD, fontSize: 14, bold: true });
    T(s, d, { x: M + 0.75, y: y + 0.3, w: 5.2, h: 0.5, fontSize: 12, color: C.muted });
  }
  card(s, 6.55, 1.95, 2.9, 2.85, C.card);
  plate(s, 6.85, 2.12, 2.3);
  T(s, "The test plate: 24 pins and holes. Print it, measure it, know your printer.", { x: 6.8, y: 4.45, w: 2.45, h: 0.32, fontSize: 9.5, color: C.muted });
  s.addNotes("0:00–0:40. Hold up the printed plate. Every printer is wrong in its own way: published measurements show desktop resin printers missing by up to a quarter of a millimetre. In a hospital or dental lab that decides whether a crown seats or a guide fits. And those labs can't pool what they learn, because patient scans and process recipes can't leave. So every lab starts from scratch. Prebuilt: every printer learns from every other, and no data leaves.");

  // 2 · how it works
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "How it works", "Learn locally, share three numbers");
  const steps = [
    ["FaPrint", "1  Print a test plate", "24 pins and holes, measured by micrometer or flatbed scanner."],
    ["FaRulerCombined", "2  Learn your printer", "A physics model of your machine, fit locally on your own data."],
    ["FaExchangeAlt", "3  Share three numbers", "Mean and spread of 3 parameters every printer shares, logged on a receipt."],
  ];
  for (const [i, [ic, h, d]] of steps.entries()) {
    const x = M + i * 3.0;
    card(s, x, 1.5, 2.8, 1.85);
    await tile(s, ic, x + 0.25, 1.7, 0.48);
    T(s, h, { x: x + 0.25, y: 2.32, w: 2.35, h: 0.33, fontFace: HEAD, fontSize: 14, bold: true });
    T(s, d, { x: x + 0.25, y: 2.68, w: 2.35, h: 0.6, fontSize: 12, color: C.muted });
  }
  card(s, M, 3.52, W - 2 * M, 0.6, C.card2);
  await tile(s, "FaLock", M + 0.18, 3.6, 0.44, C.teal);
  T(s, [{ text: "Never leaves the lab: ", options: { bold: true, color: C.teal } },
        { text: "patient scans, part geometry, measurements, machine settings. A replayable audit checks every crossing.", options: { color: C.ink } }],
    { x: M + 0.8, y: 3.52, w: 8.0, h: 0.6, fontSize: 12.5, valign: "middle" });
  card(s, M, 4.25, W - 2 * M, 0.6, C.card2);
  T(s, [{ text: "What's new: ", options: { bold: true, color: C.accent } },
        { text: "correcting printer error (Huang et al. 2015) and learning across printers (Wei et al. 2023) are proven, but pool the data. Prebuilt does it privately.", options: { color: C.ink } }],
    { x: M + 0.25, y: 4.25, w: W - 2 * M - 0.5, h: 0.6, fontSize: 12.5, valign: "middle" });
  s.addNotes("0:40–1:15. Each lab prints this plate and fits a model of its own machine, locally. The only thing that leaves is three numbers, logged on a receipt, and an audit replays every crossing. Every ingredient is published: correcting printer error from a learned model works, and printers learn faster together. What nobody had done is that without the data leaving the lab.");

  // 3 · results
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Results · simulation", "Parts that fit, and new labs get there faster");
  const stats = [
    ["9 µm", "size error from a corrected design, against 132 µm drawn as-is.", C.accent],
    [`${Math.round(SITES[2].pct)}%`, `lower error for data-poor labs when eight share (won ${SITES[2].wins} of ${SITES[2].n} fleets).`, C.teal],
    ["12%", "lower error with just two labs, matching pooling all raw data.", C.ink],
    ["0 rounds", `lost to a lying lab: ${CHECK.liar_caught} of ${CHECK.liar_notes} lies caught, ${CHECK.honest_dropped} honest notes dropped.`, C.amber],
  ];
  stats.forEach(([big, sub, col], i) => {
    const x = M + i * 2.25;
    card(s, x, 1.45, 2.08, 2.0);
    T(s, big, { x: x + 0.2, y: 1.62, w: 1.8, h: 0.65, fontFace: HEAD, fontSize: big.length > 4 ? 24 : 32, bold: true, color: col, valign: "middle" });
    T(s, sub, { x: x + 0.2, y: 2.35, w: 1.72, h: 1.05, fontSize: 12, color: C.muted });
  });
  const rig = [
    ["Registered first", "Claims committed, with a hash, before the first print."],
    ["Negative control", "Printers that share no physics gain nothing: the gain is real."],
    ["Real printer", "A Form Studio 1 pin: 1.44 mm for 1.50, inside the ±0.08 mm spec."],
  ];
  rig.forEach(([h, d], i) => {
    const x = M + i * 3.0;
    card(s, x, 3.62, 2.8, 1.15, C.card2);
    T(s, h, { x: x + 0.22, y: 3.75, w: 2.4, h: 0.3, fontFace: HEAD, fontSize: 13, bold: true, color: C.teal });
    T(s, d, { x: x + 0.22, y: 4.08, w: 2.4, h: 0.65, fontSize: 11.5, color: C.muted });
  });
  s.addNotes("1:15–2:10. In simulation, scored against the true printed size. What a lab gets: a corrected design that misses by 9 microns instead of 132. What the network adds: labs with little data get 35% lower error when eight share, so new labs need fewer test prints. Even two labs match pooling all the raw data, and a lying lab costs nothing with the consistency check. Underneath: claims registered before printing, a negative control showing the gain is real, and a real Form Studio 1 pin inside the vendor spec.");

  // 4 · who + where + close
  s = pres.addSlide({ masterName: "DARK" });
  head(s, "Who it's for", "For anyone whose precision is a trade secret");
  const groups = [
    ["NOW · MEDICAL AND BIO", C.accent, [["FaHospital", "Hospital 3D-printing labs"], ["FaTooth", "Dental labs"], ["FaMicroscope", "Bio and microfluidics labs"]]],
    ["NEXT · HIGH-PRECISION INDUSTRY", C.amber, [["FaMicrochip", "Chip makers, GPU packaging"], ["FaShieldAlt", "Defense and aerospace"], ["FaCogs", "MEMS and nanotech"]]],
  ];
  for (const [g, [lbl, col, items]] of groups.entries()) {
    const y0 = 1.45 + g * 1.0;
    T(s, lbl, { x: M, y: y0, w: 6, h: 0.22, fontSize: 9.5, bold: true, charSpacing: 2, color: col });
    for (const [i, [ic, h]] of items.entries()) {
      const x = M + i * 3.0, y = y0 + 0.28;
      card(s, x, y, 2.8, 0.6);
      await tile(s, ic, x + 0.12, y + 0.1, 0.4, col);
      T(s, h, { x: x + 0.65, y, w: 2.1, h: 0.6, fontFace: HEAD, fontSize: 12, bold: true, valign: "middle" });
    }
  }
  card(s, M, 3.5, W - 2 * M, 0.55, C.card2);
  T(s, [{ text: "Value grows with every member: ", options: { bold: true, color: C.accent } },
        { text: `${Math.round(SITES[0].pct)}% → ${Math.round(SITES[1].pct)}% → ${Math.round(SITES[2].pct)}% lower error at 2 / 4 / 8 labs. From microns today to nanometres next.`, options: { color: C.ink } }],
    { x: M + 0.25, y: 3.5, w: W - 2 * M - 0.5, h: 0.55, fontSize: 12.5, valign: "middle" });
  s.addImage({ data: LOGO, x: M, y: 4.3, w: 0.45, h: 0.45, altText: "Prebuilt logo" });
  T(s, "Print anywhere, trust the part.", { x: M + 0.6, y: 4.28, w: 6, h: 0.5, fontFace: HEAD, fontSize: 24, bold: true, valign: "middle" });
  T(s, "github.com/matte-realize/prebuilt", { x: 6.6, y: 4.38, w: 2.85, h: 0.3, fontSize: 11, color: C.faint, align: "right", valign: "middle" });
  s.addNotes("2:10–3:00. Who needs this: anyone whose precision is a trade secret. Today, hospital, dental and bio labs that legally can't pool patient data. Next, chip makers and GPU packaging lines where every nanometre is yield, defense and aerospace under export control, MEMS and nanotech. Same problem, same constraint, and the network gets more valuable with every member. From microns today to nanometres next. Print anywhere, trust the part.");

  const out = path.join(__dirname, "prebuilt-pitch.pptx");
  await pres.writeFile({ fileName: out });
  console.log(out);
}

main().catch((e) => { console.error(e); process.exit(1); });
