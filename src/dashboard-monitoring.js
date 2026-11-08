import "./dashboard-monitoring.css";
import bundledLayers from "./monitoring-layers.json";
import { api, element, dateText, sourceLink } from "./api.js";
import { createMonitoringWorkflows } from "./monitoring-workflows.js";
import { filterOrbitalPositions } from "./orbits.js";

const empty = () => ({ type: "FeatureCollection", features: [] });
const palette = {
  aviation: "#f0cc70",
  maritime: "#78bedc",
  military: "#ee9c85",
  environment: "#9bc39a",
  infrastructure: "#77d4bc",
  sensors: "#a6c9cf",
};

// Independent observation overlays share the dashboard map, while their counts
// remain separate from incident/event analytics and existing category switches.
export function createDashboardMonitoring({ open, context }) {
  const $ = (selector) => document.querySelector(selector);
  const panel = $("#monitoring-view"),
    controls = $("#monitoring-overlays");
  let layers = bundledLayers,
    items = [],
    frame = {},
    map,
    ready = false;
  let geometry = empty(),
    request,
    debounce,
    lastContext = "",
    catalogReady = false,
    pending = false;
  let selected;
  try {
    selected = new Set(
      JSON.parse(sessionStorage.getItem("osint.dashboard.monitoring")) || [],
    );
  } catch {
    selected = new Set();
  }
  const valid = new Set(layers.map((r) => r.id));
  selected = new Set([...selected].filter((id) => valid.has(id)));
  panel.innerHTML = `
    <nav class="monitor-tabs" aria-label="Monitoring panels"><button id="show-observations" aria-pressed="true">Observations</button><button id="show-investigations" aria-pressed="false">Investigations</button></nav>
    <p class="helper">Observation layers use the main map, geography and timeline. Their counts are separate from event totals.</p>
    <details id="operator-access"><summary>Operator access</summary><label for="operator-token">Local administrator token</label><input id="operator-token" type="password" autocomplete="off" /><p class="helper">Kept only in this page. Required for saved watches, imports and lookups.</p></details>
    <section id="investigations-panel" hidden aria-label="Investigation tools"></section>
    <section id="observations-panel">
      <p id="monitor-message" role="status">Select observation layers in Intelligence layers.</p>
      <button id="monitoring-retry">Refresh monitoring data</button>
      <section id="inspector" hidden aria-label="Selected monitoring observation"></section>
      <div id="dashboard-observations" aria-label="Retained monitoring observations"></div>
      <details><summary>Monitoring source health</summary><p id="monitoring-source-summary"></p><div id="monitoring-source-list"></div></details>
      <details><summary>Passive Shodan host lookup</summary><form id="shodan-form"><label for="lookup-ip">Public IP address</label><input id="lookup-ip" required maxlength="45" /><button>Look up host</button></form><p id="lookup-result" role="status"></p></details>
    </section>`;
  controls.innerHTML = `<h2>Observation layers</h2><p id="monitoring-layer-summary" class="helper"></p><div id="dashboard-monitoring-layers"></div>`;
  const workflows = createMonitoringWorkflows({
    onGeometry(data) {
      geometry = data;
      paint();
    },
    onObservation: inspect,
    onRefresh: refresh,
    getAt: () => context().at,
    getBounds: () => {
      if (!map) return null;
      const b = map.getBounds();
      return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    },
  });
  $("#monitoring-open").addEventListener("click", open);
  $("#monitoring-layer-jump").addEventListener("click", () => {
    $("#layer-search").value = "";
    $("#layer-search").dispatchEvent(new Event("input"));
    controls.scrollIntoView({ block: "start", behavior: "auto" });
    controls.querySelector("summary")?.focus();
  });
  $("#monitoring-retry").addEventListener("click", async () => {
    await catalog();
    await refresh();
  });
  $("#shodan-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = e.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      if (!$("#operator-token").value) {
        $("#operator-access").open = true;
        throw new Error("Enter the administrator token above.");
      }
      const data = await api("monitoring/shodan", {
        token: $("#operator-token").value,
        body: { ip: $("#lookup-ip").value.trim() },
      });
      $("#lookup-result").textContent =
        `${data.organization} · ports ${data.ports.join(", ") || "not supplied"}. ${data.basis}`;
      await refresh();
    } catch (e) {
      $("#lookup-result").textContent = e.message;
    } finally {
      button.disabled = false;
    }
  });

  function rows() {
    const root = $("#dashboard-monitoring-layers");
    const expanded = new Map(
      [...root.children].map((group) => [
        group.querySelector("summary").textContent,
        group.open,
      ]),
    );
    root.replaceChildren();
    const groups = [...new Set(layers.map((row) => row.group))];
    // Put the additional sensor and environment feeds ahead of overlapping views.
    const order = (group) => {
      const rank = ["Sensors", "Environment", "Reference assets"].indexOf(
        group,
      );
      return rank < 0 ? 99 : rank;
    };
    groups.sort((a, b) => order(a) - order(b));
    for (const group of groups) {
      const section = element("details", "monitoring-layer-group");
      section.open =
        expanded.get(group) ??
        (group === "Sensors" ||
          layers.some((r) => r.group === group && selected.has(r.id)));
      section.append(element("summary", "", group));
      for (const row of layers.filter((r) => r.group === group)) {
        const label = element("label", "layer-row monitoring-layer-row");
        const check = element("input");
        check.type = "checkbox";
        check.checked = selected.has(row.id);
        check.dataset.monitoringLayer = row.id;
        const copy = element("span", "layer-copy");
        copy.append(element("span", "", row.label));
        const count = element("span", "layer-count", "off");
        count.dataset.monitoringCount = row.id;
        count.title =
          "Latest retained versions in the observation response; overlapping views are not separate events";
        label.append(check, copy, count);
        check.addEventListener("change", () => {
          check.checked ? selected.add(row.id) : selected.delete(row.id);
          try {
            sessionStorage.setItem(
              "osint.dashboard.monitoring",
              JSON.stringify([...selected]),
            );
          } catch {
            /* Optional storage. */
          }
          open();
          refresh();
        });
        section.append(label);
      }
      root.append(section);
    }
    search($("#layer-search").value);
    counts();
  }
  function search(query = "") {
    const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let total = 0;
    for (const section of $("#dashboard-monitoring-layers").children) {
      let visible = 0;
      for (const label of section.querySelectorAll("label")) {
        const row = layers.find(
          (r) => r.id === label.querySelector("input").dataset.monitoringLayer,
        );
        const words = `${row.id} ${row.label} ${row.group}`.toLowerCase();
        label.hidden = !terms.every((term) => words.includes(term));
        if (!label.hidden) visible++;
      }
      section.hidden = !visible;
      total += visible;
      if (terms.length && visible) section.open = true;
    }
    controls.hidden = !total;
    return total;
  }
  function counts() {
    $("#monitoring-layer-summary").textContent =
      `${layers.length} views · ${selected.size} selected · overlapping evidence`;
    for (const node of controls.querySelectorAll("[data-monitoring-count]")) {
      const id = node.dataset.monitoringCount;
      node.textContent = selected.has(id)
        ? frame.items
          ? String(items.filter((item) => item.layers.includes(id)).length)
          : "—"
        : "off";
    }
  }
  async function catalog() {
    try {
      const data = await api("monitoring/catalog");
      catalogReady = true;
      if (data.layers?.length) layers = data.layers;
      rows();
      workflows.catalog(data);
      $("#monitoring-source-summary").textContent =
        `${data.healthy_source_count} healthy / ${data.source_count} registered sources. Registered does not mean collecting.`;
      const list = $("#monitoring-source-list");
      list.replaceChildren();
      for (const source of data.sources || []) {
        const row = element("p", "workflow-row");
        row.append(
          element("strong", "", source.name),
          element(
            "small",
            "",
            `${source.state || "never_run"} · ${source.access_requirement || source.error || source.limitation || ""}`,
          ),
        );
        list.append(row);
      }
    } catch (e) {
      catalogReady = false;
      $("#monitor-message").textContent =
        `Monitoring API unavailable (${e.message}). Layer controls remain available. Restart the API and collector, then use Refresh monitoring data.`;
      $("#monitoring-source-summary").textContent =
        `Source catalog unavailable: ${e.message}. Source health is unknown.`;
    }
  }
  function contextKey(c) {
    return JSON.stringify([c.at, c.hours, c.country, c.q, c.bbox]);
  }
  async function refresh({ quiet = false } = {}) {
    request?.abort();
    request = new AbortController();
    const own = request,
      c = context();
    lastContext = contextKey(c);
    if (!selected.size) {
      const previous = $("#monitor-message").textContent;
      items = [];
      frame = {};
      paint();
      render();
      if (catalogReady)
        $("#monitor-message").textContent =
          "Select observation layers in Intelligence layers. Their records appear on this map.";
      else $("#monitor-message").textContent = previous;
      return;
    }
    if (!quiet)
      $("#monitor-message").textContent = "Loading retained observations…";
    pending = true;
    try {
      const query = new URLSearchParams({
        layers: [...selected].join(","),
        hours: c.hours,
        limit: "2000",
      });
      if (c.at) query.set("at", c.at);
      const data = await api(`monitoring/frame?${query}`, {
        signal: own.signal,
      });
      if (own !== request) return;
      frame = data;
      items = (data.items || []).filter((item) => {
        if (
          c.q &&
          !`${item.title} ${item.description} ${(item.tags || []).join(" ")}`
            .toLowerCase()
            .includes(c.q.toLowerCase())
        )
          return false;
        if (!c.country && !c.bbox) return true;
        if (item.longitude == null || item.latitude == null) return false;
        return (
          filterOrbitalPositions([item], {
            country: c.country,
            world: c.world,
            bbox: c.bbox,
          }).length > 0
        );
      });
      paint();
      render();
    } catch (e) {
      if (e.name === "AbortError") return;
      items = [];
      frame = {};
      paint();
      render();
      $("#monitor-message").textContent =
        `Monitoring unavailable: ${e.message}. Check Source health or restart the API and collector, then retry.`;
    } finally {
      if (own === request) pending = false;
    }
  }
  function render() {
    counts();
    const list = $("#dashboard-observations");
    list.replaceChildren();
    const mapped = items.filter(
      (item) =>
        !item.expired && (item.longitude != null || item.sensor?.geometry),
    ).length;
    const c = context();
    $("#monitor-message").textContent =
      `${items.length} retained records · ${mapped} mapped${frame.truncated ? " · response capped; select fewer layers" : ""}. ${c.at ? `Playback ${dateText(c.at)}` : "Live retained view"}. ${c.country || c.bbox ? "Geographic filters show point observations only; clear them to inspect warning areas and unlocated evidence." : "Faded points are stale. Camera listings do not verify a working stream."}`;
    if (selected.size && !items.length)
      list.append(
        element(
          "p",
          "helper",
          "No retained observations match. Check source health, access requirements and the selected time. Collection begins when the updated worker runs.",
        ),
      );
    for (const item of items.slice(0, 100)) {
      const button = element("button", "dashboard-observation-row");
      button.append(
        element("strong", "", item.title),
        element(
          "small",
          "",
          `${item.source_id} · ${dateText(item.observed_at)}${item.stale ? " · stale" : ""}${item.expired ? " · expired" : ""}`,
        ),
      );
      button.addEventListener("click", () => inspect(item));
      list.append(button);
    }
    if (items.length > 100)
      list.append(
        element(
          "p",
          "helper",
          "Showing the first 100 records. Narrow the layer selection to inspect more.",
        ),
      );
  }
  function inspect(item) {
    open();
    $("#observations-panel").hidden = false;
    $("#investigations-panel").hidden = true;
    $("#show-observations").setAttribute("aria-pressed", "true");
    $("#show-investigations").setAttribute("aria-pressed", "false");
    const inspector = $("#inspector");
    inspector.hidden = false;
    const close = element("button", "", "Close observation");
    close.addEventListener("click", () => (inspector.hidden = true));
    inspector.replaceChildren(
      close,
      element("h2", "", item.title),
      element("p", "", item.description || ""),
    );
    const facts = element("dl", "workflow-facts");
    const fields = {
      Source: item.source_id,
      "Entity ID": item.entity_id,
      "Observed (UTC)": dateText(item.observed_at),
      "Received (UTC)": dateText(item.received_at),
      "Location precision": item.location_precision,
    };
    for (const [key, label] of Object.entries({
      value: "Measurement",
      unit: "Unit",
      analyte: "Analyte",
      quality: "Quality",
      expires_at: "Expires",
      method: "Method",
      product_type: "Product type",
      frequency_hz: "Frequency (Hz)",
      snr_db: "SNR (dB)",
      classification: "Classification",
      operator: "Operator",
      license: "License",
      provider_updated_at: "Provider updated",
      basis: "Evidence basis",
    })) {
      if (item.sensor?.[key] != null) fields[label] = item.sensor[key];
    }
    for (const [key, value] of Object.entries(fields)) {
      facts.append(
        element("dt", "", key.replaceAll("_", " ")),
        element("dd", "", String(value)),
      );
    }
    inspector.append(
      facts,
      element("p", "helper", item.location_basis || ""),
      sourceLink(item.source_url, "Open original source"),
    );
    if (item.sensor?.kind === "cctv" && !context().at) {
      const media =
        item.sensor.media_url ||
        (/\.mp4(?:\?|$)/i.test(item.source_url) ? item.source_url : null);
      if (media && /^https:\/\//i.test(media)) {
        const button = element("button", "", "Load public camera media");
        button.addEventListener("click", () => {
          const content = element(
            /\.mp4(?:\?|$)/i.test(media) ? "video" : "img",
            "workflow-preview",
          );
          content.controls = true;
          content.preload = "none";
          content.alt = item.title;
          content.src = media;
          content.addEventListener("error", () => {
            content.remove();
            button.textContent = "Media unavailable; open the source";
            button.disabled = true;
          });
          inspector.append(content);
          button.disabled = true;
        });
        inspector.append(button);
      }
    }
    workflows.inspectActions(inspector, item);
    if (item.longitude != null && item.latitude != null)
      map?.flyTo({
        center: [item.longitude, item.latitude],
        zoom: Math.max(map.getZoom(), 5),
        essential: false,
      });
  }
  function paint() {
    if (!ready) return;
    const features = items
      .filter((item) => !item.expired)
      .flatMap((item) => {
        const shape =
          item.sensor?.geometry ||
          (item.longitude != null && item.latitude != null
            ? { type: "Point", coordinates: [item.longitude, item.latitude] }
            : null);
        return shape
          ? [
              {
                type: "Feature",
                geometry: shape,
                properties: {
                  id: item.id,
                  color: palette[item.category] || "#b8bded",
                  stale: !!item.stale,
                },
              },
            ]
          : [];
      });
    map
      .getSource("dashboard-monitoring")
      .setData({ type: "FeatureCollection", features });
    map.getSource("dashboard-investigations").setData(geometry);
    map
      .getSource("dashboard-gnss")
      .setData(selected.has("gnss") ? frame.gnss || empty() : empty());
    map.getCanvas().dataset.monitoring = String(features.length);
  }
  function attachMap(value) {
    map = value;
    const setup = () => {
      for (const id of [
        "dashboard-monitoring",
        "dashboard-investigations",
        "dashboard-gnss",
      ])
        map.addSource(id, { type: "geojson", data: empty() });
      for (const [id, source, color] of [
        ["monitoring", "dashboard-monitoring", ["get", "color"]],
        ["investigations", "dashboard-investigations", "#77d4bc"],
      ]) {
        map.addLayer({
          id: `${id}-areas`,
          source,
          type: "fill",
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": color, "fill-opacity": 0.15 },
        });
        map.addLayer({
          id: `${id}-lines`,
          source,
          type: "line",
          filter: ["!=", ["geometry-type"], "Point"],
          paint: { "line-color": color, "line-width": 1.5 },
        });
        map.addLayer({
          id: `${id}-points`,
          source,
          type: "circle",
          filter: ["==", ["geometry-type"], "Point"],
          paint: {
            "circle-color": color,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 3, 8, 7],
            "circle-stroke-color": "#10171c",
            "circle-stroke-width": 1,
            "circle-opacity": ["case", ["get", "stale"], 0.35, 0.9],
          },
        });
      }
      map.addLayer({
        id: "dashboard-gnss-cells",
        source: "dashboard-gnss",
        type: "fill",
        paint: {
          "fill-color": "#ee9c85",
          "fill-opacity": ["*", ["get", "fraction"], 0.6],
        },
      });
      for (const id of [
        "monitoring-points",
        "monitoring-areas",
        "monitoring-lines",
      ]) {
        map.on("click", id, (e) => {
          const item = items.find((r) => r.id === e.features[0]?.properties.id);
          if (item) inspect(item);
        });
        map.on(
          "mouseenter",
          id,
          () => (map.getCanvas().style.cursor = "pointer"),
        );
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      }
      map.on("click", "dashboard-gnss-cells", (e) => {
        open();
        $("#monitor-message").textContent =
          `GNSS accuracy cell: ${e.features[0]?.properties.aircraft || "source"} aircraft; ${e.features[0]?.properties.low_accuracy || 0} low-accuracy samples. Low reported NACp is an accuracy proxy, not confirmation of jamming.`;
      });
      ready = true;
      paint();
    };
    if (map.isStyleLoaded()) setup();
    else map.once("load", setup);
  }
  rows();
  setInterval(() => {
    if (!document.hidden && selected.size && !context().at && !pending)
      refresh({ quiet: true });
  }, 15000);
  setInterval(() => {
    if (!document.hidden) catalog();
  }, 60000);
  return {
    search,
    attachMap,
    async start() {
      await catalog();
      await refresh();
    },
    contextChanged() {
      const key = contextKey(context());
      if (key === lastContext) return;
      clearTimeout(debounce);
      debounce = setTimeout(refresh, 180);
    },
  };
}
