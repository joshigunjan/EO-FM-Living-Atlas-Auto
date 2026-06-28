const landscape = {
  data: [],
  filtered: [],
  selectedId: null,
  labelMode: false,
  xMetric: "modality_stage",
  yMetric: "reported_tasks"
};

const L = {
  search: document.getElementById("landscapeSearch"),
  open: document.getElementById("landscapeOpen"),
  modality: document.getElementById("landscapeModality"),
  task: document.getElementById("landscapeTask"),
  architecture: document.getElementById("landscapeArchitecture"),
  family: document.getElementById("landscapeFamily"),
  xMetric: document.getElementById("xMetric"),
  yMetric: document.getElementById("yMetric"),
  labels: document.getElementById("showLabels"),
  reset: document.getElementById("landscapeReset"),
  plot: document.getElementById("landscapePlot"),
  count: document.getElementById("landscapeCount"),
  legend: document.getElementById("landscapeLegend"),
  familyLegend: document.getElementById("familyLegend"),
  title: document.getElementById("landscapeTitle"),
  details: document.getElementById("landscapeDetails"),
  axisHint: document.getElementById("axisHint")
};
const OPENNESS_COLORS = {
  open: "#16a34a",
  partial: "#f59e0b",
  closed: "#ef4444",
  unknown: "#64748b"
};

function opennessKey(d) {
  const o = String(d.openness || d.openness_label || "unknown").toLowerCase();
  if (o.includes("open") && !o.includes("partial")) return "open";
  if (o.includes("partial")) return "partial";
  if (o.includes("closed")) return "closed";
  return "unknown";
}

function pointColor(d) {
  return OPENNESS_COLORS[opennessKey(d)] || OPENNESS_COLORS.unknown;
}

function uniq(arr) {
  return [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[c]));
}

function accessTextFromValue(value) {
  const v = String(value || "").toLowerCase();
  if (v.includes("open")) return "Open source";
  if (v.includes("partial")) return "Partial access";
  if (v.includes("closed")) return "Closed source";
  return value || "Unknown";
}

function truncate(s, n = 145) {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function tag(text, cls = "") {
  return `<span class="badge ${cls}">${escapeHtml(text || "unknown")}</span>`;
}

function linkButton(label, url) {
  if (!url) return "";
  return `<a class="link-pill" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function hash01(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000;
}

function modalityCount(d) {
  const tags = (d.modality_tags || []).length;
  const text = String(d.input_modality || "");
  const match = text.match(/(^|\s)(\d{1,2})\s+(?:reported\s+)?(?:geospatial\s+)?modalit/i);
  const reported = match ? Number(match[2]) : 0;
  return Math.max(tags, reported, 1);
}

function taskCount(d) {
  return Math.max((d.task_tags || []).length, 1);
}

function reportedTaskCount(d) {
  const n = Number(d.reported_downstream_task_count);
  return Number.isFinite(n) && n > 0 ? n : taskCount(d);
}

function architectureCount(d) {
  return Math.max((d.architecture_tags || []).length, 1);
}

function linkCount(d) {
  return [d.paper_url, d.code_url, d.weights_url, d.project_url].filter(Boolean).length;
}

function opennessScore(d) {
  const o = String(d.openness || "unknown").toLowerCase();
  if (o === "open") return 3;
  if (o === "partial") return 2;
  if (o === "unknown") return 1;
  return 0;
}

function modalityComplexity(d) {
  const tags = new Set((d.modality_tags || []).map(x => String(x).toLowerCase()));
  const text = `${d.input_modality || ""} ${d.architecture || ""} ${d.scope || ""}`.toLowerCase();
  let score = modalityCount(d);
  if (text.includes("multi-sensor") || text.includes("multisensor")) score += 0.5;
  if (text.includes("multimodal") || text.includes("multi-modal")) score += 0.5;
  if (text.includes("any-to-any") || text.includes("sensor-agnostic")) score += 0.75;
  if (tags.has("text")) score += 0.5;
  if (tags.has("climate")) score += 0.5;
  if (tags.has("sar") && tags.has("optical")) score += 0.5;
  return Number(score.toFixed(2));
}

const FAMILIES = {
  transformer_masked: {
    label: "Transformer / masked-reconstruction encoder",
    short: "Transformer / MAE",
    shape: "circle"
  },
  joint_embedding: {
    label: "Joint-embedding / contrastive-predictive encoder",
    short: "Joint embedding",
    shape: "square"
  },
  vision_language: {
    label: "Vision-language / EO MLLM",
    short: "VLM / MLLM",
    shape: "triangle"
  },
  state_space: {
    label: "State-space / sequence model",
    short: "State-space",
    shape: "diamond"
  },
  embedding_field: {
    label: "Embedding product / representation field",
    short: "Embedding field",
    shape: "cross"
  },
  generative_hybrid: {
    label: "Any-to-any generative / hybrid multimodal system",
    short: "Generative / hybrid",
    shape: "downTriangle"
  }
};

function combinedText(d) {
  return [d.name, d.category, d.scope, d.modelling_paradigm, d.input_modality, d.architecture, d.downstream_tasks, ...(d.modality_tags || []), ...(d.architecture_tags || []), ...(d.task_tags || [])].join(" ").toLowerCase();
}

function modelFamilyKey(d) {
  if (d.modelling_paradigm_key && FAMILIES[d.modelling_paradigm_key]) return d.modelling_paradigm_key;
  if (d.modelling_paradigm) {
    const found = Object.entries(FAMILIES).find(([_, f]) => f.label === d.modelling_paradigm || f.short === d.modelling_paradigm);
    if (found) return found[0];
  }
  const text = combinedText(d);
  const name = String(d.name || "").toLowerCase();
  if (text.includes("mamba") || text.includes("state space") || text.includes("state-space")) return "state_space";
  if (text.includes("any-to-any") || text.includes("thinking-in-modalities") || text.includes("modality-to-modality") || name.includes("terramind") || name.includes("dofa+")) return "generative_hybrid";
  if (name.includes("alphaearth") || name.includes("tessera") || text.includes("embedding field") || text.includes("representation field") || text.includes("embedding product")) return "embedding_field";
  if (text.includes("vision-language") || text.includes("vision language") || text.includes("large language") || text.includes("mllm") || text.includes("llm") || text.includes("caption") || text.includes("vqa") || (d.modality_tags || []).map(x => String(x).toLowerCase()).includes("text")) return "vision_language";
  if (text.includes("contrastive") || text.includes("clip") || text.includes("dino") || text.includes("byol") || text.includes("jepa") || text.includes("predictive") || text.includes("alignment") || text.includes("joint-embedding") || text.includes("joint embedding")) return "joint_embedding";
  return "transformer_masked";
}

function modelFamilyLabel(d) {
  const f = FAMILIES[modelFamilyKey(d)] || FAMILIES.transformer_masked;
  return d.modelling_paradigm || f.label;
}

function modalityStage(d) {
  const explicit = Number(d.modality_complexity_score);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const key = String(d.modality_complexity_tier_key || "").toLowerCase();
  if (key.includes("single")) return 1;
  if (key.includes("multi")) return 2;
  if (key.includes("vision") || key.includes("language")) return 3;
  if (key.includes("general")) return 4;
  const text = combinedText(d);
  const name = String(d.name || "").toLowerCase();
  if (text.includes("any-to-any") || text.includes("generalist") || text.includes("earth system") || text.includes("embedding field") || text.includes("representation field") || name.includes("terramind") || name.includes("alphaearth") || name.includes("olmoearth") || name.includes("thor")) return 4;
  if (text.includes("vision-language") || text.includes("vision language") || text.includes("mllm") || text.includes("llm") || (d.modality_tags || []).map(x => String(x).toLowerCase()).includes("text")) return 3;
  if (modalityCount(d) > 1) return 2;
  return 1;
}
const METRICS = {
  modality_stage: {
    label: "Modality complexity",
    axis: "Modality complexity",
    desc: "Curated tier: single-modality, multi-modality, vision-language/MLLM, or generalist models.",
    value: modalityStage,
    integer: true,
    min: 0.65,
    max: 4.35,
    fixedTicks: [1, 2, 3, 4],
    tickFormat: v => ({1: "Single-modality", 2: "Multi-modality", 3: "VLM / MLLM", 4: "Generalist"}[Math.round(v)] ?? String(v)),
    tickLines: v => ({
      1: ["Single-modality", "encoders"],
      2: ["Multi-modality", "encoders"],
      3: ["Vision-language", "/ MLLM"],
      4: ["Generalist", "models"]
    }[Math.round(v)] || [String(v)])
  },
  modalities: {
    label: "Modality breadth",
    axis: "Recorded modality inputs",
    desc: "Number of modalities recorded for each model.",
    value: modalityCount,
    integer: true,
    min: 1
  },
  reported_tasks: {
    label: "Reported downstream evaluations",
    axis: "Reported downstream evaluations",
    desc: "Curated count of reported downstream tasks or evaluations from the source paper.",
    value: reportedTaskCount,
    integer: true,
    min: 1
  },
  tasks: {
    label: "Task-label coverage",
    axis: "Recorded task labels",
    desc: "Number of task labels recorded for filtering and search.",
    value: taskCount,
    integer: true,
    min: 1
  },
  modality_complexity: {
    label: "Modality complexity score",
    axis: "Modality complexity score",
    desc: "Heuristic score from modality breadth plus multimodal, sensor-agnostic, text, climate, and SAR-optical signals.",
    value: modalityComplexity,
    integer: false,
    min: 1
  },
  architecture_breadth: {
    label: "Architecture breadth",
    axis: "Architecture tags",
    desc: "Number of architecture tags recorded for the model.",
    value: architectureCount,
    integer: true,
    min: 1
  },
  openness_score: {
    label: "Access score",
    axis: "Access score",
    desc: "Closed = 0, unknown = 1, partial = 2, open = 3.",
    value: opennessScore,
    integer: true,
    min: 0,
    tickFormat: v => ({0: "Closed", 1: "Unknown", 2: "Partial", 3: "Open"}[Math.round(v)] ?? String(v))
  },
  link_availability: {
    label: "Source-link availability",
    axis: "Available source links",
    desc: "Count of available paper, code, weights, and project links.",
    value: linkCount,
    integer: true,
    min: 0
  }
};

function rowText(d) {
  return [combinedText(d), d.openness_label, d.openness, modelFamilyLabel(d)].join(" ").toLowerCase();
}

function buildFilters() {
  Object.entries(METRICS).forEach(([key, metric]) => {
    const opt = `<option value="${key}">${escapeHtml(metric.label)}</option>`;
    L.xMetric.insertAdjacentHTML("beforeend", opt);
    L.yMetric.insertAdjacentHTML("beforeend", opt);
  });
  L.xMetric.value = landscape.xMetric;
  L.yMetric.value = landscape.yMetric;

  for (const o of uniq(landscape.data.map(d => d.openness_label || d.openness))) {
    L.open.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(o)}">${escapeHtml(accessTextFromValue(o))}</option>`);
  }
  for (const m of uniq(landscape.data.flatMap(d => d.modality_tags || []))) {
    L.modality.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`);
  }
  for (const t of uniq(landscape.data.flatMap(d => d.task_tags || []))) {
    L.task.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`);
  }
  for (const a of uniq(landscape.data.flatMap(d => d.architecture_tags || []))) {
    L.architecture.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`);
  }
  Object.entries(FAMILIES).forEach(([key, f]) => {
    L.family.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(key)}">${escapeHtml(f.short)}</option>`);
  });
}

function applyFilters() {
  const q = L.search.value.trim().toLowerCase();
  const open = L.open.value;
  const modality = L.modality.value;
  const task = L.task.value;
  const architecture = L.architecture.value;
  const family = L.family.value;
  landscape.xMetric = L.xMetric.value || "modalities";
  landscape.yMetric = L.yMetric.value || "tasks";

  landscape.filtered = landscape.data.filter(d => {
    if (q && !rowText(d).includes(q)) return false;
    if (open && (d.openness_label || d.openness) !== open) return false;
    if (modality && !(d.modality_tags || []).includes(modality)) return false;
    if (task && !(d.task_tags || []).includes(task)) return false;
    if (architecture && !(d.architecture_tags || []).includes(architecture)) return false;
    if (family && modelFamilyKey(d) !== family) return false;
    return true;
  });
  renderLandscape();
}

function opennessClass(d) {
  return `point-${opennessKey(d)}`;
}

function renderLegendShape(key, size = 14) {
  const f = FAMILIES[key] || FAMILIES.transformer_masked;
  const cx = 12, cy = 12, r = size / 2;
  return `<svg class="legend-shape" viewBox="0 0 24 24" aria-hidden="true">${shapeSvg(f.shape, cx, cy, r, "legend-shape-mark", "#ffffff", "#334155", "2.3")}</svg>`;
}

function renderLegend() {
  const colorItems = [
    ["open", "Open source"],
    ["partial", "Partial access"],
    ["closed", "Closed source"],
    ["unknown", "Unknown"]
  ];
  L.legend.innerHTML = colorItems.map(([key, label]) =>
    `<span class="legend-item"><span class="legend-dot" style="background:${OPENNESS_COLORS[key]}; border-color:${OPENNESS_COLORS[key]}"></span>${label}</span>`
  ).join("");

  L.familyLegend.innerHTML = Object.entries(FAMILIES).map(([key, f]) =>
    `<span class="legend-item family-legend-item">${renderLegendShape(key)}${escapeHtml(f.short)}</span>`
  ).join("");
}

function niceTicks(min, max, integer = true, count = 6) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    min = min - 1;
    max = max + 1;
  }
  const span = max - min;
  const raw = span / Math.max(1, count - 1);
  const power = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const steps = [1, 2, 2.5, 5, 10].map(s => s * power);
  const step = steps.find(s => s >= raw) || steps[steps.length - 1];
  let start = Math.floor(min / step) * step;
  let end = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) {
    let val = Number(v.toFixed(2));
    if (integer && Math.abs(val - Math.round(val)) < 1e-8) val = Math.round(val);
    ticks.push(val);
  }
  return integer ? uniq(ticks.map(String)).map(Number) : ticks;
}

function formatTick(metric, value) {
  if (metric.tickFormat) return metric.tickFormat(value);
  if (metric.integer) return String(Math.round(value));
  return Number(value).toFixed(value % 1 === 0 ? 0 : 1);
}

function axisDomain(values, metric) {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return [0, 1];
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (metric.min !== undefined) min = Math.min(metric.min, min);
  if (metric.max !== undefined) max = Math.max(metric.max, max);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.08 || 1;
  return [min - pad, max + pad];
}


function polygonPoints(points) {
  return points.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
}

function starPoints(cx, cy, outer, inner, count = 5) {
  const pts = [];
  for (let i = 0; i < count * 2; i++) {
    const angle = -Math.PI / 2 + i * Math.PI / count;
    const rad = i % 2 === 0 ? outer : inner;
    pts.push([cx + Math.cos(angle) * rad, cy + Math.sin(angle) * rad]);
  }
  return polygonPoints(pts);
}

function svgStyle(fill, stroke, strokeWidth) {
  const parts = [];
  if (fill) parts.push(`fill:${fill}`);
  if (stroke) parts.push(`stroke:${stroke}`);
  if (strokeWidth) parts.push(`stroke-width:${strokeWidth}`);
  return parts.length ? ` style="${parts.join(';')}"` : "";
}

function shapeSvg(shape, cx, cy, r, cls = "", fill = "", stroke = "", strokeWidth = "") {
  const classAttr = cls ? ` class="${cls}"` : "";
  const styleAttr = svgStyle(fill, stroke, strokeWidth);
  if (shape === "square") {
    const s = r * 1.65;
    return `<rect x="${(cx - s / 2).toFixed(1)}" y="${(cy - s / 2).toFixed(1)}" width="${s.toFixed(1)}" height="${s.toFixed(1)}" rx="${(r * 0.12).toFixed(1)}"${classAttr}${styleAttr}></rect>`;
  }
  if (shape === "diamond") {
    return `<polygon points="${polygonPoints([[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]])}"${classAttr}${styleAttr}></polygon>`;
  }
  if (shape === "triangle") {
    return `<polygon points="${polygonPoints([[cx, cy - r], [cx + r * 0.98, cy + r * 0.78], [cx - r * 0.98, cy + r * 0.78]])}"${classAttr}${styleAttr}></polygon>`;
  }
  if (shape === "downTriangle") {
    return `<polygon points="${polygonPoints([[cx - r * 0.98, cy - r * 0.78], [cx + r * 0.98, cy - r * 0.78], [cx, cy + r]])}"${classAttr}${styleAttr}></polygon>`;
  }
  if (shape === "cross") {
    const a = r * 1.02, b = r * 0.34;
    const pts = [[cx-b,cy-a],[cx+b,cy-a],[cx+b,cy-b],[cx+a,cy-b],[cx+a,cy+b],[cx+b,cy+b],[cx+b,cy+a],[cx-b,cy+a],[cx-b,cy+b],[cx-a,cy+b],[cx-a,cy-b],[cx-b,cy-b]];
    return `<polygon points="${polygonPoints(pts)}"${classAttr}${styleAttr}></polygon>`;
  }
  return `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}"${classAttr}${styleAttr}></circle>`;
}

function pointRadius(d) {
  return Math.max(6.5, Math.min(15, 5.5 + Math.sqrt(taskCount(d) + modalityCount(d)) * 1.5));
}

function renderLandscape() {
  const w = 1160, h = 700;
  const m = { left: 92, right: 54, top: 46, bottom: 94 };
  const innerW = w - m.left - m.right;
  const innerH = h - m.top - m.bottom;
  const all = landscape.data;
  const visible = landscape.filtered;
  const xMetric = METRICS[landscape.xMetric] || METRICS.modalities;
  const yMetric = METRICS[landscape.yMetric] || METRICS.tasks;
  const xValues = visible.map(d => xMetric.value(d));
  const yValues = visible.map(d => yMetric.value(d));
  const [xMin, xMax] = axisDomain(xValues, xMetric);
  const [yMin, yMax] = axisDomain(yValues, yMetric);
  const xScale = x => m.left + ((x - xMin) / Math.max(0.001, xMax - xMin)) * innerW;
  const yScale = y => m.top + (1 - ((y - yMin) / Math.max(0.001, yMax - yMin))) * innerH;
  const ticksX = (xMetric.fixedTicks || niceTicks(xMin, xMax, xMetric.integer, 7)).filter(v => v >= xMin - 1e-6 && v <= xMax + 1e-6);
  const ticksY = (yMetric.fixedTicks || niceTicks(yMin, yMax, yMetric.integer, 7)).filter(v => v >= yMin - 1e-6 && v <= yMax + 1e-6);

  L.count.textContent = `${visible.length} of ${all.length} entries shown`;
  L.axisHint.textContent = `X: ${xMetric.label}. Y: ${yMetric.label}. Click a point to inspect.`;

  L.plot.setAttribute("viewBox", `0 0 ${w} ${h}`);
  L.plot.setAttribute("preserveAspectRatio", "xMidYMid meet");
  L.plot.setAttribute("aria-label", `Scatter plot of ${xMetric.label} versus ${yMetric.label}`);

  let svg = "";
  svg += `<defs>`;
  svg += `<linearGradient id="plotBg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#f1f7ff"/></linearGradient>`;
  svg += `<filter id="softShadow" x="-40%" y="-40%" width="180%" height="180%"><feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#0f172a" flood-opacity="0.16"/></filter>`;
  svg += `</defs>`;
  svg += `<rect x="0" y="0" width="${w}" height="${h}" rx="26" fill="#ffffff"/>`;
  svg += `<rect x="${m.left}" y="${m.top}" width="${innerW}" height="${innerH}" rx="18" fill="url(#plotBg)" stroke="#e2e8f0"/>`;

  if (landscape.xMetric === "modality_stage") {
    const bands = [
      [1, "Single-modality"], [2, "Multi-modality"], [3, "Vision-language / MLLM"], [4, "Generalist"]
    ];
    bands.forEach(([v, label], i) => {
      const x0 = Math.max(m.left, xScale(v - 0.5));
      const x1 = Math.min(m.left + innerW, xScale(v + 0.5));
      svg += `<rect x="${x0.toFixed(1)}" y="${m.top}" width="${Math.max(0, x1 - x0).toFixed(1)}" height="${innerH}" fill="${i % 2 ? "#f8fbff" : "#ffffff"}" opacity="0.72"></rect>`;
      svg += `<text x="${xScale(v).toFixed(1)}" y="${(m.top + 24).toFixed(1)}" text-anchor="middle" class="band-label">${escapeHtml(label)}</text>`;
    });
  }

  ticksX.forEach(t => {
    const x = xScale(t);
    svg += `<line x1="${x}" y1="${m.top}" x2="${x}" y2="${m.top + innerH}" class="grid-line"/>`;
    const lines = xMetric.tickLines ? xMetric.tickLines(t) : [formatTick(xMetric, t)];
    svg += `<text x="${x}" y="${m.top + innerH + 30}" text-anchor="middle" class="axis-label">${lines.map((line, idx) => `<tspan x="${x}" dy="${idx === 0 ? 0 : 15}">${escapeHtml(line)}</tspan>`).join("")}</text>`;
  });
  ticksY.forEach(t => {
    const y = yScale(t);
    svg += `<line x1="${m.left}" y1="${y}" x2="${m.left + innerW}" y2="${y}" class="grid-line"/>`;
    svg += `<text x="${m.left - 18}" y="${y + 5}" text-anchor="end" class="axis-label">${escapeHtml(formatTick(yMetric, t))}</text>`;
  });

  svg += `<line x1="${m.left}" y1="${m.top + innerH}" x2="${m.left + innerW}" y2="${m.top + innerH}" class="axis-line"/>`;
  svg += `<line x1="${m.left}" y1="${m.top}" x2="${m.left}" y2="${m.top + innerH}" class="axis-line"/>`;
  svg += `<text x="${m.left + innerW / 2}" y="${h - 32}" text-anchor="middle" class="axis-title">${escapeHtml(xMetric.axis)}</text>`;
  svg += `<text transform="translate(32 ${m.top + innerH / 2}) rotate(-90)" text-anchor="middle" class="axis-title">${escapeHtml(yMetric.axis)}</text>`;

  if (!visible.length) {
    svg += `<text x="${w / 2}" y="${h / 2}" text-anchor="middle" class="empty-plot-text">No matching models. Try clearing a filter.</text>`;
  }

  visible.forEach(d => {
    const xVal = xMetric.value(d);
    const yVal = yMetric.value(d);
    const jitterX = (hash01(d.id + landscape.xMetric + "x") - 0.5) * 34;
    const jitterY = (hash01(d.id + landscape.yMetric + "y") - 0.5) * 28;
    const cx = xScale(xVal) + jitterX;
    const cy = yScale(yVal) + jitterY;
    const r = pointRadius(d);
    const selected = d.id === landscape.selectedId ? " selected-point" : "";
    const familyKey = modelFamilyKey(d);
    const family = FAMILIES[familyKey] || FAMILIES.transformer_masked;
    svg += `<g class="model-node${selected}" data-id="${escapeHtml(d.id)}" tabindex="0" role="button" aria-label="${escapeHtml(d.name)}">`;
    svg += `<g filter="url(#softShadow)">${shapeSvg(family.shape, cx, cy, r, `landscape-point ${opennessClass(d)}`, pointColor(d), "#ffffff", "3")}</g>`;
    svg += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${(r + 7).toFixed(1)}" class="hit-ring"></circle>`;
    svg += `<title>${escapeHtml(d.name)}\nFamily: ${escapeHtml(family.label)}\n${xMetric.label}: ${formatTick(xMetric, xVal)}\n${yMetric.label}: ${formatTick(yMetric, yVal)}\n${escapeHtml(d.openness_label || d.openness || "")}</title>`;
    if (landscape.labelMode || selected) {
      const labelY = cy - r - 9;
      svg += `<text x="${cx.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" class="point-label">${escapeHtml(d.name)}</text>`;
    }
    svg += `</g>`;
  });

  L.plot.innerHTML = svg;

  L.plot.querySelectorAll(".model-node").forEach(node => {
    node.addEventListener("click", () => {
      const d = landscape.data.find(x => x.id === node.dataset.id);
      if (d) renderDetails(d);
    });
    node.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        const d = landscape.data.find(x => x.id === node.dataset.id);
        if (d) renderDetails(d);
      }
    });
  });
}

function renderDetails(d) {
  landscape.selectedId = d.id;
  const xMetric = METRICS[landscape.xMetric] || METRICS.modalities;
  const yMetric = METRICS[landscape.yMetric] || METRICS.tasks;
  L.title.textContent = d.name;
  L.details.classList.remove("empty");
  L.details.innerHTML = `
    <div class="detail-actions">${linkButton("Paper", d.paper_url)}${linkButton("Code", d.code_url)}${linkButton("Weights", d.weights_url)}${linkButton("Project", d.project_url)}</div>
    <div class="detail-section"><h3>Current map position</h3><p>${escapeHtml(xMetric.label)}: <b>${escapeHtml(formatTick(xMetric, xMetric.value(d)))}</b>; ${escapeHtml(yMetric.label)}: <b>${escapeHtml(formatTick(yMetric, yMetric.value(d)))}</b>.</p></div>
    <div class="detail-section"><h3>Modelling paradigm</h3><p>${escapeHtml(modelFamilyLabel(d))}</p></div>
    <div class="detail-section"><h3>Scope</h3><p>${escapeHtml(d.scope)}</p></div>
    <div class="detail-section"><h3>Modalities</h3><p>${escapeHtml(d.input_modality)}</p><div>${(d.modality_tags || []).map(x => tag(x)).join("")}</div></div>
    <div class="detail-section"><h3>Architecture</h3><p>${escapeHtml(d.architecture)}</p><div>${(d.architecture_tags || []).map(x => tag(x, "arch")).join("")}</div></div>
    <div class="detail-section"><h3>Downstream tasks</h3><div>${(d.task_tags || []).map(x => tag(x, "task")).join("")}</div><p>${escapeHtml(truncate(d.downstream_tasks, 360))}</p></div>
    <div class="detail-section"><h3>Access</h3><p>${escapeHtml(d.openness_text || d.openness_label || "Unknown")}</p></div>
  `;
  renderLandscape();
}

async function initLandscape() {
  const res = await fetch("data/catalogue.json");
  landscape.data = await res.json();
  landscape.filtered = landscape.data.slice();
  buildFilters();
  renderLegend();
  renderLandscape();
  [L.search, L.open, L.modality, L.task, L.architecture, L.family, L.xMetric, L.yMetric].forEach(el => {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  });
  L.labels.addEventListener("change", () => {
    landscape.labelMode = L.labels.checked;
    renderLandscape();
  });
  L.reset.addEventListener("click", () => {
    L.search.value = "";
    L.open.value = "";
    L.modality.value = "";
    L.task.value = "";
    L.architecture.value = "";
    L.family.value = "";
    L.xMetric.value = "modality_stage";
    L.yMetric.value = "reported_tasks";
    landscape.xMetric = "modality_stage";
    landscape.yMetric = "reported_tasks";
    L.labels.checked = false;
    landscape.labelMode = false;
    landscape.selectedId = null;
    L.title.textContent = "No model selected";
    L.details.className = "details empty";
    L.details.textContent = "Click a point on the landscape. The model summary and source links will open here.";
    applyFilters();
  });
}

initLandscape().catch(err => {
  console.error(err);
  document.querySelector(".container").insertAdjacentHTML("afterbegin", `<div class="panel"><b>Could not load data.</b> Serve this folder with a local web server or deploy it on GitHub Pages.</div>`);
});
