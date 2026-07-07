const paperState = {
  payload: null,
  points: [],
  filtered: [],
  selectedId: null
};

const paperEls = {
  stats: document.getElementById("paperMapStats"),
  search: document.getElementById("paperSearch"),
  typeFilter: document.getElementById("paperTypeFilter"),
  clusterFilter: document.getElementById("paperClusterFilter"),
  yearFilter: document.getElementById("paperYearFilter"),
  abstractFilter: document.getElementById("paperAbstractFilter"),
  resetBtn: document.getElementById("paperResetBtn"),
  plot: document.getElementById("paperMap"),
  count: document.getElementById("paperMapCount"),
  detailTitle: document.getElementById("paperDetailTitle"),
  details: document.getElementById("paperDetails"),
  clusterSummary: document.getElementById("clusterSummary")
};

const CLUSTER_COLORS = [
  "#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626",
  "#0891b2", "#be185d", "#4f46e5", "#65a30d", "#ea580c",
  "#0f766e", "#9333ea", "#0369a1", "#b91c1c"
];

function escapePaperHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[character]));
}

function unique(values) {
  return [...new Set(values.filter(value => value !== null && value !== undefined && value !== ""))];
}

function pointSearchText(point) {
  return [
    point.title,
    point.abstract,
    point.cluster_label,
    point.tasks,
    point.modalities,
    ...(point.associated_entries || []).flatMap(entry => [
      entry.name,
      entry.resource_type,
      entry.year
    ])
  ].join(" ").toLowerCase();
}

function resourceLabel(point) {
  const types = point.resource_types || [];
  if (types.includes("model") && types.includes("benchmark")) return "Model + benchmark";
  if (types.includes("benchmark")) return "Benchmark / dataset";
  return "Model";
}

function paperSymbol(point) {
  const types = point.resource_types || [];

  if (types.includes("model") && types.includes("benchmark")) {
    return "star";
  }

  if (types.includes("benchmark")) {
    return "diamond";
  }

  return "circle";
}

function badge(text, className = "") {
  return `<span class="badge ${className}">${escapePaperHtml(text)}</span>`;
}

function linkButton(label, url) {
  if (!url) return "";
  return `<a class="link-pill" href="${escapePaperHtml(url)}" target="_blank" rel="noreferrer">${escapePaperHtml(label)}</a>`;
}

function populatePaperFilters() {
  const clusters = [...paperState.payload.clusters]
    .sort((a, b) => b.size - a.size || a.label.localeCompare(b.label));

  for (const cluster of clusters) {
    paperEls.clusterFilter.insertAdjacentHTML(
      "beforeend",
      `<option value="${cluster.id}">${escapePaperHtml(cluster.label)} (${cluster.size})</option>`
    );
  }

  const years = unique(paperState.points.map(point => point.year))
    .sort((a, b) => b - a);

  for (const year of years) {
    paperEls.yearFilter.insertAdjacentHTML(
      "beforeend",
      `<option value="${year}">${year}</option>`
    );
  }
}

function renderPaperStats() {
  const total = paperState.points.length;
  const primary = paperState.points.filter(point => point.has_primary_abstract).length;
  const modelPapers = paperState.points.filter(point =>
    (point.resource_types || []).includes("model")
  ).length;
  const benchmarkPapers = paperState.points.filter(point =>
    (point.resource_types || []).includes("benchmark")
  ).length;

  paperEls.stats.innerHTML = `
    <div class="stat-card">
      <div class="num">${total}</div>
      <div class="label">Unique papers</div>
    </div>
    <div class="stat-card">
      <div class="num">${primary}</div>
      <div class="label">Primary abstracts</div>
    </div>
    <div class="stat-card">
      <div class="num">${modelPapers}</div>
      <div class="label">Model papers</div>
    </div>
    <div class="stat-card">
      <div class="num">${benchmarkPapers}</div>
      <div class="label">Benchmark / dataset papers</div>
    </div>
  `;
}

function applyPaperFilters() {
  const query = paperEls.search.value.trim().toLowerCase();
  const type = paperEls.typeFilter.value;
  const cluster = paperEls.clusterFilter.value;
  const year = paperEls.yearFilter.value;
  const abstractMode = paperEls.abstractFilter.value;

  paperState.filtered = paperState.points.filter(point => {
    if (query && !pointSearchText(point).includes(query)) return false;
    if (type && !(point.resource_types || []).includes(type)) return false;
    if (cluster && String(point.cluster_id) !== cluster) return false;
    if (year && String(point.year || "") !== year) return false;
    if (abstractMode === "primary" && !point.has_primary_abstract) return false;
    if (abstractMode === "fallback" && point.has_primary_abstract) return false;
    return true;
  });

  renderPaperMap();
}

function makeClusterTrace(cluster, points) {
  const color = CLUSTER_COLORS[cluster.id % CLUSTER_COLORS.length];

  return {
    x: points.map(point => point.x),
    y: points.map(point => point.y),
    text: points.map(point => point.title),
    customdata: points.map(point => point.id),
    hovertemplate:
      "<b>%{text}</b><br>" +
      escapePaperHtml(cluster.label) +
      "<br><extra></extra>",
    mode: "markers",
    type: "scatter",
    name: `${cluster.label} (${points.length})`,
    marker: {
  color,
  symbol: points.map(point => paperSymbol(point)),
  size: points.map(point =>
    (point.resource_types || []).includes("benchmark") ? 12 : 10
  ),
  opacity: 0.86,
  line: {
    color: "#ffffff",
    width: 0.8
  }
},
showlegend: false
  };
}

function renderPaperMap() {
  paperEls.count.textContent =
    `${paperState.filtered.length} of ${paperState.points.length} papers shown`;

  const grouped = new Map();

  for (const point of paperState.filtered) {
    if (!grouped.has(point.cluster_id)) {
      grouped.set(point.cluster_id, []);
    }

    grouped.get(point.cluster_id).push(point);
  }

  const clusterById = new Map(
    paperState.payload.clusters.map(cluster => [cluster.id, cluster])
  );

  const traces = [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([clusterId, points]) =>
      makeClusterTrace(clusterById.get(clusterId), points)
    );

  const annotations = [...grouped.entries()].map(([clusterId, points]) => {
    const cluster = clusterById.get(clusterId);

    const x =
      points.reduce((sum, point) => sum + point.x, 0) / points.length;

    const y =
      points.reduce((sum, point) => sum + point.y, 0) / points.length;

    return {
      x,
      y,
      xref: "x",
      yref: "y",
      text:
        `<b>${escapePaperHtml(cluster.label)}</b>` +
        `<br>${points.length} papers`,
      showarrow: false,
      bgcolor: "rgba(255,255,255,0.88)",
      bordercolor: "rgba(15,23,42,0.20)",
      borderwidth: 1,
      borderpad: 5,
      font: {
        size: 11,
        color: "#0f172a"
      },
      opacity: 0.95
    };
  });

  const layout = {
    showlegend: false,
    annotations,
    margin: {
      l: 24,
      r: 24,
      t: 28,
      b: 20
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    hovermode: "closest",
    xaxis: {
      visible: false,
      zeroline: false,
      automargin: true
    },
    yaxis: {
      visible: false,
      zeroline: false,
      automargin: true,
      scaleanchor: "x",
      scaleratio: 1
    },
    dragmode: "pan",
    uirevision: "paper-map"
  };

  const config = {
    responsive: true,
    displaylogo: false,
    scrollZoom: true,
    modeBarButtonsToRemove: [
      "select2d",
      "lasso2d",
      "autoScale2d",
      "toggleSpikelines"
    ]
  };

  Plotly.react(
    paperEls.plot,
    traces,
    layout,
    config
  );

  paperEls.plot.removeAllListeners?.("plotly_click");

  paperEls.plot.on("plotly_click", event => {
    const id = event?.points?.[0]?.customdata;

    const point = paperState.points.find(
      candidate => candidate.id === id
    );

    if (point) {
      renderPaperDetails(point);
    }
  });
}
function renderPaperDetails(point) {
  paperState.selectedId = point.id;
  paperEls.detailTitle.textContent = point.title;
  paperEls.details.classList.remove("empty");

  const associated = (point.associated_entries || [])
    .map(entry =>
      `<li><strong>${escapePaperHtml(entry.name)}</strong> · ${escapePaperHtml(entry.resource_type)}${entry.year ? ` · ${entry.year}` : ""}</li>`
    )
    .join("");

  paperEls.details.innerHTML = `
    <div class="detail-actions">
      ${linkButton("Open paper", point.paper_url)}
    </div>

    <div class="paper-meta">
      ${badge(point.year || "Year unknown")}
      ${badge(resourceLabel(point))}
      ${badge(point.cluster_label, "paradigm")}
      ${badge(
        point.has_primary_abstract
          ? `Abstract: ${point.abstract_source}`
          : "Catalogue-summary fallback",
        point.has_primary_abstract ? "open" : "unknown"
      )}
    </div>

    <div class="detail-section">
      <h3>Abstract</h3>
      <p class="paper-abstract">${escapePaperHtml(point.abstract)}</p>
    </div>

    <div class="detail-section">
      <h3>Associated atlas entries</h3>
      <ul>${associated || "<li>No linked atlas entries.</li>"}</ul>
    </div>

    ${point.modalities ? `
      <div class="detail-section">
        <h3>Modalities</h3>
        <p>${escapePaperHtml(point.modalities)}</p>
      </div>
    ` : ""}

    ${point.tasks ? `
      <div class="detail-section">
        <h3>Tasks / attributes</h3>
        <p>${escapePaperHtml(point.tasks)}</p>
      </div>
    ` : ""}
  `;
}

function renderClusterSummary() {
  paperEls.clusterSummary.innerHTML = `
    <h3>Semantic clusters</h3>
    ${[...paperState.payload.clusters]
      .sort((a, b) => b.size - a.size)
      .map(cluster => `
        <button class="cluster-item" data-cluster="${cluster.id}">
          <strong>${escapePaperHtml(cluster.label)}</strong>
          <span class="muted">${cluster.size} papers</span>
        </button>
      `)
      .join("")}
  `;

  paperEls.clusterSummary
    .querySelectorAll(".cluster-item")
    .forEach(button => {
      button.addEventListener("click", () => {
        paperEls.clusterFilter.value = button.dataset.cluster;
        applyPaperFilters();
      });
    });
}

async function initPaperMap() {
  const response = await fetch("data/paper-map.json");
  if (!response.ok) {
    throw new Error(`Could not load paper-map.json (${response.status})`);
  }

  paperState.payload = await response.json();
  paperState.points = paperState.payload.points || [];

  if (paperState.payload.embedding?.semantic === false) {
    document.querySelector(".controls-panel")?.insertAdjacentHTML(
      "beforeend",
      `<p class="hint map-note"><strong>Development preview:</strong> this map currently uses a lexical TF-IDF fallback. Run the semantic paper-map workflow to replace it with abstract embeddings.</p>`
    );
  }
  paperState.filtered = paperState.points.slice();

  populatePaperFilters();
  renderPaperStats();
  renderClusterSummary();
  renderPaperMap();

  [
    paperEls.search,
    paperEls.typeFilter,
    paperEls.clusterFilter,
    paperEls.yearFilter,
    paperEls.abstractFilter
  ].forEach(element => {
    element.addEventListener("input", applyPaperFilters);
    element.addEventListener("change", applyPaperFilters);
  });

  paperEls.resetBtn.addEventListener("click", () => {
    paperEls.search.value = "";
    paperEls.typeFilter.value = "";
    paperEls.clusterFilter.value = "";
    paperEls.yearFilter.value = "";
    paperEls.abstractFilter.value = "";
    applyPaperFilters();
  });
}

initPaperMap().catch(error => {
  console.error(error);
  paperEls.plot.innerHTML = `
    <div class="panel">
      <b>Could not load the semantic paper map.</b>
      Run <code>python scripts/build_paper_map.py</code> to generate
      <code>data/paper-map.json</code>.
    </div>
  `;
});
