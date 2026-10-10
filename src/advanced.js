import "./advanced.css";
import * as echarts from "echarts";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const $ = (id) => document.getElementById(id);
const state = {
  token: "",
  module: "search",
  offset: 0,
  category: "",
  filters: {},
  graphType: "",
  graphStatus: "",
  threatKind: "threat_actor",
  threatSource: "",
  cases: [],
  selected: new Set(),
  chart: null,
  map: null,
  generation: 0,
};
const modules = [
  [
    "search",
    "Search & resources",
    "Search collected intelligence and discover research resources. External lookups open only when you choose a provider.",
  ],
  [
    "cyber",
    "Cyber intelligence",
    "Normalize indicators and cross-reference official advisories. Source mentions retain their classifications and evidence.",
  ],
  [
    "narratives",
    "Narratives & sentiment",
    "Explore related reporting, wording sentiment, language coverage and changes in discussion volume.",
  ],
  [
    "actors",
    "Threat actors & campaigns",
    "Browse source-backed actor profiles, aliases, malware and techniques. Follow historical catalog relationships and recent report mentions separately.",
  ],
  [
    "geo",
    "Geographic evidence",
    "Resolve country references, measure coordinates and import geographic evidence with its precision and source.",
  ],
  [
    "media",
    "Image & video evidence",
    "Inspect authorized images and videos, record hashes and document verification steps.",
  ],
  [
    "graph",
    "Entity relationships",
    "Follow evidence-supported references. Dashed edges show reported co-mentions, rather than confirmed operational relationships.",
  ],
  [
    "watch",
    "Source monitoring",
    "Monitor explicitly authorized public pages with version history, text differences and pause controls.",
  ],
  [
    "documents",
    "Documents & organizations",
    "Index authorized public-document references and text, preserving versions and licensing conditions.",
  ],
  [
    "correlation",
    "Cross-domain analysis",
    "Compare selected records using transparent rules, then optionally request an evidence-grounded AI assessment.",
  ],
  [
    "cases",
    "Investigation cases",
    "Organize evidence, immutable snapshots, private notes and a chronological investigation history.",
  ],
  [
    "sources",
    "Source quality",
    "Inspect collection health, geographic coverage, access requirements and source validation.",
  ],
];
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notify(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
}
function action(label, fn) {
  const node = el("button", label);
  node.type = "button";
  node.addEventListener("click", () =>
    Promise.resolve().then(fn).catch(failed),
  );
  return node;
}
function failed(error) {
  notify(error.message || "This request could not be completed.", true);
}
async function api(path, { method = "GET", body, raw, type } = {}) {
  const headers = { Authorization: `Bearer ${state.token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (raw) headers["Content-Type"] = type;
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: raw || (body === undefined ? undefined : JSON.stringify(body)),
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      result.message || result.detail || `Request failed (${response.status})`,
    );
  return result;
}
function link(url, label = "Original source ↗") {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol))
      return el("span", "Source unavailable");
    const node = el("a", label);
    node.href = parsed.href;
    node.target = "_blank";
    node.rel = "noopener noreferrer";
    return node;
  } catch {
    return el("span", "Source unavailable");
  }
}
function date(value) {
  return value
    ? new Date(value).toLocaleString(undefined, { timeZone: "UTC" }) + " UTC"
    : "Unknown";
}
function jsonDetails(data) {
  const details = el("details");
  details.append(
    el("summary", "Full evidence metadata"),
    el("pre", JSON.stringify(data, null, 2)),
  );
  return details;
}
function detail(data, title) {
  $("detail").replaceChildren(
    el(
      "h3",
      title ||
        data.title ||
        data.name ||
        data.filename ||
        data.normalized_value ||
        "Evidence",
    ),
  );
  const fields = [
    ["Source", data.source_id],
    [
      "Published",
      data.published_at === undefined ? undefined : date(data.published_at),
    ],
    ["Observed", data.observed_at ? date(data.observed_at) : undefined],
    ["Retrieved", data.ingested_at || data.retrieved_at || data.uploaded_at],
    ["Precision", data.precision],
    ["Confidence", data.confidence],
    ["Language", data.language],
    ["License", data.license_classification],
    ["SHA-256", data.sha256 || data.content_hash],
  ];
  const dl = el("dl");
  for (const [label, value] of fields)
    if (value !== undefined && value !== null)
      dl.append(el("dt", label), el("dd", value));
  $("detail").append(dl);
  if (data.analysis_id) {
    $("detail").append(
      el("p", `${data.model_id} · ${date(data.generated_at)}`, "muted"),
    );
    if (data.output_mode === "draft") {
      $("detail").append(el("strong", "AI draft · citations not validated"));
      const draft = el("p", data.draft_text);
      draft.style.whiteSpace = "pre-wrap";
      $("detail").append(draft);
    } else {
      for (const [label, rows] of [
        ["Reported observations", data.observations],
        ["Unverified hypotheses", data.hypotheses],
      ]) {
        $("detail").append(el("h4", label));
        for (const row of rows || []) {
          const statement = el("article");
          statement.append(el("p", row.text));
          for (const id of row.evidence_ids || []) {
            const reference = data.references?.find(
              (r) => r.evidence_id === id,
            );
            if (reference?.original_url)
              statement.append(
                link(
                  reference.original_url,
                  reference.title || "Supplied evidence",
                ),
              );
          }
          $("detail").append(statement);
        }
      }
    }
    for (const limitation of data.limitations || [])
      $("detail").append(el("p", limitation, "muted"));
    if (data.output_mode === "draft") {
      $("detail").append(el("h4", "Sources supplied for context"));
      for (const ref of data.references || [])
        if (ref.original_url)
          $("detail").append(
            link(ref.original_url, ref.title || "Supplied source"),
          );
    }
  }
  if (data.text || data.description || data.basis)
    $("detail").append(
      el(
        "p",
        typeof data.basis === "object"
          ? JSON.stringify(data.basis)
          : data.text || data.description || data.basis,
      ),
    );
  if (data.original_url || data.source_url)
    $("detail").append(link(data.original_url || data.source_url));
  $("detail").append(jsonDetails(data));
}
function threatDetail(data) {
  detail(data);
  const root = $("detail");
  root.append(
    el(
      "p",
      "Reported source knowledge. A name match does not establish responsibility for an incident.",
      "muted",
    ),
  );
  for (const profile of data.catalog_profiles || []) {
    const section = el("section", undefined, "catalog-profile");
    section.append(
      el("h4", profile.source_id.replaceAll("_", " ")),
      el(
        "p",
        `${profile.active ? "Current reference" : "Withdrawn or deprecated"} · ${profile.license_classification}`,
      ),
      el(
        "p",
        `Catalog version ${profile.version} · Retrieved ${date(profile.retrieved_at)}`,
      ),
    );
    if (profile.modified_at)
      section.append(el("p", `Source revised ${profile.modified_at}`));
    section.append(el("p", profile.description));
    if (profile.profile?.copyright_and_license)
      section.append(
        el(
          "p",
          "© 2026 The MITRE Corporation. Reproduced and distributed with permission.",
        ),
        link(
          "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/LICENSE.txt",
          "ATT&CK license ↗",
        ),
      );
    if (profile.profile?.catalog_exclusions?.length)
      section.append(
        el(
          "p",
          `${profile.profile.catalog_exclusions.length} malformed entries excluded from this source export. See catalog status for details.`,
          "muted",
        ),
      );
    if (profile.aliases?.length)
      section.append(
        el("p", "Also named: " + profile.aliases.slice(0, 20).join(", ")),
      );
    const association = profile.profile?.country;
    if (association)
      section.append(
        el(
          "p",
          "Catalog country association (not a location): " +
            (Array.isArray(association) ? association.join(", ") : association),
        ),
      );
    section.append(link(profile.original_url, "Catalog source ↗"));
    for (const url of (profile.profile?.refs || []).slice(0, 8))
      section.append(link(url, "Underlying reference ↗"));
    root.append(section);
  }
  const reports = data.reports || data.cyber_reports || [];
  root.append(el("h4", "Recent collected report mentions"));
  if (!reports.length)
    root.append(
      el("p", "No matching reports in the collected cyber coverage.", "muted"),
    );
  for (const report of reports) {
    root.append(
      action(report.title, () => detail(report)),
      el(
        "p",
        `${report.source_id} · ${date(report.published_at)} · ${report.match_status === "ambiguous_alias" ? "Ambiguous alias; unresolved" : "Explicit name mention; responsibility unverified"}`,
        "muted",
      ),
    );
  }
}
function ipActivityDetail(payload) {
  detail(payload, `${payload.resource} · SANS IP observation`);
  const data = payload.data || {},
    rows = el("dl", undefined, "facts");
  for (const [label, value] of [
    ["Network prefix", data.network],
    ["Autonomous system", data.as],
    ["Network owner", data.asname],
    ["ASN registration country (not physical origin)", data.ascountry],
    ["Reported observation count", data.count],
    ["Reported attacks", data.attacks],
    ["First reported date", data.mindate],
    ["Last reported date", data.maxdate],
  ])
    rows.append(
      el("dt", label),
      el("dd", value == null ? "Not supplied by provider" : String(value)),
    );
  $("detail").append(
    rows,
    el("p", data.comment || ""),
    el("p", payload.limitations, "muted"),
  );
  const feeds = Object.keys(data.threatfeeds || {});
  if (feeds.length)
    $("detail").append(
      el(
        "p",
        "Provider feed mentions (not a maliciousness verdict): " +
          feeds.join(", "),
      ),
    );
}
function modal(title, fields, submit) {
  $("dialog-title").textContent = title;
  const form = $("action-form");
  form.replaceChildren();
  for (const field of fields) {
    const label = el("label", field.label);
    let input;
    if (field.options) {
      input = el("select");
      for (const [value, text] of field.options) {
        const option = el("option", text);
        option.value = value;
        input.append(option);
      }
    } else input = el(field.multiline ? "textarea" : "input");
    input.name = field.name;
    if (!field.options && !field.multiline) input.type = field.type || "text";
    if (field.accept) input.accept = field.accept;
    if (field.value !== undefined) input.value = field.value;
    if (field.required !== false) input.required = true;
    if (field.max) input.maxLength = field.max;
    label.append(input);
    form.append(label);
  }
  const error = el("p", "", "error-text");
  error.setAttribute("role", "alert");
  const button = el("button", "Save");
  button.type = "submit";
  form.append(error, button);
  form.onsubmit = async (event) => {
    event.preventDefault();
    button.disabled = true;
    try {
      await submit(new FormData(form));
      $("action-dialog").close();
      await refresh();
    } catch (e) {
      error.textContent = e.message;
    } finally {
      button.disabled = false;
    }
  };
  $("action-dialog").showModal();
}
async function refreshCases() {
  state.cases = (await api("/cases?limit=200")).data;
  const current = $("active-case").value;
  $("active-case").replaceChildren(el("option", "Choose a case"));
  $("active-case").firstChild.value = "";
  for (const item of state.cases) {
    const option = el("option", item.title);
    option.value = item.id;
    $("active-case").append(option);
  }
  $("active-case").value = current;
}
async function saveEvidence(kind, id) {
  const caseId = $("active-case").value;
  if (!caseId) throw new Error("Choose a case before saving evidence.");
  await api(`/cases/${caseId}/evidence`, {
    method: "POST",
    body: { kind, reference_id: id },
  });
  notify("Evidence snapshot and hash saved to the selected case.");
}
function records(items, kind, select) {
  $("pagination").hidden = true;
  const list = el("div", undefined, "records");
  if (!items.length)
    list.append(
      el(
        "div",
        "No records match this view. Source coverage and availability determine what can be shown.",
        "empty",
      ),
    );
  for (const item of items) {
    const id =
      item.record_id ||
      item.entity_id ||
      item.indicator_id ||
      item.cluster_id ||
      item.id ||
      item.source_id;
    const card = el("article", undefined, "record");
    const title = action(
      item.title ||
        item.name ||
        item.filename ||
        item.normalized_value ||
        item.source_id ||
        "Source change · " + date(item.created_at),
      () => (select ? select(item) : detail(item)),
    );
    title.className = "record-title";
    card.append(title);
    const meta = el("div", undefined, "record-meta");
    for (const value of [
      item.category || item.type,
      item.source_id,
      item.language,
      item.precision,
      item.confidence,
      item.samples ? `${item.samples} samples` : null,
      item.integration,
      item.catalog_sources?.join(" · "),
      item.report_count !== undefined
        ? `${item.report_count} explicit report mentions`
        : null,
      item.access_class,
      item.health
        ? `${item.enabled ? "Collection" : "Inactive"}: ${item.health.state}${item.health.stale ? " · stale" : ""}`
        : null,
      item.details?.geographic_coverage,
      item.latest || item.published_at || item.updated_at || item.created_at
        ? date(
            item.latest ||
              item.published_at ||
              item.updated_at ||
              item.created_at,
          )
        : null,
    ])
      if (value) meta.append(el("span", value));
    card.append(meta);
    if (item.text || item.description)
      card.append(el("p", (item.text || item.description).slice(0, 260)));
    const buttons = el("div", undefined, "record-actions");
    if (item.original_url || item.source_url || item.official_url)
      buttons.append(
        link(item.original_url || item.source_url || item.official_url),
      );
    if (kind)
      buttons.append(action("Save to case", () => saveEvidence(kind, id)));
    if (item.record_id) {
      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selected.has(id);
      checkbox.addEventListener("change", () => {
        checkbox.checked ? state.selected.add(id) : state.selected.delete(id);
        notify(`${state.selected.size} records selected for comparison.`);
      });
      const label = el("label", " Compare");
      label.prepend(checkbox);
      buttons.append(label);
    }
    card.append(buttons);
    list.append(card);
  }
  $("results").replaceChildren(list);
}
function metrics(values) {
  const root = el("div", undefined, "metrics");
  for (const [label, value] of values) {
    const item = el("div", undefined, "metric");
    item.append(el("strong", value), el("span", label));
    root.append(item);
  }
  $("summary").append(root);
}
function selectors(options, initial, fn) {
  const node = el("select");
  node.setAttribute("aria-label", options[0][1]);
  for (const [value, text] of options) {
    const option = el("option", text);
    option.value = value;
    node.append(option);
  }
  node.value = initial;
  node.addEventListener("change", () => {
    fn(node.value);
    state.offset = 0;
    refresh().catch(failed);
  });
  return node;
}
function disposeVisual() {
  state.chart?.dispose();
  state.chart = null;
  state.map?.remove();
  state.map = null;
  $("visual").replaceChildren();
  $("visual").hidden = true;
}
function graph(data, onSelect = null, focusId = null) {
  const generation = state.generation;
  disposeVisual();
  $("visual").hidden = false;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 900 390");
  svg.setAttribute("role", "group");
  svg.setAttribute("aria-label", "Evidence-supported entity relationships");
  const defs = document.createElementNS(ns, "defs");
  const marker = document.createElementNS(ns, "marker");
  for (const [key, value] of Object.entries({
    id: "catalog-arrow",
    viewBox: "0 0 10 10",
    refX: "16",
    refY: "5",
    markerWidth: "6",
    markerHeight: "6",
    orient: "auto-start-reverse",
  }))
    marker.setAttribute(key, value);
  const arrow = document.createElementNS(ns, "path");
  arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
  arrow.setAttribute("fill", "#93c7b6");
  marker.append(arrow);
  defs.append(marker);
  svg.append(defs);
  const positions = new Map();
  if (focusId && data.nodes.some((node) => node.entity_id === focusId)) {
    positions.set(focusId, [450, 195]);
    const peers = data.nodes
      .filter((node) => node.entity_id !== focusId)
      .sort(
        (a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name),
      );
    const split = Math.ceil(peers.length / 2);
    peers.forEach((node, i) => {
      const right = i >= split,
        columnIndex = right ? i - split : i;
      const count = right ? peers.length - split : split;
      positions.set(node.entity_id, [
        right ? 650 : 250,
        count === 1 ? 195 : 32 + (columnIndex * 326) / (count - 1),
      ]);
    });
  } else
    data.nodes.forEach((node, i) => {
      const angle = (i * Math.PI * 2) / data.nodes.length;
      positions.set(node.entity_id, [
        450 + 320 * Math.cos(angle),
        195 + 140 * Math.sin(angle),
      ]);
    });
  for (const edge of data.edges) {
    const a = positions.get(edge.from_id),
      b = positions.get(edge.to_id);
    if (!a || !b) continue;
    const line = document.createElementNS(ns, "line");
    for (const [key, value] of [
      ["x1", a[0]],
      ["y1", a[1]],
      ["x2", b[0]],
      ["y2", b[1]],
    ])
      line.setAttribute(key, value);
    line.setAttribute("class", "graph-edge");
    if (edge.type.startsWith("catalog_")) {
      line.setAttribute("marker-end", "url(#catalog-arrow)");
      line.style.strokeDasharray = "none";
      line.style.stroke = "#93c7b6";
    }
    const tooltip = document.createElementNS(ns, "title");
    tooltip.textContent = `${edge.type.replaceAll("_", " ")} · ${edge.status}`;
    line.append(tooltip);
    if (edge.status === "inferred") line.style.stroke = "#c38feb";
    line.setAttribute("tabindex", "0");
    line.setAttribute("role", "button");
    line.setAttribute("aria-label", "Inspect " + edge.type + " evidence");
    const choose = async () => {
      if (edge.snapshot) {
        detail(edge.snapshot);
        return;
      }
      detail(edge, edge.type + " · " + edge.status);
      for (const evidence of edge.catalog_evidence || []) {
        $("detail").append(
          el(
            "p",
            `${evidence.source_id} · Historical reference · Revised ${evidence.modified_at || "unknown"}`,
          ),
          link(evidence.original_url, "Catalog relationship source ↗"),
        );
        for (const url of evidence.refs.slice(0, 8))
          $("detail").append(link(url, "Relationship evidence ↗"));
      }
      for (const rid of edge.evidence_ids.slice(0, 10)) {
        const record = (await api(`/osint/records/${rid}`)).data;
        if (generation !== state.generation) return;
        $("detail").append(action(record.title, () => detail(record)));
      }
    };
    line.addEventListener("click", () => choose().catch(failed));
    line.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        choose().catch(failed);
      }
    });
    svg.append(line);
  }
  for (const node of data.nodes) {
    const [x, y] = positions.get(node.entity_id);
    const group = document.createElementNS(ns, "g");
    group.setAttribute("class", "graph-node");
    group.setAttribute("transform", `translate(${x},${y})`);
    group.setAttribute("tabindex", "0");
    group.setAttribute("role", "button");
    group.setAttribute("aria-label", "Inspect " + node.name);
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("r", node.entity_id === focusId ? "11" : "7");
    const text = document.createElementNS(ns, "text");
    const sideLabel = focusId && node.entity_id !== focusId;
    text.setAttribute("y", sideLabel ? "4" : "22");
    text.setAttribute("x", sideLabel ? (x < 450 ? "-14" : "14") : "0");
    text.setAttribute(
      "text-anchor",
      sideLabel ? (x < 450 ? "end" : "start") : "middle",
    );
    text.textContent = node.name.slice(0, 28);
    const fullName = document.createElementNS(ns, "title");
    fullName.textContent = `${node.name} · ${node.type.replaceAll("_", " ")}`;
    group.append(fullName);
    group.append(circle, text);
    const choose = async () => {
      if (onSelect) {
        await onSelect(node);
        return;
      }
      const result = await api(`/graph/entities/${node.entity_id}`);
      if (generation !== state.generation) return;
      if (result.data.catalog_profiles?.length) threatDetail(result.data);
      else detail(result.data);
      const next = await api(
        `/graph/neighborhood/${node.entity_id}?nodes=24&edges=40&status=${state.graphStatus}`,
      );
      if (generation !== state.generation) return;
      graph(next.data);
    };
    group.addEventListener("click", () => choose().catch(failed));
    group.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        choose().catch(failed);
      }
    });
    svg.append(group);
  }
  $("visual").append(svg);
}
async function showGeo(data) {
  const generation = state.generation;
  detail(data);
  disposeVisual();
  $("visual").hidden = false;
  const container = el("div");
  container.style.height = "100%";
  $("visual").append(container);
  const world = await (await fetch("/countries.geojson")).json();
  if (generation !== state.generation) return;
  state.map = new maplibregl.Map({
    container,
    center: [10, 20],
    zoom: 0.4,
    attributionControl: true,
    style: {
      version: 8,
      sources: {
        world: { type: "geojson", data: world },
        evidence: { type: "geojson", data: data.geojson },
      },
      layers: [
        {
          id: "background",
          type: "background",
          paint: { "background-color": "#0e1b22" },
        },
        {
          id: "land",
          source: "world",
          type: "fill",
          paint: { "fill-color": "#243741", "fill-outline-color": "#49616b" },
        },
        {
          id: "areas",
          source: "evidence",
          type: "fill",
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: {
            "fill-color": [
              "interpolate",
              ["linear"],
              ["coalesce", ["get", "count"], 1],
              1,
              "#73d3bb",
              10,
              "#e19c72",
              40,
              "#cb6d71",
            ],
            "fill-opacity": 0.5,
          },
        },
        {
          id: "lines",
          source: "evidence",
          type: "line",
          filter: [
            "in",
            ["geometry-type"],
            ["literal", ["LineString", "Polygon"]],
          ],
          paint: { "line-color": "#f1c680", "line-width": 2 },
        },
        {
          id: "points",
          source: "evidence",
          type: "circle",
          filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-color": "#f1c680", "circle-radius": 6 },
        },
      ],
    },
  });
  state.map.addControl(new maplibregl.NavigationControl());
  state.map.on("click", "areas", (event) => {
    const feature = event.features?.[0];
    if (feature)
      detail(feature.properties, feature.properties.name || data.title);
  });
  state.map.on("error", () =>
    notify(
      "The geographic preview could not load; evidence metadata remains available.",
      true,
    ),
  );
}
async function inspectCase(item) {
  const generation = state.generation;
  const data = (await api(`/cases/${item.id}`)).data;
  if (generation !== state.generation) return;
  detail(data, data.title);
  $("active-case").value = item.id;
  const buttons = el("div", undefined, "export-row");
  for (const format of ["json", "markdown"])
    buttons.append(
      action(`Export ${format === "json" ? "data" : "report"}`, async () => {
        const result = await api(`/cases/${item.id}/export?format=${format}`, {
          method: "POST",
        });
        const blob = new Blob(
          [
            format === "json"
              ? JSON.stringify(result, null, 2)
              : result.data.text,
          ],
          { type: "text/plain;charset=utf-8" },
        );
        const url = URL.createObjectURL(blob);
        const a = el("a");
        a.href = url;
        a.download = `case-${item.id}.${format === "json" ? "json" : "md"}`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }),
    );
  $("detail").append(buttons);
  $("detail").append(
    action("Show case evidence network", async () => {
      const network = (await api(`/cases/${item.id}/graph`)).data;
      graph(network, (node) => {
        const evidence = data.evidence.find((e) => e.id === node.entity_id);
        detail(evidence?.snapshot || data, node.name);
      });
    }),
  );
  $("detail").append(
    action("Add private note", () =>
      modal(
        "Add analyst note",
        [{ name: "text", label: "Note", multiline: true, max: 10000 }],
        async (form) => {
          await api(`/cases/${item.id}/notes`, {
            method: "POST",
            body: { text: form.get("text") },
          });
          await inspectCase(item);
        },
      ),
    ),
  );
  $("detail").append(
    action("Change case status", () =>
      modal(
        "Update case",
        [
          {
            name: "status",
            label: "Status",
            options: [
              ["open", "Open"],
              ["review", "Review"],
              ["closed", "Closed"],
              ["deleted", "Delete with retention policy"],
            ],
            value: data.status,
          },
        ],
        async (form) => {
          await api(`/cases/${item.id}`, {
            method: "PATCH",
            body: {
              title: data.title,
              description: data.description,
              tags: data.tags,
              status: form.get("status"),
            },
          });
          await refreshCases();
        },
      ),
    ),
  );
  const timeline = (await api(`/cases/${item.id}/timeline`)).data;
  $("detail").append(el("h3", "Investigation timeline"));
  for (const row of timeline.slice(-30))
    $("detail").append(
      el(
        "p",
        `${date(row.timestamp)} · ${row.action || row.text || row.snapshot?.title || row.kind}`,
      ),
    );
  $("summary").textContent =
    `${data.evidence.length} evidence snapshots · ${data.notes.length} private notes · ${data.history.length} audit entries`;
  records(
    data.evidence.map((r) => ({
      ...r.snapshot,
      id: r.reference_id,
      saved_hash: r.sha256,
      saved_at: r.added_at,
    })),
    null,
    (record) => detail(record),
  );
}
async function pollJob(id) {
  notify(
    "Request queued. You can continue investigating while the worker processes it.",
  );
  for (let count = 0; count < 90; count++) {
    await new Promise((r) => setTimeout(r, 4000));
    if (!state.token) return;
    const job = (await api(`/jobs/${id}`)).data;
    if (job.state === "completed") {
      if (job.result?.source_id === "sans") ipActivityDetail(job.result);
      else
        detail(
          job.result,
          job.kind === "analysis"
            ? "Evidence-grounded assessment"
            : job.kind === "threat_catalog"
              ? "Reference catalog refresh"
              : "Source observation",
        );
      notify(
        "Request completed; inspect source evidence and limitations in the evidence desk.",
      );
      return;
    }
    if (["failed", "cancelled"].includes(job.state))
      throw new Error(job.error || "Request cancelled.");
  }
  notify("Request is still queued or running. Refresh its job status later.");
}
function analyzeSelected(kind = "record") {
  const ids = [...state.selected];
  if (!ids.length) throw new Error("Select evidence records first.");
  modal(
    "Evidence-grounded analysis",
    [{ name: "question", label: "Research question", max: 1000 }],
    async (form) => {
      const result = await api(
        kind === "document" ? "/documents/analyze" : "/correlation/analyze",
        {
          method: "POST",
          body: {
            question: form.get("question"),
            record_ids: ids.slice(0, 20),
          },
        },
      );
      pollJob(result.data.job_id).catch(failed);
    },
  );
}
async function refresh() {
  const generation = ++state.generation;
  $("pagination").hidden = true;
  disposeVisual();
  $("controls").replaceChildren();
  $("results").replaceChildren(el("p", "Loading stored evidence…", "muted"));
  $("summary").replaceChildren();
  const q = $("query").value,
    params = new URLSearchParams({
      q,
      limit: "50",
      offset: String(state.offset),
    });
  let result;
  const controls = $("controls");
  if (state.module === "search") {
    controls.append(
      action("Refine search", () =>
        modal(
          "Search filters",
          [
            {
              name: "source",
              label: "Registered source ID (optional)",
              required: false,
              max: 100,
              value: state.filters.source || "",
            },
            {
              name: "language",
              label: "Language code (optional)",
              required: false,
              max: 10,
              value: state.filters.language || "",
            },
            {
              name: "country",
              label: "Country code (optional)",
              required: false,
              max: 2,
              value: state.filters.country || "",
            },
            {
              name: "start",
              label: "Published from (UTC, optional)",
              type: "datetime-local",
              required: false,
            },
            {
              name: "end",
              label: "Published until (UTC, optional)",
              type: "datetime-local",
              required: false,
            },
          ],
          async (form) => {
            state.filters = Object.fromEntries(
              [...form.entries()].filter(([, value]) => value),
            );
            for (const key of ["start", "end"])
              if (state.filters[key])
                state.filters[key] = new Date(
                  state.filters[key] + "Z",
                ).toISOString();
            state.offset = 0;
          },
        ),
      ),
      action("Clear filters", () => {
        state.filters = {};
        state.offset = 0;
        return refresh();
      }),
    );
    controls.append(
      selectors(
        [
          ["", "All intelligence"],
          ["geopolitical", "Geopolitical"],
          ["military", "Military"],
          ["cyber", "Cyber"],
          ["sentiment", "Public discourse"],
          ["documents", "Documents"],
          ["organizations", "Organizations"],
          ["locations", "Geographic evidence"],
          ["cases", "Cases"],
          ["resources", "Research resources"],
          ["indicators", "Indicators"],
        ],
        state.category,
        (value) => (state.category = value),
      ),
      action("Research resources", () => navigate("sources")),
      action("Compare selected", () => navigate("correlation")),
    );
    params.set("category", state.category);
    for (const [key, value] of Object.entries(state.filters))
      params.set(key, value);
    params.set("order", "relevance");
    result = await api(`/osint/search?${params}`);
    if (generation !== state.generation) return;
    records(
      result.data,
      state.category === "documents"
        ? "document"
        : !state.category ||
            ["geopolitical", "military", "cyber", "sentiment"].includes(
              state.category,
            )
          ? "record"
          : null,
    );
  } else if (state.module === "cyber") {
    controls.append(
      action("Threat actors & campaigns", () => navigate("actors")),
      action("Dated cyber reports", async () => {
        const found = await api(`/osint/search?category=cyber&${params}`);
        records(found.data, "record", (item) => detail(item));
        $("summary").textContent =
          "Collected cyber reports and advisories. KEV records are catalog additions; country mentions provide report context.";
      }),
      action("Saved SANS IP activity", async () => {
        const found = await api("/cyber/activity");
        records(
          found.data.map((row) => ({
            ...row,
            title: `${row.payload.resource} · Observed IP activity`,
          })),
          null,
          (row) => ipActivityDetail(row.payload),
        );
        $("summary").textContent =
          "SANS sensor observations and ASN context. Source IP is not an actor's physical location; false positives are possible.";
      }),
    );
    controls.append(
      action("Look up an indicator", () =>
        modal(
          "Local indicator enrichment",
          [
            {
              name: "indicator",
              label: "IP, domain, URL, file hash, CVE or AS number",
              max: 2048,
            },
            {
              name: "provider_id",
              label: "Provider",
              options: [
                ["local", "Local collected advisories"],
                ["ripe", "RIPEstat public routing lookup (free)"],
                ["sans", "SANS ISC public IP activity (free)"],
              ],
            },
          ],
          async (form) => {
            const found = await api("/cyber/enrich", {
              method: "POST",
              body: {
                indicator: form.get("indicator"),
                provider_id: form.get("provider_id"),
              },
            });
            detail(found.data);
            if (found.data.job_id) pollJob(found.data.job_id).catch(failed);
          },
        ),
      ),
      action("Research providers", () => {
        state.category = "cyber";
        navigate("sources");
      }),
      action("Country outage observations", async () => {
        const observations = await api("/cyber/disruptions?limit=200");
        records(
          observations.data.map((r) => ({
            ...r,
            title: `${r.name} · ${r.datasource} availability observation`,
            published_at: r.start_at,
          })),
          null,
          (item) => detail(item),
        );
        $("summary").textContent =
          `IODA · ${date(observations.meta.measurement_period?.from)} to ${date(observations.meta.measurement_period?.until)} · Country aggregates; source scores are not causal probabilities.`;
        if (observations.data.length) {
          const world = await (await fetch("/countries.geojson")).json();
          const counts = new Map();
          for (const row of observations.data)
            counts.set(row.country, (counts.get(row.country) || 0) + 1);
          await showGeo({
            title: "IODA country observation counts",
            precision: "country",
            basis:
              "Country-level measurement observations. Color shows count of reported observations, not outage severity or population affected.",
            source_url: "https://ioda.inetintel.cc.gatech.edu/",
            geojson: {
              type: "FeatureCollection",
              features: world.features
                .filter((f) => counts.has(f.properties.code))
                .map((f) => ({
                  ...f,
                  properties: {
                    ...f.properties,
                    count: counts.get(f.properties.code),
                  },
                })),
            },
          });
        }
      }),
      action("Refresh IODA observations", async () => {
        const job = await api("/cyber/disruptions/refresh", { method: "POST" });
        pollJob(job.data.job_id).catch(failed);
      }),
      action("Saved routing lookups", async () => {
        const lookups = await api("/cyber/infrastructure");
        records(
          lookups.data.map((r) => ({
            ...r,
            title: r.payload.resource + " · RIPEstat routing",
          })),
          null,
          (item) => detail(item.payload),
        );
      }),
    );
    result = await api(`/cyber/indicators?${params}`);
    if (generation !== state.generation) return;
    records(result.data, null, async (item) =>
      detail((await api(`/cyber/indicators/${item.indicator_id}`)).data),
    );
    $("summary").textContent =
      "Public cyber feeds, local indicators, country outages, RIPEstat routing and SANS IP observations. Open Threat actors & campaigns for historical knowledge and report links.";
  } else if (state.module === "actors") {
    const catalogs = (await api("/cyber/catalogs")).data;
    if (generation !== state.generation) return;
    controls.append(
      selectors(
        [
          ["threat_actor", "Threat actors"],
          ["campaign", "Campaigns"],
          ["malware", "Malware"],
          ["tool", "Tools"],
          ["technique", "Techniques"],
        ],
        state.threatKind,
        (value) => (state.threatKind = value),
      ),
      selectors(
        [
          ["", "All reference catalogs"],
          ...catalogs.map((row) => [row.source_id, row.name]),
        ],
        state.threatSource,
        (value) => (state.threatSource = value),
      ),
      action("Catalog status & refresh", () => {
        records(
          catalogs.map((row) => ({
            ...row,
            title: row.name,
            description: `${row.object_count} active objects · ${row.relation_count} relationships · Last successful check ${date(row.last_success)} · ${row.error || row.state}${row.validation_notes?.length ? ` · ${row.validation_notes.length} malformed entries excluded` : ""}`,
          })),
          null,
          (row) => {
            detail(row);
            $("detail").append(
              action("Refresh this catalog", async () => {
                const job = await api(
                  `/cyber/catalogs/${row.source_id}/refresh`,
                  { method: "POST" },
                );
                pollJob(job.data.job_id).catch(failed);
              }),
            );
          },
        );
        disposeVisual();
        $("summary").textContent =
          "Daily reference refreshes. Last successful snapshots remain available after a provider failure.";
      }),
    );
    params.set("type", state.threatKind);
    params.set("source", state.threatSource);
    result = await api(`/cyber/actors?${params}`);
    if (generation !== state.generation) return;
    const select = async (item) => {
      const profile = await api(`/cyber/actors/${item.entity_id}`);
      if (generation !== state.generation) return;
      threatDetail(profile.data);
      const network = await api(
        `/graph/neighborhood/${item.entity_id}?nodes=24&edges=40`,
      );
      if (generation !== state.generation) return;
      graph(network.data, null, item.entity_id);
    };
    records(result.data, "entity", select);
    metrics([
      ["Matching reference entities", result.meta.total],
      ["Catalogs collected", catalogs.filter((row) => row.last_success).length],
      [
        "Reported catalog relationships",
        catalogs.reduce((sum, row) => sum + row.relation_count, 0),
      ],
    ]);
    $("summary").append(
      el(
        "p",
        "Arrows show historical catalog relationships. Dashed lines show report co-mentions. Shared source identifiers are deduplicated; source revisions are not incident dates.",
        "muted",
      ),
    );
    if (result.data.length)
      await select(
        result.data.find((item) => item.report_count > 0) ||
          result.data.find((item) =>
            item.catalog_sources.includes("mitre_attack"),
          ) ||
          result.data[0],
      );
  } else if (state.module === "narratives") {
    controls.append(
      action("Save this topic", () =>
        modal(
          "Save narrative search",
          [{ name: "name", label: "Topic name", max: 200 }],
          async (form) => {
            await api("/narratives/saved", {
              method: "POST",
              body: { name: form.get("name"), query: q || "world" },
            });
          },
        ),
      ),
      action("Saved topics", async () => {
        const saved = (await api("/narratives/saved")).data;
        records(saved, null, (item) => {
          $("query").value = item.query;
          refresh().catch(failed);
        });
      }),
    );
    const [clusters, sentiment, trends] = await Promise.all([
      api(`/narratives?${params}`),
      api(`/narratives/sentiment?q=${encodeURIComponent(q)}`),
      api(`/narratives/trends?q=${encodeURIComponent(q)}`),
    ]);
    result = clusters;
    if (generation !== state.generation) return;
    metrics([
      ["Indexed samples", sentiment.data.reduce((a, r) => a + r.samples, 0)],
      ["Languages", new Set(sentiment.data.map((r) => r.language)).size],
      ["Prior daily baseline", trends.meta.baseline_daily.toFixed(1)],
    ]);
    $("summary").append(
      el(
        "p",
        sentiment.meta.method +
          ". Unsupported languages remain unclassified. These samples do not measure national public opinion.",
      ),
    );
    $("visual").hidden = false;
    state.chart = echarts.init($("visual"));
    state.chart.setOption({
      backgroundColor: "transparent",
      color: ["#72cfb3", "#d89482", "#8095a1", "#766e95"],
      tooltip: { trigger: "item" },
      legend: { bottom: 12, textStyle: { color: "#c0d4dc" } },
      series: [
        {
          type: "pie",
          radius: ["45%", "68%"],
          label: { color: "#c0d4dc" },
          data: ["positive", "negative", "neutral", "unclassified"].map(
            (name) => ({
              name,
              value: sentiment.data
                .filter((r) => r.sentiment === name)
                .reduce((a, r) => a + r.samples, 0),
            }),
          ),
        },
      ],
    });
    records(result.data, null, async (item) => {
      const found = (await api(`/narratives/${item.cluster_id}`)).data;
      detail(found);
      records(found.members, "record");
    });
  } else if (state.module === "geo") {
    controls.append(
      action("Resolve a place or coordinate", async () => {
        const found = await api(`/geo/search?q=${encodeURIComponent(q)}`);
        records(found.data, null);
        $("summary").textContent =
          found.meta.geocoder ||
          found.meta.coverage ||
          "Analyst coordinate input";
      }),
      action("Measure distance or area", () =>
        modal(
          "Geographic measurement",
          [
            {
              name: "operation",
              label: "Measurement",
              options: [
                ["distance", "Distance"],
                ["area", "Closed polygon area"],
              ],
            },
            {
              name: "coordinates",
              label: "One longitude, latitude pair per line",
              multiline: true,
            },
          ],
          async (form) => {
            const coordinates = String(form.get("coordinates"))
              .trim()
              .split("\n")
              .map((line) => line.split(",").map(Number));
            detail(
              (
                await api("/geo/measure", {
                  method: "POST",
                  body: { operation: form.get("operation"), coordinates },
                })
              ).data,
              "Measurement result",
            );
          },
        ),
      ),
      action("Import geographic evidence", () =>
        modal(
          "Import geographic evidence",
          [
            { name: "title", label: "Evidence title", max: 200 },
            {
              name: "file",
              label: "GeoJSON file",
              type: "file",
              accept: ".geojson,.json",
            },
            {
              name: "precision",
              label: "Location precision",
              options: [
                ["approximate", "Approximate"],
                ["region", "Administrative region"],
                ["country", "Country only"],
                ["exact", "Independently substantiated coordinate"],
                ["unresolved", "Unresolved"],
              ],
            },
            {
              name: "basis",
              label: "Evidence supporting this location",
              multiline: true,
              max: 1000,
            },
            {
              name: "source_url",
              label: "Original source URL",
              type: "url",
              max: 2048,
            },
            {
              name: "acquired_at",
              label: "Imagery acquisition time (optional, UTC)",
              type: "datetime-local",
              required: false,
            },
          ],
          async (form) => {
            const file = form.get("file");
            if (file.size > 60000)
              throw new Error("Use an overlay smaller than 60 KB.");
            await api("/geo/import", {
              method: "POST",
              body: {
                title: form.get("title"),
                geojson: JSON.parse(await file.text()),
                precision: form.get("precision"),
                basis: form.get("basis"),
                source_url: form.get("source_url"),
                acquired_at: form.get("acquired_at")
                  ? new Date(form.get("acquired_at") + "Z").toISOString()
                  : null,
                license_classification: "authorized",
              },
            });
          },
        ),
      ),
    );
    result = await api(`/geo/evidence?${params}`);
    if (generation !== state.generation) return;
    records(result.data, "geo", showGeo);
    $("summary").textContent =
      "Country lookup uses Natural Earth. Measurements assume a spherical Earth. Historical imagery acquisition and retrieval times remain separate.";
  } else if (state.module === "media") {
    controls.append(
      action("Upload authorized evidence", () =>
        modal(
          "Inspect image or video evidence",
          [
            {
              name: "file",
              label: "PNG, JPEG or MP4 · maximum 20 MB",
              type: "file",
              accept: "image/png,image/jpeg,video/mp4",
            },
            {
              name: "original_url",
              label: "Original public source URL (optional)",
              type: "url",
              required: false,
            },
          ],
          async (form) => {
            const file = form.get("file");
            if (file.size > 20 * 1024 * 1024)
              throw new Error("File exceeds 20 MB.");
            const found = await api(
              `/media/evidence?filename=${encodeURIComponent(file.name)}&original_url=${encodeURIComponent(form.get("original_url"))}`,
              { method: "POST", raw: file, type: file.type },
            );
            detail(found.data);
          },
        ),
      ),
    );
    result = await api(`/media/evidence?${params}`);
    if (generation !== state.generation) return;
    records(result.data, "media", async (item) => {
      detail((await api(`/media/evidence/${item.id}`)).data);
      $("detail").append(
        action("Record verification step", () =>
          modal(
            "Record verification step",
            [
              { name: "step", label: "Method used", max: 200 },
              {
                name: "result",
                label: "Findings and limitations",
                multiline: true,
                max: 4000,
              },
            ],
            async (form) => {
              await api(`/media/evidence/${item.id}/verify`, {
                method: "POST",
                body: { step: form.get("step"), result: form.get("result") },
              });
            },
          ),
        ),
        action("Delete evidence", async () => {
          await api(`/media/evidence/${item.id}`, { method: "DELETE" });
          notify(
            "Evidence deleted from the active collection. Retention policy applies to the stored file.",
          );
          await refresh();
        }),
      );
    });
    $("summary").textContent =
      "Hashes identify the uploaded file. EXIF and container metadata are unverified. Content Credentials verification is not configured.";
  } else if (state.module === "graph") {
    controls.append(
      selectors(
        [
          ["", "All entity types"],
          ["country", "Countries"],
          ["institution", "Public institutions"],
          ["organization", "Organizations"],
          ["infrastructure", "Infrastructure"],
          ["threat_actor", "Threat actors"],
          ["campaign", "Campaigns"],
          ["malware", "Malware"],
          ["tool", "Tools"],
          ["technique", "Techniques"],
        ],
        state.graphType,
        (value) => (state.graphType = value),
      ),
      selectors(
        [
          ["", "All relationship evidence"],
          ["reported", "Reported references"],
          ["inferred", "Analyst hypotheses"],
        ],
        state.graphStatus,
        (value) => (state.graphStatus = value),
      ),
    );
    controls.append(
      action("Create or resolve an entity", () =>
        modal(
          "Entity identity and alias",
          [
            { name: "name", label: "Entity name", max: 200 },
            {
              name: "type",
              label: "Entity type",
              options: [
                ["organization", "Organization"],
                ["institution", "Institution"],
                ["location", "Location"],
                ["infrastructure", "Infrastructure"],
              ],
            },
            {
              name: "entity_id",
              label: "Existing entity ID (optional)",
              required: false,
              max: 32,
            },
            {
              name: "alias",
              label: "Alias (optional)",
              required: false,
              max: 200,
            },
          ],
          async (form) => {
            await api("/graph/resolve", {
              method: "POST",
              body: {
                name: form.get("name"),
                type: form.get("type"),
                entity_id: form.get("entity_id") || null,
                alias: form.get("alias") || null,
                evidence_ids: [...state.selected].slice(0, 20),
              },
            });
          },
        ),
      ),
    );
    params.set("type", state.graphType);
    result = await api(`/graph/entities?${params}`);
    if (generation !== state.generation) return;
    records(result.data, "entity", async (item) => {
      detail((await api(`/graph/entities/${item.entity_id}`)).data);
      graph(
        (
          await api(
            `/graph/neighborhood/${item.entity_id}?nodes=24&edges=40&status=${state.graphStatus}`,
          )
        ).data,
      );
    });
    if (result.data.length)
      graph(
        (
          await api(
            `/graph/neighborhood/${result.data[0].entity_id}?nodes=24&edges=40&status=${state.graphStatus}`,
          )
        ).data,
      );
    $("summary").textContent =
      "Click a node to expand one bounded neighborhood. Click a dashed edge for its source records. Shared labels never automatically merge analyst-created identities.";
    controls.append(
      action("Add evidence-supported relationship", () => {
        if (!state.selected.size)
          throw new Error("Select supporting source records in Search first.");
        const options = result.data.map((n) => [
          n.entity_id,
          `${n.name} · ${n.type}`,
        ]);
        modal(
          "Document a relationship",
          [
            { name: "from_id", label: "First entity", options },
            { name: "to_id", label: "Second entity", options },
            {
              name: "type",
              label: "Relationship type",
              options: [
                ["reported_link", "Reported link"],
                ["institutional", "Institutional relationship"],
                ["documented_ownership", "Documented ownership"],
                ["analyst_hypothesis", "Analyst hypothesis"],
              ],
            },
            {
              name: "status",
              label: "Evidence status",
              options: [
                ["reported", "Reported by source"],
                ["inferred", "Analyst inference"],
              ],
            },
            {
              name: "basis",
              label: "Evidence basis and limitations",
              multiline: true,
              max: 1000,
            },
          ],
          async (form) => {
            await api("/graph/relationships", {
              method: "POST",
              body: {
                ...Object.fromEntries(form),
                evidence_ids: [...state.selected].slice(0, 20),
              },
            });
          },
        );
      }),
    );
  } else if (state.module === "watch") {
    controls.append(
      action("Register an authorized page", () =>
        modal(
          "Register source monitoring",
          [
            { name: "title", label: "Source name", max: 200 },
            {
              name: "url",
              label: "HTTPS URL on a configured allowed host",
              type: "url",
              max: 2048,
            },
            {
              name: "permission_basis",
              label: "Basis for permitted monitoring (at least 30 characters)",
              multiline: true,
              max: 1000,
            },
            {
              name: "interval_seconds",
              label: "Poll interval in seconds (minimum 900)",
              type: "number",
              value: "3600",
            },
          ],
          async (form) => {
            await api("/watch/sources", {
              method: "POST",
              body: {
                title: form.get("title"),
                url: form.get("url"),
                permission_basis: form.get("permission_basis"),
                interval_seconds: Number(form.get("interval_seconds")),
              },
            });
          },
        ),
      ),
    );
    result = await api(`/watch/sources?${params}`);
    if (generation !== state.generation) return;
    records(result.data, null, async (item) => {
      detail(item);
      $("detail").append(
        action(item.enabled ? "Pause monitor" : "Resume monitor", async () => {
          await api(`/watch/sources/${item.id}`, {
            method: "PATCH",
            body: { enabled: !item.enabled },
          });
          await refresh();
        }),
      );
      const changes = await api(`/watch/sources/${item.id}/changes`);
      records(changes.data, "change", async (row) =>
        detail(
          (await api(`/watch/changes/${row.id}`)).data,
          "Versioned source change",
        ),
      );
    });
    $("summary").textContent =
      "Monitors require an allowed hostname and permission basis. Public DNS is pinned, redirects are blocked, robots policies are checked, and the latest 20 snapshots are retained.";
  } else if (state.module === "documents") {
    controls.append(
      action("Filter documents", () =>
        modal(
          "Document filters",
          [
            {
              name: "organization",
              label: "Organization (optional)",
              required: false,
              max: 200,
            },
            {
              name: "jurisdiction",
              label: "Jurisdiction country code (optional)",
              required: false,
              max: 2,
            },
            {
              name: "source",
              label: "Source ID (optional)",
              required: false,
              max: 100,
            },
            {
              name: "start",
              label: "Published from (UTC, optional)",
              type: "datetime-local",
              required: false,
            },
            {
              name: "end",
              label: "Published until (UTC, optional)",
              type: "datetime-local",
              required: false,
            },
          ],
          async (form) => {
            state.documentFilters = Object.fromEntries(
              [...form.entries()].filter(([, value]) => value),
            );
            if (state.documentFilters.jurisdiction)
              state.documentFilters.jurisdiction =
                state.documentFilters.jurisdiction.toUpperCase();
            for (const key of ["start", "end"])
              if (state.documentFilters[key])
                state.documentFilters[key] = new Date(
                  state.documentFilters[key] + "Z",
                ).toISOString();
            state.offset = 0;
          },
        ),
      ),
      action("Clear document filters", () => {
        state.documentFilters = {};
        return refresh();
      }),
    );
    controls.append(
      action("Import an authorized document", () =>
        modal(
          "Document reference and text",
          [
            { name: "title", label: "Document title", max: 500 },
            { name: "organization", label: "Organization", max: 200 },
            {
              name: "jurisdiction",
              label: "Jurisdiction country code (optional)",
              required: false,
              max: 2,
            },
            {
              name: "published_at",
              label: "Publication time in UTC (optional)",
              type: "datetime-local",
              required: false,
            },
            {
              name: "version",
              label: "Document version",
              value: "1",
              max: 100,
            },
            {
              name: "source_id",
              label: "Registered source ID",
              value: "documentcloud",
              max: 100,
            },
            {
              name: "original_url",
              label: "Original document URL",
              type: "url",
              max: 2048,
            },
            {
              name: "license_classification",
              label: "Content permission",
              options: [
                ["metadata_only", "Reference metadata only"],
                ["authorized", "Authorized text"],
                ["public_domain", "Public domain"],
                [
                  "restricted",
                  "Restricted internal text; excluded from export",
                ],
              ],
            },
            {
              name: "text",
              label: "Authorized text (optional)",
              multiline: true,
              required: false,
              max: 40000,
            },
          ],
          async (form) => {
            await api("/documents", {
              method: "POST",
              body: {
                ...Object.fromEntries(form),
                jurisdiction: form.get("jurisdiction")?.toUpperCase() || null,
                published_at: form.get("published_at")
                  ? new Date(form.get("published_at") + "Z").toISOString()
                  : null,
              },
            });
          },
        ),
      ),
    );
    for (const [key, value] of Object.entries(state.documentFilters || {}))
      params.set(key, value);
    result = await api(`/documents?${params}`);
    if (generation !== state.generation) return;
    records(result.data, "document", (item) => {
      detail(item);
      $("detail").append(
        action("Summarize this document", () => {
          state.selected = new Set([item.id]);
          analyzeSelected("document");
        }),
      );
    });
    $("summary").textContent =
      "Text import is optional and permission-labeled. Publication dates remain unknown unless supplied; restricted text is excluded from AI packets and exports.";
  } else if (state.module === "correlation") {
    controls.append(
      action("Choose source records", () => navigate("search")),
      action("Compare selected records", async () => {
        if (state.selected.size < 2)
          throw new Error(
            "Select at least two records in Search before comparing.",
          );
        const found = await api("/correlation/candidates", {
          method: "POST",
          body: { record_ids: [...state.selected].slice(0, 50) },
        });
        records(
          found.data.map((r) => ({
            ...r,
            title: `Association score ${(r.score * 100).toFixed(1)} / 100`,
          })),
          null,
          (item) => detail(item, "Deterministic association"),
        );
      }),
      action("Request AI assessment", () => analyzeSelected()),
    );
    const usage = await api("/ai/usage");
    if (generation !== state.generation) return;
    metrics([
      ["Selected source records", state.selected.size],
      ["Investigation requests left", usage.data.remaining],
      ["Provider requests left", usage.data.provider.remaining],
    ]);
    $("summary").append(
      el(
        "p",
        "Default score: time 40%, shared country 30%, title overlap 30%. These scores indicate associations, not causal probabilities. AI assessment is optional and citation-validated.",
      ),
    );
    records([], null);
    result = { data: [], meta: { total: 0 } };
  } else if (state.module === "cases") {
    result = await api(`/cases?${params}`);
    if (generation !== state.generation) return;
    records(result.data, null, inspectCase);
    $("summary").textContent =
      "Evidence snapshots remain unchanged when source records update. Case notes are private; deletion applies the configured retention period.";
  } else if (state.module === "sources") {
    controls.append(
      selectors(
        [
          ["", "All source categories"],
          ["geopolitical", "Geopolitical"],
          ["military", "Military"],
          ["cyber", "Cyber"],
          ["documents", "Documents"],
          ["geo", "Geographic"],
          ["media", "Media"],
        ],
        state.category,
        (value) => (state.category = value),
      ),
    );
    params.set("category", state.category);
    result = await api(`/sources?${params}`);
    if (generation !== state.generation) return;
    records(result.data, null, (item) => {
      detail(item);
      if (item.integration === "analyst_lookup" && item.details?.search_url)
        $("detail").append(
          action(`Open ${item.name} search`, async () => {
            if (!q)
              throw new Error(
                "Enter a search term before opening an external provider.",
              );
            const result = await api("/osint/search/external", {
              method: "POST",
              body: { provider_id: item.source_id, query: q, confirmed: true },
            });
            $("detail").append(
              link(result.data.url, `Continue to ${result.data.provider} ↗`),
            );
          }),
        );
      if (item.permissions_state === "existing_connector")
        $("detail").append(
          action(
            item.enabled ? "Disable collection" : "Enable collection",
            () =>
              modal(
                "Source collection settings",
                [
                  {
                    name: "permission_basis",
                    label:
                      "Reason and permission basis (at least 30 characters)",
                    multiline: true,
                    max: 1000,
                  },
                ],
                async (form) => {
                  await api(`/sources/${item.source_id}`, {
                    method: "PATCH",
                    body: {
                      enabled: !item.enabled,
                      permission_basis: form.get("permission_basis"),
                    },
                  });
                },
              ),
          ),
        );
    });
    metrics([
      ["Registered resources", result.meta.total],
      ["Sources on this page", result.data.length],
      [
        "Current on this page",
        result.data.filter((r) => r.health.state === "ok" && !r.health.stale)
          .length,
      ],
    ]);
    $("summary").append(
      el(
        "p",
        "Source validation tracks access and freshness. A successful collection does not certify a publisher's claims. Lookup-only resources stay disabled for automation.",
      ),
    );
  }
  if (generation !== state.generation) return;
  $("pagination").hidden = false;
  $("previous").disabled = state.offset === 0;
  $("next").disabled =
    state.offset + 50 >= (result?.meta.total ?? result?.data.length ?? 0);
  $("page-description").textContent = result?.meta.total
    ? `${state.offset + 1}–${Math.min(state.offset + 50, result.meta.total)} of ${result.meta.total}`
    : "";
}
function navigate(id) {
  state.module = id;
  state.offset = 0;
  const index = modules.findIndex((m) => m[0] === id);
  // Actor research extends Cyber (AOS-02), preserving the specification's module IDs.
  $("module-code").textContent =
    id === "actors"
      ? "AOS-02 · ACTORS"
      : `AOS-${String(index + 1 - (index > 3 ? 1 : 0)).padStart(2, "0")}`;
  $("module-title").textContent = modules[index][1];
  $("module-description").textContent = modules[index][2];
  for (const button of $("modules").children)
    button.setAttribute(
      "aria-current",
      button.dataset.module === id ? "page" : "false",
    );
  refresh().catch(failed);
}
for (const [id, title] of modules) {
  const button = action(title, () => navigate(id));
  button.dataset.module = id;
  $("modules").append(button);
}
$("access-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = $("access-token").value.trim();
  $("access-token").value = "";
  try {
    await refreshCases();
    $("access-form").hidden = true;
    $("disconnect").hidden = false;
    notify(
      "Connected. Private evidence and notes stay behind server authorization.",
    );
    navigate(state.module);
  } catch (error) {
    state.token = "";
    failed(error);
  }
});
$("disconnect").addEventListener("click", () => {
  state.token = "";
  state.selected.clear();
  state.generation++;
  disposeVisual();
  $("results").replaceChildren();
  $("detail").replaceChildren();
  $("summary").replaceChildren();
  $("active-case").replaceChildren(el("option", "Choose a case"));
  $("access-form").hidden = false;
  $("disconnect").hidden = true;
  notify("Disconnected. Access token cleared from memory.");
});
$("new-case").addEventListener("click", () =>
  modal(
    "Create investigation case",
    [
      { name: "title", label: "Case name", max: 200 },
      {
        name: "description",
        label: "Research scope",
        multiline: true,
        required: false,
        max: 4000,
      },
      {
        name: "tags",
        label: "Countries, organizations or topics (comma separated)",
        required: false,
        max: 500,
      },
    ],
    async (form) => {
      const result = await api("/cases", {
        method: "POST",
        body: {
          title: form.get("title"),
          description: form.get("description"),
          tags: String(form.get("tags"))
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
        },
      });
      await refreshCases();
      $("active-case").value = result.data.id;
      notify("Investigation case created.");
    },
  ),
);
$("filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.offset = 0;
  refresh().catch(failed);
});
$("reload").addEventListener("click", () => refresh().catch(failed));
$("previous").addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - 50);
  refresh().catch(failed);
});
$("next").addEventListener("click", () => {
  state.offset += 50;
  refresh().catch(failed);
});
window.addEventListener("resize", () => state.chart?.resize());
$("module-code").textContent = "AOS-01";
$("module-description").textContent = modules[0][2];
$("modules").firstChild.setAttribute("aria-current", "page");
$("previous").disabled = true;
$("next").disabled = true;
