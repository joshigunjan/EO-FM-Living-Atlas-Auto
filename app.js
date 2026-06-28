const state = {
  data: [],
  filtered: [],
  selectedId: null
};

const els = {
  stats: document.getElementById("stats"),
  search: document.getElementById("search"),
  categoryFilter: document.getElementById("categoryFilter"),
  opennessFilter: document.getElementById("opennessFilter"),
  modalityFilter: document.getElementById("modalityFilter"),
  taskFilter: document.getElementById("taskFilter"),
  paradigmFilter: document.getElementById("paradigmFilter"),
  resetBtn: document.getElementById("resetBtn"),
  clearSelection: document.getElementById("clearSelection"),
  tbody: document.querySelector("#catalogueTable tbody"),
  details: document.getElementById("details"),
  detailTitle: document.getElementById("detailTitle"),
  resultCount: document.getElementById("resultCount")
};

function uniq(arr) {
  return [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[c]));
}

function truncate(s, n = 120) {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function tag(text, cls = "") {
  return `<span class="badge ${cls}">${escapeHtml(text || "unknown")}</span>`;
}

function accessLabel(d) {
  const o = String(d?.openness || d?.openness_label || "unknown").toLowerCase();
  if (o.includes("open")) return "Open source";
  if (o.includes("partial")) return "Partial access";
  if (o.includes("closed")) return "Closed source";
  return "Unknown";
}

function accessOptionLabel(value) {
  const v = String(value || "").toLowerCase();
  if (v.includes("open")) return "Open source";
  if (v.includes("partial")) return "Partial access";
  if (v.includes("closed")) return "Closed source";
  return value || "Unknown";
}

function linkButton(label, url, compact = false) {
  if (!url) return `<span class="empty-link">—</span>`;
  const text = compact ? "Link" : label;
  return `<a class="link-pill" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(text)}</a>`;
}

function buildFilters() {
  const categories = uniq(state.data.map(d => d.category));
  const openness = uniq(state.data.map(d => d.openness_label || d.openness));
  const modalities = uniq(state.data.flatMap(d => d.modality_tags || []));
  const tasks = uniq(state.data.flatMap(d => d.task_tags || []));
  const paradigms = uniq(state.data.map(d => d.modelling_paradigm));

  for (const s of categories) els.categoryFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`);
  for (const o of openness) els.opennessFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(o)}">${escapeHtml(accessOptionLabel(o))}</option>`);
  for (const m of modalities) els.modalityFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`);
  for (const t of tasks) els.taskFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`);
  for (const p of paradigms) els.paradigmFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`);
}

function renderStats() {
  const total = state.data.length;
  const openish = state.data.filter(d => ["open", "partial"].includes(d.openness)).length;
  const tasks = uniq(state.data.flatMap(d => d.task_tags || [])).length;
  const withPaper = state.data.filter(d => d.paper_url).length;

  els.stats.innerHTML = `
    <div class="stat-card"><div class="num">${total}</div><div class="label">Catalogue entries</div></div>
    <div class="stat-card"><div class="num">${openish}</div><div class="label">Open / partial access</div></div>
    <div class="stat-card"><div class="num">${tasks}</div><div class="label">Downstream task labels</div></div>
    <div class="stat-card"><div class="num">${withPaper}</div><div class="label">Direct paper links</div></div>
  `;
}

function rowText(d) {
  return [
    d.name, d.category, d.scope, d.modelling_paradigm, d.input_modality, d.architecture, d.downstream_tasks,
    d.training_scale, d.openness_text, d.fm_strength, d.notes, d.paper_url, d.code_url,
    d.weights_url, d.project_url,
    ...(d.modality_tags || []), ...(d.architecture_tags || []), ...(d.task_tags || [])
  ].join(" ").toLowerCase();
}

function applyFilters() {
  const q = els.search.value.trim().toLowerCase();
  const category = els.categoryFilter.value;
  const open = els.opennessFilter.value;
  const mod = els.modalityFilter.value;
  const task = els.taskFilter.value;
  const paradigm = els.paradigmFilter.value;

  state.filtered = state.data.filter(d => {
    if (q && !rowText(d).includes(q)) return false;
    if (category && d.category !== category) return false;
    if (open && (d.openness_label || d.openness) !== open) return false;
    if (mod && !(d.modality_tags || []).includes(mod)) return false;
    if (task && !(d.task_tags || []).includes(task)) return false;
    if (paradigm && d.modelling_paradigm !== paradigm) return false;
    return true;
  });
  renderTable();
}

function renderTable() {
  els.tbody.innerHTML = "";
  els.resultCount.textContent = `${state.filtered.length} of ${state.data.length} entries shown`;

  for (const d of state.filtered) {
    const tr = document.createElement("tr");
    if (d.id === state.selectedId) tr.classList.add("selected");
    const taskChips = (d.task_tags || []).slice(0, 5).map(x => tag(x, "task")).join("");
    const moreTasks = (d.task_tags || []).length > 5 ? `<span class="more">+${(d.task_tags || []).length - 5}</span>` : "";
    tr.innerHTML = `
      <td class="name"><span>${escapeHtml(d.name)}</span><small>${escapeHtml(d.category || "")}</small></td>
      <td>${escapeHtml(d.scope)}</td>
      <td>${tag(d.modelling_paradigm || "Unknown", "paradigm")}</td>
      <td>${(d.modality_tags || []).map(x => tag(x)).join("") || escapeHtml(truncate(d.input_modality, 80))}</td>
      <td>${(d.architecture_tags || []).map(x => tag(x, "arch")).join("") || escapeHtml(truncate(d.architecture, 80))}</td>
      <td class="tasks-cell">${taskChips}${moreTasks}<div class="task-preview">${escapeHtml(truncate(d.downstream_tasks, 125))}</div></td>
      <td>${tag(accessLabel(d), d.openness || "unknown")}</td>
      <td class="single-link">${linkButton("Paper", d.paper_url, true)}</td>
      <td class="single-link">${linkButton("Code", d.code_url, true)}</td>
      <td class="single-link">${linkButton("Weights", d.weights_url, true)}</td>
      <td class="single-link">${linkButton("Project", d.project_url, true)}</td>
    `;
    tr.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;
      renderDetails(d);
    });
    els.tbody.appendChild(tr);
  }
}

function renderDetails(d) {
  state.selectedId = d.id;
  els.detailTitle.textContent = d.name;
  els.details.classList.remove("empty");
  const tasks = (d.task_tags || []).map(x => tag(x, "task")).join("") || "No task tags available yet.";
  els.details.innerHTML = `
    <div class="detail-actions">${linkButton("Original paper", d.paper_url)}${linkButton("Code", d.code_url)}${linkButton("Weights", d.weights_url)}${linkButton("Project page", d.project_url)}</div>
    <div class="detail-section"><h3>Scientific scope</h3><p>${escapeHtml(d.scope)}</p></div>
    <div class="detail-section"><h3>Modelling paradigm</h3><p>${escapeHtml(d.modelling_paradigm || "Unknown")}</p></div>
    <div class="detail-section"><h3>Modalities</h3><p>${escapeHtml(d.input_modality)}</p><div>${(d.modality_tags || []).map(x => tag(x)).join("")}</div></div>
    <div class="detail-section"><h3>Architecture</h3><p>${escapeHtml(d.architecture)}</p><div>${(d.architecture_tags || []).map(x => tag(x, "arch")).join("")}</div></div>
    <div class="detail-section"><h3>Downstream tasks</h3><div class="task-strip">${tasks}</div><p>${escapeHtml(d.downstream_tasks)}</p></div>
    <div class="detail-section"><h3>Training scale / representation</h3><p>${escapeHtml(d.training_scale)}</p></div>
    <div class="detail-grid">
      <div class="detail-key">Access</div><div>${escapeHtml(d.openness_text || accessLabel(d))}</div>
      <div class="detail-key">Strength</div><div>${escapeHtml(d.fm_strength)}</div>
      <div class="detail-key">Notes</div><div>${escapeHtml(d.notes)}</div>
    </div>
  `;
  renderTable();
}

function clearDetails() {
  state.selectedId = null;
  els.detailTitle.textContent = "No entry selected";
  els.details.className = "details empty";
  els.details.textContent = "Click a row. Details open here next to the table.";
  renderTable();
}

async function init() {
  const res = await fetch("data/catalogue.json");
  state.data = await res.json();
  state.filtered = state.data.slice();
  buildFilters();
  renderStats();
  renderTable();

  [els.search, els.categoryFilter, els.opennessFilter, els.modalityFilter, els.taskFilter, els.paradigmFilter].forEach(el => {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  });
  els.resetBtn.addEventListener("click", () => {
    els.search.value = "";
    els.categoryFilter.value = "";
    els.opennessFilter.value = "";
    els.modalityFilter.value = "";
    els.taskFilter.value = "";
    els.paradigmFilter.value = "";
    applyFilters();
  });
  els.clearSelection.addEventListener("click", clearDetails);
}

init().catch(err => {
  console.error(err);
  document.querySelector(".container").insertAdjacentHTML(
    "afterbegin",
    `<div class="panel"><b>Could not load data.</b> Serve this folder with a local web server or deploy it on GitHub Pages.</div>`
  );
});
