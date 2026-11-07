import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { element, sourceLink } from "./api.js";
import {
  appendReportPreview,
  countryReportPreviews,
  reportHoverCard,
} from "./report-preview.js";
import { attackVectorLabel } from "./threats.js";
import {
  connectionGeometry,
  straightConnectionGeometry,
  pointAlong,
} from "./geo-lines.js";
import {
  CYBER_PALETTE,
  cyberRouteFeatures,
  routeBearing,
} from "./cyber-routes.js";
import {
  latestAircraft,
  aircraftTransition,
  aircraftSummary,
  aircraftMotionDuration,
  isRotorcraft,
} from "./aircraft.js";
import { latestVessel, vesselSummary } from "./vessels.js";
import { vesselHoverCard } from "./vessel-details.js";
import {
  colors,
  CATEGORY_NAMES,
  symbolImage,
  conflictIcon,
  conflictColor,
  referenceImage,
} from "./layer-symbols.js";
import { CONFLICT_TYPES, conflictType, conflictSummary } from "./conflicts.js";
import { disruptionCard } from "./disruptions.js";
import {
  REFERENCE_LAYER_IDS,
  REFERENCE_REGISTRY,
  referenceCard,
  referenceData,
  referencePointLayers,
} from "./reference-layers.js";
import { orbitalFacts, orbitalLabel, orbitalCountry } from "./orbits.js";
import { drawCountryFlag, countryFlagImage } from "./country-flags.js";
import {
  aircraftDetailCard,
  aircraftRegistry,
  loadAircraftDetails,
} from "./aircraft-details.js";
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
// Aircraft class selection is applied before supplying the map source.
function helicopterIcon() {
  // The glyph rotates with the reported ground track, so it must be a plan
  // view: a side or three-quarter silhouette would lie sideways for half the
  // compass. The map draws this at roughly 20-40 pixels, so it uses heavy
  // marks only. The rotor sits above the cabin, never behind it, or the shape
  // reads as a swept wing.
  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  context.translate(size / 2, size / 2);
  context.scale(2, 2);
  context.lineCap = "round";
  context.fillStyle = colors.aviation;
  context.strokeStyle = colors.aviation;
  // Four main-rotor blades over the hub: the recognisable plan view of a
  // helicopter. The nose leads, because this glyph rotates with the reported
  // ground track.
  const hub = [0, -4];
  context.lineWidth = 2.2;
  for (const angle of [45, 135, 225, 315]) {
    const radians = (angle * Math.PI) / 180;
    context.beginPath();
    context.moveTo(
      hub[0] + Math.cos(radians) * 2.6,
      hub[1] + Math.sin(radians) * 2.6,
    );
    context.lineTo(
      hub[0] + Math.cos(radians) * 10.2,
      hub[1] + Math.sin(radians) * 10.2,
    );
    context.stroke();
  }
  // Cabin, drawn over the blades so its outline separates it from the rotor.
  context.fillStyle = colors.aviation;
  context.beginPath();
  context.ellipse(0, -3, 2.8, 3.4, 0, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = "#55460a";
  context.lineWidth = 0.9;
  context.stroke();
  // Rotor hub on top of the cabin.
  context.fillStyle = colors.aviation;
  context.beginPath();
  context.arc(hub[0], hub[1], 1.7, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = "#55460a";
  context.stroke();
  // Tail boom.
  context.fillStyle = colors.aviation;
  context.beginPath();
  context.moveTo(-1.5, 0.2);
  context.lineTo(1.5, 0.2);
  context.lineTo(0.9, 8);
  context.lineTo(-0.9, 8);
  context.closePath();
  context.fill();
  // Tail rotor, a small cross on the fin.
  context.strokeStyle = colors.aviation;
  context.lineWidth = 1.5;
  context.beginPath();
  context.moveTo(-2.8, 9.2);
  context.lineTo(2.8, 9.2);
  context.moveTo(0, 6.6);
  context.lineTo(0, 11.8);
  context.stroke();
  return context.getImageData(0, 0, size, size);
}
const AIRCRAFT_ICON = [
  "case",
  ["get", "rotorcraft"],
  "aircraft-helicopter",
  "aircraft-plane",
];
function aircraftIcon() {
  // Drawn nose-up: icon-rotation-alignment "map" then points it along the track.
  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  context.translate(size / 2, size / 2);
  context.scale(2, 2);
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
function shipIcon() {
  // Drawn bow-up: icon-rotation-alignment "map" then points the hull along the
  // reported course, the same contract as the aircraft glyphs. A plan view is
  // required or the ship lies sideways for half the compass.
  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  context.translate(size / 2, size / 2);
  context.scale(2, 2);
  context.fillStyle = colors.maritime;
  context.beginPath();
  context.moveTo(0, -11);
  context.quadraticCurveTo(4.6, -7.5, 4.6, -3);
  context.lineTo(4.6, 7);
  context.quadraticCurveTo(4.6, 9.6, 2.4, 10.4);
  context.lineTo(-2.4, 10.4);
  context.quadraticCurveTo(-4.6, 9.6, -4.6, 7);
  context.lineTo(-4.6, -3);
  context.quadraticCurveTo(-4.6, -7.5, 0, -11);
  context.closePath();
  context.fill();
  context.strokeStyle = "#123a47";
  context.lineWidth = 0.9;
  context.stroke();
  // Deck line and superstructure block read as a ship at small sizes without
  // fine detail that would vanish below zoom 6.
  context.strokeStyle = "#123a47";
  context.lineWidth = 0.8;
  context.beginPath();
  context.moveTo(0, -8);
  context.lineTo(0, -4.5);
  context.stroke();
  context.fillStyle = "#123a47";
  context.fillRect(-2.6, -3.4, 5.2, 6.4);
  return context.getImageData(0, 0, size, size);
}
export const THIN_SAMPLE = 5;

// Which pictogram a reference feature gets. Shape separates the layer; within the
// military layer, colour separates naval from air facilities, which is the
// distinction an analyst actually asks about.
// Which pictogram each reference layer draws. Shape separates the layer; within
// the military layer, colour separates naval from air facilities, which is the
// distinction an analyst actually asks about.
const REFERENCE_IMAGE_NAMES = {
  military: "ref-military",
  naval: "ref-naval",
  air: "ref-air",
  nuclear: "ref-nuclear",
  spaceport: "ref-spaceport",
  port: "ref-port",
};

// Keyed by layer id rather than derived from it, so a plural layer id cannot
// silently fall through to another layer's pictogram.
const REFERENCE_ICON_BY_LAYER = {
  bases: [
    "match",
    ["get", "facility_type"],
    "naval_base",
    REFERENCE_IMAGE_NAMES.naval,
    ["air_base", "aerodrome", "airfield"],
    REFERENCE_IMAGE_NAMES.air,
    REFERENCE_IMAGE_NAMES.military,
  ],
  nuclear: REFERENCE_IMAGE_NAMES.nuclear,
  spaceports: REFERENCE_IMAGE_NAMES.spaceport,
  ports: REFERENCE_IMAGE_NAMES.port,
};

function referenceIconExpression(id) {
  return REFERENCE_ICON_BY_LAYER[id] || REFERENCE_IMAGE_NAMES.military;
}

function satelliteIcon(iss = false, color = colors.space) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 48;
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);
  ctx.translate(12, 12);
  ctx.fillStyle = iss ? "#eef0ff" : color;
  ctx.strokeStyle = "#202736";
  ctx.lineWidth = 1;
  ctx.fillRect(-3, -4, 6, 8);
  ctx.strokeRect(-3, -4, 6, 8);
  for (const side of [-1, 1]) {
    ctx.fillRect(side < 0 ? -10 : 4, -5, 6, 10);
    ctx.strokeRect(side < 0 ? -10 : 4, -5, 6, 10);
    ctx.beginPath();
    ctx.moveTo(side * 4, 0);
    ctx.lineTo(side * 10, 0);
    ctx.stroke();
  }
  if (iss) {
    ctx.fillRect(-1, -9, 2, 18);
    ctx.fillRect(-5, -1, 10, 2);
  }
  return ctx.getImageData(0, 0, 48, 48);
}
function satelliteNameImage(item) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const text = orbitalLabel(item.name).slice(0, 48);
  ctx.font = "11px Arial, sans-serif";
  const textWidth = Math.ceil(ctx.measureText(text).width);
  const width = textWidth + 8 + 22;
  canvas.width = width * 2;
  canvas.height = 36;
  ctx.scale(2, 2);
  ctx.font = "11px Arial, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#101b22";
  ctx.fillStyle = "#edf1f5";
  ctx.strokeText(text, 4, 9);
  ctx.fillText(text, 4, 9);
  drawCountryFlag(ctx, item.operator_country, textWidth + 8, 3, 18, 12);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}
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
  {
    selectEvent,
    selectCountry,
    viewportChanged,
    mapError,
    inspectRegion,
    followStopped,
  },
) {
  const map = new maplibregl.Map({
    container: "map",
    center: [0, 22],
    zoom: 0.5,
    minZoom: -3,
    maxZoom: 12,
    attributionControl: false,
    renderWorldCopies: false,
    // The default Mercator constraint zooms in until the world fills a tall
    // canvas. Allow letterboxing so both dateline edges fit on narrow screens.
    transformConstrain: (center, zoom) => ({
      center: new maplibregl.LngLat(
        Math.max(-180, Math.min(180, center.lng)),
        Math.max(-85, Math.min(85, center.lat)),
      ),
      zoom: Math.max(-3, Math.min(12, zoom)),
    }),
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
  // Debug handle for browser tests that need rendered-feature hit testing.
  window.__osintMap = map;
  let eventData = empty(),
    aircraftData = empty(),
    vesselData = empty(),
    vesselRecords = [],
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
  let selectedAircraftId = "";
  let followedAircraftId = "";
  // The events source is clustered, so below zoom 7 a selected point exists
  // only inside a cluster feature and cannot be highlighted there. The
  // selection therefore gets its own unclustered single-feature source, the
  // same reason aircraft have a source of their own. It must be built by the
  // same helper the main source uses, so the enlarged copy of the icon is
  // identical to the one the event would otherwise have drawn.
  const features = (records) => ({
    type: "FeatureCollection",
    features: records
      .filter((event) => event.latitude !== null)
      .map((event) => {
        const kind = conflictType(event);
        return {
          type: "Feature",
          id: event.event_id,
          geometry: {
            type: "Point",
            coordinates: [event.longitude, event.latitude],
          },
          properties: {
            ...event,
            marker_type: kind
              ? `conflict-${event.category}-${kind.id}`
              : event.category,
            conflict_label: kind?.label || "",
            conflict_kind: kind?.id || "",
            hover_summary: conflictSummary(event),
            hover_source: (() => {
              try {
                return new URL(event.source_url).hostname;
              } catch {
                return event.source_id;
              }
            })(),
          },
        };
      }),
  });
  function eventSelectionData(event) {
    return event && event.latitude !== null && event.longitude !== null
      ? features([event])
      : empty();
  }
  // Following reads the interpolated collection, so the camera tracks the
  // aircraft between observations instead of jumping once per report.
  function recentreFollowedAircraft() {
    if (!followedAircraftId) return;
    const feature = aircraftData.features.find(
      (item) => item.properties.event_id === followedAircraftId,
    );
    if (!feature) return;
    const [longitude, latitude] = feature.geometry.coordinates;
    const center = map.getCenter();
    // Skip the redraw while the aircraft is already comfortably in frame.
    if (
      Math.abs(center.lat - latitude) * 90 < 0.4 &&
      Math.abs(center.lng - longitude) * 90 < 0.4
    )
      return;
    map.jumpTo({ center: [longitude, latitude] });
  }
  // One aircraft would be lost among a thousand, so only the aircraft under
  // attention carries a trail. The caller owns the samples; the map only draws.
  function setTrailCoordinates(points) {
    const line = Array.isArray(points) && points.length > 1 ? points : null;
    map.getSource("aircraft-trail")?.setData(
      line
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                id: "aircraft-trail-line",
                properties: { points: line.length },
                geometry: { type: "LineString", coordinates: line },
              },
            ],
          }
        : empty(),
    );
    map.getCanvas().dataset.aircraftTrail = String(line?.length || 0);
  }
  const aircraftSelectionFilter = () => [
    "==",
    ["get", "event_id"],
    selectedAircraftId,
  ];
  const aircraftMotion = matchMedia("(prefers-reduced-motion: reduce)");
  function finishAircraftMotion() {
    cancelAnimationFrame(aircraftFrame);
    aircraftFrame = undefined;
    aircraftData = aircraftTarget;
    map.getSource("aircraft")?.setData(aircraftData);
    recentreFollowedAircraft();
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
  function updateAircraft(records) {
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
      records.map((r) => ({
        ...r,
        aircraft_summary: aircraftSummary(r),
        rotorcraft: isRotorcraft(r, aircraftRegistry()[r.aircraft?.icao24]),
      })),
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
    const duration = Math.max(
      8000,
      ...records.map((record, index) =>
        transitions[index]
          ? aircraftMotionDuration(previous.get(record.event_id), record)
          : 0,
      ),
    );
    let last = -Infinity;
    map.getCanvas().dataset.aircraftMoving = String(
      transitions.filter(Boolean).length,
    );
    function animate(now) {
      if (
        document.hidden ||
        !aircraftInView ||
        aircraftMotion.matches ||
        now - began >= duration
      ) {
        finishAircraftMotion();
        return;
      }
      if (now - last >= 70) {
        last = now;
        const fraction = Math.min(1, (now - began) / duration);
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
        recentreFollowedAircraft();
      }
      aircraftFrame = requestAnimationFrame(animate);
    }
      aircraftFrame = requestAnimationFrame(animate);
    }
    let vesselSignature = "";
    function updateVessels(records) {
      // The hover card needs the record behind the hull, so keep them even when
      // the rendered set has not moved.
      vesselRecords = records;
      const signature = JSON.stringify(
        records.map((r) => [
          r.event_id,
          r.time_key,
          r.longitude,
          r.latitude,
          r.vessel_course_deg,
        ]),
      );
      if (signature === vesselSignature) return;
      vesselSignature = signature;
      vesselData = features(
        records.map((r) => ({ ...r, vessel_summary: vesselSummary(r) })),
      );
      map.getSource("vessels")?.setData(vesselData);
    }
    let newsData = empty(),
    threatData = empty(),
    threatNetwork = null,
    threatVisible = false,
    cyberData = empty(),
    cyberNetwork = null,
    cyberVisible = false,
    socialData = empty(),
    publisherData = empty(),
    newsVisible = false,
    socialVisible = false;
  let militaryPlaces = empty();
  let militaryReports = [],
    previewEvents = [],
    reportSignature = "";
  let sentimentResult = null;
  let referenceLayers = new Set();
  const referenceLoading = new Map();
  const referenceProblems = new Map();
  const referenceCounts = new Map();
  let terminatorTimer = null;
  let disruptionsVisible = false;
  let disruptionRecords = [];
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
  // MapLibre 6 awaits this resolver; styleimagemissing is notification-only.
  map.setMissingStyleImageResolver((id) => {
    if (map.hasImage(id)) return;
    if (id.startsWith("orbit-label-")) {
      const item = orbitalData.features.find(
        (feature) => feature.properties.name_icon === id,
      )?.properties;
      if (item && !map.hasImage(id))
        map.addImage(id, satelliteNameImage(item), { pixelRatio: 2 });
      return;
    }
    const briefing = /^military-brief-(\d+|99plus)$/.exec(id);
    if (briefing) {
      map.addImage(
        id,
        symbolImage("military", {
          context: true,
          count: briefing[1] === "99plus" ? "99+" : briefing[1],
        }),
        { pixelRatio: 2 },
      );
      return;
    }
    const match = /^cluster-(\w+)-(reported|context)-(\d+|99plus)$/.exec(id);
    const [category, type] = match?.[1]?.split("_") || [];
    if (
      match &&
      ["military", "geopolitical"].includes(category) &&
      CONFLICT_TYPES.some((t) => t.id === type)
    ) {
      map.addImage(
        id,
        conflictIcon(
          type,
          conflictColor(type, category),
          match[2] === "context",
          match[3] === "99plus" ? "99+" : match[3],
          category === "military",
        ),
        { pixelRatio: 2 },
      );
      return;
    }
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
  const hoverPopup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    maxWidth: "360px",
    className: "map-hover-details",
  });
  let selectedThreatRoute = null;
  let orbitalData = empty();
  let orbitalTracks = empty();
  let orbitHoverId = null;
  const orbitColor = [
    "match",
    ["get", "role"],
    "military",
    "#e5b06a",
    "navigation",
    "#8dc7da",
    "#c6bcff",
  ];
  let worldView = true;
  const resetWorld = () => {
    worldView = true;
    popup.remove();
    hoverPopup.remove();
    map.fitBounds(
      [
        [-179.9, -57],
        [179.9, 74],
      ],
      { padding: { top: 12, bottom: 24, left: 12, right: 44 }, duration: 0 },
    );
    // Preserve the horizontal world extent and anchor Cape Horn above the
    // lower canvas edge, instead of leaving a large southern letterbox.
    const bottomGap =
      map.getCanvas().clientHeight - 18 - map.project([-67.3, -55.98]).y;
    if (bottomGap > 0) map.panBy([0, -bottomGap], { duration: 0 });
  };
  for (const type of ["dragstart", "zoomstart", "rotatestart", "pitchstart"])
    map.on(type, (event) => {
      if (!event.originalEvent) return;
      worldView = false;
      // Panning away is how a viewer says they have seen enough of the
      // aircraft; programmatic moves carry no originalEvent and are exempt.
      if (followedAircraftId) {
        followedAircraftId = "";
        map.getCanvas().dataset.followedAircraft = "";
        followStopped?.();
      }
    });

  // Give the canvas the actual unobscured rectangle. Resizing a sidebar must
  // refit a world overview, but must not reset a country, route or manual view.
  const workspace = document.querySelector(".map-workspace");
  const toolbar = document.querySelector(".map-toolbar");
  const ribbon = document.querySelector("#country-ribbon");
  let layoutFrame;
  const updateLayout = () => {
    cancelAnimationFrame(layoutFrame);
    layoutFrame = requestAnimationFrame(() => {
      workspace.style.setProperty(
        "--map-toolbar-height",
        `${toolbar.offsetHeight}px`,
      );
      const left = Math.min(
        ribbon.offsetLeft + ribbon.offsetWidth + 8,
        workspace.clientWidth - 120,
      );
      workspace.style.setProperty(
        "--map-ribbon-width",
        `${Math.max(0, left)}px`,
      );
      map.resize();
      if (worldView) resetWorld();
    });
  };
  const resize = new ResizeObserver(updateLayout);
  for (const item of [workspace, toolbar, ribbon]) resize.observe(item);
  map.on("remove", () => {
    resize.disconnect();
    cancelAnimationFrame(layoutFrame);
  });
  const menus = [...toolbar.querySelectorAll("details")];
  for (const menu of menus) {
    menu.addEventListener("toggle", () => {
      if (menu.open)
        for (const other of menus) if (other !== menu) other.open = false;
    });
    menu.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        menu.open = false;
        menu.querySelector("summary").focus();
      }
    });
  }

  // Weight by evidence strength, not just volume. A single unverified report
  // should not heat a cell like corroborated reporting.
  const confidenceWeight = (name, fallback) => {
    const layer = map.getLayer(name);
    if (layer) map.setPaintProperty(name, "heatmap-weight", fallback);
  };
  function setDisruptions(records) {
    // Records can arrive before the style has finished loading, so they are kept
    // here and pushed to the source again once it exists rather than dropped.
    disruptionRecords = records || [];
    map.getSource("disruptions")?.setData({
      type: "FeatureCollection",
      features: disruptionRecords,
    });
    setDisruptionsVisible(disruptionsVisible);
  }

  function setDisruptionsVisible(visible) {
    disruptionsVisible = Boolean(visible);
    for (const id of ["disruptions-halo", "disruptions-point"])
      if (map.getLayer(id))
        map.setLayoutProperty(
          id,
          "visibility",
          disruptionsVisible ? "visible" : "none",
        );
  }

  function referenceVisibility() {
    const terminatorOn = referenceLayers.has("terminator");
    for (const id of ["reference-night", "reference-boundary"])
      if (map.getLayer(id))
        map.setLayoutProperty(
          id,
          "visibility",
          terminatorOn ? "visible" : "none",
        );
    for (const id of REFERENCE_LAYER_IDS) {
      if (REFERENCE_REGISTRY[id].computed) continue;
      const on = referenceLayers.has(id);
      for (const suffix of ["-halo", "-point"]) {
        const layerId = `reference-${id}${suffix}`;
        if (map.getLayer(layerId))
          map.setLayoutProperty(layerId, "visibility", on ? "visible" : "none");
      }
    }
  }

  function setTerminator(date) {
    const collection = referenceData("terminator", date);
    map.getSource("reference-night")?.setData(collection);
    map.getSource("reference-boundary")?.setData(collection);
  }

  async function loadReference(id) {
    if (referenceLoading.has(id)) return referenceLoading.get(id);
    const entry = REFERENCE_REGISTRY[id];
    if (!entry?.file) return null;
    const pending = fetch(entry.file, { cache: "no-cache" })
      .then((response) => {
        if (!response.ok)
          throw new Error(
            `Reference registry unavailable (HTTP ${response.status})`,
          );
        return response.json();
      })
      .then((data) => {
        // FR-LY-02: geometry that does not declare the registry version this build
        // expects is not drawn, rather than shown as current.
        const declared = data?.metadata?.registry_version;
        if (declared !== entry.registry.version) {
          referenceProblems.set(
            id,
            `Registry version mismatch: expected ${entry.registry.version}, file declares ${declared ?? "none"}`,
          );
          map.getSource(`reference-${id}`)?.setData(empty());
          return null;
        }
        referenceProblems.delete(id);
        referenceCounts.set(
          id,
          Array.isArray(data.features) ? data.features.length : 0,
        );
        map.getSource(`reference-${id}`)?.setData(data);
        return data;
      })
      .catch((error) => {
        referenceProblems.set(id, String(error.message || error));
        referenceCounts.set(id, 0);
        map.getSource(`reference-${id}`)?.setData(empty());
        return null;
      });
    referenceLoading.set(id, pending);
    return pending;
  }

  function referenceStatus() {
    return REFERENCE_LAYER_IDS.map((id) => {
      const entry = REFERENCE_REGISTRY[id];
      const problem = referenceProblems.get(id);
      let state;
      if (problem) state = "unavailable";
      else if (entry.computed)
        state = referenceLayers.has(id) ? "available" : "off";
      else if (referenceLoading.has(id)) state = "available";
      else state = "not_loaded";
      return {
        id,
        label: entry.label,
        enabled: referenceLayers.has(id),
        registry_version: entry.registry.version,
        license: entry.registry.license,
        state,
        problem: problem || null,
      };
    });
  }

  function visibility() {
    document.querySelector("#cyber-map-legend").hidden = !threatVisible;
    if (!threatVisible) hoverPopup.remove();
    if (!map.getLayer("event-density")) return;
    setAnalysisVisibility();
    for (const id of [
      "threat-directions",
      "threat-endpoints",
      "threat-selected",
      "threat-flow-arrows",
    ])
      if (map.getLayer(id))
        map.setLayoutProperty(
          id,
          "visibility",
          threatVisible ? "visible" : "none",
        );
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
        newsVisible ||
          militaryVisible ||
          socialVisible ||
          cyberVisible ||
          threatVisible
          ? "visible"
          : "none",
      );
    if (map.getLayer("threat-connections"))
      map.setLayoutProperty(
        "threat-connections",
        "visibility",
        threatVisible ? "visible" : "none",
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
    map.setPaintProperty(
      "polar-mask",
      "fill-color",
      light ? "#dee8ed" : "#101b22",
    );
  }
  map.on("load", () => {
    map.addImage("satellite", satelliteIcon(), { pixelRatio: 2 });
    map.addImage("iss", satelliteIcon(true), { pixelRatio: 2 });
    map.addImage("satellite-military", satelliteIcon(false, "#e5b06a"), {
      pixelRatio: 2,
    });
    map.addImage("satellite-navigation", satelliteIcon(false, "#8dc7da"), {
      pixelRatio: 2,
    });
    const arrowIcon = (color) => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 48;
      const context = canvas.getContext("2d");
      context.beginPath();
      context.moveTo(24, 4);
      context.lineTo(39, 38);
      context.lineTo(24, 30);
      context.lineTo(9, 38);
      context.closePath();
      context.fillStyle = color;
      context.fill();
      context.strokeStyle = "#101b22";
      context.lineWidth = 3;
      context.stroke();
      return context.getImageData(0, 0, 48, 48);
    };
    map.addImage("traffic-direction", arrowIcon(CYBER_PALETTE.traffic), {
      pixelRatio: 2,
    });
    map.addImage("report-direction", arrowIcon(CYBER_PALETTE.reported), {
      pixelRatio: 2,
    });
    map.addImage(
      "threat-origin",
      symbolImage("attacker", { color: CYBER_PALETTE.origin }),
      { pixelRatio: 2 },
    );
    map.addImage(
      "threat-target",
      symbolImage("victim", { color: CYBER_PALETTE.target }),
      {
        pixelRatio: 2,
      },
    );
    for (const category of [...Object.keys(colors), "publisher"]) {
      for (const context of [false, true])
        map.addImage(
          `${category}-${context ? "context" : "reported"}`,
          symbolImage(category, { context }),
          { pixelRatio: 2 },
        );
    }
    for (const category of ["military", "geopolitical"])
      for (const type of CONFLICT_TYPES)
        for (const context of [false, true])
          map.addImage(
            `conflict-${category}-${type.id}-${context ? "context" : "reported"}`,
            conflictIcon(
              type.id,
              conflictColor(type.id, category),
              context,
              null,
              category === "military",
            ),
            { pixelRatio: 2 },
          );
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
    // Exclude polar cartography from the overview without hiding the evidence
    // routes above the basemap. The southern cutoff retains Cape Horn.
    map.addSource("polar-mask", {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: [
          [-85.051129, -57],
          [74, 85.051129],
        ].map(([south, north]) => ({
          type: "Feature",
          properties: {},
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [-180, south],
                [180, south],
                [180, north],
                [-180, north],
                [-180, south],
              ],
            ],
          },
        })),
      },
    });
    map.addLayer({
      id: "polar-mask",
      type: "fill",
      source: "polar-mask",
      paint: { "fill-color": "#101b22", "fill-antialias": false },
    });

    // Reference geometry sits directly on the basemap and beneath every evidence
    // layer, so published context can never be read as a detected event.
    map.addSource("reference-night", { type: "geojson", data: empty() });
    map.addSource("reference-boundary", { type: "geojson", data: empty() });
    map.addLayer({
      id: "reference-night",
      type: "fill",
      source: "reference-night",
      paint: { "fill-color": "#05090c", "fill-opacity": 0.55 },
    });
    map.addLayer({
      id: "reference-boundary",
      type: "line",
      source: "reference-boundary",
      paint: {
        "line-color": colors.terminator,
        "line-width": 1.1,
        "line-dasharray": [4, 3],
        "line-opacity": 0.8,
      },
    });
    for (const id of REFERENCE_LAYER_IDS) {
      if (REFERENCE_REGISTRY[id].computed) continue;
      map.addSource(`reference-${id}`, { type: "geojson", data: empty() });
      map.addLayer({
        id: `reference-${id}-halo`,
        type: "circle",
        source: `reference-${id}`,
        paint: {
          // Grown with zoom so a published coordinate stays reachable as the map
          // closes in; at world scale a 3px dot is not a usable pointer target.
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            0,
            7,
            6,
            11,
            12,
            16,
          ],
          "circle-color": colors.reference,
          "circle-opacity": 0.22,
        },
      });
      map.addLayer({
        id: `reference-${id}-point`,
        type: "circle",
        source: `reference-${id}`,
        // Below the icon threshold, where thousands of pictograms would be
        // unreadable anyway.
        maxzoom: 3,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            0,
            3.5,
            6,
            5.5,
          ],
          "circle-color": colors.reference,
          "circle-stroke-color": "#101b22",
          "circle-stroke-width": 1.1,
        },
      });
      map.addLayer({
        id: `reference-${id}-icon`,
        type: "symbol",
        source: `reference-${id}`,
        minzoom: 3,
        layout: {
          "icon-image": referenceIconExpression(id),
          "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 8, 0.78],
          // Reference points are context, not the subject of the map, so they
          // never displace each other or the evidence layers above them.
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: { "icon-opacity": 0.96 },
      });
    }
    referenceVisibility();
    // symbols, and stay hidden until the layer is switched on. Any records that
    // arrived before the style finished loading are pushed now.
    setDisruptionsVisible(false);
    map.addSource("disruptions", {
      type: "geojson",
      data: { type: "FeatureCollection", features: disruptionRecords },
    });
    map.addLayer({
      id: "disruptions-halo",
      type: "circle",
      source: "disruptions",
      paint: {
        "circle-radius": [
          "interpolate",
          ["linear"],
          ["get", "size"],
          0,
          5,
          1,
          22,
        ],
        "circle-color": "#ef8ca2",
        "circle-opacity": 0.18,
      },
    });
    map.addLayer({
      id: "disruptions-point",
      type: "circle",
      source: "disruptions",
      paint: {
        "circle-radius": [
          "interpolate",
          ["linear"],
          ["get", "size"],
          0,
          3,
          1,
          9,
        ],
        "circle-color": "#ef8ca2",
        "circle-stroke-color": "#101b22",
        "circle-stroke-width": 1.1,
        "circle-opacity": 0.9,
      },
    });
    setDisruptionsVisible(disruptionsVisible);
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
    map.moveLayer("polar-mask");
    map.addSource("events", {
      type: "geojson",
      data: eventData,
      cluster: true,
      clusterMaxZoom: 7,
      clusterRadius: 38,
      clusterProperties: {
        ...Object.fromEntries(
          CONFLICT_TYPES.map((type) => [
            `type_${type.id}`,
            ["+", ["case", ["==", ["get", "conflict_kind"], type.id], 1, 0]],
          ]),
        ),
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
    map.addSource("vessels", { type: "geojson", data: vesselData });
    map.addSource("event-selection", { type: "geojson", data: empty() });
    map.addSource("aircraft-trail", { type: "geojson", data: empty() });
    map.addSource("sentiment", { type: "geojson", data: sentimentData });
    map.addSource("military-places", { type: "geojson", data: militaryPlaces });
    map.addSource("military-network", { type: "geojson", data: militaryData });
    map.addSource("news-network", { type: "geojson", data: newsData });
    map.addSource("cyber-network", { type: "geojson", data: cyberData });
    map.addSource("threat-network", { type: "geojson", data: threatData });
    const routeFeatures = cyberRouteFeatures(threatNetwork);
    map.addSource("threat-directions", {
      type: "geojson",
      data: routeFeatures.arrows,
    });
    map.addSource("threat-endpoints", {
      type: "geojson",
      data: routeFeatures.endpoints,
    });
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
      ["threat-connections", "threat-network", true, "#ef8ca2"],
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
          "line-color":
            id === "threat-connections"
              ? [
                  "case",
                  ["==", ["get", "kind"], "observed_traffic_to_target"],
                  "#69c8e5",
                  color,
                ]
              : color,
          "line-width": [
            "interpolate",
            ["linear"],
            ["get", "count"],
            1,
            0.8,
            20,
            2.4,
          ],
          "line-opacity":
            id === "military-connections"
              ? [
                  "interpolate",
                  ["linear"],
                  ["coalesce", ["get", "count"], 1],
                  1,
                  0.08,
                  3,
                  0.18,
                  10,
                  0.38,
                  30,
                  0.6,
                ]
              : id === "threat-connections"
                ? 0.72
                : 0.38,
          ...(dotted ? { "line-dasharray": [2, 3] } : {}),
        },
      });
    }
    map.addLayer({
      id: "threat-selected",
      type: "line",
      source: "threat-network",
      filter: ["==", ["get", "id"], ""],
      paint: { "line-color": "#f9d48f", "line-width": 4, "line-opacity": 0.95 },
    });
    map.addLayer({
      id: "threat-directions",
      type: "symbol",
      source: "threat-directions",
      layout: {
        "icon-image": [
          "case",
          ["==", ["get", "kind"], "observed_traffic_to_target"],
          "traffic-direction",
          "report-direction",
        ],
        "icon-size": 0.4,
        "icon-rotate": ["get", "rotation"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
      },
    });
    map.addLayer({
      id: "threat-endpoints",
      type: "symbol",
      source: "threat-endpoints",
      layout: {
        "icon-image": [
          "case",
          ["==", ["get", "role"], "origin"],
          "threat-origin",
          "threat-target",
        ],
        "icon-offset": [
          "case",
          ["==", ["get", "role"], "origin"],
          ["literal", [-14, -14]],
          ["literal", [14, 14]],
        ],
        "icon-size": 0.5,
        "icon-allow-overlap": true,
      },
    });
    map.addLayer({
      id: "military-context",
      type: "symbol",
      source: "military-places",
      layout: {
        "icon-image": [
          "case",
          [">", ["get", "count"], 1],
          [
            "concat",
            "military-brief-",
            [
              "case",
              [">", ["get", "count"], 99],
              "99plus",
              ["to-string", ["get", "count"]],
            ],
          ],
          "military-context",
        ],
        "icon-size": ["step", ["get", "count"], 0.72, 2, 0.85, 20, 1],
        "symbol-sort-key": ["get", "count"],
        "icon-allow-overlap": true,
      },
    });
    map.addLayer({
      id: "publisher-points",
      type: "symbol",
      source: "publishers",
      layout: {
        "icon-image": "publisher-reported",
        "icon-size": 0.45,
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
    map.addLayer({
      id: "threat-flow-arrows",
      type: "symbol",
      source: "new-reports",
      filter: [
        "in",
        ["get", "kind"],
        [
          "literal",
          ["observed_traffic_to_target", "reported_attacker_to_victim"],
        ],
      ],
      layout: {
        "icon-image": [
          "case",
          ["==", ["get", "kind"], "observed_traffic_to_target"],
          "traffic-direction",
          "report-direction",
        ],
        "icon-size": 0.4,
        "icon-rotate": ["get", "rotation"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
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
            ...["military", "geopolitical"].flatMap((category) =>
              CONFLICT_TYPES.flatMap((type) => [
                [
                  "all",
                  ["==", ["get", category], ["get", "point_count"]],
                  ["==", ["get", `type_${type.id}`], ["get", "point_count"]],
                ],
                `${category}_${type.id}`,
              ]),
            ),
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
          ["coalesce", ["get", "marker_type"], ["get", "category"]],
          "-",
          [
            "case",
            ["==", ["get", "location_precision"], "regional"],
            "context",
            "reported",
          ],
        ],
        "icon-size": [
          "interpolate",
          ["linear"],
          ["zoom"],
          0,
          ["case", ["==", ["get", "category"], "military"], 0.68, 0.45],
          5,
          ["case", ["==", ["get", "category"], "military"], 0.85, 0.65],
        ],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
    });
    map.addLayer({
      id: "event-selected-halo",
      type: "circle",
      source: "event-selection",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 0, 9, 5, 18],
        "circle-stroke-width": 2.5,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-opacity": 0.95,
        "circle-color": "#ffffff",
        "circle-opacity": 0.14,
      },
    });
    map.addLayer({
      id: "event-selected",
      type: "symbol",
      source: "event-selection",
      layout: {
        // The same icon expression as event-points, so the enlarged copy matches
        // whatever marker the selected event would otherwise have drawn.
        "icon-image": [
          "concat",
          ["coalesce", ["get", "marker_type"], ["get", "category"]],
          "-",
          [
            "case",
            ["==", ["get", "location_precision"], "regional"],
            "context",
            "reported",
          ],
        ],
        "icon-size": [
          "interpolate",
          ["linear"],
          ["zoom"],
          0,
          ["case", ["==", ["get", "category"], "military"], 1.35, 1.0],
          5,
          ["case", ["==", ["get", "category"], "military"], 1.65, 1.3],
        ],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
    });
    map.addLayer({
      id: "aircraft-trail-line",
      type: "line",
      source: "aircraft-trail",
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": colors.aviation,
        "line-width": 2,
        // Retained observations are half-hourly, so the trail is evidence of
        // where the aircraft was reported, not a continuous path.
        "line-opacity": 0.75,
        "line-dasharray": [2, 1.5],
      },
    });
    map.addImage("aircraft-plane", aircraftIcon(), { pixelRatio: 2 });
    map.addImage("aircraft-helicopter", helicopterIcon(), { pixelRatio: 2 });
    map.addLayer({
      id: "aircraft-track",
      type: "symbol",
      source: "aircraft",
      filter: [
        "all",
        ["==", ["get", "category"], "aviation"],
        // Null tracks are absent observations, not a heading of north.
        [">=", ["get", "aircraft_track_deg"], 0],
      ],
      layout: {
        "icon-image": AIRCRAFT_ICON,
        "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.85, 8, 1.1],
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
    // A selected aircraft is redrawn ringed and larger. It reads from the same
    // source and matches on the event id, so it follows the interpolated
    // position between observations instead of snapping between reports.
    map.addLayer({
      id: "aircraft-selected-halo",
      type: "circle",
      source: "aircraft",
      filter: aircraftSelectionFilter(),
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 17, 8, 32],
        "circle-stroke-width": 2.5,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-opacity": 0.95,
        "circle-color": colors.aviation,
        "circle-opacity": 0.16,
      },
    });
    map.addLayer({
      id: "aircraft-selected",
      type: "symbol",
      source: "aircraft",
      filter: aircraftSelectionFilter(),
      layout: {
        "icon-image": AIRCRAFT_ICON,
        "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 1.35, 8, 1.75],
        "icon-rotate": ["get", "aircraft_track_deg"],
        "icon-rotation-alignment": "map",
        "icon-pitch-alignment": "map",
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
      paint: { "icon-opacity": 1 },
    });
    // A forgiving hit target also covers the gaps between the wings and tail.
    // It shares the symbol's filter/source, so hidden or excluded aircraft
    // cannot be selected. Resolve overlapping targets by screen distance.
    map.addLayer({
      id: "aircraft-hit-target",
      type: "circle",
      source: "aircraft",
      filter: map.getFilter("aircraft-track"),
      paint: { "circle-radius": 16, "circle-opacity": 0 },
    });
    map.addImage("vessel-ship", shipIcon(), { pixelRatio: 2 });
    map.addLayer({
      id: "vessel-track",
      type: "symbol",
      source: "vessels",
      filter: [
        "all",
        ["==", ["get", "category"], "maritime"],
        // A null course is an absent observation, not a heading of north.
        [">=", ["get", "vessel_course_deg"], 0],
      ],
      layout: {
        "icon-image": "vessel-ship",
        "icon-size": ["interpolate", ["linear"], ["zoom"], 2, 0.85, 8, 1.1],
        // Map alignment rotates the hull along the reported course, so the bow
        // points where the vessel is going at every zoom and bearing.
        "icon-rotate": ["get", "vessel_course_deg"],
        "icon-rotation-alignment": "map",
        "icon-pitch-alignment": "map",
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "icon-padding": 2,
      },
      paint: { "icon-opacity": 1 },
    });
    map.addLayer({
      id: "vessel-hit-target",
      type: "circle",
      source: "vessels",
      filter: map.getFilter("vessel-track"),
      paint: { "circle-radius": 16, "circle-opacity": 0 },
    });
    const nearestAircraft = (event) =>
      event.features.reduce((nearest, feature) => {
        const point = map.project(feature.geometry.coordinates);
        const distance = Math.hypot(
          point.x - event.point.x,
          point.y - event.point.y,
        );
        return !nearest || distance < nearest.distance
          ? { feature, distance }
          : nearest;
      }, null)?.feature;
    // A hull glyph shares its pixel with report clusters and aircraft at world
    // zoom. It is the precise thing under the pointer, so it answers and the
    // layers it overlaps stand aside rather than hijack the click or the hover.
    const vesselUnder = (point) =>
      map.queryRenderedFeatures(point, {
        layers: ["vessel-hit-target"],
      }).length > 0;
    map.on("click", "clusters", async (event) => {
      if (vesselUnder(event.point)) return;
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
    map.on("click", "event-points", (event) => {
      if (vesselUnder(event.point)) return;
      selectEvent(event.features[0].properties.event_id);
    });
    map.on("click", "aircraft-hit-target", (event) => {
      if (
        vesselUnder(event.point) ||
        map.queryRenderedFeatures(event.point, {
          layers: ["threat-endpoints", "orbital-positions"],
        }).length
      )
        return;
      const feature = nearestAircraft(event);
      if (feature) selectEvent(feature.properties.event_id);
    });
    map.on("click", "vessel-hit-target", (event) => {
      const feature = event.features.sort(
        (a, b) =>
          Math.hypot(
            map.project(a.geometry.coordinates).x - event.point.x,
            map.project(a.geometry.coordinates).y - event.point.y,
          ) -
          Math.hypot(
            map.project(b.geometry.coordinates).x - event.point.x,
            map.project(b.geometry.coordinates).y - event.point.y,
          ),
      )[0];
      if (feature) selectEvent(feature.properties.event_id);
    });
    map.addSource("orbital-positions", { type: "geojson", data: orbitalData });
    map.addSource("orbital-tracks", { type: "geojson", data: orbitalTracks });
    for (const phase of ["past", "future"])
      map.addLayer({
        id: `orbital-tracks-${phase}`,
        type: "line",
        source: "orbital-tracks",
        filter: ["==", ["get", "phase"], phase],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": orbitColor,
          "line-width": 1,
          "line-opacity": phase === "past" ? 0.12 : 0.17,
          ...(phase === "future" ? { "line-dasharray": [3, 4] } : {}),
        },
      });
    map.addLayer({
      id: "orbital-track-highlight",
      type: "line",
      source: "orbital-tracks",
      filter: ["==", ["get", "event_id"], ""],
      paint: {
        "line-color": orbitColor,
        "line-width": 1.5,
        "line-opacity": 0.5,
      },
    });
    map.addLayer({
      id: "orbital-positions",
      type: "symbol",
      source: "orbital-positions",
      layout: {
        "icon-image": ["get", "icon"],
        "icon-size": 0.72,
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
    });
    // Locally drawn name sprites avoid a remote glyph service or font download.
    // Labels can yield to each other while spacecraft icons remain visible.
    map.addLayer({
      id: "orbital-labels",
      type: "symbol",
      source: "orbital-positions",
      layout: {
        "icon-image": ["get", "name_icon"],
        "icon-size": 1,
        "icon-anchor": "top",
        "icon-offset": [0, 11],
        "icon-padding": 2,
        "icon-allow-overlap": false,
        "symbol-sort-key": ["get", "label_priority"],
      },
    });
    map.on("click", "orbital-positions", (event) =>
      selectEvent(event.features[0].properties.event_id),
    );
    map.on("mouseenter", "orbital-positions", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mousemove", "orbital-positions", (event) => {
      // A hull glyph under the pointer is the closer object, so the satellite
      // card must not replace the vessel the pointer is actually on.
      if (vesselUnder(event.point)) return;
      const item = event.features[0].properties;
      orbitHoverId = item.event_id;
      map.setFilter("orbital-track-highlight", [
        "==",
        ["get", "event_id"],
        orbitHoverId,
      ]);
      const card = element("div", "orbital-hover-card");
      const title = element("strong", "orbital-name", item.name);
      title.append(
        countryFlagImage(item.operator_country, orbitalCountry(item)),
      );
      card.append(
        title,
        element("p", "hover-summary", item.purpose),
        element("p", "hover-meta", item.operator || "Operator not specified"),
      );
      const facts = orbitalFacts(item);
      const fields = element("dl");
      for (const label of [
        "Type",
        "Country of origin",
        "NORAD catalogue",
        "Altitude",
        "Orbital speed",
        "Orbital period",
        "Inclination",
        "Element age",
        "Tracking basis",
      ])
        fields.append(
          element("dt", "", `${label}:`),
          element("dd", "", facts[label]),
        );
      card.append(
        fields,
        element("p", "hover-meta", `Source: ${item.source}`),
        element(
          "p",
          "helper",
          "Calculated orbital position · ground track, not sensor coverage",
        ),
      );
      hoverPopup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
    });
    map.on("mouseleave", "orbital-positions", () => {
      map.getCanvas().style.cursor = "";
      orbitHoverId = null;
      map.setFilter("orbital-track-highlight", ["==", ["get", "event_id"], ""]);
      hoverPopup.remove();
    });
    map.on("click", "countries-fill", (event) => {
      if (event.lngLat.lat < -57 || event.lngLat.lat > 74) return;
      if (
        map.queryRenderedFeatures(event.point, {
          layers: [
            "event-points",
            "aircraft-hit-target",
            "orbital-positions",
            "clusters",
            "publisher-points",
            "news-connections-solid",
            "news-connections-dotted",
            "social-connections",
            "military-connections",
            "cyber-connections",
            "threat-connections",
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
      "threat-connections",
    ]) {
      const showConnection = (event) => {
        const network =
          layer === "threat-connections"
            ? threatNetwork
            : layer === "cyber-connections"
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
          edge.kind === "reported_attacker_to_victim"
            ? `${edge.actor}: reported attacker country → reported victim country`
            : edge.kind === "observed_traffic_to_target"
              ? `${edge.source_id}: observed infrastructure origin → destination`
              : edge.kind === "publisher_to_country"
                ? `${edge.source_id}: publisher base → country discussed`
                : edge.kind === "declared_origin_to_mention"
                  ? "Declared country origin → country discussed"
                  : "Countries mentioned together";
        card.append(
          element(
            "strong",
            "",
            `${name(edge.from)} → ${name(edge.to)}`,
          ),
          element(
            "p",
            "",
            `${kind}. ${edge.count} ${edge.kind === "observed_traffic_to_target" ? "sampled detections" : "supporting feed reports"}. ${edge.basis || "This is context, not movement or verified interaction."}`,
          ),
        );
        if (layer === "threat-connections")
          card.append(
            element(
              "p",
              "attack-vector",
              `Vector / type: ${attackVectorLabel(edge)}`,
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
    map.on("mousemove", "military-context", (event) => {
      if (
        map.queryRenderedFeatures(event.point, {
          layers: [
            "event-points",
            "clusters",
            "aircraft-hit-target",
            "threat-endpoints",
            "orbital-positions",
          ],
        }).length
      )
        return;
      const p = event.features?.[0]?.properties;
      if (!p) return;
      const card = element("div", "event-hover-card country-hover-card");
      card.append(
        element(
          "div",
          "hover-kind",
          `${p.name} · Military reports`,
        ),
      );
      const stories = countryReportPreviews(
        p.code,
        p.name,
        militaryReports,
        previewEvents,
        militaryNetwork?.edges,
      );
      for (const report of stories) appendReportPreview(card, report);
      card.append(
        element(
          "p",
          "hover-location",
          `${p.count} reports mention this country`,
        ),
        element(
          "p",
          "hover-hint",
          "Country context · select to explore reports",
        ),
      );
      hoverPopup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "military-context", () => {
      hoverPopup.remove();
      map.getCanvas().style.cursor = "";
    });
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
    map.on("click", "threat-directions", (event) => {
      const edge = threatNetwork?.edges.find(
        (item) => item.id === event.features[0].properties.id,
      );
      if (edge) focusThreatRoute(edge, false);
    });
    for (const layer of [
      "threat-endpoints",
      "threat-directions",
      "threat-connections",
    ]) {
      map.on("mousemove", layer, (event) => {
        // A hull glyph is a concrete tracked object, so it keeps the pointer
        // even from the threat overlays below it. Those still outrank report
        // clusters and aircraft, which is why the endpoint layer is exempt from
        // the list check rather than from this one.
        if (vesselUnder(event.point)) return;
        if (
          layer !== "threat-endpoints" &&
          map.queryRenderedFeatures(event.point, {
            layers: [
              "event-points",
              "clusters",
              "aircraft-hit-target",
              "military-context",
              "orbital-positions",
            ],
          }).length
        )
          return;
        const p = event.features?.[0]?.properties;
        if (!p) return;
        const name = (code) =>
          world.features.find((f) => f.properties.code === code)?.properties
            .name || code;
        const edges =
          layer === "threat-endpoints"
            ? (threatNetwork?.edges || []).filter(
                (e) => (p.role === "origin" ? e.from : e.to) === p.country,
              )
            : (threatNetwork?.edges || []).filter((e) => e.id === p.id);
        const card = element("div", "connection-popup");
        card.append(
          element(
            "strong",
            "",
            layer === "threat-endpoints"
              ? `${p.role === "origin" ? "A · Origin" : "V · Target"}: ${name(p.country)}`
              : `${name(edges[0]?.from)} → ${name(edges[0]?.to)}`,
          ),
        );
        for (const edge of edges.slice(0, 3)) {
          card.append(
            element(
              "p",
              "",
              `${name(edge.from)} → ${name(edge.to)} · ${edge.count} observations / reports`,
            ),
            element("p", "helper", edge.titles[0]),
            element(
              "p",
              "attack-vector",
              `Vector / type: ${attackVectorLabel(edge)}`,
            ),
          );
          if (edge.reporting_period)
            card.append(
              element(
                "p",
                "helper",
                `${edge.reporting_period} · ${edge.request_count.toLocaleString()} provider requests (daily aggregate)`,
              ),
            );
          if (edge.last_seen)
            card.append(
              element(
                "p",
                "helper",
                `Evidence last seen ${new Date(edge.last_seen).toLocaleString()}`,
              ),
            );
        }
        card.append(
          element(
            "p",
            "helper",
            "Country-level evidence. Hover previews; click opens source evidence. Traffic origin does not identify an actor.",
          ),
        );
        hoverPopup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        hoverPopup.remove();
        map.getCanvas().style.cursor = "";
      });
    }
    map.on("click", "threat-endpoints", (event) => {
      const properties = event.features[0].properties;
      const place = world.features.find(
        (item) => item.properties.code === properties.country,
      )?.properties;
      const card = element("div", "connection-popup");
      card.append(
        element(
          "strong",
          "",
          `${properties.role === "origin" ? "A · Attacker / IP origin" : "V · Victim / target"}: ${place?.name || properties.country}`,
        ),
        element(
          "p",
          "",
          `${properties.count} observations / reports. Country refers to provider traffic geography or reported attribution; it does not prove actor nationality or compromise.`,
        ),
      );
      const related = (threatNetwork?.edges || []).filter((edge) =>
        properties.role === "origin"
          ? edge.from === properties.country
          : edge.to === properties.country,
      );
      for (const edge of related.slice(0, 3))
        card.append(
          element(
            "p",
            "attack-vector",
            `${edge.from} → ${edge.to} · Vector / type: ${attackVectorLabel(edge)}`,
          ),
        );
      const button = element("button", "", "Open source details");
      button.addEventListener("click", () => selectEvent(properties.event_id));
      card.append(button);
      popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
    });
    map.on("click", "regional-anomalies", (event) => {
      const feature = event.features[0];
      const card = element("div", "");
      card.append(
        element("strong", "", "Regional reporting surge"),
        element(
          "p",
          "",
          `${feature.properties.recent_count} records in the last 6h, against ${feature.properties.previous_count} in the prior 6h and ${feature.properties.baseline_count} in the prior 72h.`,
        ),
        element("p", "helper", feature.properties.basis),
      );
      const inspect = element("button", "", "Inspect reports in area");
      inspect.addEventListener("click", () =>
        inspectRegion?.({
          ...feature.properties,
          longitude: feature.geometry.coordinates[0],
          latitude: feature.geometry.coordinates[1],
        }),
      );
      card.append(inspect);
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
      const inspect = element("button", "", "Inspect country reports");
      inspect.addEventListener("click", () =>
        selectCountry(entry.country, true),
      );
      card.append(inspect);
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
    let eventHoverKey = null;
    for (const layer of [
      "clusters",
      "event-points",
      "vessel-hit-target",
      "aircraft-hit-target",
    ]) {
      map.on("mousemove", layer, async (event) => {
        // Country endpoints can share a position with a report cluster. Keep
        // their attacker/target evidence visible instead of replacing it with
        // an asynchronously loaded cluster preview. A hull is exempt because
        // these overlays already stand aside for it.
        if (
          layer !== "vessel-hit-target" &&
          map.queryRenderedFeatures(event.point, {
            layers: ["threat-endpoints", "orbital-positions"],
          }).length
        ) {
          eventHoverKey = null;
          return;
        }
        // One hull answers for the vessel, so a cluster preview or an aircraft
        // card must not replace the vessel the pointer is actually on.
        if (layer !== "vessel-hit-target" && vesselUnder(event.point)) {
          eventHoverKey = null;
          return;
        }
        map.getCanvas().style.cursor = "pointer";
        const feature =
          layer === "aircraft-hit-target"
            ? nearestAircraft(event)
            : event.features[0];
        if (!feature) return;
        const hoverKey = `${layer}-${feature.properties.cluster_id ?? feature.properties.event_id}`;
        if (eventHoverKey === hoverKey) return;
        eventHoverKey = hoverKey;
        let card;
        if (layer === "vessel-hit-target") {
          const record = vesselRecords.find(
            (item) => item.event_id === feature.properties.event_id,
          );
          if (!record) return;
          hoverPopup
            .setLngLat(feature.geometry.coordinates)
            .setDOMContent(vesselHoverCard(record))
            .addTo(map);
          const details = await loadVesselDetails(record);
          if (eventHoverKey !== hoverKey) return;
          hoverPopup.setDOMContent(vesselHoverCard(record, false, details));
          return;
        }
        if (layer === "aircraft-hit-target") {
          const record = aircraftRecords.find(
            (item) => item.event_id === feature.properties.event_id,
          );
          if (!record) return;
          card = aircraftDetailCard(record, null);
          hoverPopup
            .setLngLat(feature.geometry.coordinates)
            .setDOMContent(card)
            .addTo(map);
          const details = await loadAircraftDetails(record);
          if (eventHoverKey !== hoverKey) return;
          card = aircraftDetailCard(record, details);
        } else if (!feature.properties.point_count) {
          card = reportHoverCard(feature.properties);
        } else {
          card = element("div", "event-hover-card");
          card.append(
            element(
              "div",
              "hover-kind",
              feature.properties.infrastructure ===
                feature.properties.point_count
                ? `${feature.properties.point_count} infrastructure observations nearby`
                : `${feature.properties.point_count} reports nearby`,
            ),
          );
          try {
            const leaves = await map
              .getSource("events")
              .getClusterLeaves(feature.properties.cluster_id, 2, 0);
            if (eventHoverKey !== hoverKey) return;
            for (const leaf of leaves)
              appendReportPreview(card, leaf.properties);
          } catch {
            if (eventHoverKey !== hoverKey) return;
            card.append(
              element(
                "p",
                "hover-summary",
                "These reports are updating. Select the cluster to explore.",
              ),
            );
          }
          card.append(
            element("p", "hover-hint", "Select to expand these reports"),
          );
          if (feature.properties.infrastructure > 0)
            card.append(
              element(
                "p",
                "hover-location",
                "Illustrative IP infrastructure country centres; not actor or victim attribution",
              ),
            );
        }
        hoverPopup
          .setLngLat(feature.geometry.coordinates)
          .setDOMContent(card)
          .addTo(map);
        // Keep the photo and flight facts inside the visible map, including
        // aircraft near its bottom edge. The popup tip is hidden when shifted.
        const popupElement = hoverPopup.getElement();
        popupElement.style.translate = "";
        popupElement.classList.remove("aircraft-hover-shifted");
        if (layer === "aircraft-hit-target") {
          const bounds = map.getContainer().getBoundingClientRect();
          const rect = popupElement.getBoundingClientRect();
          const dx =
            Math.max(0, bounds.left + 8 - rect.left) -
            Math.max(0, rect.right - bounds.right + 8);
          const dy =
            Math.max(0, bounds.top + 8 - rect.top) -
            Math.max(0, rect.bottom - bounds.bottom + 8);
          popupElement.style.translate = `${dx}px ${dy}px`;
          popupElement.classList.toggle(
            "aircraft-hover-shifted",
            Boolean(dx || dy),
          );
        }
      });
      map.on("mouseleave", layer, () => {
        eventHoverKey = null;
        map.getCanvas().style.cursor = "";
        hoverPopup.remove();
      });
    }
    theme();
    visibility();
    resetWorld();
    map.on("click", "disruptions-point", (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      event.originalEvent?.stopPropagation?.();
      hoverPopup
        .setLngLat(feature.geometry.coordinates)
        .setDOMContent(
          disruptionCard(feature.properties, (url) =>
            sourceLink(url, "Open the provider's original record"),
          ),
        )
        .addTo(map);
    });
    map.on("mouseenter", "disruptions-point", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mousemove", "disruptions-point", (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      if (vesselUnder(event.point)) return;
      const key = `disruption:${feature.properties.id}`;
      if (eventHoverKey === key) return;
      eventHoverKey = key;
      hoverPopup
        .setLngLat(event.lngLat)
        .setDOMContent(
          disruptionCard(feature.properties, (url) =>
            sourceLink(url, "Open the provider's original record"),
          ),
        )
        .addTo(map);
    });
    map.on("mouseleave", "disruptions-point", () => {
      map.getCanvas().style.cursor = "";
      eventHoverKey = null;
      hoverPopup.remove();
    });
    // Reference pictograms are registered before the map is declared ready, so a
    // symbol layer never points at an image the style does not hold.
    for (const [kind, name] of Object.entries(REFERENCE_IMAGE_NAMES))
      if (!map.hasImage(name))
        map.addImage(name, referenceImage(kind), { pixelRatio: 2 });
    // Reference points answer a hover the same way recorded events do, so a
    // published coordinate is never a mystery dot on the map.
    for (const id of referencePointLayers()) {
      // The dot answers below zoom 3 and the pictogram above it.
      for (const suffix of ["-point", "-icon"]) {
        const layerId = `reference-${id}${suffix}`;
        const show = (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          // A vessel under the pointer is a live tracked position and keeps it,
          // so a moored port marker never hides the ship beside it.
          if (vesselUnder(event.point)) return;
          const key = `${id}:${feature.properties.name}`;
          if (eventHoverKey === key) return;
          eventHoverKey = key;
          hoverPopup
            .setLngLat(event.lngLat)
            .setDOMContent(
              referenceCard(id, feature.properties, (url) =>
                sourceLink(url, "Open the registry's licence terms"),
              ),
            )
            .addTo(map);
        };
        // Hover, not just click, so a reference point reads the same way a
        // recorded event does when the pointer passes over it.
        map.on("mousemove", layerId, show);
        map.on("click", layerId, (event) => {
          event.originalEvent?.stopPropagation?.();
          show(event);
        });
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
          eventHoverKey = null;
          hoverPopup.remove();
        });
      }
    }
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
    const sampled = map.queryRenderedFeatures({
        layers: [
          "event-points",
          "clusters",
          "aircraft-track",
          "vessel-track",
          "countries-fill",
        "military-context",
        "news-connections-solid",
        "news-connections-dotted",
        "military-connections",
        "social-connections",
        "threat-connections",
        "threat-directions",
        "threat-endpoints",
        "disruptions-point",
        ...referencePointLayers().flatMap((id) => [
          `reference-${id}-point`,
          `reference-${id}-icon`,
        ]),
      ],
    });
    const byLayer = new Map();
    for (const feature of sampled) {
      const list = byLayer.get(feature.layer.id) || [];
      list.push(feature);
      byLayer.set(feature.layer.id, list);
    }
    const samples = ({ layers }) =>
      layers.flatMap((id) => byLayer.get(id) || []);
    map.getCanvas().dataset.worldView = String(worldView);
    map.getCanvas().dataset.southTip = String(map.project([-67.3, -55.98]).y);
    map.getCanvas().dataset.worldFrame = JSON.stringify(
      [
        [-179.9, -57],
        [179.9, 74],
      ].map((point) => {
        const projected = map.project(point);
        return [projected.x, projected.y];
      }),
    );
      const observations = samples({
        layers: ["event-points", "clusters", "aircraft-track", "vessel-track"],
      }).length;
    const countries = samples({
      layers: ["countries-fill"],
    }).length;
    map.getCanvas().dataset.rendered = String(observations + countries > 0);
    map.getCanvas().dataset.observations = String(observations);
      map.getCanvas().dataset.aircraft = String(
        samples({ layers: ["aircraft-track"] }).length,
      );
      map.getCanvas().dataset.vessels = String(
        samples({ layers: ["vessel-track"] }).length,
      );
    map.getCanvas().dataset.aircraftHoverPoints = JSON.stringify(
      samples({ layers: ["aircraft-track"] })
        .slice(0, 12)
        .map((feature) => {
          const point = map.project(feature.geometry.coordinates);
          return {
            x: point.x,
            y: point.y,
            event_id: feature.properties.event_id,
          };
        }),
    );
    const symbols = samples({ layers: ["event-points"] });
    const clusters = samples({ layers: ["clusters"] });
    map.getCanvas().dataset.infrastructureHoverPoints = JSON.stringify(
      [...symbols, ...clusters]
        .filter(
          (feature) =>
            feature.properties.category === "infrastructure" ||
            feature.properties.infrastructure > 0,
        )
        .map((feature) => {
          const point = map.project(feature.geometry.coordinates);
          return { x: point.x, y: point.y, layer: feature.layer.id };
        }),
    );
    map.getCanvas().dataset.layerSymbols = String(symbols.length);
    map.getCanvas().dataset.symbolCategories = [
      ...new Set(symbols.map((feature) => feature.properties.category)),
    ]
      .sort()
      .join(",");
    map.getCanvas().dataset.conflictKinds = [
      ...new Set(
        symbols.map((f) => f.properties.conflict_kind).filter(Boolean),
      ),
    ].join(",");
    map.getCanvas().dataset.conflictHoverPoints = JSON.stringify(
      [
        ...[...symbols].sort(
          (a, b) =>
            Number(Boolean(b.properties.conflict_kind)) -
            Number(Boolean(a.properties.conflict_kind)),
        ),
        ...clusters,
        ...samples({ layers: ["military-context"] }),
      ]
        .filter(
          (f) =>
            ["military", "geopolitical"].includes(f.properties.category) ||
            f.properties.military > 0 ||
            f.layer.id === "military-context",
        )
        .slice(0, 25)
        .map((f) => {
          const p = map.project(f.geometry.coordinates);
          return {
            x: p.x,
            y: p.y,
            event_id: f.properties.event_id,
            category: f.properties.category,
            layer: f.layer.id,
            type: f.properties.conflict_kind,
          };
        }),
    );
    map.getCanvas().dataset.clusterSymbols = String(clusters.length);
    // Internet-disruption markers are drawn in their own source, so expose them
    // alongside the other instrumentation rather than only as pixels.
    const canvas = map.getCanvas();
    canvas.dataset.disruptionsLoaded = String(disruptionRecords.length);
    canvas.dataset.referenceLoaded = String(
      [...referenceCounts.values()].reduce((total, count) => total + count, 0),
    );
    // Which pictogram each layer asks for, reported from this module rather than
    // read back from MapLibre, which does not expose its parsed expressions.
    canvas.dataset.referenceIcons = JSON.stringify(
      referencePointLayers().map((id) => [id, referenceIconExpression(id)]),
    );
    canvas.dataset.referenceImages = JSON.stringify(
      Object.entries(REFERENCE_IMAGE_NAMES).map(([kind, name]) => [
        kind,
        map.hasImage(name),
      ]),
    );
    const iconDrawn = referencePointLayers().flatMap(
      (id) => byLayer.get(`reference-${id}-icon`) || [],
    ).length;
    const dotDrawn = referencePointLayers().flatMap(
      (id) => byLayer.get(`reference-${id}-point`) || [],
    ).length;
    canvas.dataset.referenceIconDrawn = String(iconDrawn);
    canvas.dataset.referenceDotDrawn = String(dotDrawn);
    // One projected reference feature well inside the canvas, so a test can hover a
    // real point that no side panel is covering.
    const projected = referencePointLayers()
      .flatMap((id) => byLayer.get(`reference-${id}-point`) || [])
      .filter((feature) => feature.geometry?.type === "Point")
      .map((feature) => map.project(feature.geometry.coordinates))
      .filter(
        (point) =>
          point.x > map.getCanvas().clientWidth * 0.2 &&
          point.x < map.getCanvas().clientWidth * 0.8 &&
          point.y > map.getCanvas().clientHeight * 0.2 &&
          point.y < map.getCanvas().clientHeight * 0.8,
      );
    if (projected.length)
      canvas.dataset.referenceHoverPoint = `${Math.round(projected[0].x)},${Math.round(projected[0].y)}`;
    canvas.dataset.disruptionsVisible = String(disruptionsVisible);
    canvas.dataset.disruptionsDrawn = disruptionsVisible
      ? String(samples({ layers: ["disruptions-point"] }).length)
      : "0";
    map.getCanvas().dataset.newsConnections = String(
      samples({
        layers: ["news-connections-solid", "news-connections-dotted"],
      }).length,
    );
    map.getCanvas().dataset.militaryConnections = String(
      samples({ layers: ["military-connections"] }).length,
    );
    map.getCanvas().dataset.socialConnections = String(
      samples({ layers: ["social-connections"] }).length,
    );
    map.getCanvas().dataset.threatConnections = String(
      samples({ layers: ["threat-connections"] }).length,
    );
    map.getCanvas().dataset.threatDirections = String(
      samples({ layers: ["threat-directions"] }).length,
    );
    const endpointFeatures = samples({
      layers: ["threat-endpoints"],
    });
    map.getCanvas().dataset.threatEndpoints = String(endpointFeatures.length);
    const hoverPoint = endpointFeatures
      .map((f) => {
        const p = map.project(f.geometry.coordinates),
          delta = f.properties.role === "origin" ? -7 : 7;
        return [p.x + delta, p.y + delta];
      })
      .find(
        ([x, y]) =>
          x > 20 &&
          y > 20 &&
          x < map.getCanvas().clientWidth - 35 &&
          y < map.getCanvas().clientHeight - 35,
      );
    map.getCanvas().dataset.threatHoverPoint = JSON.stringify(hoverPoint || []);
  };
  map.on("render", sampleCanvas);
  map.on("idle", sampleCanvas);
  map.on("error", (event) =>
    mapError(event.error?.message || "Map rendering failed"),
  );

  function networkFeatures(network, geometry = connectionGeometry) {
    return {
      type: "FeatureCollection",
      features: (network?.edges || []).map((edge) => ({
        type: "Feature",
        geometry: geometry(edge.from_coordinates, edge.to_coordinates),
        properties: {
          id: edge.id,
          kind: edge.kind,
          domestic: Boolean(edge.domestic),
          count: edge.count,
          sentiment: edge.sentiment,
        },
      })),
    };
  }
  function focusThreatRoute(edge, move = true) {
    if (move) worldView = false;
    selectedThreatRoute = edge.id;
    map.setFilter("threat-selected", ["==", ["get", "id"], edge.id]);
    const name = (code) =>
      world.features.find((item) => item.properties.code === code)?.properties
        .name || code;
    const geometry = connectionGeometry(
      edge.from_coordinates,
      edge.to_coordinates,
    );
    const card = element("div", "connection-popup");
    card.append(
      element(
        "strong",
        "",
        `${name(edge.from)} → ${name(edge.to)}`,
      ),
      element(
        "p",
        "",
        `A · Attacker / origin: ${name(edge.from)} (${edge.from})`,
      ),
      element(
        "p",
        "",
        `V · Victim / target: ${name(edge.to)} (${edge.to})`,
      ),
      element(
        "p",
        "attack-vector",
        `Vector / type: ${attackVectorLabel(edge)}`,
      ),
      element(
        "p",
        "",
        `${edge.count} ${edge.reporting_period ? "daily aggregate rows" : edge.kind === "observed_traffic_to_target" ? "sampled provider detections" : "published reports"}${edge.domestic ? " · same country" : ""}. ${edge.basis}`,
      ),
    );
    if (edge.reporting_period)
      card.append(
        element(
          "p",
          "",
          `${edge.reporting_period} · ${edge.request_count.toLocaleString()} provider requests. This is a daily aggregate.`,
        ),
      );
    const button = element("button", "", "Open source evidence");
    button.addEventListener("click", () => selectEvent(edge.event_ids[0]));
    card.append(button);
    popup.setLngLat(pointAlong(geometry, 0.5)).setDOMContent(card).addTo(map);
    if (move) {
      const points = geometry.coordinates
        .flat()
        .map(([x, y]) => [
          x + 360 * Math.round((edge.from_coordinates[0] - x) / 360),
          y,
        ]);
      map.fitBounds(
        [
          [
            Math.min(...points.map((p) => p[0])),
            Math.min(...points.map((p) => p[1])),
          ],
          [
            Math.max(...points.map((p) => p[0])),
            Math.max(...points.map((p) => p[1])),
          ],
        ],
        {
          padding: {
            left: Math.min(35, map.getContainer().clientWidth * 0.1),
            right: Math.min(50, map.getContainer().clientWidth * 0.1),
            top: Math.min(80, map.getContainer().clientHeight * 0.2),
            bottom: Math.min(50, map.getContainer().clientHeight * 0.15),
          },
          maxZoom: 4,
          duration: reducedMotion() ? 0 : 700,
        },
      );
    }
  }
  function pulseTracks() {
    const tracks = [];
    for (const [visible, data] of [
      [newsVisible, newsData],
      [cyberVisible, cyberData],
      [threatVisible, threatData],
      [militaryVisible, militaryData],
      [socialVisible, socialData],
    ])
      if (visible)
        for (const feature of data.features.filter(
          (f) => !f.properties.domestic,
        ))
          tracks.push({
            geometry: feature.geometry,
            color:
              feature.properties.kind === "observed_traffic_to_target"
                ? "#69c8e5"
                : pulseColor(feature.properties.sentiment),
            kind: feature.properties.kind,
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
    if (document.hidden || !aircraftInView) {
      clearPulses();
      return;
    }
    if (!map.getSource("new-reports")) {
      pulseFrame = requestAnimationFrame(runPulses);
      return;
    }
    const tracks = pulseTracks();
    if (reducedMotion() || !tracks.length) {
      if (pulses.length || pulseFrame) clearPulses();
      return;
    }
    if (now - lastPulsePaint < 50) {
      pulseFrame = requestAnimationFrame(runPulses);
      return;
    }
    lastPulsePaint = now;
    if (threatVisible && threatNetwork?.edges.length) {
      const arrows = cyberRouteFeatures(
        threatNetwork,
        (now % 6000) / 6000,
      ).arrows;
      map.getSource("threat-directions")?.setData(arrows);
      map.getCanvas().dataset.threatArrowPosition = JSON.stringify(
        arrows.features[0]?.geometry.coordinates || [],
      );
    }
    if (now >= nextPulseAt && pulses.length < PULSE_LIMIT) {
      const track = tracks[pulseCursor % tracks.length];
      pulseCursor = (pulseCursor + 1) % tracks.length;
      pulses.push({
        geometry: track.geometry,
        color: track.color,
        kind: track.kind,
        began: now,
      });
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
        properties: {
          color: pulse.color,
          kind: pulse.kind || "context",
          rotation: routeBearing(
            pointAlong(pulse.geometry, (now - pulse.began) / PULSE_DURATION),
            pointAlong(
              pulse.geometry,
              Math.min(1, (now - pulse.began) / PULSE_DURATION + 0.01),
            ),
          ),
        },
      })),
    });
    pulseFrame = requestAnimationFrame(runPulses);
  }

  function startPulses() {
    if (pulseFrame || reducedMotion() || document.hidden || !aircraftInView)
      return;
    pulseFrame = requestAnimationFrame(runPulses);
  }
  let lastPulsePaint = -Infinity;
  const pulseVisibilityChanged = () => {
    if (document.hidden || aircraftMotion.matches) clearPulses();
    else startPulses();
  };
  document.addEventListener("visibilitychange", pulseVisibilityChanged);
  aircraftMotion.addEventListener("change", pulseVisibilityChanged);
  const pulseObserver = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) startPulses();
    else clearPulses();
  });
  pulseObserver.observe(map.getCanvas());
  map.on("remove", () => {
    clearPulses();
    hoverPopup.remove();
    pulseObserver.disconnect();
    document.removeEventListener("visibilitychange", pulseVisibilityChanged);
    aircraftMotion.removeEventListener("change", pulseVisibilityChanged);
  });

  return {
    map,
    focusThreatRoute,
    setSelectedEvent(event) {
      // Takes the whole event, not an id: the highlight is a standalone
      // unclustered feature, so it has to be rebuilt from the record and
      // re-applied whenever the style reloads.
      const id = String(event?.event_id || "");
      map.getSource("event-selection")?.setData(eventSelectionData(event));
      map.getCanvas().dataset.selectedEvent = id;
    },
    setSelectedAircraft(eventId) {
      const next = String(eventId || "");
      if (next === selectedAircraftId) return;
      selectedAircraftId = next;
      for (const id of ["aircraft-selected-halo", "aircraft-selected"])
        if (map.getLayer(id)) map.setFilter(id, aircraftSelectionFilter());
      map.getCanvas().dataset.selectedAircraft = next;
    },
    setFollowedAircraft(eventId) {
      const next = String(eventId || "");
      if (next === followedAircraftId) return;
      followedAircraftId = next;
      map.getCanvas().dataset.followedAircraft = next;
      if (!next) return;
      const feature = aircraftData.features.find(
        (item) => item.properties.event_id === next,
      );
      if (!feature) return;
      worldView = false;
      map.easeTo({
        center: feature.geometry.coordinates,
        zoom: Math.max(map.getZoom(), 7),
        duration: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 0
          : 600,
      });
    },
    setTrailCoordinates,
    setAircraftRegistry() {
      // The registry arrives after the first positions; identity only decides
      // the glyph, so it lands on the next aircraft update.
      map.getCanvas().dataset.aircraftRegistry = String(
        Object.keys(aircraftRegistry()).length,
      );
    },
    setOrbits(items, tracks) {
      for (const item of items) {
        const id = `orbit-label-${item.catalog_id}`;
        if (map.isStyleLoaded() && !map.hasImage(id))
          map.addImage(id, satelliteNameImage(item), { pixelRatio: 2 });
      }
      orbitalData = {
        type: "FeatureCollection",
        features: items.map((item) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [item.longitude, item.latitude],
          },
          properties: {
            ...item,
            name_icon: `orbit-label-${item.catalog_id}`,
            label_priority:
              item.icon === "iss"
                ? 0
                : item.role === "military"
                  ? 1
                  : item.role === "station"
                    ? 2
                    : 3,
          },
        })),
      };
      map.getSource("orbital-positions")?.setData(orbitalData);
      const nextTracks =
        tracks || (orbitalTracks.features.length ? empty() : orbitalTracks);
      if (nextTracks !== orbitalTracks) {
        orbitalTracks = nextTracks;
        map.getSource("orbital-tracks")?.setData(orbitalTracks);
      }
      if (
        !items.some((item) => item.event_id === orbitHoverId) &&
        orbitHoverId
      ) {
        orbitHoverId = null;
        hoverPopup.remove();
        map.setFilter("orbital-track-highlight", [
          "==",
          ["get", "event_id"],
          "",
        ]);
      }
      map.getCanvas().dataset.orbitalTracks = String(
        orbitalTracks.features.length,
      );
      map.getCanvas().dataset.orbitalPositions = JSON.stringify(
        items.map((item) => ({
          id: item.event_id,
          name: item.name,
          role: item.role,
          longitude: item.longitude,
          latitude: item.latitude,
          ...(() => {
            const point = map.project([item.longitude, item.latitude]);
            return { x: point.x, y: point.y };
          })(),
        })),
      );
    },
    setEvents(events) {
      previewEvents = events;
      const reports = events.filter(
        (event) =>
          event.category !== "aviation" && event.category !== "maritime",
      );
      const signature = JSON.stringify(reports);
      const reportsChanged = signature !== reportSignature;
      if (reportsChanged) {
        reportSignature = signature;
        eventData = features(reports);
        map.getSource("events")?.setData(eventData);
      }
      updateAircraft(latestAircraft(events));
      updateVessels(latestVessel(events));
      map.getSource("density")?.setData({
        type: "FeatureCollection",
        features: [...eventData.features, ...aircraftData.features, ...vesselData.features],
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
            cell_degrees: item.cell_degrees,
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
      if (cyberNetwork === network && cyberVisible === enabled) return;
      cyberNetwork = network;
      cyberVisible = enabled;
      cyberData = networkFeatures(network);
      map.getSource("cyber-network")?.setData(cyberData);
      visibility();
      startPulses();
    },
    setThreatNetwork(network, enabled) {
      if (threatNetwork === network && threatVisible === enabled) return;
      threatNetwork = network;
      threatVisible = enabled;
      threatData = networkFeatures(network);
      map.getSource("threat-network")?.setData(threatData);
      const routeFeatures = cyberRouteFeatures(network);
      map.getSource("threat-directions")?.setData(routeFeatures.arrows);
      map.getSource("threat-endpoints")?.setData(routeFeatures.endpoints);
      if (
        selectedThreatRoute &&
        !network?.edges.some((edge) => edge.id === selectedThreatRoute)
      ) {
        selectedThreatRoute = null;
        map.setFilter("threat-selected", ["==", ["get", "id"], ""]);
        popup.remove();
      }
      visibility();
      startPulses();
    },
    setMilitaryNetwork(network, enabled, reports = []) {
      militaryNetwork = network;
      militaryReports = reports;
      militaryVisible = enabled;
      militaryData = networkFeatures(network, straightConnectionGeometry);
      map.getCanvas().dataset.militaryLinkSample = JSON.stringify(
        militaryData.features[0]?.geometry.coordinates || [],
      );
      militaryPlaces = {
        type: "FeatureCollection",
        features: (network?.nodes || [])
          .filter(
            (n) =>
              n.count > 0 &&
              countryReportPreviews(
                n.id,
                n.name,
                reports,
                previewEvents,
                network?.edges,
              ).length,
          )
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
      if (fly && feature) {
        worldView = false;
        map.jumpTo({ center: feature.properties.center, zoom: 3 });
      }
    },
    locate(event) {
      if (event.latitude !== null) {
        worldView = false;
        map.jumpTo({
          center: [event.longitude, event.latitude],
          zoom: event.location_precision === "regional" ? 3 : 5,
        });
      }
    },
    focusRegion(item) {
      worldView = false;
      const radius = (Number(item.cell_degrees) || 10) / 2;
      map.fitBounds(
        [
          [
            Math.max(-180, item.longitude - radius),
            Math.max(-80, item.latitude - radius),
          ],
          [
            Math.min(180, item.longitude + radius),
            Math.min(80, item.latitude + radius),
          ],
        ],
        { padding: 30, duration: 0 },
      );
    },
    setTheme(value) {
      light = value;
      theme();
    },
    setDisruptions(records) {
      disruptionRecords = records || [];
      map.getSource("disruptions")?.setData({
        type: "FeatureCollection",
        features: disruptionRecords,
      });
      setDisruptionsVisible(disruptionsVisible);
    },
    setDisruptionsVisible,
    disruptionCount: () => disruptionRecords.length,
    setReferenceLayers(ids) {
      referenceLayers = new Set(
        REFERENCE_LAYER_IDS.filter((id) => (ids || []).includes(id)),
      );
      referenceVisibility();
      for (const id of referenceLayers)
        if (!REFERENCE_REGISTRY[id].computed) loadReference(id);
      if (referenceLayers.has("terminator")) {
        setTerminator(new Date());
        // The terminator is the one reference layer that moves; refresh it while
        // the tab is visible so a backgrounded tab does not spin the geometry.
        if (!terminatorTimer)
          terminatorTimer = setInterval(() => {
            if (!document.hidden) setTerminator(new Date());
          }, 60000);
      } else if (terminatorTimer) {
        clearInterval(terminatorTimer);
        terminatorTimer = null;
      }
      return referenceStatus();
    },
    referenceStatus,
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
