import "./style.css";
import { api, dateText, element, relativeTime, sourceLink } from "./api.js";
import { createWorldMap, THIN_SAMPLE } from "./map.js";
import { renderMilitary } from "./military.js";
import { renderSocial, focusSocialPost } from "./social.js";
import {
  symbolCanvas,
  conflictIcon,
  conflictCanvas,
  colors,
} from "./layer-symbols.js";
import { CONFLICT_TYPES, conflictType } from "./conflicts.js";
import { createCountryRibbon } from "./country-ribbon.js";
import { aircraftFacts } from "./aircraft.js";
import {
  buildThreatNetwork,
  threatFacts,
  threatCaption,
  threatCountryActivity,
  threatTimeline,
  filterThreatNetwork,
  matchesThreatVector,
} from "./threats.js";
import { VECTOR_LABELS, renderVectorBreakdown } from "./threat-vectors.js";
import { searchLayers } from "./layer-search.js";
import {
  prepareOrbits,
  orbitalPositions,
  filterOrbitalPositions,
  orbitalFacts,
} from "./orbits.js";

const $ = (selector) => document.querySelector(selector);
const threatProviders = [
  "bitdefender_threatmap",
  "bunkerweb_threatmap",
  "imperva_threatmap",
  "radware_threatmap",
];
const backgroundSources = (id) =>
  threatProviders.includes(id) ||
  id.startsWith("threat_research_") ||
  id.startsWith("conflict_");
const names = {
  geopolitical: "Geopolitical events",
  military: "Military OSINT",
  aviation: "Aviation",
  maritime: "Maritime",
  sentiment: "Global sentiment",
  cyber: "Cyber: Threat Actors",
  threat: "Cyber: Threat Actors",
  economic: "Economic and energy",
  environment: "Environment and humanitarian",
  analysis: "Reporting signals & alerts",
  space: "Satellites & ISS",
};
const defaults = [
  "geopolitical",
  "military",
  "aviation",
  "maritime",
  "environment",
  "cyber",
  "threat",
  "economic",
  "space",
];
function readSession(key, fallback) {
  try {
    return JSON.parse(sessionStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}
function saveSession(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Session storage can be blocked. */
  }
}
const state = {
  layers: new Set(
    readSession("osint.layers", defaults).filter((id) => id in names),
  ),
  events: [],
  total: 0,
  categoryCounts: {},
  sources: [],
  selectedEvent: null,
  country: "",
  q: "",
  token: "",
  world: null,
  lastRefresh: null,
  period: "24",
  light: readSession("osint.light", false),
  view: "feed",
  sentimentResult: null,
  layerHealth: {},
  extendedSources: false,
  analysisOverlays: readSession("osint.analysisOverlays", false),
  densityConfidence: readSession("osint.densityConfidence", true),
  crossCategory: [],
  sentimentEvidence: readSession("osint.sentimentEvidence", true),
  newsNetwork: null,
  cyberNetwork: null,
  threatEvents: [],
  threatCount: 0,
  threatNetwork: null,
  threatVector: readSession("osint.threatVector", "all"),
  vectorSummary: null,
  timelineResult: null,
  countryActivity: null,
  military: null,
  militaryTopic: "",
  analysisEventIds: null,
  aircraft: null,
  aircraftFilter: "",
  orbits: [],
  orbitalItems: [],
  orbitalLoaded: false,
  reportingSignals: 0,
};
if (state.analysisOverlays) state.layers.add("analysis");
state.analysisOverlays = state.layers.has("analysis");
// Preserve old saved selections while exposing a single cyber layer control.
if (state.layers.has("cyber") || state.layers.has("threat")) {
  state.layers.add("cyber");
  state.layers.add("threat");
}
let worldMap,
  chart,
  refreshController,
  busy = false,
  playbackTimer,
  viewportTimer,
  countryController;
const countryRibbon = createCountryRibbon({
  selectCountry,
  readSession,
  saveSession,
  selectThreatRoute: (edge) => worldMap?.focusThreatRoute(edge),
});
for (const [value, label] of [
  ["all", "All evidence · known vectors first"],
  ["known", "Known attack vectors only"],
  ["reputation", "Reputation / blocking signals"],
  ...VECTOR_LABELS.map((label) => [label, label]),
]) {
  const option = element("option", "", label);
  option.value = value;
  $("#cyber-vector-filter").append(option);
}
if (
  !["all", "known", "reputation", ...VECTOR_LABELS].includes(state.threatVector)
)
  state.threatVector = "all";
$("#cyber-vector-filter").value = state.threatVector;
$("#cyber-vector-filter").addEventListener("change", () => {
  state.threatVector = $("#cyber-vector-filter").value;
  saveSession("osint.threatVector", state.threatVector);
  renderEvents();
  renderCountryActivity();
  renderNetworkSummary();
  if (state.timelineResult && chart)
    renderTimeline(
      threatTimeline(
        state.timelineResult,
        displayThreatNetwork(),
        state.layers,
        Number(state.period) > 168 || state.period === "custom"
          ? "day"
          : "hour",
      ),
    );
});
function displayThreatNetwork() {
  return filterThreatNetwork(
    state.threatNetwork,
    state.world?.features.map((f) => f.properties) || [],
    state.threatVector,
  );
}
for (const [category, name] of Object.entries(names)) {
  if (category === "threat") continue;
  const key = element("span");
  key.append(symbolCanvas(category), element("span", "", name));
  $("#layer-symbol-key").append(key);
}

function timeRange() {
  if (state.period === "custom") {
    const start = $("#start-date").value,
      end = $("#end-date").value;
    if (!start || !end) throw new Error("Choose both custom dates in UTC.");
    if (start > end)
      throw new Error("The start date must precede the end date.");
    return { start: new Date(start + "Z"), end: new Date(end + "Z") };
  }
  const end = new Date(),
    start = new Date(end.getTime() - Number(state.period) * 3600000);
  return { start, end };
}
function filters({ sentiment = false } = {}) {
  const { start, end } = timeRange();
  const physical = [...state.layers].filter(
    (id) => !["sentiment", "analysis", "threat", "space"].includes(id),
  );
  return {
    categories: sentiment
      ? []
      : physical.length
        ? physical
        : state.layers.has("analysis")
          ? ["geopolitical", "military"]
          : ["sentiment"],
    q: state.q,
    country: state.country || undefined,
    start: start.toISOString(),
    end: end.toISOString(),
    bbox: $("#viewport-filter").checked ? worldMap?.bounds() : undefined,
    time_basis: $("#time-basis").value,
    aircraft_categories: [4, 5],
  };
}
function params(options = {}) {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(filters(options)))
    if (value !== undefined && value !== "")
      result.set(key, Array.isArray(value) ? value.join(",") : value);
  return result;
}
function message(text) {
  $("#load-error").textContent = text;
  $("#load-error").hidden = !text;
}
function badge(confidence) {
  return element(
    "span",
    "badge " + confidence.toLowerCase().replaceAll(" ", "-"),
    confidence,
  );
}

function renderLayers() {
  $("#layers").replaceChildren();
  for (const [id, name] of Object.entries(names)) {
    if (id === "threat") continue;
    const label = element("label", "layer-row");
    const input = element("input");
    input.type = "checkbox";
    input.checked = state.layers.has(id);
    input.dataset.layer = id;
    const mark = symbolCanvas(id);
    const count = element("span", "layer-count", "");
    count.dataset.count = id;
    count.title =
      id === "aviation"
        ? "Matching observations for ADS-B classes 4 and 5 with a reported track; the map shows the latest loaded position per aircraft"
        : "All matching records in the selected period and geography";
    const copy = element("span", "layer-copy");
    const note = element("small", "layer-note");
    note.dataset.layerNote = id;
    if (id === "analysis")
      note.textContent = "Report surges & links across layers";
    copy.append(element("span", "", name), note);
    label.append(input, mark, copy, count);
    input.addEventListener("change", () => {
      input.checked ? state.layers.add(id) : state.layers.delete(id);
      if (id === "cyber")
        input.checked
          ? state.layers.add("threat")
          : state.layers.delete("threat");
      saveSession("osint.layers", [...state.layers]);
      if (input.checked && id === "sentiment") showView("sentiment");
      if (input.checked && id === "military") showView("military");
      if (id === "analysis") {
        syncReportingSignals();
        if (input.checked) showView("feed");
      }
      if (worldMap) {
        renderEvents();
        renderNetworkSummary();
        renderCountryActivity();
      }
      refresh();
    });
    $("#layers").append(label);
  }
  applyLayerSearch();
}

function syncReportingSignals() {
  state.analysisOverlays = state.layers.has("analysis");
  saveSession("osint.analysisOverlays", state.analysisOverlays);
  saveSession("osint.layers", [...state.layers]);
  $("#analysis-overlays").checked = state.analysisOverlays;
  $("#reporting-signals").hidden = !state.analysisOverlays;
  const layer = $('[data-layer="analysis"]');
  if (layer) layer.checked = state.analysisOverlays;
  worldMap?.setAnalysisVisible(state.analysisOverlays);
  renderCrossCategoryPanel();
}

function renderConflictKey(events) {
  const key = $("#conflict-symbol-key");
  key.replaceChildren();
  $("#conflict-legend").hidden =
    !state.layers.has("military") && !state.layers.has("geopolitical");
  const used = new Set(
    events.map((event) => conflictType(event)?.id).filter(Boolean),
  );
  for (const type of CONFLICT_TYPES) {
    const row = element("div", "conflict-key-item");
    row.classList.toggle("conflict-key-inactive", !used.has(type.id));
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 48;
    canvas.setAttribute("aria-hidden", "true");
    canvas
      .getContext("2d")
      .putImageData(conflictIcon(type.id, colors.military), 0, 0);
    row.append(canvas, element("span", "", type.label));
    key.append(row);
  }
}

function applyLayerSearch() {
  const query = $("#layer-search").value;
  const matches = searchLayers(query, names);
  for (const row of $("#layers").children) {
    const id = row.querySelector("input").dataset.layer;
    row.hidden = !matches.includes(id);
    row.style.order = String(matches.indexOf(id));
  }
  const result = $("#layer-search-result");
  result.hidden = !query.trim();
  result.textContent = matches.length
    ? `${matches.length} related ${matches.length === 1 ? "layer" : "layers"}`
    : "No related layers. Try a topic such as flights, oil or space.";
}
$("#layer-search").addEventListener("input", applyLayerSearch);
$("#layer-search").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.currentTarget.value = "";
    applyLayerSearch();
  }
});

function updateOrbitalPositions() {
  state.orbitalItems = filterOrbitalPositions(orbitalPositions(state.orbits), {
    country: state.country,
    world: state.world,
    q: state.q,
    bbox: $("#viewport-filter").checked ? worldMap?.bounds() : undefined,
  });
  const enabled =
    state.layers.has("space") && Number($("#playhead").value) === 100;
  $("#orbital-live-status").hidden = !enabled;
  $("#orbital-live-status").textContent =
    `${state.orbitalItems.length} satellites`;
  worldMap?.setOrbits(enabled ? state.orbitalItems : []);
  const count = $('[data-count="space"]');
  if (count) count.textContent = state.orbitalItems.length;
  const note = $('[data-layer-note="space"]');
  if (note)
    note.textContent =
      Number($("#playhead").value) < 100
        ? "Current positions only"
        : state.orbitalItems.length
          ? "Calculated orbital positions"
          : state.orbitalLoaded
            ? "No current positions in this view"
            : "Orbital data unavailable";
  for (const node of document.querySelectorAll("[data-orbit-card]")) {
    const item = state.orbitalItems.find(
      (entry) => entry.event_id === node.dataset.orbitCard,
    );
    if (item)
      node.textContent = `${item.altitude_km.toFixed(0)} km altitude · ${item.speed_kms.toFixed(2)} km/s · ${item.latitude.toFixed(1)}°, ${item.longitude.toFixed(1)}°`;
  }
  if (state.selectedEvent?.category === "space" && !$("#event-detail").hidden) {
    const item = state.orbitalItems.find(
      (entry) => entry.event_id === state.selectedEvent.event_id,
    );
    if (item)
      for (const [label, value] of Object.entries(orbitalFacts(item))) {
        const node = [...document.querySelectorAll("[data-orbit-fact]")].find(
          (entry) => entry.dataset.orbitFact === label,
        );
        if (node) node.textContent = value;
      }
  }
}
async function refreshOrbits() {
  try {
    const response = await fetch("/orbital-elements.json", {
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Orbital data unavailable");
    const snapshot = await response.json();
    state.orbits = prepareOrbits(snapshot);
    state.orbitalLoaded = true;
  } catch {
    /* Previously loaded elements expire by epoch even when downloads fail. */
  }
  updateOrbitalPositions();
  if (worldMap) renderEvents();
}

function showOrbitDetail(item, locate) {
  state.selectedEvent = item;
  showView("feed");
  const card = element("article", "detail-card");
  const close = element("button", "detail-close", "Close");
  close.addEventListener("click", () => {
    $("#event-detail").hidden = true;
    state.selectedEvent = null;
  });
  card.append(close, element("h3", "", item.name));
  const fields = element("dl");
  for (const [label, value] of Object.entries(orbitalFacts(item))) {
    const detail = element("dd", "", value);
    detail.dataset.orbitFact = label;
    fields.append(element("dt", "", label), detail);
  }
  card.append(
    fields,
    element(
      "p",
      "helper",
      "Position calculated from published orbital elements.",
    ),
    sourceLink(item.source_url, "View orbital source"),
  );
  $("#event-detail").replaceChildren(card);
  $("#event-detail").hidden = false;
  if ($("#workspace").classList.contains("right-collapsed"))
    togglePanel("right");
  if (locate) worldMap?.locate(item);
}

function renderSources(status) {
  $("#source-statuses").replaceChildren();
  const active = status.connectors.filter(
    (source) => source.state === "ok" && !source.stale,
  ).length;
  $("#source-count").textContent =
    `${active}/${status.connectors.length} current`;
  $("#system-status").textContent = status.worker_alive
    ? `${active} sources current`
    : status.public_gatherer_alive
      ? "Live source updates"
      : "Collector inactive";
  $("#system-status").title =
    !status.worker_alive && status.public_gatherer_alive
      ? "Public conflict, cyber and satellite collection is active."
      : "Collection status";
  $("#system-status").classList.toggle(
    "offline",
    (!status.worker_alive && !status.public_gatherer_alive) || active === 0,
  );
  const coverage = $("#coverage-summary");
  coverage.replaceChildren();
  for (const id of ["opensky", "firms"]) {
    const source = status.connectors.find((item) => item.source_id === id);
    if (source)
      coverage.append(
        element(
          "p",
          "helper",
          `${id === "opensky" ? "Aircraft" : "Thermal detections"}: ${source.coverage_scope === "world" ? "worldwide sample" : "regional coverage"}. ${source.truncated ? `${source.truncated.toLocaleString()} records outside ${id === "opensky" ? "the class/track selection or 400-observation limit" : "the collection bound"}.` : ""}`,
        ),
      );
  }
  const unavailable = status.connectors.filter((source) =>
    ["error", "access_required", "never_run"].includes(source.state),
  );
  if (unavailable.length)
    coverage.append(
      element(
        "p",
        "helper",
        `${unavailable.length} sources unavailable: ${unavailable
          .slice(0, 4)
          .map((source) => source.name)
          .join(
            ", ",
          )}${unavailable.length > 4 ? " and more" : ""}. See Source health for the reasons.`,
      ),
    );
  for (const source of status.connectors) {
    const node = element("div", "source-status");
    node.append(sourceLink(source.homepage, source.name));
    const text =
      source.state === "ok" && source.stale
        ? "Stale"
        : source.state.replaceAll("_", " ");
    node.append(
      element(
        "span",
        "status-label " +
          (source.state === "error"
            ? "error"
            : source.state === "access_required"
              ? "access"
              : ""),
        ` ${text}`,
      ),
    );
    node.append(
      element("p", "", `Last success: ${dateText(source.last_success)}`),
    );
    if (source.error) node.append(element("p", "", source.error));
    if (source.stored !== undefined)
      node.append(
        element(
          "p",
          "",
          `${source.stored} stored · ${source.rejected || 0} rejected · ${source.truncated || 0} outside record bound`,
        ),
      );
    const detail = element("details");
    detail.append(
      element("summary", "", "Coverage limitations"),
      element("p", "", source.limitation),
    );
    node.append(detail);
    if (source.compatibility_only) {
      node.append(
        element(
          "p",
          "helper",
          source.background_collection
            ? "Background feed thread · every 10 seconds"
            : "Stored collection result. Scheduled updates begin after your next collector reload.",
        ),
      );
      $("#source-statuses").append(node);
      continue;
    }
    const refreshSource = element(
      "button",
      "",
      source.manual ? "Import browser capture" : "Collect this source",
    );
    refreshSource.addEventListener("click", async () => {
      if (source.manual) {
        showView("sentiment");
        $("#sentiment-kind").value = "public";
        await refresh();
        $("#reddit-browser-import").open = true;
        $("#reddit-import-file").focus();
        return;
      }
      const feedback = element("p", "helper");
      node.append(feedback);
      if (!state.token) {
        feedback.textContent = "Enter the server access token in Settings.";
        return;
      }
      refreshSource.disabled = true;
      try {
        await api(`admin/connectors/${source.source_id}/refresh`, {
          token: state.token,
          body: {},
        });
        feedback.textContent = "Scheduled for the collection worker.";
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        refreshSource.disabled = false;
      }
    });
    node.append(refreshSource);
    $("#source-statuses").append(node);
  }
}

function renderEvents() {
  $("#radware-vector-panel").hidden = !state.layers.has("threat");
  renderVectorBreakdown(state.vectorSummary);
  $("#threat-map-references").hidden = !state.layers.has("threat");
  $("#event-list").replaceChildren();
  const playhead = Number($("#playhead").value);
  const { start, end } = timeRange();
  const cutoff = new Date(start.getTime() + ((end - start) * playhead) / 100);
  const timeColumn = {
    event: "time_key",
    published: "published_at",
    ingested: "ingested_at",
  }[$("#time-basis").value];
  let visible = [
    ...state.events.filter((event) => state.layers.has(event.category)),
    ...(state.layers.has("threat") ? state.threatEvents : []),
  ].filter(
    (event) =>
      (playhead === 100 || new Date(event[timeColumn]) <= cutoff) &&
      (!["threat", "cyber"].includes(event.category) ||
        matchesThreatVector(event, state.threatVector)),
  );
  if (state.threatNetwork) {
    const network =
      playhead === 100
        ? displayThreatNetwork()
        : buildThreatNetwork(
            visible.filter((event) => event.category === "threat"),
            state.world.features.map((feature) => feature.properties),
          );
    worldMap?.setThreatNetwork(network, state.layers.has("threat"));
  }
  worldMap?.setCyberNetwork(
    state.cyberNetwork,
    state.layers.has("cyber") &&
      $("#cyber-connections").checked &&
      state.threatVector === "all",
  );
  const live =
    playhead === 100 &&
    state.period !== "custom" &&
    state.layers.has("aviation") &&
    state.aircraft?.available &&
    state.aircraftFilter === aircraftFilterKey();
  if (live) {
    state.aircraft.items = state.aircraft.items.filter(
      (event) => Date.now() - Date.parse(event.time_key) <= 600000,
    );
    if (Date.now() - Date.parse(state.aircraft.collected_at) > 240000)
      state.aircraft.stale = true;
    const flights = [...state.aircraft.items];
    // Replace historical aircraft slots in the balanced feed so current cards
    // remain interleaved with other layers instead of being buried at the end.
    visible = visible.flatMap((event) =>
      event.category === "aviation"
        ? flights.length
          ? [flights.shift()]
          : []
        : [event],
    );
    visible.push(...flights);
  }
  worldMap?.setEvents(visible);
  renderConflictKey(visible);
  updateOrbitalPositions();
  $("#matched-count").textContent = Math.max(
    0,
    state.total -
      (state.layers.has("cyber") && state.threatVector !== "all"
        ? state.categoryCounts.cyber || 0
        : 0) -
      (state.layers.has("threat")
        ? state.threatCount - (displayThreatNetwork()?.events.length || 0)
        : 0),
  ).toLocaleString();
  $("#mapped-count").textContent = visible
    .filter((event) => event.latitude !== null)
    .length.toLocaleString();
  $("#list-count").textContent = live
    ? `${visible.length} shown · ${state.events.length} history records loaded`
    : `${visible.length} loaded / ${state.total}`;
  $("#list-label").textContent =
    playhead < 100 ? "HISTORICAL OBSERVATIONS" : "RECENT RECORDS BY LAYER";
  $("#playhead-time").textContent =
    playhead === 100
      ? "Latest"
      : cutoff.toISOString().slice(5, 16).replace("T", " ") + "Z";
  $("#aircraft-live-status").hidden = !state.layers.has("aviation");
  $("#aircraft-live-status").textContent = live
    ? `${state.aircraft.stale ? "Aircraft update delayed" : "Current aircraft"} · ${state.aircraft.items.length} positions`
    : "Aircraft: stored observations · position age shown on cards";
  for (const event of visible) {
    const li = element("li");
    const button = element("button", "event-button");
    button.dataset.eventId = event.event_id;
    const meta = element("div", "event-meta");
    const type = conflictType(event);
    const mark = type
      ? conflictCanvas(
          type.id,
          event.category,
          event.location_precision === "regional",
        )
      : symbolCanvas(event.category);
    const time = element("time", "", relativeTime(event[timeColumn]));
    time.dateTime = event[timeColumn];
    time.title = dateText(event[timeColumn]);
    meta.append(mark, element("span", "", names[event.category]), time);
    const footer = element("div", "event-footer");
    footer.append(
      badge(event.confidence),
      element("span", "", event.source_id.toUpperCase()),
      element(
        "span",
        "",
        event.latitude === null ? "Unlocated" : event.location_precision,
      ),
    );
    button.append(meta, element("span", "event-title", event.title));
    if (event.category === "aviation") {
      const facts = aircraftFacts(event);
      const flight = element("dl", "aircraft-card-facts");
      for (const label of [
        "Registration country",
        "Barometric altitude",
        "Ground speed",
        "Ground track",
      ])
        flight.append(
          element("dt", "", label),
          element("dd", "", facts[label]),
        );
      button.append(flight);
    } else if (event.category === "threat") {
      const facts = threatFacts(event);
      button.append(element("p", "event-excerpt", threatCaption(facts)));
    } else if (event.description)
      button.append(
        element("span", "event-excerpt", event.description.slice(0, 220)),
      );
    button.append(footer);
    button.addEventListener("click", () => selectEvent(event.event_id, true));
    li.append(button);
    $("#event-list").append(li);
  }
  const orbitVisible =
    state.layers.has("space") && playhead === 100 ? state.orbitalItems : [];
  for (const item of orbitVisible) {
    const li = element("li");
    const button = element("button", "event-button orbital-card");
    button.dataset.eventId = item.event_id;
    const meta = element("div", "event-meta");
    meta.append(symbolCanvas("space"), element("span", "", names.space));
    const position = element("p", "orbital-position");
    position.dataset.orbitCard = item.event_id;
    position.textContent = `${item.altitude_km.toFixed(0)} km altitude · ${item.speed_kms.toFixed(2)} km/s · ${item.latitude.toFixed(1)}°, ${item.longitude.toFixed(1)}°`;
    button.append(
      meta,
      element("span", "event-title", item.name),
      element("span", "event-excerpt", item.purpose),
      position,
    );
    button.addEventListener("click", () =>
      showOrbitDetail(
        state.orbitalItems.find((entry) => entry.event_id === item.event_id) ||
          item,
        true,
      ),
    );
    li.append(button);
    $("#event-list").append(li);
  }
  if (!visible.length && !orbitVisible.length) {
    const empty = element("li", "empty-state");
    empty.append(
      element("strong", "", "No matching observations"),
      element(
        "p",
        "",
        "Broaden the time window or enable another layer. Source health shows feed errors and access requirements.",
      ),
    );
    const action = element("button", "", "Show last 7 days");
    action.addEventListener("click", () => {
      state.period = "168";
      $("#period").value = "168";
      $("#custom-dates").hidden = true;
      $("#playhead").value = "100";
      refresh();
    });
    empty.append(action);
    $("#event-list").append(empty);
  }
  for (const id of Object.keys(names)) {
    if (["sentiment", "analysis", "threat", "space"].includes(id)) continue;
    const count =
      id === "aviation" && live
        ? state.aircraft.items.length
        : (state.categoryCounts[id] || 0) +
          (id === "cyber" ? state.threatCount : 0);
    $(`[data-count="${id}"]`).textContent = count.toLocaleString();
    if (id === "aviation")
      $(`[data-count="${id}"]`).title = live
        ? `${state.aircraft.items.length} current positions; ${(state.categoryCounts[id] || 0).toLocaleString()} retained observations in the selected period`
        : "Retained observations in the selected period";
    if (id === "cyber")
      $(`[data-count="${id}"]`).title =
        "Cyber advisories and investigations plus up to 500 attack reports and 300 sampled detections; not global attack totals";
    const health = state.layerHealth[id];
    const sources = state.sources.filter(
      (source) => source.category === id || source.categories?.includes(id),
    );
    const note = $(`[data-layer-note="${id}"]`);
    // Prefer the server's per-layer health verdict: a layer can be empty
    // because its sources are down, not because nothing happened.
    const healthNote = health
      ? health.coverage === "none_current"
        ? health.needs_access
          ? "Feed access required"
          : "Sources unavailable"
        : health.coverage === "no_sources"
          ? "No configured source"
          : health.failing
            ? `${health.failing} of ${health.total} sources unavailable or stale`
            : ""
      : "";
    note.textContent = count
      ? id === "cyber"
        ? "Advisories, attack reports & traffic detections"
        : id === "aviation"
          ? `Classes 4 & 5 · ${live ? "current positions" : "stored observations"}`
          : id === "economic"
            ? "Business, energy, sanctions and official releases"
            : id === "threat"
              ? "Published reports · reported origin → target"
              : id === "military"
                ? "Conflict reports, forces & defence coverage"
                : healthNote
      : id === "threat"
        ? "No matching published threat reports"
        : healthNote ||
          (sources.length
            ? "No records in this period"
            : "No configured source");
    if (health)
      note.classList.toggle(
        "layer-note-warning",
        health.coverage === "none_current" || health.coverage === "no_sources",
      );
  }
  $('[data-count="analysis"]').textContent = String(state.reportingSignals);
  $('[data-count="analysis"]').title =
    "Regional report surges plus countries with evidence in multiple enabled layers; not a count of attacks";
  $("#map-sample-note").textContent =
    state.events.length < state.total
      ? `Showing ${state.events.length.toLocaleString()} records across layers and regions; load more in Events. Threat layer uses up to 500 recent reports; other layer counts include all matches.`
      : "Showing all matching records. Layer counts include records without map coordinates.";
  $("#load-more").hidden =
    state.events.length >= state.total || state.events.length >= 5000;
}

async function selectEvent(id, locate = false) {
  state.analysisEventIds = null;
  if (id.startsWith("orbit-")) {
    const item = state.orbitalItems.find((entry) => entry.event_id === id);
    if (item) showOrbitDetail(item, locate);
    return;
  }
  try {
    const event =
      state.aircraft?.items.find((item) => item.event_id === id) ||
      (await api(`events/${encodeURIComponent(id)}`));
    state.selectedEvent = event;
    showView("feed");
    $("#event-detail").hidden = false;
    const card = element("article", "detail-card");
    const close = element("button", "detail-close", "Close");
    close.addEventListener("click", () => {
      $("#event-detail").hidden = true;
      state.selectedEvent = null;
    });
    card.append(
      close,
      badge(event.confidence),
      element("h3", "", event.title),
      element("p", "", event.description),
    );
    const fields = element("dl");
    if (event.category === "threat") {
      event.threat ||= event.reports?.[0]?.metadata?.threat;
      const facts = threatFacts(event);
      const telemetry = facts.classification !== "reported_attack";
      for (const [label, value] of [
        ["Named actor", facts.actor],
        [
          "Known attack vectors",
          facts.attack_vectors.join(" · ") || "Not specified by source",
        ],
        [
          "Vector evidence",
          facts.vector_evidence || "No specific technique supplied",
        ],
        ["CVE references", facts.cves.join(", ") || "None supplied"],
        [
          telemetry ? "Provider detection" : "Attack reporting",
          facts.attack_kind,
        ],
        [
          telemetry ? "Traffic origin country" : "Reported attacker country",
          (telemetry ? facts.traffic_origin_country : facts.attacker_country) ||
            "Unknown",
        ],
        [
          telemetry
            ? "Traffic destination country"
            : "Reported victim countries",
          (telemetry
            ? facts.traffic_target_country
            : facts.victim_countries.join(", ")) || "Unknown",
        ],
        [
          "Attribution evidence",
          event.threat?.attribution_basis || event.evidence_basis,
        ],
        [
          "Target evidence",
          event.threat?.victim_basis ||
            "Open the original report to inspect the targeting wording",
        ],
      ])
        fields.append(element("dt", "", label), element("dd", "", value));
      if (telemetry) {
        for (const [label, value] of [
          [
            "Observation type",
            facts.classification === "detection"
              ? "Provider location detection"
              : "Sampled provider traffic",
          ],
          ["Detection country", facts.detection_country || "Not supplied"],
          [
            "Received",
            dateText(event.threat?.received_at || event.published_at),
          ],
          ["Provider timestamp", event.threat?.provider_time || "Not supplied"],
          [
            "Occurrence time",
            event.occurred_at
              ? dateText(event.occurred_at)
              : "Unknown; receipt time used in timeline",
          ],
        ])
          fields.append(element("dt", "", label), element("dd", "", value));
      }
    }
    if (event.category === "aviation") {
      for (const [label, value] of Object.entries(aircraftFacts(event)))
        fields.append(element("dt", "", label), element("dd", "", value));
      fields.append(
        element("dt", "", "Departure / destination"),
        element(
          "dd",
          "",
          "Not provided by OpenSky · registration country is not departure origin",
        ),
      );
      fields.append(
        element("dt", "", "ADS-B class"),
        element(
          "dd",
          "",
          event.aircraft_category === 4
            ? "4 · Large"
            : event.aircraft_category === 5
              ? "5 · High Vortex Large"
              : "Unknown or excluded",
        ),
        element("dt", "", "Reported ground track"),
        element(
          "dd",
          "",
          Number.isFinite(event.aircraft_track_deg)
            ? `${event.aircraft_track_deg.toFixed(1)}° clockwise from true north`
            : "Unknown",
        ),
      );
    }
    for (const [label, value] of Object.entries({
      Occurred: dateText(event.occurred_at),
      Published: dateText(event.published_at),
      Ingested: dateText(event.ingested_at),
      Location:
        event.latitude === null
          ? "Unknown"
          : `${event.latitude.toFixed(3)}, ${event.longitude.toFixed(3)} (${event.location_precision})`,
      Severity: event.severity,
    }))
      fields.append(element("dt", "", label), element("dd", "", value));
    card.append(
      fields,
      element("p", "helper", event.location_basis),
      element("p", "helper", event.evidence_basis),
      element("p", "helper", event.severity_basis),
    );
    card.append(
      element("h3", "", `Supporting reports (${event.report_count})`),
    );
    for (const report of event.reports) {
      const reference = element("div", "source-reference");
      reference.append(
        sourceLink(report.source_url, report.title),
        element(
          "p",
          "helper",
          `${report.source_id} · ${dateText(report.published_at)}`,
        ),
      );
      const news = report.metadata?.news;
      if (news?.reporting_location)
        reference.append(
          element("p", "helper", `Reported place: ${news.reporting_location}`),
        );
      for (const url of news?.upstream_sources || [])
        reference.append(sourceLink(url, "Cited original source ↗"));
      if (report.report_id)
        reference.append(
          sourceLink(
            `/api/reports/${report.report_id}`,
            "View source metadata",
          ),
        );
      card.append(reference);
    }
    const analyze = element("button", "wide", "Analyze this event");
    analyze.addEventListener("click", () => {
      showView("analysis");
      $("#ai-question").focus();
    });
    card.append(analyze);
    $("#event-detail").replaceChildren(card);
    if ($("#workspace").classList.contains("right-collapsed"))
      togglePanel("right");
    $("#event-detail").scrollIntoView({ block: "start", behavior: "instant" });
    if (event.live) {
      analyze.remove();
      if (locate) worldMap?.locate(event);
      return;
    }
    const review = element("details");
    review.append(element("summary", "", "Review evidence classification"));
    const form = element("form");
    const classification = element("select");
    classification.id = "evidence-classification";
    const classificationLabel = element(
      "label",
      "field-label",
      "Evidence status",
    );
    classificationLabel.htmlFor = classification.id;
    for (const name of [
      "Verified",
      "Corroborated",
      "Single-source",
      "Disputed",
      "Unverified",
    ]) {
      const option = element("option", "", name);
      option.value = name;
      classification.append(option);
    }
    classification.value = event.confidence;
    const notes = element("textarea");
    notes.id = "evidence-basis";
    notes.required = true;
    notes.minLength = 30;
    notes.maxLength = 2000;
    notes.rows = 3;
    const notesLabel = element(
      "label",
      "field-label",
      "Evidence and limitations (30 characters minimum)",
    );
    notesLabel.htmlFor = notes.id;
    const reports = element("fieldset");
    reports.append(element("legend", "", "Supporting source reports"));
    for (const report of event.reports.slice(0, 20)) {
      const label = element("label", "check-row"),
        input = element("input");
      input.type = "checkbox";
      input.value = report.report_id;
      input.name = "report";
      label.append(
        input,
        element("span", "", report.source_id + ": " + report.title),
      );
      reports.append(label);
    }
    const independent = element("input");
    independent.type = "checkbox";
    const independentLabel = element("label", "check-row");
    independentLabel.append(
      independent,
      element(
        "span",
        "",
        "I checked that the cited sources report independently.",
      ),
    );
    const conflict = element("input");
    conflict.type = "checkbox";
    const conflictLabel = element("label", "check-row");
    conflictLabel.append(
      conflict,
      element("span", "", "The cited reports contain conflicting evidence."),
    );
    const feedback = element("p", "error-text");
    feedback.id = "evidence-error";
    feedback.setAttribute("role", "alert");
    notes.setAttribute("aria-describedby", feedback.id);
    const submit = element("button", "wide", "Save evidence review");
    submit.type = "submit";
    form.append(
      classificationLabel,
      classification,
      notesLabel,
      notes,
      reports,
      independentLabel,
      conflictLabel,
      submit,
      feedback,
    );
    form.addEventListener("submit", async (submitEvent) => {
      submitEvent.preventDefault();
      feedback.textContent = "";
      if (!state.token) {
        feedback.textContent = "Enter the server access token in Settings.";
        return;
      }
      const reportIds = [...reports.querySelectorAll("input:checked")].map(
        (input) => input.value,
      );
      if (!reportIds.length) {
        feedback.textContent = "Select at least one supporting report.";
        return;
      }
      submit.disabled = true;
      try {
        await api(`admin/events/${event.event_id}/evidence`, {
          token: state.token,
          body: {
            confidence: classification.value,
            basis: notes.value,
            report_ids: reportIds,
            independent_sources_confirmed: independent.checked,
            contradiction_confirmed: conflict.checked,
          },
        });
        await selectEvent(event.event_id);
        await refresh();
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
    review.append(form);
    card.append(review);
    if (locate) worldMap.locate(event);
  } catch (error) {
    message(error.message);
  }
}

async function selectCountry(code, fly = false) {
  state.country = code;
  $("#country").value = code;
  worldMap.selectCountry(code, fly);
  const properties = state.world.features.find(
    (feature) => feature.properties.code === code,
  )?.properties;
  $("#map-title").textContent = properties?.name || "World view";
  $("#country-insight").hidden = !code;
  await refresh();
  countryController?.abort();
  countryController = new AbortController();
  if (!code) return;
  try {
    const result = await api(`countries/${code}?${params()}`, {
      signal: countryController.signal,
    });
    const insight = $("#country-insight");
    insight.replaceChildren(element("strong", "", result.country.name));
    insight.append(
      element(
        "p",
        "",
        `${result.events.total} matching events · ${result.sentiment.sample_count} scored news headlines`,
      ),
      element("p", "helper", result.limitation),
    );
  } catch (error) {
    if (error.name !== "AbortError")
      $("#country-insight").textContent = error.message;
  }
}

function showView(view) {
  state.view = view;
  for (const name of ["feed", "analysis", "sentiment", "military"]) {
    $(`#${name}-view`).hidden = view !== name;
    $(`#${name}-tab`).setAttribute("aria-pressed", String(view === name));
  }
  chart?.resize();
}

function renderSentimentEvidence(result) {
  const panel = $("#sentiment-evidence-panel");
  panel.hidden = !result;
  if (!result) return;
  const total = result.sample_count || 0;
  const share = (value) =>
    total ? `${Math.round((value / total) * 100)}%` : "0%";
  const body = $("#sentiment-evidence-body");
  body.replaceChildren();

  const head = element("div", "evidence-head");
  head.append(
    element(
      "strong",
      "",
      `${result.posts ? "Public feed texts" : "Media headlines"} · ${total.toLocaleString()} scored`,
    ),
    element("span", "helper", "Why a region reads green or red"),
  );
  body.append(head);

  const bar = element("div", "evidence-bar");
  bar.setAttribute("role", "img");
  bar.setAttribute(
    "aria-label",
    `${result.distribution.positive} positive, ${result.distribution.negative} negative, ${result.distribution.neutral} neutral of ${total} scored texts`,
  );
  for (const [kind, color] of [
    ["positive", "#6ec8a9"],
    ["negative", "#d87d78"],
    ["neutral", "#8195a1"],
  ]) {
    const value = result.distribution[kind];
    if (!value) continue;
    const slice = element("span", `evidence-slice ${kind}`);
    slice.style.width = share(value);
    slice.style.background = color;
    slice.title = `${value} ${kind} (${share(value)})`;
    bar.append(slice);
  }
  body.append(bar);

  const key = element("ul", "evidence-key");
  for (const kind of ["positive", "negative", "neutral"]) {
    const value = result.distribution[kind];
    const row = element("li");
    row.append(
      element("span", `evidence-dot ${kind}`),
      element("span", "", `${value} ${kind}`),
      element("span", "helper", share(value)),
    );
    key.append(row);
  }
  body.append(key);

  body.append(element("h4", "", "Strongest regions"));
  const regions = [...result.regions]
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
  const list = element("ul", "evidence-regions");
  for (const region of regions) {
    const thin = region.count < THIN_SAMPLE;
    const row = element("li", thin ? "thin" : "");
    row.append(
      element(
        "span",
        `evidence-score ${region.score >= 0 ? "pos" : "neg"}`,
        `${region.score >= 0 ? "+" : ""}${region.score.toFixed(2)}`,
      ),
      element("span", "evidence-name", region.name || region.country),
      element("span", "evidence-n", `n=${region.count}${thin ? " thin" : ""}`),
    );
    row.title = `Mean wording score ${region.score.toFixed(3)} from ${region.count} scored ${region.count === 1 ? "text" : "texts"}.${thin ? " Thin evidence." : ""}`;
    list.append(row);
  }
  body.append(list);

  body.append(
    element(
      "p",
      "helper",
      "Colour marks the sign of the mean lexicon score for wording published in, or naming, each country. It describes wording, not attitude toward the country, and 'thin' marks fewer than 5 texts.",
    ),
  );
  if (result.posts)
    body.append(
      element(
        "p",
        "helper",
        `Origin basis: ${result.geography_basis}. Countries are where wording names them, not where authors are.`,
      ),
    );
  body.append(element("p", "helper", result.methodology));
}

function renderSentiment(result) {
  state.sentimentResult = result;
  const summary = element("div", "sentiment-summary");
  summary.append(
    element("strong", "", result.sample_count.toLocaleString()),
    element(
      "span",
      "",
      result.posts ? "scored English feed texts" : "scored English headlines",
    ),
  );
  summary.append(
    element(
      "p",
      "",
      `${result.distribution.positive} positive · ${result.distribution.negative} negative · ${result.distribution.neutral} neutral`,
    ),
  );
  summary.append(
    element(
      "p",
      "helper",
      `Topic: ${result.topic}. Dataset: ${result.dataset_count} ${result.posts ? "unique platform posts" : "unique URLs"}; ${result.excluded_language_count} excluded for language. Period uses each feed's publication/update time.${result.truncated ? " Dataset bound reached." : ""}`,
    ),
  );
  $("#sentiment-summary").replaceChildren(summary);
  $("#sentiment-method").replaceChildren(
    element("p", "", result.methodology),
    element(
      "p",
      "",
      `Sources: ${
        Object.entries(result.sources)
          .map(([source, count]) => `${source} (${count})`)
          .join(", ") || "No source coverage"
      }`,
    ),
    element(
      "p",
      "",
      `Languages: ${
        Object.entries(result.languages)
          .map(([language, count]) => `${language} (${count})`)
          .join(", ") || "No samples"
      }`,
    ),
  );
  $("#sentiment-regions").replaceChildren(
    element("h3", "", "Regional comparison"),
  );
  const table = element("table", "coverage-table");
  const head = element("thead"),
    heading = element("tr");
  for (const title of ["Country", "Samples", "Mean score"]) {
    const th = element("th", "", title);
    th.scope = "col";
    heading.append(th);
  }
  head.append(heading);
  table.append(head);
  const body = element("tbody");
  for (const region of result.regions
    .sort((a, b) => b.count - a.count)
    .slice(0, 15)) {
    const row = element("tr");
    row.append(
      element("td", "", region.country),
      element("td", "", region.count),
      element("td", "", region.score.toFixed(2)),
    );
    body.append(row);
  }
  table.append(body);
  $("#sentiment-regions").append(table);
  $("#topic-frequency").replaceChildren(
    element(
      "h3",
      "",
      result.posts ? "Feed wording groups" : "Headline keyword groups",
    ),
  );
  for (const term of result.topic_frequency) {
    const node = element("span", "topic-term", term.term);
    node.append(element("small", "", term.count));
    node.title = `${term.count} matching headlines. Report IDs: ${term.report_ids.join(", ")}`;
    $("#topic-frequency").append(node);
  }
  chart.setSentiment(result);
  renderSocial(result, state.sources);
  chart.setDiscussionNetwork(result.discussion_network);
  const count = $(`[data-count="sentiment"]`);
  count.textContent = result.sample_count.toLocaleString();
  count.title =
    "Scored records in the selected sentiment dataset; separate from physical event counts";
  $('[data-layer-note="sentiment"]').textContent = result.posts
    ? "Public feed wording · origins often unknown"
    : "Media/institutional wording";
  $("#sentiment-key").hidden = !state.layers.has("sentiment");
  worldMap.setSentiment(result, state.layers.has("sentiment"));
  worldMap.setSentimentEvidence(state.sentimentEvidence);
  renderSentimentEvidence(result);
  worldMap.setSocialNetwork(
    result.map_network,
    state.layers.has("sentiment") && $("#social-edges").checked,
  );
}

function renderTimeline(result) {
  chart.setTimeline(result.items);
  $("#timeline-table-body").replaceChildren();
  for (const item of result.items) {
    const row = element("tr");
    row.append(
      element("td", "", item.time),
      element("td", "", names[item.category]),
      element("td", "", item.count),
    );
    $("#timeline-table-body").append(row);
  }
  const range = timeRange();
  $("#timeline-range").textContent =
    `${range.start.toISOString().slice(0, 16).replace("T", " ")} to ${range.end.toISOString().slice(0, 16).replace("T", " ")} UTC · ${result.time_basis} time`;
}

async function refresh() {
  refreshController?.abort();
  refreshController = new AbortController();
  const signal = refreshController.signal;
  $("#refresh").disabled = true;
  $("#event-list").setAttribute("aria-busy", "true");
  countryRibbon.setBusy(true);
  try {
    // Adjacent filter changes should issue one query batch. Aborting a browser
    // request cannot cancel work that the API has already begun.
    await new Promise((resolve) => setTimeout(resolve, 300));
    if (signal.aborted) return;
    const query = params();
    const threatQuery = new URLSearchParams(query);
    threatQuery.delete("categories");
    threatQuery.delete("aircraft_categories");
    threatQuery.delete("country");
    threatQuery.delete("bbox");
    threatQuery.set("q", "threat-report");
    const telemetryQuery = new URLSearchParams(threatQuery);
    telemetryQuery.set("q", "threat-telemetry");
    const requestedPlatform = $("#sentiment-platform").value;
    const sentimentQuery = params({ sentiment: true });
    const kind = $("#sentiment-kind").value;
    sentimentQuery.set("kind", kind === "youtube" ? "news" : kind);
    sentimentQuery.set(
      "platform",
      kind === "youtube"
        ? "youtube"
        : kind === "public"
          ? state.extendedSources
            ? requestedPlatform
            : ["all", "reddit", "x"].includes(requestedPlatform)
              ? requestedPlatform
              : "all"
          : "all",
    );
    sentimentQuery.set("geography", $("#sentiment-geography").value);
    const countryQuery = new URLSearchParams(query);
    countryQuery.delete("country");
    for (const key of ["kind", "platform", "geography"])
      countryQuery.set(key, sentimentQuery.get(key));
    // The comparison refreshes independently, so a slow ranking query cannot
    // hold back fresh observations, layer counts or context links.
    api(`country-activity?${countryQuery}`, { signal })
      .then((value) => {
        if (!signal.aborted) {
          state.countryActivity = value;
          renderCountryActivity();
        }
      })
      .catch(() => {
        if (!signal.aborted) countryRibbon.setError();
      })
      .finally(() => {
        if (!signal.aborted) countryRibbon.setBusy(false);
      });
    const interval =
      Number(state.period) > 168 || state.period === "custom" ? "day" : "hour";
    const results = await Promise.allSettled([
      api(`events?${query}&limit=500&order=balanced`, { signal }),
      api("status", { signal }),
      api(`timeline?${query}&interval=${interval}`, { signal }),
      api(`sentiment?${sentimentQuery}`, { signal }),
      Promise.resolve(null),
      Promise.resolve(null),
      api(`relations?${query}`, { signal }),
      api(`military?${query}`, { signal }),
      api("layers", { signal }),
      api(`anomalies/regional?${query}`, { signal }),
      api(`cross-category?${query}`, { signal }),
      api(`cyber/relations?${query}`, { signal }),
      api(`events?${threatQuery}&limit=500`, { signal }),
      loadThreatTelemetry(telemetryQuery, signal),
      fetch("/threatmap-status.json", { signal, cache: "no-store" })
        .then((response) => response.json())
        .catch(() => null),
    ]);
    if (signal.aborted) return;
    if (results[0].status === "rejected") throw results[0].reason;
    const data = results[0].value;
    state.events = data.items.filter((event) => event.category !== "threat");
    state.total = [...state.layers].some(
      (id) => !["threat", "analysis", "space"].includes(id),
    )
      ? data.total
      : 0;
    state.categoryCounts = data.category_counts || {};
    if (
      results[12].status === "fulfilled" ||
      results[13].status === "fulfilled"
    ) {
      const world = state.world;
      state.threatNetwork = buildThreatNetwork(
        [12, 13]
          .flatMap((index) =>
            results[index].status === "fulfilled"
              ? results[index].value.items
              : [],
          )
          .filter((event) => event.category === "threat"),
        world.features.map((feature) => feature.properties),
        {
          country: state.country,
          bbox: $("#viewport-filter").checked ? worldMap.bounds() : null,
          q: state.q,
        },
      );
      state.threatEvents = state.threatNetwork.events;
      state.threatCount = state.threatEvents.length;
      state.categoryCounts.threat = state.threatCount;
      worldMap.setThreatNetwork(
        state.threatNetwork,
        state.layers.has("threat"),
      );
      if (state.layers.has("threat")) state.total += state.threatCount;
      renderCountryActivity();
    }
    refreshAircraft();
    if (results[1].status === "fulfilled")
      state.sources = results[1].value.connectors;
    renderEvents();
    if (results[1].status === "fulfilled") {
      const status = {
        ...results[1].value,
        connectors: [...results[1].value.connectors],
      };
      const bridge =
        results[14].status === "fulfilled" ? results[14].value : null;
      state.vectorSummary = bridge?.vector_summary || state.vectorSummary;
      status.public_gatherer_alive =
        bridge?.background_collection &&
        Date.now() - Date.parse(bridge.checked_at) < 30000;
      renderVectorBreakdown(state.vectorSummary);
      for (const source of bridge?.connectors || []) {
        if (
          !backgroundSources(source.source_id) ||
          status.connectors.some((item) => item.source_id === source.source_id)
        )
          continue;
        const last = Date.parse(source.last_success);
        status.connectors.push({
          ...source,
          compatibility_only: true,
          background_collection:
            bridge.background_collection === true &&
            Date.now() - Date.parse(bridge.checked_at) < 30000,
          stale:
            !Number.isFinite(last) ||
            Date.now() - last > (source.interval_seconds || 120) * 2000,
        });
      }
      state.sources = status.connectors;
      renderSources(status);
      $("#threat-stream-health").replaceChildren();
      for (const source of status.connectors.filter(
        (item) =>
          threatProviders.includes(item.source_id) ||
          item.source_id.startsWith("threat_research_"),
      )) {
        $("#threat-stream-health").append(
          element(
            "p",
            "helper",
            `${source.name}: ${source.state === "ok" ? (source.stale ? "Update delayed" : "Available") : "Update unavailable"}`,
          ),
        );
      }
    }
    if (results[2].status === "fulfilled") {
      state.timelineResult = results[2].value;
      renderTimeline(
        threatTimeline(
          results[2].value,
          displayThreatNetwork(),
          state.layers,
          interval,
        ),
      );
    }
    if (results[3].status === "fulfilled") renderSentiment(results[3].value);
    if (results[6].status === "fulfilled") {
      state.newsNetwork = results[6].value;
      worldMap.setNewsNetwork(
        state.newsNetwork,
        state.layers.has("geopolitical") && $("#news-connections").checked,
      );
    }
    if (results[7].status === "fulfilled") {
      state.military = results[7].value;
      renderMilitary(state.military, state.sources, {
        selectEvent,
        showTopic,
        analyzeTopic,
      });
      showTopic(state.militaryTopic);
    }
    if (results[11].status === "fulfilled") {
      state.cyberNetwork = results[11].value;
      worldMap.setCyberNetwork(
        state.cyberNetwork,
        state.layers.has("cyber") &&
          $("#cyber-connections").checked &&
          state.threatVector === "all",
      );
    }
    renderNetworkSummary();
    if (results[8].status === "fulfilled") {
      state.extendedSources = results[8].value.some(
        (layer) =>
          layer.id === "threat" || layer.categories?.includes("threat"),
      );
      state.layerHealth = Object.fromEntries(
        results[8].value.map((layer) => [layer.id, layer.health]),
      );
      for (const source of state.sources.filter(
        (s) => s.compatibility_only && s.source_id.startsWith("conflict_"),
      )) {
        for (const category of new Set([
          source.category,
          ...(source.categories || []),
        ])) {
          const health = state.layerHealth[category];
          if (!health) continue;
          health.total += 1;
          if (source.state === "ok" && !source.stale) health.current += 1;
          else health.failing += 1;
          health.coverage = health.current
            ? health.failing
              ? "degraded"
              : "current"
            : "none_current";
        }
      }
      for (const option of $("#sentiment-platform").options) {
        if (["mastodon", "lemmy", "telegram"].includes(option.value))
          option.disabled = !state.extendedSources;
      }
      renderEvidenceGaps();
      renderEvents();
    }
    renderAnomalyAlerts(results);
    const failures = results
      .slice(1)
      .filter((result) => result.status === "rejected");
    message(
      failures.length
        ? `Some dashboard panels could not refresh: ${failures.map((result) => result.reason.message).join("; ")}`
        : "",
    );
    state.lastRefresh = new Date();
    $("#refresh-time").textContent =
      `Read ${state.lastRefresh.toISOString().slice(11, 19)} UTC`;
  } catch (error) {
    if (error.name !== "AbortError") {
      message(error.message);
      $("#system-status").textContent = "API unavailable";
      $("#system-status").classList.add("offline");
    }
  } finally {
    if (!signal.aborted) {
      $("#refresh").disabled = false;
      $("#event-list").setAttribute("aria-busy", "false");
    }
  }
}

function renderCrossCategoryPanel() {
  const body = $("#cross-category-body");
  if (!body) return;
  const open = state.analysisOverlays;
  $("#analysis-evidence").hidden = !open;
  if (!open) {
    body.replaceChildren();
    return;
  }
  body.replaceChildren();
  if (!state.crossCategory.length) {
    body.append(
      element(
        "p",
        "helper",
        "No country currently carries records in two or more categories in the last 24 hours.",
      ),
    );
    return;
  }
  body.append(
    element(
      "p",
      "helper",
      "Teal rings mark countries named across multiple categories in 24h. Ring size grows with the number of categories.",
    ),
  );
  const list = element("ul", "cross-list");
  for (const item of state.crossCategory.slice(0, 8)) {
    const row = element("li");
    const name =
      state.world?.features.find((f) => f.properties.code === item.country)
        ?.properties.name || item.country;
    row.append(
      element("span", "evidence-name", name),
      element(
        "span",
        "helper",
        Object.entries(item.categories)
          .map(([key, count]) => `${names[key] || key} ${count}`)
          .join(" · "),
      ),
    );
    list.append(row);
  }
  body.append(list);
  body.append(element("p", "helper", state.crossCategory[0].basis));
}

function renderAnomalyAlerts(results) {
  $("#anomaly-alerts").replaceChildren();
  worldMap.setRegionalAnomalies(
    results[9].status === "fulfilled" ? results[9].value.items : [],
  );
  worldMap.setCrossCategory(
    results[10].status === "fulfilled" ? results[10].value.regions : [],
  );
  state.crossCategory =
    results[10].status === "fulfilled" ? results[10].value.regions : [];
  renderCrossCategoryPanel();
  const regional =
    results[9].status === "fulfilled" ? results[9].value.items : [];
  const cross =
    results[10].status === "fulfilled" ? results[10].value.regions : [];
  state.reportingSignals = regional.length + cross.length;
  $('[data-count="analysis"]').textContent = String(state.reportingSignals);
  syncReportingSignals();
  if (!state.layers.has("analysis")) return;
  if (regional.length)
    $("#anomaly-alerts").append(
      element(
        "p",
        "anomaly",
        `${regional.length} areas show a report surge against their 72-hour baseline. Amber rings mark these areas.`,
      ),
    );
  if (cross.length)
    $("#anomaly-alerts").append(
      element(
        "p",
        "anomaly",
        `${cross.length} countries have reports in multiple enabled layers within the past 24 hours. Teal rings mark shared country context.`,
      ),
    );
  if (!regional.length && !cross.length)
    $("#anomaly-alerts").append(
      element(
        "p",
        "helper",
        "No report surge or overlap meets the threshold in this view. Enable additional layers or broaden the period to explore more evidence.",
      ),
    );
  for (const item of cross.slice(0, 5)) {
    const name =
      state.world.features.find((f) => f.properties.code === item.country)
        ?.properties.name || item.country;
    const row = element("div", "reporting-signal-row");
    row.append(
      element("strong", "", name),
      element(
        "p",
        "helper",
        Object.entries(item.categories)
          .map(([category, count]) => `${names[category]}: ${count}`)
          .join(" · "),
      ),
    );
    const inspect = element("button", "", "Inspect reports");
    inspect.addEventListener("click", () => {
      ensureSignalEvidence();
      selectCountry(item.country, true);
    });
    row.append(inspect);
    $("#anomaly-alerts").append(row);
  }
  for (const item of regional.slice(0, 5)) {
    const row = element("div", "reporting-signal-row");
    row.append(
      element(
        "strong",
        "",
        `Report surge · ${item.latitude.toFixed(1)}°, ${item.longitude.toFixed(1)}°`,
      ),
      element(
        "p",
        "helper",
        `${item.recent_count} reports in six hours; ${item.previous_count} in the preceding six hours. Comparison uses ${item.baseline_count} reports across 72 hours.`,
      ),
    );
    const inspect = element("button", "", "Inspect reports in area");
    inspect.addEventListener("click", () => inspectSignalRegion(item));
    row.append(inspect);
    $("#anomaly-alerts").append(row);
  }
}

function ensureSignalEvidence() {
  if (
    ![...state.layers].some(
      (id) => !["analysis", "sentiment", "space", "threat"].includes(id),
    )
  ) {
    state.layers.add("geopolitical");
    state.layers.add("military");
    renderLayers();
    syncReportingSignals();
  }
}

function inspectSignalRegion(item) {
  ensureSignalEvidence();
  state.country = "";
  $("#country").value = "";
  $("#viewport-filter").checked = true;
  worldMap.focusRegion(item);
  showView("feed");
  refresh();
}

function renderEvidenceGaps() {
  const panel = $("#evidence-gaps");
  if (!panel) return;
  const gaps = Object.entries(state.layerHealth).filter(
    ([id, health]) =>
      id !== "analysis" &&
      (health.coverage === "none_current" || health.coverage === "no_sources"),
  );
  const degraded = Object.entries(state.layerHealth).filter(
    ([, health]) => health.coverage === "degraded",
  );
  panel.replaceChildren();
  if (!gaps.length && !degraded.length) {
    panel.append(
      element(
        "p",
        "helper",
        "All configured layers have at least one current source.",
      ),
    );
    return;
  }
  if (gaps.length) {
    panel.append(element("h4", "", "Layers with no current source"));
    const list = element("ul", "gap-list");
    for (const [id, health] of gaps) {
      const row = element("li");
      row.append(
        element("strong", "", names[id] || id),
        element(
          "span",
          "helper",
          health.needs_access
            ? `${health.needs_access} source(s) need access credentials`
            : health.total
              ? "no configured source is current; check failures and stale collections"
              : "no source configured for this layer",
        ),
      );
      list.append(row);
    }
    panel.append(list);
  }
  if (degraded.length) {
    panel.append(element("h4", "", "Partially covered layers"));
    const list = element("ul", "gap-list");
    for (const [id, health] of degraded) {
      const row = element("li");
      row.append(
        element("strong", "", names[id] || id),
        element(
          "span",
          "helper",
          `${health.current} of ${health.total} sources current${health.failing ? `, ${health.failing} failing` : ""}`,
        ),
      );
      list.append(row);
    }
    panel.append(list);
  }
  panel.append(
    element(
      "p",
      "helper",
      "A layer with no current source renders near-empty for collection reasons. That is not evidence that nothing is happening.",
    ),
  );
}

function togglePanel(panel) {
  const collapsed = $("#workspace").classList.toggle(`${panel}-collapsed`);
  const button = $(`[data-panel="${panel}"]`);
  button.setAttribute("aria-expanded", String(!collapsed));
  const label =
    panel === "left"
      ? "intelligence controls"
      : panel === "right"
        ? "intelligence details"
        : "timeline";
  button.setAttribute(
    "aria-label",
    `${collapsed ? "Expand" : "Collapse"} ${label}`,
  );
  button.textContent =
    panel === "left"
      ? collapsed
        ? "›"
        : "‹"
      : panel === "right"
        ? collapsed
          ? "‹"
          : "›"
        : collapsed
          ? "⌃"
          : "⌄";
  chart?.resize();
}

function setTheme() {
  document.documentElement.classList.toggle("light", state.light);
  $("#theme span").textContent = state.light ? "Dark" : "Light";
  $("#theme").setAttribute(
    "aria-label",
    `Switch to ${state.light ? "dark" : "light"} theme`,
  );
  worldMap?.setTheme(state.light);
  chart?.setTheme(state.light);
  saveSession("osint.light", state.light);
}

function showTopic(name = "") {
  const group = state.military?.groups.find((group) => group.name === name);
  state.militaryTopic = group ? name : "";
  worldMap?.setMilitaryNetwork(
    group?.network || state.military?.network,
    state.layers.has("military") && $("#military-connections").checked,
  );
  $("#military-map-label").textContent =
    `Map: ${group ? name : "all defence topics"}. Pink lines link cited reports to country context.`;
  renderNetworkSummary();
}
function renderCountryActivity() {
  countryRibbon.setCyberData(
    displayThreatNetwork(),
    state.layers.has("cyber"),
    state.world?.features.map((feature) => feature.properties) || [],
  );
  if (!state.countryActivity) return;
  if ([...state.layers].every((id) => ["space", "analysis"].includes(id))) {
    countryRibbon.setData({
      ...state.countryActivity,
      items: [],
      selected_country: state.country,
    });
    return;
  }
  countryRibbon.setData({
    ...threatCountryActivity(
      state.countryActivity,
      displayThreatNetwork(),
      state.world.features.map((feature) => feature.properties),
      state.threatVector === "all"
        ? state.layers
        : new Set([...state.layers].filter((id) => id !== "cyber")),
    ),
    selected_country: state.country,
  });
}
function renderNetworkSummary() {
  const parts = [];
  if (state.layers.has("threat") && state.threatNetwork) {
    const network = displayThreatNetwork();
    parts.push(
      `Cyber evidence: ${network.report_count} published attack reports · ${network.observation_count} sampled detections${network.aggregate_count ? ` · ${network.aggregate_count} daily aggregate rows` : ""} · ${network.edges.filter((edge) => edge.kind === "reported_attacker_to_victim").length} attribution links · ${network.edges.filter((edge) => edge.kind === "observed_traffic_to_target").length} traffic routes`,
    );
    const note = $('[data-layer-note="cyber"]');
    if (note) note.textContent = "Advisories, reports & traffic country routes";
  }
  if (
    state.layers.has("cyber") &&
    $("#cyber-connections").checked &&
    state.cyberNetwork
  )
    parts.push(
      `Cyber: ${state.cyberNetwork.report_count} reports · ${state.cyberNetwork.edges.length} context links`,
    );
  if (state.layers.has("geopolitical") && $("#news-connections").checked) {
    const news = state.newsNetwork;
    if (news)
      parts.push(
        `News: ${news.report_count} reports · ${news.edges.length} links`,
      );
  }
  if (state.layers.has("military") && $("#military-connections").checked) {
    const group = state.military?.groups.find(
      (group) => group.name === state.militaryTopic,
    );
    const network = group?.network || state.military?.network;
    if (network)
      parts.push(
        `Defence: ${group?.count ?? state.military.report_count} reports · ${network.edges.length} links`,
      );
  }
  $("#network-summary").textContent =
    parts.join(" · ") || "News and defence connections hidden";
}
function analyzeTopic(group) {
  state.selectedEvent = null;
  state.analysisEventIds = group.event_ids;
  $("#ai-question").value =
    `Assess the public evidence for ${group.name}. Distinguish official claims from independently supported facts, explain geographic relationships, identify source bias and evidence gaps. Do not infer military movements or capabilities beyond the cited wording.`;
  showView("analysis");
}
$("#reddit-import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = $("#reddit-import-status"),
    button = $("#reddit-import-submit");
  if (!state.token) {
    status.textContent =
      "Enter your local access token in Settings to import. No social API key is required.";
    return;
  }
  const file = $("#reddit-import-file").files[0];
  const pasted = $("#reddit-import-text").value.trim();
  if (
    (!file && !pasted) ||
    (file && file.size > 65_536) ||
    new TextEncoder().encode(pasted).length > 65_536
  ) {
    status.textContent =
      "Choose a public snapshot file or paste a capture smaller than 64 KB.";
    return;
  }
  button.disabled = true;
  try {
    const body = JSON.parse(pasted || (await file.text()));
    const result = await api("admin/social/reddit-browser", {
      token: state.token,
      body,
    });
    status.textContent = `Imported ${result.stored} public records. Manual browser sample; expires after 24 hours.`;
    $("#reddit-import-text").value = "";
    $("#reddit-import-file").value = "";
    await refresh();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#military-all").addEventListener("click", () => showTopic());
$("#military-connections").addEventListener("change", () =>
  showTopic(state.militaryTopic),
);
async function analyze(event) {
  event.preventDefault();
  $("#ai-error").textContent = "";
  if (state.selectedEvent?.live) {
    $("#ai-error").textContent =
      "This aircraft card shows a current position. Select a retained source event for evidence analysis.";
    return;
  }
  if (!state.token) {
    $("#ai-error").textContent =
      "Enter the server access token in Settings to use protected analysis.";
    return;
  }
  const button = $("#ai-submit");
  button.disabled = true;
  button.textContent = "Analyzing sources…";
  $("#ai-result").setAttribute("aria-busy", "true");
  try {
    const result = await api("ai/analyze", {
      token: state.token,
      body: {
        question: $("#ai-question").value,
        event_ids:
          state.analysisEventIds ||
          (state.selectedEvent ? [state.selectedEvent.event_id] : []),
        filters: state.analysisEventIds ? {} : filters(),
      },
    });
    $("#ai-result").replaceChildren(
      element("p", "helper", dateText(result.analyzed_at)),
    );
    if (result.output_mode === "draft") {
      $("#ai-result").append(
        element("strong", "", "AI draft · citations not validated"),
        element("p", "ai-draft", result.draft_text),
        element("h4", "", "Sources supplied for context"),
      );
      for (const reference of result.references)
        $("#ai-result").append(
          sourceLink(reference.source_url, "Open supplied source"),
        );
    }
    for (const claim of result.claims || []) {
      const node = element("article", "analysis-claim");
      node.append(
        element("span", "badge", claim.kind.replaceAll("_", " ")),
        element("p", "", claim.text),
      );
      for (const citation of claim.citations) {
        const reference = result.references.find(
          (reference) =>
            reference.event_id === citation.event_id &&
            reference.report_id === citation.report_id,
        );
        if (reference)
          node.append(
            sourceLink(
              reference.source_url,
              `Open ${new URL(reference.source_url).hostname.replace(/^www\./, "")}`,
            ),
          );
        const select = element("button", "", "Inspect cited evidence on map");
        select.addEventListener("click", () =>
          selectEvent(citation.event_id, true),
        );
        node.append(select);
      }
      $("#ai-result").append(node);
    }
    const limitations = element("ul", "analysis-limitations");
    for (const limitation of result.limitations)
      limitations.append(element("li", "", limitation));
    $("#ai-result").append(limitations);
  } catch (error) {
    $("#ai-error").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Analyze source records";
    $("#ai-result").setAttribute("aria-busy", "false");
  }
}

async function initialize() {
  renderLayers();
  $("#sentiment-evidence").checked = state.sentimentEvidence;
  $("#analysis-overlays").checked = state.analysisOverlays;
  $("#density-confidence").checked = state.densityConfidence;
  $("#utc-clock").textContent = new Date().toISOString().slice(11, 19) + " UTC";
  setInterval(() => {
    $("#utc-clock").textContent =
      new Date().toISOString().slice(11, 19) + " UTC";
  }, 1000);
  try {
    const responses = await Promise.all([
      fetch("/countries.geojson"),
      fetch("/country-context.geojson"),
    ]);
    if (responses.some((response) => !response.ok))
      throw new Error("Local country map could not load");
    const [world, context] = await Promise.all(
      responses.map((response) => response.json()),
    );
    const known = new Set(
      world.features.map((feature) => feature.properties.code),
    );
    world.features.push(
      ...context.features.filter(
        (feature) => !known.has(feature.properties.code),
      ),
    );
    state.world = world;
    for (const feature of [...state.world.features].sort((a, b) =>
      a.properties.name.localeCompare(b.properties.name),
    )) {
      const option = element("option", "", feature.properties.name);
      option.value = feature.properties.code;
      $("#country").append(option);
    }
    worldMap = createWorldMap(state.world, {
      selectEvent,
      selectCountry,
      inspectRegion: inspectSignalRegion,
      viewportChanged() {
        if ($("#viewport-filter").checked) {
          clearTimeout(viewportTimer);
          viewportTimer = setTimeout(refresh, 300);
        }
      },
      mapError: (text) =>
        message(`Map: ${text}. Use the event list to inspect observations.`),
    });
    worldMap.setDensityWeighted(state.densityConfidence);
    await refreshOrbits();
    worldMap.setAnalysisVisible(state.analysisOverlays);
    const { charts } = await import("./charts.js");
    chart = charts({ selectReport: focusSocialPost });
    setTheme();
    await refresh();
  } catch (error) {
    message(error.message);
  }
}

$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.q = $("#search").value.trim();
  refresh();
});
$("#search").addEventListener("search", () => {
  state.q = $("#search").value.trim();
  refresh();
});
$("#refresh").addEventListener("click", refresh);
$("#country").addEventListener("change", (event) =>
  selectCountry(event.target.value, true),
);
$("#viewport-filter").addEventListener("change", refresh);
$("#period").addEventListener("change", (event) => {
  state.period = event.target.value;
  $("#custom-dates").hidden = state.period !== "custom";
  if (state.period !== "custom") {
    $("#playhead").value = "100";
    refresh();
  }
});
$("#apply-dates").addEventListener("click", () => {
  $("#playhead").value = "100";
  refresh();
});
$("#time-basis").addEventListener("change", refresh);
$("#sentiment-kind").addEventListener("change", refresh);
$("#sentiment-platform").addEventListener("change", refresh);
$("#sentiment-geography").addEventListener("change", refresh);
$("#social-edges").addEventListener("change", () =>
  worldMap.setSocialNetwork(
    state.sentimentResult?.map_network,
    state.layers.has("sentiment") && $("#social-edges").checked,
  ),
);
$("#news-connections").addEventListener("change", () => {
  worldMap.setNewsNetwork(
    state.newsNetwork,
    state.layers.has("geopolitical") && $("#news-connections").checked,
  );
  renderNetworkSummary();
});
$("#cyber-connections").addEventListener("change", () => {
  worldMap.setCyberNetwork(
    state.cyberNetwork,
    state.layers.has("cyber") &&
      $("#cyber-connections").checked &&
      state.threatVector === "all",
  );
  renderNetworkSummary();
});
$("#reset-view").addEventListener("click", () => {
  worldMap.reset();
  selectCountry("");
});
$("#theme").addEventListener("click", () => {
  state.light = !state.light;
  setTheme();
});
$("#heatmap").addEventListener("change", (event) =>
  worldMap.setDensity(event.target.checked),
);
$("#density-confidence").addEventListener("change", (event) => {
  state.densityConfidence = event.target.checked;
  saveSession("osint.densityConfidence", state.densityConfidence);
  worldMap.setDensityWeighted(state.densityConfidence);
});
$("#analysis-overlays").addEventListener("change", (event) => {
  event.target.checked
    ? state.layers.add("analysis")
    : state.layers.delete("analysis");
  syncReportingSignals();
  if (event.target.checked) showView("feed");
  refresh();
});
$("#sentiment-evidence").addEventListener("change", (event) => {
  state.sentimentEvidence = event.target.checked;
  saveSession("osint.sentimentEvidence", state.sentimentEvidence);
  worldMap.setSentimentEvidence(state.sentimentEvidence);
});
for (const panel of ["left", "right", "bottom"])
  $(`[data-panel="${panel}"]`).addEventListener("click", () =>
    togglePanel(panel),
  );
for (const view of ["feed", "analysis", "sentiment", "military"])
  $(`#${view}-tab`).addEventListener("click", () => showView(view));
$("#settings-open").addEventListener("click", () =>
  $("#settings-dialog").showModal(),
);
$("#settings-close").addEventListener("click", () =>
  $("#settings-dialog").close(),
);
$("#settings-dialog").addEventListener("close", () =>
  $("#settings-open").focus(),
);
$("#settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.token = $("#admin-token").value;
  $("#admin-token").value = "";
  $("#settings-dialog").close();
});
$("#ai-form").addEventListener("submit", analyze);
$("#ai-question").setAttribute("aria-describedby", "ai-error");
$("#load-more").addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  $("#load-more").disabled = true;
  try {
    const result = await api(
      `events?${params()}&limit=500&order=balanced&offset=${state.events.length}`,
    );
    state.events = [
      ...state.events,
      ...result.items.filter(
        (event) =>
          !state.events.some(
            (existing) => existing.event_id === event.event_id,
          ),
      ),
    ];
    state.total = result.total;
    state.categoryCounts = result.category_counts || {};
    renderEvents();
  } catch (error) {
    message(error.message);
  } finally {
    busy = false;
    $("#load-more").disabled = false;
  }
});
$("#playhead").addEventListener("input", renderEvents);
$("#playback").addEventListener("click", () => {
  if (playbackTimer) {
    clearInterval(playbackTimer);
    playbackTimer = undefined;
    $("#playback").textContent = "▷ Play history";
    $("#playback").setAttribute("aria-pressed", "false");
    return;
  }
  $("#playhead").value = "0";
  $("#playback").textContent = "Ⅱ Pause history";
  $("#playback").setAttribute("aria-pressed", "true");
  renderEvents();
  playbackTimer = setInterval(() => {
    $("#playhead").value = Math.min(100, Number($("#playhead").value) + 2);
    renderEvents();
    if (Number($("#playhead").value) === 100) $("#playback").click();
  }, 300);
});
setInterval(() => {
  if (!document.hidden && !playbackTimer && !busy && !$("#refresh").disabled)
    refresh();
}, 60000);
function aircraftFilterKey() {
  const f = filters();
  return JSON.stringify({
    country: f.country,
    q: f.q,
    bbox: f.bbox,
    time_basis: f.time_basis,
    period: state.period,
  });
}
let aircraftBusy = false;
async function refreshAircraft() {
  if (
    aircraftBusy ||
    document.hidden ||
    !worldMap ||
    !state.layers.has("aviation") ||
    state.period === "custom" ||
    Number($("#playhead").value) !== 100
  )
    return;
  aircraftBusy = true;
  const key = aircraftFilterKey();
  try {
    const result = await api(`aviation/live?${params()}`);
    if (key !== aircraftFilterKey()) return;
    state.aircraft = result;
    state.aircraftFilter = key;
    renderEvents();
  } catch {
    if (state.aircraft) state.aircraft.stale = true;
    renderEvents();
  } finally {
    aircraftBusy = false;
  }
}
setInterval(refreshAircraft, 15000);

async function loadThreatTelemetry(query, signal) {
  const results = await Promise.allSettled(
    [
      "Bitdefender detections:",
      "BunkerWeb WAF:",
      "Imperva daily attack requests:",
      "Radware detections:",
    ].map((name) => {
      const sourceQuery = new URLSearchParams(query);
      sourceQuery.set("q", name);
      return api(`events?${sourceQuery}&limit=100&order=balanced`, { signal });
    }),
  );
  if (results.every((r) => r.status === "rejected")) throw results[0].reason;
  return {
    items: results.flatMap((r) =>
      r.status === "fulfilled"
        ? r.value.items.filter(
            (e) =>
              e.category === "threat" && threatProviders.includes(e.source_id),
          )
        : [],
    ),
    failed_sources: results.flatMap((r, i) =>
      r.status === "rejected" ? [threatProviders[i]] : [],
    ),
  };
}
let threatBusy = false;
async function refreshThreatFeeds() {
  if (
    threatBusy ||
    document.hidden ||
    !worldMap ||
    !state.layers.has("threat") ||
    $("#refresh").disabled ||
    playbackTimer ||
    Number($("#playhead").value) !== 100
  )
    return;
  threatBusy = true;
  const key = aircraftFilterKey(),
    controller = refreshController;
  try {
    const query = new URLSearchParams(params());
    for (const field of [
      "categories",
      "aircraft_categories",
      "country",
      "bbox",
    ])
      query.delete(field);
    const [data, bridge] = await Promise.all([
      loadThreatTelemetry(query),
      fetch("/threatmap-status.json", { cache: "no-store" })
        .then((r) => r.json())
        .catch(() => null),
    ]);
    if (
      key !== aircraftFilterKey() ||
      controller !== refreshController ||
      !state.layers.has("threat")
    )
      return;
    const oldCount = state.threatCount;
    state.threatNetwork = buildThreatNetwork(
      [
        ...state.threatEvents.filter(
          (e) =>
            !e.tags?.includes("threat-telemetry") ||
            data.failed_sources.includes(e.source_id),
        ),
        ...data.items,
      ],
      state.world.features.map((f) => f.properties),
      {
        country: state.country,
        bbox: $("#viewport-filter").checked ? worldMap.bounds() : null,
        q: state.q,
      },
    );
    state.threatEvents = state.threatNetwork.events;
    state.threatCount = state.threatEvents.length;
    state.categoryCounts.threat = state.threatCount;
    state.total = Math.max(0, state.total - oldCount + state.threatCount);
    renderEvents();
    renderCountryActivity();
    if (bridge) {
      state.vectorSummary = bridge.vector_summary || state.vectorSummary;
      renderVectorBreakdown(state.vectorSummary);
      $("#threat-stream-health").replaceChildren();
      for (const source of bridge.connectors || []) {
        if (
          !threatProviders.includes(source.source_id) &&
          !source.source_id.startsWith("threat_research_")
        )
          continue;
        $("#threat-stream-health").append(
          element(
            "p",
            "helper",
            `${source.name}: ${source.state === "ok" ? "Available" : source.state === "deferred" ? "Awaiting next update" : "Update unavailable"}`,
          ),
        );
      }
    }
  } catch {
    /* Last successful evidence stays visible; provider health records collection failures. */
  } finally {
    threatBusy = false;
  }
}
setInterval(refreshThreatFeeds, 10000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshAircraft();
});
initialize();
setInterval(() => {
  if (!document.hidden && state.layers.has("space")) updateOrbitalPositions();
}, 2000);
setInterval(() => {
  if (!document.hidden) refreshOrbits();
}, 3600000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) updateOrbitalPositions();
});
