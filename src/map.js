import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { element } from "./api.js";
import { connectionGeometry, pointAlong } from "./geo-lines.js";
import {
  latestAircraft,
  aircraftTransition,
  aircraftSummary,
} from "./aircraft.js";
import { colors, CATEGORY_NAMES, symbolImage } from "./layer-symbols.js";
export { colors, CATEGORY_NAMES } from "./layer-symbols.js";

maplibregl.setWorkerUrl(workerUrl);
maplibregl.setWorkerCount(2);

const empty = () => ({ type: "FeatureCollection", features: [] });
const reducedMotion = () =>
  matchMedia("(prefers-reduced-motion: reduce)").matches;
// Pulse colour carries the tone of the reports travelling the edge, on the same
// ramp as the sentiment heatmaps. Scores are bounded to [-1, 1] by both the
// headline lexicon and VADER, so magnitude maps straight onto the mix.
const PULSE_NEGATIVE = "#d87d78";
const PULSE_NEUTRAL = "#8195a1";
const PULSE_POSITIVE = "#6ec8a9";
function pulseColor(score) {
  if (!score) return PULSE_NEUTRAL;
  const weight = Math.min(1, Math.abs(score));
  const target = score < 0 ? PULSE_NEGATIVE : PULSE_POSITIVE;
  const channel = (offset) => {
    const from = parseInt(PULSE_NEUTRAL.slice(offset, offset + 2), 16);
    const to = parseInt(target.slice(offset, offset + 2), 16);
    return Math.round(from + (to - from) * weight);
  };
  return `rgb(${channel(1)},${channel(3)},${channel(5)})`;
}
const PULSE_DURATION = 1800;
const PULSE_GAP = 380;
const PULSE_LIMIT = 18;
// ADS-B size class: 4 Large (75,000-300,000 lbs), 5 High Vortex. These are
// the classes selected for this map, declared by the transponder.
function aircraftIcon() {
  // Drawn nose-up: icon-rotation-alignment "map" then points it along the track.
  const size = 24;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  context.translate(size / 2, size / 2);
  context.fillStyle = colors.aviation;
  context.beginPath();
  context.moveTo(0, -10);
  context.quadraticCurveTo(2.6, -6, 2.4, 0);
  context.lineTo(9, 4.5);
  context.quadraticCurveTo(9.8, 6, 8.6, 6.2);
  context.lineTo(1.9, 3.6);
  context.lineTo(1.4, 8.4);
  context.lineTo(4.6, 10);
  context.quadraticCurveTo(5.2, 11, 4, 11.2);
  context.lineTo(0, 9.8);
  context.lineTo(-4, 11.2);
  context.quadraticCurveTo(-5.2, 11, -4.6, 10);
  context.lineTo(-1.4, 8.4);
  context.lineTo(-1.9, 3.6);
  context.lineTo(-8.6, 6.2);
  context.quadraticCurveTo(-9.8, 6, -9, 4.5);
  context.lineTo(-2.4, 0);
  context.quadraticCurveTo(-2.6, -6, 0, -10);
  context.closePath();
  context.fill();
  context.strokeStyle = "#55460a";
  context.lineWidth = 0.7;
  context.stroke();
  return context.getImageData(0, 0, size, size);
}
export const THIN_SAMPLE = 5;
function graticule() {
  const features = [];
  for (let longitude = -180; longitude <= 180; longitude += 30)
    features.push({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [longitude, -85],
          [longitude, 85],
        ],
      },
    });
  for (let latitude = -60; latitude <= 60; latitude += 30)
    features.push({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [-180, latitude],
          [180, latitude],
        ],
      },
    });
  return { type: "FeatureCollection", features };
}

export function createWorldMap(
  world,
  { selectEvent, selectCountry, viewportChanged, mapError },
) {
  const map = new maplibregl.Map({
    container: "map",
    center: [0, 22],
    zoom: 0.5,
    minZoom: -1,
    maxZoom: 12,
    attributionControl: false,
    renderWorldCopies: false,
    style: {
      version: 8,
      sources: {},
      layers: [
        {
          id: "ocean",
          type: "background",
          paint: { "background-color": "#101b22" },
        },
      ],
    },
  });
  let eventData = empty(),
    aircraftData = empty(),
    sentimentData = empty(),
    selected = "",
    density = false,
    densityWeighted = true,
    light = false,
    analysisVisible = false,
    sentimentVisible = false,
    sentimentEvidence = false;
  let aircraftRecords = [],
    aircraftFrame,
    aircraftTarget = empty(),
    aircraftSignature = "";
  let aircraftInView = true;
  const aircraftMotion = matchMedia("(prefers-reduced-motion: reduce)");
  function finishAircraftMotion() {
    cancelAnimationFrame(aircraftFrame);
    aircraftFrame = undefined;
    aircraftData = aircraftTarget;
    map.getSource("aircraft")?.setData(aircraftData);
    map.getCanvas().dataset.aircraftMoving = "0";
  }
  function aircraftVisibilityChanged() {
    if (document.hidden || aircraftMotion.matches) finishAircraftMotion();
  }
  document.addEventListener("visibilitychange", aircraftVisibilityChanged);
  aircraftMotion.addEventListener("change", aircraftVisibilityChanged);
  const aircraftObserver = new IntersectionObserver(([entry]) => {
    aircraftInView = entry.isIntersecting;
    if (!aircraftInView) finishAircraftMotion();
  });
  aircraftObserver.observe(map.getCanvas());
  map.on("remove", () => {
    cancelAnimationFrame(aircraftFrame);
    document.removeEventListener("visibilitychange", aircraftVisibilityChanged);
    aircraftMotion.removeEventListener("change", aircraftVisibilityChanged);
    aircraftObserver.disconnect();
  });
  function updateAircraft(records, features) {
    const signature = JSON.stringify(
      records.map((r) => [
        r.event_id,
        r.time_key,
        r.longitude,
        r.latitude,
        r.aircraft_track_deg,
        r.live,
      ]),
    );
    if (signature === aircraftSignature) return;
    finishAircraftMotion();
    aircraftSignature = signature;
    const previous = new Map(aircraftRecords.map((r) => [r.event_id, r]));
    const transitions = records.map((r) =>
      aircraftTransition(previous.get(r.event_id), r),
    );
    aircraftRecords = records;
    aircraftTarget = features(
      records.map((r) => ({ ...r, aircraft_summary: aircraftSummary(r) })),
    );
    aircraftData = aircraftTarget;
    if (
      document.hidden ||
      !aircraftInView ||
      aircraftMotion.matches ||
      !transitions.some(Boolean) ||
      !map.getSource("aircraft")
    ) {
      finishAircraftMotion();
      return;
    }
    const began = performance.now();
    let last = -Infinity;
    map.getCanvas().dataset.aircraftMoving = String(
      transitions.filter(Boolean).length,
    );
    function animate(now) {
      if (
        document.hidden ||
        !aircraftInView ||
        aircraftMotion.matches ||
        now - began >= 8000
      ) {
        finishAircraftMotion();
        return;
      }
      if (now - last >= 70) {
        last = now;
        const fraction = Math.min(1, (now - began) / 8000);
        aircraftData = {
          type: "FeatureCollection",
          features: aircraftTarget.features.map((feature, index) => {
            const position = transitions[index]?.(fraction);
            return position
              ? {
                  ...feature,
                  geometry: {
                    type: "Point",
                    coordinates: [position.longitude, position.latitude],
                  },
                  properties: {
                    ...feature.properties,
                    aircraft_track_deg: position.aircraft_track_deg,
                  },
                }
              : feature;
          }),
        };
        map.getSource("aircraft")?.setData(aircraftData);
      }
      aircraftFrame = requestAnimationFrame(animate);
    }
    aircraftFrame = requestAnimationFrame(animate);
  }
  let newsData = empty(),
    cyberData = empty(),
    cyberNetwork = null,
    cyberVisible = false,
    socialData = empty(),
    publisherData = empty(),
    newsVisible = false,
    socialVisible = false;
  let militaryPlaces = empty();
  let sentimentResult = null;
  let militaryData = empty(),
    militaryNetwork = null,
    militaryVisible = false;
  let newsNetwork = null,
    socialNetwork = null,
    crossCategoryData = [];
  let pulseFrame,
    pulses = [],
    nextPulseAt = 0,
    pulseCursor = 0;
  map.on("styleimagemissing", ({ id }) => {
    const match = /^cluster-(\w+)-(reported|context)-(\d+|99plus)$/.exec(id);
    if (!match || !(match[1] in colors || match[1] === "mixed")) return;
    map.addImage(
      id,
      symbolImage(match[1], {
        context: match[2] === "context",
        count: match[3] === "99plus" ? "99+" : match[3],
      }),
      { pixelRatio: 2 },
    );
  });
  map.addControl(
    new maplibregl.NavigationControl({ showCompass: false }),
    "top-right",
  );
  map.addControl(
    new maplibregl.FullscreenControl({
      container: document.querySelector(".map-workspace"),
    }),
    "top-right",
  );
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 80 }), "bottom-right");
  const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "270px" });
  const resetWorld = () =>
    map.fitBounds(
      [
        [-179.9, -55],
        [179.9, 80],
      ],
      { padding: { top: 140, bottom: 80, left: 20, right: 20 }, duration: 0 },
    );

  // Weight by evidence strength, not just volume. A single unverified report
  // should not heat a cell like corroborated reporting.
  const confidenceWeight = (name, fallback) => {
    const layer = map.getLayer(name);
    if (layer) map.setPaintProperty(name, "heatmap-weight", fallback);
  };
  function visibility() {
    if (!map.getLayer("event-density")) return;
    setAnalysisVisibility();
    confidenceWeight(
      "event-density",
      densityWeighted
        ? [
            "*",
            [
              "case",
              ["==", ["get", "confidence"], "Verified"],
              3,
              ["==", ["get", "confidence"], "Corroborated"],
              2,
              ["==", ["get", "confidence"], "Disputed"],
              0.4,
              1,
            ],
            ["coalesce", ["get", "count"], 1],
          ]
        : ["coalesce", ["get", "count"], 1],
    );
    map.setLayoutProperty(
      "event-density",
      "visibility",
      density ? "visible" : "none",
    );
    for (const kind of ["positive", "negative", "neutral"])
      map.setLayoutProperty(
        `sentiment-${kind}`,
        "visibility",
        sentimentVisible ? "visible" : "none",
      );
    for (const layer of ["sentiment-hover", "sentiment-symbols"])
      if (map.getLayer(layer))
        map.setLayoutProperty(
          layer,
          "visibility",
          sentimentVisible && sentimentEvidence ? "visible" : "none",
        );
    for (const layer of [
      "news-connections-solid",
      "news-connections-dotted",
      "publisher-points",
    ])
      if (map.getLayer(layer))
        map.setLayoutProperty(
          layer,
          "visibility",
          newsVisible ? "visible" : "none",
        );
    if (map.getLayer("new-report-pulses"))
      map.setLayoutProperty(
        "new-report-pulses",
        "visibility",
        newsVisible || militaryVisible || socialVisible || cyberVisible
          ? "visible"
          : "none",
      );
    if (map.getLayer("cyber-connections"))
      map.setLayoutProperty(
        "cyber-connections",
        "visibility",
        cyberVisible ? "visible" : "none",
      );
    if (map.getLayer("military-context"))
      map.setLayoutProperty(
        "military-context",
        "visibility",
        militaryVisible ? "visible" : "none",
      );
    if (map.getLayer("military-connections"))
      map.setLayoutProperty(
        "military-connections",
        "visibility",
        militaryVisible ? "visible" : "none",
      );
    if (map.getLayer("social-connections"))
      map.setLayoutProperty(
        "social-connections",
        "visibility",
        socialVisible ? "visible" : "none",
      );
  }
  function setAnalysisVisibility() {
    for (const layer of [
      "regional-anomalies",
      "cross-category",
      "regional-anomalies-symbol",
      "cross-category-symbol",
    ])
      if (map.getLayer(layer))
        map.setLayoutProperty(
          layer,
          "visibility",
          analysisVisible ? "visible" : "none",
        );
  }

  function countryCenter(code) {
    const feature = world.features.find(
      (item) => item.properties.code === code,
    );
    return feature ? feature.properties.center : [0, 0];
  }

  function theme() {
    if (!map.getLayer("countries-fill")) return;
    map.setPaintProperty(
      "ocean",
      "background-color",
      light ? "#dee8ed" : "#101b22",
    );
    map.setPaintProperty(
      "countries-fill",
      "fill-color",
      light ? "#c8d5dc" : "#202f38",
    );
    map.setPaintProperty(
      "countries-line",
      "line-color",
      light ? "#a9bdc8" : "#40525d",
    );
    map.setPaintProperty("grid", "line-color", light ? "#becdd5" : "#243741");
  }
  map.on("load", () => {
    for (const category of [...Object.keys(colors), "publisher"]) {
      for (const context of [false, true])
        map.addImage(
          `${category}-${context ? "context" : "reported"}`,
          symbolImage(category, { context }),
          { pixelRatio: 2 },
        );
    }
    for (const [tone, color] of [
      ["positive", PULSE_POSITIVE],
      ["negative", PULSE_NEGATIVE],
      ["neutral", PULSE_NEUTRAL],
    ])
      map.addImage(
        `sentiment-${tone}-symbol`,
        symbolImage("sentiment", { context: true, color }),
        { pixelRatio: 2 },
      );
    map.addSource("world", { type: "geojson", data: world });
    map.addSource("grid", { type: "geojson", data: graticule() });
    map.addLayer({
      id: "grid",
      type: "line",
      source: "grid",
      paint: {
        "line-color": "#243741",
        "line-width": 0.6,
        "line-opacity": 0.6,
      },
    });
    map.addLayer({
      id: "countries-fill",
      type: "fill",
      source: "world",
      paint: { "fill-color": "#202f38" },
    });
    map.addLayer({
      id: "countries-line",
      type: "line",
      source: "world",
      paint: {
        "line-color": "#40525d",
        "line-width": 0.65,
        "line-opacity": 0.7,
      },
    });
    map.addLayer({
      id: "country-selected",
      type: "fill",
      source: "world",
      filter: ["==", ["get", "code"], selected],
      paint: { "fill-color": "#77d4bc", "fill-opacity": 0.14 },
    });
    map.addLayer({
      id: "country-selected-line",
      type: "line",
      source: "world",
      filter: ["==", ["get", "code"], selected],
      paint: { "line-color": "#77d4bc", "line-width": 1.4 },
    });
    map.addSource("events", {
      type: "geojson",
      data: eventData,
      cluster: true,
      clusterMaxZoom: 7,
      clusterRadius: 38,
      clusterProperties: {
        ...Object.fromEntries(
          Object.keys(colors).map((category) => [
            category,
            ["+", ["case", ["==", ["get", "category"], category], 1, 0]],
          ]),
        ),
        regional_count: [
          "+",
          ["case", ["==", ["get", "location_precision"], "regional"], 1, 0],
        ],
      },
    });
    map.addSource("density", { type: "geojson", data: eventData });
    map.addSource("aircraft", { type: "geojson", data: aircraftData });
    map.addSource("sentiment", { type: "geojson", data: sentimentData });
    map.addSource("military-places", { type: "geojson", data: militaryPlaces });
    map.addSource("military-network", { type: "geojson", data: militaryData });
    map.addSource("news-network", { type: "geojson", data: newsData });
    map.addSource("cyber-network", { type: "geojson", data: cyberData });
    map.addSource("social-network", { type: "geojson", data: socialData });
    map.addSource("publishers", { type: "geojson", data: publisherData });
    map.addSource("new-reports", { type: "geojson", data: empty() });
    map.addSource("regional-anomalies", {
      type: "geojson",
      data: empty(),
    });
    map.addSource("cross-category", { type: "geojson", data: empty() });
    map.addLayer({
      id: "regional-anomalies",
      type: "circle",
      source: "regional-anomalies",
      paint: {
        "circle-radius": [
          "interpolate",
          ["linear"],
          ["get", "recent_count"],
          5,
          10,
          60,
          30,
        ],
        "circle-color": "#e4cc8a",
        "circle-opacity": 0.18,
        "circle-stroke-color": "#e4cc8a",
        "circle-stroke-width": 1.5,
      },
    });
    map.addLayer({
      id: "cross-category",
      type: "circle",
      source: "cross-category",
      paint: {
        "circle-radius": [
          "step",
          ["get", "category_count"],
          8,
          2,
          14,
          3,
          20,
          4,
          26,
        ],
        "circle-color": "#77d4bc",
        "circle-opacity": 0.22,
        "circle-stroke-color": "#77d4bc",
        "circle-stroke-width": 1.2,
      },
    });
    for (const source of ["regional-anomalies", "cross-category"])
      map.addLayer({
        id: `${source}-symbol`,
        type: "symbol",
        source,
        layout: {
          "icon-image": "analysis-context",
          "icon-allow-overlap": true,
        },
      });
    for (const [id, source, dotted, color] of [
      ["military-connections", "military-network", false, "#df9592"],
      ["cyber-connections", "cyber-network", true, "#b2a3db"],
      ["news-connections-solid", "news-network", false, "#dda96d"],
      ["news-connections-dotted", "news-network", true, "#91a7bd"],
      ["social-connections", "social-network", true, "#89c6b8"],
    ]) {
      map.addLayer({
        id,
        type: "line",
        source,
        ...(source === "news-network"
          ? {
              filter: [
                dotted ? "==" : "!=",
                ["get", "kind"],
                "country_co_mention",
              ],
            }
          : {}),
        layout: { "line-cap": "round" },
        paint: {
          "line-color": color,
          "line-width": [
            "interpolate",
            ["linear"],
            ["get", "count"],
            1,
            0.8,
            20,
            2.4,
          ],
          "line-opacity": 0.38,
          ...(dotted ? { "line-dasharray": [2, 3] } : {}),
        },
      });
    }
    map.addLayer({
      id: "military-context",
      type: "symbol",
      source: "military-places",
      layout: { "icon-image": "military-context", "icon-allow-overlap": true },
    });
    map.addLayer({
      id: "publisher-points",
      type: "symbol",
      source: "publishers",
      layout: {
        "icon-image": "publisher-reported",
        "icon-size": 0.8,
        "icon-allow-overlap": true,
      },
    });
    map.addLayer({
      id: "new-report-pulses",
      type: "circle",
      source: "new-reports",
      paint: {
        "circle-radius": 4,
        "circle-color": ["get", "color"],
        "circle-blur": 0.4,
        "circle-opacity": 0.9,
      },
    });
    for (const [kind, operator, color] of [
      ["positive", ">", "#6ec8a9"],
      ["negative", "<", "#d87d78"],
      ["neutral", "==", "#8195a1"],
    ]) {
      map.addLayer({
        id: `sentiment-${kind}`,
        type: "heatmap",
        source: "sentiment",
        filter: [operator, ["get", "score"], 0],
        paint: {
          "heatmap-weight": [
            "interpolate",
            ["linear"],
            ["get", "count"],
            1,
            0.35,
            10,
            2.4,
            50,
            4,
          ],
          "heatmap-intensity": 1,
          "heatmap-radius": 52,
          "heatmap-opacity": 0.6,
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(0,0,0,0)",
            0.2,
            color,
            1,
            color,
          ],
        },
      });
    }
    map.addLayer({
      id: "sentiment-symbols",
      type: "symbol",
      source: "sentiment",
      layout: {
        "icon-image": [
          "case",
          [">", ["get", "score"], 0],
          "sentiment-positive-symbol",
          ["<", ["get", "score"], 0],
          "sentiment-negative-symbol",
          "sentiment-neutral-symbol",
        ],
        "icon-allow-overlap": true,
      },
    });
    map.addLayer({
      id: "sentiment-hover",
      type: "circle",
      source: "sentiment",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 0, 16, 6, 42],
        "circle-color": "#ffffff",
        "circle-opacity": 0,
      },
    });
    map.addLayer({
      id: "event-density",
      type: "heatmap",
      source: "density",
      paint: {
        "heatmap-intensity": 0.65,
        "heatmap-radius": 28,
        "heatmap-opacity": 0.55,
        "heatmap-color": [
          "interpolate",
          ["linear"],
          ["heatmap-density"],
          0,
          "rgba(0,0,0,0)",
          0.25,
          "#396b63",
          0.6,
          "#77d4bc",
          1,
          "#e4cc8a",
        ],
      },
    });
    map.addLayer({
      id: "clusters",
      type: "symbol",
      source: "events",
      filter: ["has", "point_count"],
      layout: {
        "icon-image": [
          "concat",
          "cluster-",
          [
            "case",
            ...Object.keys(colors).flatMap((category) => [
              ["==", ["get", category], ["get", "point_count"]],
              category,
            ]),
            "mixed",
          ],
          "-",
          [
            "case",
            ["==", ["get", "regional_count"], ["get", "point_count"]],
            "context",
            "reported",
          ],
          "-",
          [
            "case",
            [">", ["get", "point_count"], 99],
            "99plus",
            ["to-string", ["get", "point_count"]],
          ],
        ],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
    });
    map.addLayer({
      id: "event-points",
      type: "symbol",
      source: "events",
      filter: ["!", ["has", "point_count"]],
      layout: {
        "icon-image": [
          "concat",
          ["get", "category"],
          "-",
          [
            "case",
            ["==", ["get", "location_precision"], "regional"],
            "context",
            "reported",
          ],
        ],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 0, 0.85, 5, 1.1],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
    });
    map.addImage("aircraft-plane", aircraftIcon(), { pixelRatio: 2 });
    map.addLayer({
      id: "aircraft-track",
      type: "symbol",
      source: "aircraft",
      filter: [
        "all",
        ["==", ["get", "category"], "aviation"],
        // ADS-B size class 4 Large (75,000-300,000 lbs) and 5 High Vortex.
        ["in", ["get", "aircraft_category"], ["literal", [4, 5]]],
        // Null tracks are absent observations, not a heading of north.
        [">=", ["get", "aircraft_track_deg"], 0],
      ],
      layout: {
        "icon-image": "aircraft-plane",
        "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 1, 8, 1.25],
        // Map alignment rotates the glyph along the reported track, so the
        // nose points where the aircraft is going at every zoom and bearing.
        "icon-rotate": ["get", "aircraft_track_deg"],
        "icon-rotation-alignment": "map",
        "icon-pitch-alignment": "map",
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "icon-padding": 2,
      },
      paint: {
        "icon-opacity": 1,
      },
    });
    map.on("click", "clusters", async (event) => {
      const feature = event.features[0];
      const zoom = await map
        .getSource("events")
        .getClusterExpansionZoom(feature.properties.cluster_id);
      map.easeTo({
        center: feature.geometry.coordinates,
        zoom,
        duration: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 0
          : 180,
      });
    });
    map.on("click", "event-points", (event) =>
      selectEvent(event.features[0].properties.event_id),
    );
    map.on("click", "aircraft-track", (event) =>
      selectEvent(event.features[0].properties.event_id),
    );
    map.on("click", "countries-fill", (event) => {
      if (
        map.queryRenderedFeatures(event.point, {
          layers: [
            "event-points",
            "aircraft-track",
            "clusters",
            "publisher-points",
            "news-connections-solid",
            "news-connections-dotted",
            "social-connections",
            "military-connections",
            "cyber-connections",
            "military-context",
          ],
        }).length
      )
        return;
      selectCountry(event.features[0].properties.code);
    });
    for (const layer of [
      "news-connections-solid",
      "news-connections-dotted",
      "social-connections",
      "military-connections",
      "cyber-connections",
    ]) {
      const showConnection = (event) => {
        const network =
          layer === "cyber-connections"
            ? cyberNetwork
            : layer === "military-connections"
              ? militaryNetwork
              : layer === "social-connections"
                ? socialNetwork
                : newsNetwork;
        const edge = network?.edges.find(
          (item) => item.id === event.features[0].properties.id,
        );
        if (!edge) return;
        const card = element("div", "connection-popup");
        const name = (code) =>
          world.features.find((f) => f.properties.code === code)?.properties
            .name || code;
        const kind =
          edge.kind === "publisher_to_country"
            ? `${edge.source_id}: publisher base → country discussed`
            : edge.kind === "declared_origin_to_mention"
              ? "Declared country origin → country discussed"
              : "Countries mentioned together";
        card.append(
          element("strong", "", `${name(edge.from)} → ${name(edge.to)}`),
          element(
            "p",
            "",
            `${kind}. ${edge.count} supporting feed reports. This is context, not movement or verified interaction.`,
          ),
        );
        for (let i = 0; i < Math.min(3, edge.titles.length); i++) {
          const button = element("button", "connection-story", edge.titles[i]);
          button.addEventListener("click", () =>
            selectEvent(edge.event_ids[i]),
          );
          card.append(button);
        }
        popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
      };
      map.on("click", layer, showConnection);
      map.on("mouseenter", layer, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }
    map.on("click", "military-context", (event) => {
      const feature = event.features[0];
      const card = element("div", "");
      card.append(
        element("strong", "", feature.properties.name),
        element(
          "p",
          "",
          `${feature.properties.count} defence reports name this country. Regional context; not a unit position.`,
        ),
      );
      const button = element("button", "", "Explore country evidence");
      button.addEventListener("click", () =>
        selectCountry(feature.properties.code),
      );
      card.append(button);
      popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
    });
    map.on("click", "regional-anomalies", (event) => {
      const feature = event.features[0];
      const card = element("div", "");
      card.append(
        element("strong", "", "Regional volume anomaly"),
        element(
          "p",
          "",
          `${feature.properties.recent_count} records in the last 6h, against ${feature.properties.previous_count} in the prior 6h and ${feature.properties.baseline_count} in the prior 72h.`,
        ),
        element("p", "helper", feature.properties.basis),
      );
      popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
    });
    map.on("click", "cross-category", (event) => {
      const feature = event.features[0];
      const entry = crossCategoryData.find(
        (item) => item.country === feature.properties.code,
      );
      if (!entry) return;
      const card = element("div", "");
      card.append(
        element(
          "strong",
          "",
          world.features.find((f) => f.properties.code === entry.country)
            ?.properties.name || entry.country,
        ),
        element(
          "p",
          "",
          `${entry.category_count} categories with 3+ records naming this country in the last 24h.`,
        ),
      );
      const list = element("ul", "cross-category-list");
      for (const [category, count] of Object.entries(entry.categories)) {
        const row = element("li");
        const mark = element("span", "layer-mark");
        mark.style.backgroundColor = colors[category] || "#a2b1bc";
        row.append(
          mark,
          element("span", "", CATEGORY_NAMES[category] || category),
          element("span", "layer-count", String(count)),
        );
        list.append(row);
      }
      card.append(list, element("p", "helper", entry.basis));
      popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
    });
    map.on("mouseenter", "cross-category", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "cross-category", () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("click", "publisher-points", (event) => {
      const feature = event.features[0];
      popup
        .setLngLat(feature.geometry.coordinates)
        .setDOMContent(
          element(
            "p",
            "",
            `${feature.properties.country}: configured publisher-country anchor for ${feature.properties.publishers}. Not an author's location or an incident origin.`,
          ),
        )
        .addTo(map);
    });
    map.on("mouseenter", "sentiment-hover", (event) => {
      map.getCanvas().style.cursor = "help";
      const region = sentimentData.features.find(
        (feature) =>
          feature.properties.country === event.features[0].properties.country,
      );
      if (!region) return;
      const { count, score, samples } = region.properties;
      const card = element("div", "sentiment-evidence-card");
      card.append(
        element("strong", "", region.properties.name),
        element(
          "p",
          "",
          `Mean wording score ${score >= 0 ? "+" : ""}${score.toFixed(3)} from ${samples} scored ${samples === 1 ? "text" : "texts"}`,
        ),
      );
      card.append(
        element(
          "p",
          samples < THIN_SAMPLE ? "thin-evidence" : "helper",
          samples < THIN_SAMPLE
            ? `Thin evidence: fewer than ${THIN_SAMPLE} texts. Treat this shade as weak, not a national mood.`
            : `Relatively supported: ${samples} scored texts.`,
        ),
      );
      card.append(
        element(
          "p",
          "helper",
          "Colour marks the sign of the mean lexicon score for wording published in, or naming, this country. It is not public opinion toward the country.",
        ),
      );
      popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
    });
    map.on("mouseleave", "sentiment-hover", () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    });
    for (const layer of ["clusters", "event-points", "aircraft-track"]) {
      map.on("mouseenter", layer, (event) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = event.features[0];
        const text = feature.properties.point_count
          ? `${feature.properties.point_count} loaded observations. ${Object.keys(
              colors,
            )
              .filter((category) => feature.properties[category] > 0)
              .map((category) => `${category}: ${feature.properties[category]}`)
              .join(
                ", ",
              )}. ${feature.properties.regional_count} regional context records. Select to expand.`
          : layer === "aircraft-track"
            ? `${feature.properties.title} · ${feature.properties.aircraft_summary || ""} · Position observed ${feature.properties.time_key}. Departure / destination not provided.`
            : feature.properties.title;
        popup
          .setLngLat(feature.geometry.coordinates)
          .setDOMContent(element("p", "", text))
          .addTo(map);
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
    }
    theme();
    visibility();
    resetWorld();
    map.getCanvas().dataset.ready = "true";
  });
  map.on("moveend", () => viewportChanged());
  // Continuous pulse animation keeps the map permanently busy, so "idle" never
  // fires. Sample on a throttle instead so instrumentation stays current.
  let lastSample = 0;
  const sampleCanvas = () => {
    const now = performance.now();
    if (now - lastSample < 250 || !map.getLayer("event-points")) return;
    lastSample = now;
    const observations = map.queryRenderedFeatures({
      layers: ["event-points", "clusters", "aircraft-track"],
    }).length;
    const countries = map.queryRenderedFeatures({
      layers: ["countries-fill"],
    }).length;
    map.getCanvas().dataset.rendered = String(observations + countries > 0);
    map.getCanvas().dataset.observations = String(observations);
    map.getCanvas().dataset.aircraft = String(
      map.queryRenderedFeatures({ layers: ["aircraft-track"] }).length,
    );
    const symbols = map.queryRenderedFeatures({ layers: ["event-points"] });
    const clusters = map.queryRenderedFeatures({ layers: ["clusters"] });
    map.getCanvas().dataset.layerSymbols = String(symbols.length);
    map.getCanvas().dataset.symbolCategories = [
      ...new Set(symbols.map((feature) => feature.properties.category)),
    ]
      .sort()
      .join(",");
    map.getCanvas().dataset.clusterSymbols = String(clusters.length);
    map.getCanvas().dataset.newsConnections = String(
      map.queryRenderedFeatures({
        layers: ["news-connections-solid", "news-connections-dotted"],
      }).length,
    );
    map.getCanvas().dataset.militaryConnections = String(
      map.queryRenderedFeatures({ layers: ["military-connections"] }).length,
    );
    map.getCanvas().dataset.socialConnections = String(
      map.queryRenderedFeatures({ layers: ["social-connections"] }).length,
    );
  };
  map.on("render", sampleCanvas);
  map.on("idle", sampleCanvas);
  map.on("error", (event) =>
    mapError(event.error?.message || "Map rendering failed"),
  );
  const resize = new ResizeObserver(() => map.resize());
  resize.observe(document.querySelector(".map-workspace"));

  function networkFeatures(network) {
    return {
      type: "FeatureCollection",
      features: (network?.edges || []).map((edge) => ({
        type: "Feature",
        geometry: connectionGeometry(
          edge.from_coordinates,
          edge.to_coordinates,
        ),
        properties: {
          id: edge.id,
          kind: edge.kind,
          count: edge.count,
          sentiment: edge.sentiment,
        },
      })),
    };
  }
  function pulseTracks() {
    const tracks = [];
    for (const [visible, data] of [
      [newsVisible, newsData],
      [cyberVisible, cyberData],
      [militaryVisible, militaryData],
      [socialVisible, socialData],
    ])
      if (visible)
        for (const feature of data.features)
          tracks.push({
            geometry: feature.geometry,
            color: pulseColor(feature.properties.sentiment),
          });
    return tracks;
  }

  function clearPulses() {
    cancelAnimationFrame(pulseFrame);
    pulseFrame = undefined;
    pulses = [];
    nextPulseAt = 0;
    pulseCursor = 0;
    map.getSource("new-reports")?.setData(empty());
  }

  function runPulses(now) {
    if (!map.getSource("new-reports")) {
      pulseFrame = requestAnimationFrame(runPulses);
      return;
    }
    const tracks = pulseTracks();
    if (reducedMotion() || !tracks.length) {
      if (pulses.length || pulseFrame) clearPulses();
      return;
    }
    if (now >= nextPulseAt && pulses.length < PULSE_LIMIT) {
      const track = tracks[pulseCursor % tracks.length];
      pulseCursor = (pulseCursor + 1) % tracks.length;
      pulses.push({ geometry: track.geometry, color: track.color, began: now });
      nextPulseAt = now + PULSE_GAP;
    }
    pulses = pulses.filter((pulse) => now - pulse.began < PULSE_DURATION);
    map.getSource("new-reports")?.setData({
      type: "FeatureCollection",
      features: pulses.map((pulse) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: pointAlong(
            pulse.geometry,
            (now - pulse.began) / PULSE_DURATION,
          ),
        },
        properties: { color: pulse.color },
      })),
    });
    pulseFrame = requestAnimationFrame(runPulses);
  }

  function startPulses() {
    if (pulseFrame || reducedMotion()) return;
    pulseFrame = requestAnimationFrame(runPulses);
  }

  return {
    map,
    setEvents(events) {
      const features = (records) => ({
        type: "FeatureCollection",
        features: records
          .filter((event) => event.latitude !== null)
          .map((event) => ({
            type: "Feature",
            id: event.event_id,
            geometry: {
              type: "Point",
              coordinates: [event.longitude, event.latitude],
            },
            properties: event,
          })),
      });
      eventData = features(
        events.filter((event) => event.category !== "aviation"),
      );
      updateAircraft(latestAircraft(events), features);
      map.getSource("events")?.setData(eventData);
      map.getSource("density")?.setData({
        type: "FeatureCollection",
        features: [...eventData.features, ...aircraftData.features],
      });
    },
    setSentiment(result, enabled) {
      sentimentVisible = enabled;
      sentimentResult = result;
      sentimentData = {
        type: "FeatureCollection",
        features: result.regions
          .filter(
            (region) => region.latitude !== null && region.longitude !== null,
          )
          .map((region) => ({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [region.longitude, region.latitude],
            },
            properties: {
              count: Math.min(region.count, 50),
              samples: region.count,
              score: region.score,
              country: region.country,
              name: region.name || region.country,
              thin: region.count < THIN_SAMPLE,
            },
          })),
      };
      map.getSource("sentiment")?.setData(sentimentData);
      visibility();
    },
    setSentimentEvidence(enabled) {
      sentimentEvidence = enabled;
      visibility();
    },
    setAnalysisVisible(enabled) {
      analysisVisible = enabled;
      setAnalysisVisibility();
    },
    setRegionalAnomalies(items) {
      map.getSource("regional-anomalies")?.setData({
        type: "FeatureCollection",
        features: (items || []).map((item) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [item.longitude, item.latitude],
          },
          properties: {
            recent_count: item.recent_count,
            previous_count: item.previous_count,
            baseline_count: item.baseline_count,
            basis: item.basis,
          },
        })),
      });
      setAnalysisVisibility();
    },
    setCrossCategory(items) {
      crossCategoryData = items || [];
      map.getSource("cross-category")?.setData({
        type: "FeatureCollection",
        features: crossCategoryData.map((item) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: countryCenter(item.country),
          },
          properties: {
            code: item.country,
            category_count: item.category_count,
            categories: item.categories,
            basis: item.basis,
          },
        })),
      });
      setAnalysisVisibility();
    },
    setNewsNetwork(network, enabled) {
      newsNetwork = network;
      newsVisible = enabled;
      newsData = networkFeatures(network);
      publisherData = {
        type: "FeatureCollection",
        features: (network?.nodes || [])
          .filter((node) => node.publishers.length)
          .map((node) => ({
            type: "Feature",
            geometry: { type: "Point", coordinates: node.coordinates },
            properties: {
              country: node.name,
              publishers: node.publishers.join(", "),
            },
          })),
      };
      map.getSource("news-network")?.setData(newsData);
      map.getSource("publishers")?.setData(publisherData);
      visibility();
      startPulses();
    },
    setCyberNetwork(network, enabled) {
      cyberNetwork = network;
      cyberVisible = enabled;
      cyberData = networkFeatures(network);
      map.getSource("cyber-network")?.setData(cyberData);
      visibility();
      startPulses();
    },
    setMilitaryNetwork(network, enabled) {
      militaryNetwork = network;
      militaryVisible = enabled;
      militaryData = networkFeatures(network);
      militaryPlaces = {
        type: "FeatureCollection",
        features: (network?.nodes || [])
          .filter((n) => n.count > 0)
          .map((n) => ({
            type: "Feature",
            geometry: { type: "Point", coordinates: n.coordinates },
            properties: { name: n.name, code: n.id, count: n.count },
          })),
      };
      map.getSource("military-places")?.setData(militaryPlaces);
      map.getSource("military-network")?.setData(militaryData);
      visibility();
      startPulses();
    },
    setSocialNetwork(network, enabled) {
      socialNetwork = network;
      socialVisible = enabled;
      socialData = networkFeatures(network);
      map.getSource("social-network")?.setData(socialData);
      visibility();
      startPulses();
    },
    selectCountry(code, fly = false) {
      selected = code;
      for (const layer of ["country-selected", "country-selected-line"])
        if (map.getLayer(layer))
          map.setFilter(layer, ["==", ["get", "code"], code]);
      const feature = world.features.find(
        (feature) => feature.properties.code === code,
      );
      if (fly && feature)
        map.jumpTo({ center: feature.properties.center, zoom: 3 });
    },
    locate(event) {
      if (event.latitude !== null)
        map.jumpTo({
          center: [event.longitude, event.latitude],
          zoom: event.location_precision === "regional" ? 3 : 5,
        });
    },
    setTheme(value) {
      light = value;
      theme();
    },
    setDensity(value) {
      density = value;
      visibility();
    },
    setDensityWeighted(value) {
      densityWeighted = value;
      visibility();
    },
    reset: resetWorld,
    bounds() {
      const bounds = map.getBounds();
      const normalize = (value) => ((((value + 180) % 360) + 360) % 360) - 180;
      return [
        bounds.getEast() - bounds.getWest() >= 360
          ? -180
          : normalize(bounds.getWest()),
        Math.max(-90, bounds.getSouth()),
        bounds.getEast() - bounds.getWest() >= 360
          ? 180
          : normalize(bounds.getEast()),
        Math.min(90, bounds.getNorth()),
      ];
    },
  };
}
