import "./monitoring.css";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { api, element, dateText, sourceLink } from "./api.js";
import { prepareOrbits, orbitalPositions } from "./orbits.js";
import { REFERENCE_REGISTRY, nightStrips } from "./reference-layers.js";

const $ = (selector) => document.querySelector(selector);
const colors = {
  aviation: "#f0cc70",
  maritime: "#78bedc",
  military: "#ee9c85",
  geopolitical: "#b8bded",
  environment: "#9bc39a",
  infrastructure: "#77d4bc",
  cyber: "#d2a4db",
  threat: "#d2a4db",
  analysis: "#a6c9cf",
  sensors: "#a6c9cf",
  space: "#dee5f0",
};
const orbitViews = [
  {
    id: "orbit-all",
    label: "All satellites & stations",
    group: "Orbit estimates",
  },
  {
    id: "orbit-military",
    label: "Military satellites",
    group: "Orbit estimates",
  },
  {
    id: "orbit-navigation",
    label: "Navigation satellites",
    group: "Orbit estimates",
  },
  {
    id: "orbit-station",
    label: "Crewed space stations",
    group: "Orbit estimates",
  },
];
const referenceViews = Object.values(REFERENCE_REGISTRY).map((entry) => ({
  id: `ref-${entry.id}`,
  label: entry.label,
  group: "Reference geography",
}));
const defaultLayers = [
  "aircraft",
  "vessels",
  "military",
  "cctv",
  "radio",
  "ground-stations",
  "gnss",
  "infrastructure",
  "orbit-all",
];
let selected;
try {
  selected = new Set(
    JSON.parse(sessionStorage.getItem("osint.monitoring.layers")) ||
      defaultLayers,
  );
} catch {
  selected = new Set(defaultLayers);
}
let catalog,
  layers = [],
  items = [],
  orbits = [],
  orbitBasis = "",
  currentFrame;
let at = null,
  timer = null,
  controller,
  loading = false,
  mapReady = false,
  shown = [];
const referenceData = new Map();
const referencePending = new Set();
const empty = () => ({ type: "FeatureCollection", features: [] });
maplibregl.setWorkerUrl(workerUrl);

const map = new maplibregl.Map({
  container: "monitor-map",
  center: [20, 22],
  zoom: 1.2,
  minZoom: 0.6,
  attributionControl: false,
  style: {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#101b22" },
      },
    ],
  },
});
map.addControl(
  new maplibregl.NavigationControl({ showCompass: false }),
  "top-right",
);
map.addControl(
  new maplibregl.AttributionControl({
    compact: true,
    customAttribution: "Natural Earth · Source details in observations",
  }),
);
map.on("error", () => {
  $("#map-summary").textContent =
    "Map rendering unavailable. Retained observations remain accessible in the feed.";
});
map.on("load", () => {
  map.addSource("countries", {
    type: "geojson",
    data: "/countries.geojson",
    attribution: "Natural Earth",
  });
  map.addLayer({
    id: "land",
    type: "fill",
    source: "countries",
    paint: { "fill-color": "#21313b" },
  });
  map.addLayer({
    id: "borders",
    type: "line",
    source: "countries",
    paint: { "line-color": "#4a5d67", "line-width": 0.5 },
  });
  map.addSource("night", { type: "geojson", data: empty() });
  map.addLayer({
    id: "night-fill",
    type: "fill",
    source: "night",
    paint: { "fill-color": "#000000", "fill-opacity": 0.25 },
  });
  map.addSource("gnss", { type: "geojson", data: empty() });
  map.addLayer({
    id: "gnss-cells",
    type: "fill",
    source: "gnss",
    paint: {
      "fill-color": "#ee9c85",
      "fill-opacity": ["*", ["get", "fraction"], 0.6],
      "fill-outline-color": "#ee9c85",
    },
  });
  map.addSource("observations", { type: "geojson", data: empty() });
  map.addLayer({
    id: "points",
    type: "circle",
    source: "observations",
    paint: {
      "circle-color": ["get", "color"],
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3, 8, 7],
      "circle-stroke-color": "#10171c",
      "circle-stroke-width": 1,
      "circle-opacity": ["case", ["get", "stale"], 0.35, 0.9],
    },
  });
  map.on("click", "points", (event) => {
    const item = shown.find(
      (row) => row.id === event.features[0].properties.id,
    );
    if (item) inspect(item);
  });
  map.on("mouseenter", "points", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "points", () => {
    map.getCanvas().style.cursor = "";
  });
  map.on("click", "gnss-cells", (event) => {
    const props = event.features[0].properties;
    const panel = $("#inspector");
    panel.hidden = false;
    panel.replaceChildren(
      element("h2", "", "GNSS accuracy cell"),
      element(
        "p",
        "",
        `${props.low_accuracy} of ${props.aircraft} sampled airborne aircraft reported NACp 1–4.`,
      ),
      element("p", "muted", props.basis),
      element(
        "p",
        "muted",
        currentFrame?.gnss_sample_truncated
          ? "The aircraft response was truncated; this cell has incomplete sample coverage."
          : "Coverage follows the configured ADS-B source. NACp 0 and missing values are excluded.",
      ),
    );
  });
  mapReady = true;
  render();
});
map.on("idle", () => {
  if (mapReady) $("#monitor-map").dataset.ready = "true";
});

function persistLayers() {
  try {
    sessionStorage.setItem(
      "osint.monitoring.layers",
      JSON.stringify([...selected]),
    );
  } catch {
    /* Storage is optional. */
  }
}

function renderLayers() {
  const query = $("#layer-search").value.trim().toLowerCase();
  const container = $("#monitoring-layers");
  container.replaceChildren();
  for (const group of new Set(layers.map((row) => row.group))) {
    const matches = layers.filter(
      (row) =>
        row.group === group &&
        `${row.label} ${group}`.toLowerCase().includes(query),
    );
    if (!matches.length) continue;
    const fieldset = element("fieldset");
    fieldset.append(element("legend", "", group));
    for (const row of matches) {
      const label = element("label");
      const check = document.createElement("input");
      check.type = "checkbox";
      check.value = row.id;
      check.checked = selected.has(row.id);
      check.addEventListener("change", () => {
        check.checked ? selected.add(row.id) : selected.delete(row.id);
        persistLayers();
        render();
        loadFrame();
      });
      label.append(check, element("span", "", row.label));
      fieldset.append(label);
    }
    container.append(fieldset);
  }
  $("#layer-summary").textContent =
    `${layers.length} views · ${selected.size} selected`;
}

function inspect(item) {
  const panel = $("#inspector");
  panel.hidden = false;
  const close = element("button", "", "Close details");
  close.addEventListener("click", () => {
    panel.hidden = true;
  });
  const facts = element("dl");
  const fields = [
    ["Source", item.source_id || "Public orbital elements"],
    ["Observed", dateText(item.observed_at)],
    ["Received", dateText(item.received_at)],
    ["Precision", item.location_precision || "Estimated"],
    [
      "Status",
      item.stale
        ? "Stale observation"
        : item.category === "space"
          ? "Calculated orbit estimate"
          : "Retained observation",
    ],
  ];
  if (item.sensor?.nac_p != null) fields.push(["NACp", item.sensor.nac_p]);
  if (item.sensor?.directory_status)
    fields.push(["Directory", item.sensor.directory_status]);
  if (item.sensor?.provider_updated_at)
    fields.push(["Provider time", item.sensor.provider_updated_at]);
  for (const [label, value] of fields)
    facts.append(element("dt", "", label), element("dd", "", value));
  panel.replaceChildren(
    close,
    element("h2", "", item.title),
    element("p", "", item.description || ""),
    facts,
    element("p", "muted", item.location_basis || orbitBasis),
    sourceLink(item.source_url, "Open original source"),
  );
  if (
    item.sensor?.kind === "cctv" &&
    !at &&
    /\.mp4(?:\?|$)/i.test(item.source_url)
  ) {
    const play = element("button", "", "Play public camera");
    play.addEventListener("click", () => {
      const video = element("video");
      video.controls = true;
      video.playsInline = true;
      video.preload = "none";
      video.src = item.source_url;
      panel.append(video);
      play.remove();
    });
    panel.append(play);
  }
  if (at && item.sensor?.kind)
    panel.append(
      element(
        "p",
        "muted",
        "This is historical metadata. The linked source shows its current content; footage and audio are not archived.",
      ),
    );
  if (Number.isFinite(item.longitude) && Number.isFinite(item.latitude))
    map.flyTo({
      center: [item.longitude, item.latitude],
      zoom: Math.max(map.getZoom(), 5),
      essential: false,
    });
}

async function references() {
  for (const [id, entry] of Object.entries(REFERENCE_REGISTRY)) {
    if (
      !entry.file ||
      !selected.has(`ref-${id}`) ||
      referenceData.has(id) ||
      referencePending.has(id)
    )
      continue;
    referencePending.add(id);
    try {
      const response = await fetch(entry.file);
      if (!response.ok) throw new Error("Reference file unavailable");
      referenceData.set(id, await response.json());
    } catch {
      $("#monitor-message").textContent =
        `Could not load ${entry.label}. Toggle the layer to retry.`;
    } finally {
      referencePending.delete(id);
    }
  }
  if (!mapReady) return;
  for (const [id, data] of referenceData) {
    if (!map.getSource(`ref-${id}`)) {
      map.addSource(`ref-${id}`, {
        type: "geojson",
        data,
        attribution: REFERENCE_REGISTRY[id].registry.publisher,
      });
      map.addLayer({
        id: `ref-${id}`,
        type: "circle",
        source: `ref-${id}`,
        paint: {
          "circle-color": "#a5aeb8",
          "circle-radius": 3,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#10171c",
        },
      });
      map.on("click", `ref-${id}`, (event) => {
        const entry = REFERENCE_REGISTRY[id];
        const panel = $("#inspector");
        panel.hidden = false;
        panel.replaceChildren(
          element("h2", "", event.features[0].properties.name || entry.label),
          element("p", "", entry.basis),
          element(
            "p",
            "muted",
            `${entry.registry.publisher} · ${entry.registry.version} · ${entry.registry.license}`,
          ),
          element("p", "muted", entry.limitation),
          element(
            "p",
            "muted",
            "Reference geometry uses the current registry version, including during playback.",
          ),
        );
      });
    }
    map.setLayoutProperty(
      `ref-${id}`,
      "visibility",
      selected.has(`ref-${id}`) ? "visible" : "none",
    );
  }
}

function render() {
  const point = at ? new Date(at) : new Date();
  const orbital = orbitalPositions(orbits, point)
    .filter(
      (row) => selected.has("orbit-all") || selected.has(`orbit-${row.role}`),
    )
    .map((row) => ({
      ...row,
      id: row.event_id,
      layers: ["orbit-all"],
      observed_at: point.toISOString(),
      description: `${row.purpose || "Satellite"}. SGP4 estimate, not live telemetry. Element epoch: ${row.epoch}.`,
      location_basis: orbitBasis,
      stale: false,
    }));
  shown = [
    ...items.filter((item) => item.layers.some((id) => selected.has(id))),
    ...orbital,
  ];
  const located = shown.filter(
    (item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude),
  );
  if (mapReady) {
    map.getSource("observations").setData({
      type: "FeatureCollection",
      features: located.map((item) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [item.longitude, item.latitude],
        },
        properties: {
          id: item.id,
          color: colors[item.category] || "#b5c1ca",
          stale: item.stale,
        },
      })),
    });
    map
      .getSource("gnss")
      .setData(selected.has("gnss") ? currentFrame?.gnss || empty() : empty());
    map
      .getSource("night")
      .setData(
        selected.has("ref-terminator")
          ? { type: "FeatureCollection", features: nightStrips(point) }
          : empty(),
      );
    references();
  }
  $("#record-count").textContent = shown.length.toLocaleString();
  $("#map-summary").textContent =
    `${located.length.toLocaleString()} mapped · ${(shown.length - located.length).toLocaleString()} unlocated · ${at ? dateText(at) : "Live retained view"}${currentFrame?.truncated ? " · response capped" : ""}`;
  const list = $("#observation-list");
  list.replaceChildren();
  // Keep a large sensor directory from hiding every other source in the feed.
  const queues = new Map();
  for (const item of shown) {
    const source = item.source_id || "orbit-estimates";
    if (!queues.has(source)) queues.set(source, []);
    queues.get(source).push(item);
  }
  const feed = [];
  for (let index = 0; feed.length < Math.min(150, shown.length); index++) {
    for (const queue of queues.values()) {
      if (queue[index] && feed.length < 150) feed.push(queue[index]);
    }
  }
  for (const item of feed) {
    const row = element("button", "observation-row");
    row.append(
      element("strong", "", item.title),
      element(
        "small",
        "",
        `${item.source_id || "Orbit estimate"} · ${item.stale ? "stale · " : ""}${dateText(item.observed_at)}`,
      ),
    );
    row.addEventListener("click", () => inspect(item));
    list.append(row);
  }
  if (!shown.length && !loading)
    $("#monitor-message").textContent = selected.size
      ? "No retained observations match these layers and this time. Check Source health and run the collector."
      : "Select a layer to inspect observations.";
  else if (!loading)
    $("#monitor-message").textContent =
      `${shown.length > 150 ? "Showing 150, balanced across sources. " : ""}${currentFrame?.truncated ? "The server response is capped. Select fewer layers for coverage. " : ""}Faded points are stale. Directory records do not verify a working stream.`;
  $("#mode").textContent = at ? "Playback · UTC" : "Live · 15s refresh";
  $("#go-live").setAttribute("aria-pressed", String(!at));
}

async function loadFrame() {
  controller?.abort();
  controller = new AbortController();
  const own = controller,
    signal = own.signal;
  loading = true;
  $("#refresh-monitoring").disabled = true;
  $("#monitor-message").textContent = "Loading retained observations…";
  const eventIds = [...selected].filter(
    (id) => !id.startsWith("ref-") && !id.startsWith("orbit-"),
  );
  const query = new URLSearchParams({
    layers: eventIds.join(","),
    limit: "2000",
  });
  if (at) query.set("at", at);
  try {
    const results = await Promise.allSettled([
      eventIds.length
        ? api(`monitoring/frame?${query}`, { signal })
        : Promise.resolve({ items: [], gnss: empty() }),
      api(`monitoring/orbits${at ? `?at=${encodeURIComponent(at)}` : ""}`, {
        signal,
      }),
    ]);
    if (own !== controller) return;
    if (results[0].status === "rejected") throw results[0].reason;
    currentFrame = results[0].value;
    items = currentFrame.items;
    const orbitResponse =
      results[1].status === "fulfilled" ? results[1].value : null;
    orbits = prepareOrbits(orbitResponse?.snapshot);
    orbitBasis = orbitResponse?.basis || "Orbital elements unavailable";
    loading = false;
    render();
    if (!orbits.length && [...selected].some((id) => id.startsWith("orbit-")))
      $("#monitor-message").append(` ${orbitBasis}.`);
    if (!at && selected.has("aircraft")) api("aviation/live").catch(() => {}); // Existing demand-driven collector lease.
  } catch (error) {
    if (own !== controller || error.name === "AbortError") return;
    items = [];
    orbits = [];
    currentFrame = null;
    loading = false;
    render();
    $("#monitor-message").textContent =
      `Could not load observations: ${error.message}. Use Refresh to retry.`;
    $("#mode").textContent = "Unavailable";
  } finally {
    if (own === controller) {
      loading = false;
      $("#refresh-monitoring").disabled = false;
    }
  }
}

async function loadCatalog() {
  try {
    catalog = await api("monitoring/catalog");
    layers = [...catalog.layers, ...orbitViews, ...referenceViews];
    selected = new Set(
      [...selected].filter((id) => layers.some((row) => row.id === id)),
    );
    renderLayers();
    $("#source-summary").textContent =
      `${catalog.healthy_source_count} healthy / ${catalog.source_count} registered feeds. ${catalog.limitation}`;
    const sources = $("#source-list");
    sources.replaceChildren();
    for (const source of catalog.sources) {
      const row = element("div", "source-row", source.name);
      row.append(
        element(
          "small",
          "",
          `${source.state || "never_run"}${source.stale ? " · stale" : ""} · ${source.last_success ? dateText(source.last_success) : "No successful collection"}`,
        ),
        element(
          "small",
          "",
          source.access_requirement || source.error || source.limitation,
        ),
      );
      sources.append(row);
    }
    const history = catalog.history;
    $("#history-note").textContent = history.first
      ? `Retained since ${dateText(history.first)} · ${history.observations.toLocaleString()} observations · up to ${history.retention_days} days / ${history.max_rows.toLocaleString()} rows. Camera footage and radio audio are not archived. Reference geography uses current registries.`
      : "No history yet. Start or restart the collector to retain observations. Camera footage and radio audio are not archived.";
    const scrubber = $("#history-scrubber");
    scrubber.disabled = !history.first;
    $("#play").disabled = !history.first;
    if (history.first) {
      scrubber.min = String(Date.parse(history.first));
      scrubber.max = String(Date.now());
      scrubber.step = "1000";
      if (!at) scrubber.value = scrubber.max;
    }
  } catch (error) {
    $("#source-summary").textContent =
      `Source health unavailable: ${error.message}`;
    throw error;
  }
}

function stop() {
  clearInterval(timer);
  timer = null;
  $("#play").textContent = "Play history";
}
async function setTime(value) {
  const point = new Date(value);
  if (!Number.isFinite(point.getTime()) || point.getTime() > Date.now()) {
    $("#monitor-message").textContent =
      "Choose a valid UTC time at or before now.";
    stop();
    return;
  }
  at = point.toISOString();
  $("#playback-time").value = at.slice(0, 16);
  $("#history-scrubber").value = String(point.getTime());
  $("#inspector").replaceChildren();
  $("#inspector").hidden = true;
  await loadFrame();
}
$("#layer-search").addEventListener("input", renderLayers);
$("#clear-layers").addEventListener("click", () => {
  selected.clear();
  persistLayers();
  renderLayers();
  loadFrame();
});
$("#default-layers").addEventListener("click", () => {
  selected = new Set(defaultLayers);
  persistLayers();
  renderLayers();
  loadFrame();
});
$("#refresh-monitoring").addEventListener("click", async () => {
  try {
    await loadCatalog();
  } catch {
    /* Frame errors show separately. */
  }
  await loadFrame();
});
$("#time-form").addEventListener("submit", (event) => {
  event.preventDefault();
  stop();
  setTime(`${$("#playback-time").value}Z`);
});
$("#history-scrubber").addEventListener("change", (event) => {
  stop();
  setTime(Number(event.target.value));
});
$("#go-live").addEventListener("click", () => {
  stop();
  at = null;
  $("#inspector").replaceChildren();
  $("#inspector").hidden = true;
  $("#playback-time").value = new Date().toISOString().slice(0, 16);
  loadFrame();
});
$("#play").addEventListener("click", () => {
  if (timer) {
    stop();
    return;
  }
  if (!catalog?.history.first) return;
  if (!at || Date.parse(at) >= Number($("#history-scrubber").max))
    setTime(catalog.history.first);
  $("#play").textContent = "Pause";
  timer = setInterval(() => {
    if (loading || document.hidden) return;
    const next = Math.min(
      Date.parse(at) + 300000,
      Number($("#history-scrubber").max),
    );
    setTime(next);
    if (next >= Number($("#history-scrubber").max)) stop();
  }, 2000);
});
$("#shodan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  $("#lookup-result").textContent = "Reading provider record…";
  try {
    const result = await api("monitoring/shodan", {
      token: $("#operator-token").value,
      body: { ip: $("#lookup-ip").value.trim() },
    });
    $("#lookup-result").textContent =
      `${result.organization} · ports ${result.ports.join(", ") || "not supplied"}${result.cached ? " · cached" : ""}. ${result.basis}`;
    if (!at) await loadFrame();
  } catch (error) {
    $("#lookup-result").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#playback-time").value = new Date().toISOString().slice(0, 16);
try {
  await loadCatalog();
  await loadFrame();
} catch (error) {
  $("#monitor-message").textContent =
    `Monitoring unavailable: ${error.message}. Use Refresh to retry.`;
  $("#mode").textContent = "Unavailable";
}
setInterval(() => {
  if (!at && !loading && !document.hidden) loadFrame();
}, 15000);
setInterval(() => {
  if (!document.hidden) loadCatalog().catch(() => {});
}, 60000);
