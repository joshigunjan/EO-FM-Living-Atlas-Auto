const state = {
  data: [],
  filtered: []
};

const els = {
  stats: document.getElementById("benchmarkStats"),
  search: document.getElementById("benchmarkSearch"),
  typeFilter: document.getElementById("typeFilter"),
  accessFilter: document.getElementById("accessFilter"),
  yearFilter: document.getElementById("benchmarkYearFilter"),
  timeline: document.getElementById("benchmarkTimeline"),
  resetBtn: document.getElementById("benchmarkResetBtn"),
  tbody: document.querySelector("#benchmarksTable tbody"),
  resultCount: document.getElementById("benchmarkResultCount")
};

function uniq(arr) {
  return [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[c]));
}

function truncate(s, n = 160) {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function tag(text, cls = "") {
  return `<span class="badge ${cls}">${escapeHtml(text || "unknown")}</span>`;
}

function linkButton(label, url) {
  if (!url) return `<span class="empty-link">—</span>`;
  return `<a class="link-pill" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function renderTimeline() {
  const counts = {};
  state.data.forEach(d => { if (d.publication_year) counts[d.publication_year] = (counts[d.publication_year] || 0) + 1; });
  const years = Object.keys(counts).map(Number).sort((a,b) => a-b);
  const max = Math.max(1, ...years.map(y => counts[y]));
  els.timeline.innerHTML = years.map(y => `
    <button class="timeline-item" data-year="${y}" title="${counts[y]} releases in ${y}">
      <span class="timeline-count">${counts[y]}</span>
      <span class="timeline-bar" style="height:${Math.max(12, Math.round(counts[y]/max*100))}%"></span>
      <span class="timeline-year">${y}</span>
    </button>`).join("") || '<span class="muted">No publication years recorded.</span>';
  els.timeline.querySelectorAll(".timeline-item").forEach(btn => btn.addEventListener("click", () => { els.yearFilter.value = btn.dataset.year; applyFilters(); }));
}

function renderStats() {
  const total = state.data.length;
  const benchmarks = state.data.filter(d => String(d.benchmark_type || "").toLowerCase().includes("benchmark")).length;
  const datasets = state.data.filter(d => String(d.benchmark_type || "").toLowerCase().includes("dataset")).length;
  const withPaper = state.data.filter(d => d.paper_url).length;
  els.stats.innerHTML = `
    <div class="stat-card"><div class="num">${total}</div><div class="label">Benchmark / dataset entries</div></div>
    <div class="stat-card"><div class="num">${benchmarks}</div><div class="label">Benchmarks</div></div>
    <div class="stat-card"><div class="num">${datasets}</div><div class="label">Datasets / embedding resources</div></div>
    <div class="stat-card"><div class="num">${withPaper}</div><div class="label">Direct paper links</div></div>
  `;
}

function buildFilters() {
  for (const t of uniq(state.data.map(d => d.benchmark_type))) {
    els.typeFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`);
  }
  for (const a of uniq(state.data.map(d => d.access))) {
    els.accessFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`);
  }
  for (const y of [...new Set(state.data.map(d => d.publication_year).filter(Boolean))].sort((a,b) => b-a)) {
    els.yearFilter.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
  }
}

function rowText(d) {
  return [
    d.name, d.publication_year, d.title, d.scope, d.benchmark_type, d.tasks, d.modalities, d.access, d.paper_url, d.code_url, d.dataset_url, d.project_url,
  ].join(" ").toLowerCase();
}

function applyFilters() {
  const q = els.search.value.trim().toLowerCase();
  const type = els.typeFilter.value;
  const access = els.accessFilter.value;
  const year = els.yearFilter.value;
  state.filtered = state.data.filter(d => {
    if (q && !rowText(d).includes(q)) return false;
    if (type && d.benchmark_type !== type) return false;
    if (access && d.access !== access) return false;
    if (year && String(d.publication_year || "") !== year) return false;
    return true;
  });
  renderTable();
}

function renderTable() {
  els.tbody.innerHTML = "";
  els.resultCount.textContent = `${state.filtered.length} of ${state.data.length} entries shown`;
  for (const d of state.filtered) {
    const tr = document.createElement("tr");
    const datasetUrl = d.dataset_url || d.project_url;
    tr.innerHTML = `
      <td class="name"><span>${escapeHtml(d.name)}</span></td>
      <td>${escapeHtml(d.publication_year || "—")}</td>
      <td>${tag(d.benchmark_type || "Needs review", "paradigm")}</td>
      <td><strong>${escapeHtml(truncate(d.title, 120))}</strong><div class="task-preview">${escapeHtml(truncate(d.scope, 150))}</div></td>
      <td class="tasks-cell"><div class="task-preview">${escapeHtml(truncate(d.tasks, 180))}</div></td>
      <td>${escapeHtml(truncate(d.modalities, 90))}</td>
      <td>${tag(d.access || "Unknown", "unknown")}</td>
      <td class="single-link">${linkButton("Link", d.paper_url)}</td>
      <td class="single-link">${linkButton("Link", d.code_url)}</td>
      <td class="single-link">${linkButton("Link", datasetUrl)}</td>
    `;
    els.tbody.appendChild(tr);
  }
}

async function init() {
  const res = await fetch("data/benchmarks.json");
  state.data = await res.json();
  state.filtered = state.data.slice();
  renderStats();
  renderTimeline();
  buildFilters();
  renderTable();
  [els.search, els.typeFilter, els.accessFilter, els.yearFilter].forEach(el => {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  });
  els.resetBtn.addEventListener("click", () => {
    els.search.value = "";
    els.typeFilter.value = "";
    els.accessFilter.value = "";
    els.yearFilter.value = "";
    applyFilters();
  });
}

init().catch(err => {
  console.error(err);
  document.querySelector(".container").insertAdjacentHTML(
    "afterbegin",
    `<div class="panel"><b>Could not load benchmark data.</b> The upstream sync may not have run yet.</div>`
  );
});
