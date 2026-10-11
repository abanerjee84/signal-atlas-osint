// OpenSky documents state vector index 17 as a weight and role classification,
// not the ICAO ADS-B emitter category. 0-3 cover light to small airframes,
// 4-6 large to heavy, 7-15 performance and role, 16-17 surface vehicles and
// 18-20 obstacles. Values are the provider's own; treat them as reported.
const AIRCRAFT_CLASS_LABELS = {
  0: "No information at all",
  1: "No ADS-B emitter category",
  2: "Light · under 15,500 lb",
  3: "Small · 15,500 to 75,000 lb",
  4: "Large · 75,000 to 300,000 lb",
  5: "High vortex large · such as B-757",
  6: "Heavy · over 300,000 lb",
  7: "High performance · over 5 g and 400 kt",
  8: "Rotorcraft",
  9: "Glider or sailplane",
  10: "Lighter-than-air",
  11: "Parachutist or skydiver",
  12: "Ultralight, hang-glider or paraglider",
  13: "Reserved by the provider",
  14: "Unmanned aerial vehicle",
  15: "Space or trans-atmospheric vehicle",
  16: "Surface vehicle · emergency",
  17: "Surface vehicle · service",
  18: "Point obstacle",
  19: "Cluster obstacle",
  20: "Line obstacle",
};
export const AIRCRAFT_FILTERS = [
  ["military", "Military · database flag"],
  ["all", "All classes"],
  ...Object.entries(AIRCRAFT_CLASS_LABELS).map(([value, label]) => [
    value,
    `Class ${value} · ${label}`,
  ]),
];
// ICAO type designators do not form a clean rotorcraft namespace, so this is a
// deliberately conservative prefix list rather than a complete one; a
// helicopter without a resolved type code keeps the fixed-wing glyph.
const ROTORCRAFT_TYPE_PREFIXES = [
  "A1",
  "AS",
  "AW1",
  "B4",
  "BK",
  "CH",
  "EC",
  "EH",
  "MD5",
  "MD9",
  "MI",
  "R4",
  "S7",
  "S8",
  "S9",
  "SA",
  "UH",
];
export function isRotorcraft(event, details) {
  // Class 8 is the provider's own Rotorcraft value; it is reported rarely, so
  // the registry type code carries most of the identification.
  if (event.aircraft_category === 8) return true;
  const type = String(details?.type_code || "").toUpperCase();
  return ROTORCRAFT_TYPE_PREFIXES.some((prefix) => type.startsWith(prefix));
}
export function matchesAircraftFilter(event, selection = "all", registry = {}) {
  if (event.category !== "aviation") return true;
  if (selection === "all") return true;
  if (selection === "military") {
    const hex = String(event.aircraft?.icao24 || "").toLowerCase();
    const entry = registry[hex];
    return (
      event.aircraft?.military === true ||
      (entry?.icao24 === hex && entry.military === true)
    );
  }
  return event.aircraft_category === Number(selection);
}
export function filterLiveAircraft(items, filters) {
  return items.filter((event) => {
    if (!eligibleAircraft(event, "all")) return false;
    if (filters.country && event.country_code !== filters.country) return false;
    if (
      filters.q &&
      !`${event.title} ${event.description}`
        .toLowerCase()
        .includes(filters.q.toLowerCase())
    )
      return false;
    const field = {
      event: "time_key",
      published: "published_at",
      ingested: "ingested_at",
    }[filters.time_basis || "event"];
    if (
      (filters.start && Date.parse(event[field]) < Date.parse(filters.start)) ||
      (filters.end && Date.parse(event[field]) > Date.parse(filters.end))
    )
      return false;
    if (filters.bbox) {
      const [w, s, e, n] = filters.bbox;
      if (
        event.latitude < s ||
        event.latitude > n ||
        !(w <= e
          ? event.longitude >= w && event.longitude <= e
          : event.longitude >= w || event.longitude <= e)
      )
        return false;
    }
    return true;
  });
}
// A reported position and ground track qualify; class selection is independent.
export function eligibleAircraft(event, selection = "all") {
  return (
    event.category === "aviation" &&
    matchesAircraftFilter(event, selection) &&
    Number.isFinite(event.aircraft_track_deg) &&
    event.aircraft_track_deg >= 0 &&
    event.aircraft_track_deg < 360 &&
    Number.isFinite(event.latitude) &&
    Number.isFinite(event.longitude)
  );
}

// One aircraft is one transponder, not one observation; repeated positions for
// the same airframe must not become several aircraft.
export function aircraftTransponderId(event) {
  return event.tags?.includes("ads-b")
    ? event.tags[event.tags.indexOf("ads-b") + 1] || event.event_id
    : event.event_id;
}
export function latestAircraft(events) {
  const latest = new Map();
  for (const event of events.filter((event) =>
    eligibleAircraft(event, "all"),
  )) {
    const identifier = aircraftTransponderId(event);
    const previous = latest.get(identifier);
    if (!previous || event.time_key > previous.time_key)
      latest.set(identifier, event);
  }
  return [...latest.values()];
}

// Retained history is coarse by design, so a trail is a coarse breadcrumb of
// real observations rather than a smoothed path. Samples carry their time so a
// live position can be merged with them without inventing a duplicate.
export function trailSamples(events, limit = 240) {
  return events
    .filter(
      (event) =>
        eligibleAircraft(event, "all") &&
        Number.isFinite(event.longitude) &&
        Number.isFinite(event.latitude),
    )
    .sort((a, b) => (a.time_key < b.time_key ? -1 : 1))
    .slice(-limit)
    .map((event) => [event.time_key, event.longitude, event.latitude]);
}

// Live positions arrive every cycle, so the path of a watched airframe is
// built by appending each observation rather than re-reading history. Points
// carry their time so a live position can merge with history without a
// duplicate at the instant they share.
export function recordTrailPoints(store, records, limit = 240) {
  for (const record of records) {
    if (!eligibleAircraft(record, "all")) continue;
    const id = aircraftTransponderId(record);
    const points = store.get(id) || [];
    if (points.length && record.time_key <= points[points.length - 1][0])
      continue;
    points.push([record.time_key, record.longitude, record.latitude]);
    if (points.length > limit) points.splice(0, points.length - limit);
    store.set(id, points);
  }
  return store;
}

// One ordered path from history and live positions, with the same instant kept
// once. Two samples are the shortest line worth drawing.
export function trailLine(...groups) {
  const seen = new Set();
  return groups
    .flat()
    .filter((sample) => {
      if (seen.has(sample[0])) return false;
      seen.add(sample[0]);
      return true;
    })
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map((sample) => [sample[1], sample[2]]);
}

export function aircraftFacts(event) {
  const data = event.aircraft || {};
  // Older retained observations predate the richer metadata. Their original
  // description contains reported values; never infer airports from a callsign.
  const altitude =
    data.barometric_altitude_m ?? numericDescription(event, "altitude", "m");
  const speed = data.speed_mps ?? numericDescription(event, "velocity", "m/s");
  const registration =
    data.registration_country ||
    event.description?.match(/registration country ([^;]+);/)?.[1] ||
    "Unknown";
  const fields = {
    "Registration country": registration,
    "Barometric altitude": Number.isFinite(altitude)
      ? `${Math.round(altitude * 3.28084).toLocaleString()} ft · ${Math.round(altitude).toLocaleString()} m`
      : "Unknown",
    "Ground speed": Number.isFinite(speed)
      ? `${Math.round(speed * 1.94384)} kt · ${Math.round(speed * 3.6)} km/h`
      : "Unknown",
    "Ground track": Number.isFinite(event.aircraft_track_deg)
      ? `${event.aircraft_track_deg.toFixed(0)}°`
      : "Unknown",
  };
  if (Number.isFinite(data.geometric_altitude_m))
    fields["Geometric altitude"] =
      `${Math.round(data.geometric_altitude_m * 3.28084).toLocaleString()} ft`;
  if (Number.isFinite(data.vertical_rate_mps))
    fields["Vertical rate"] =
      `${Math.round(data.vertical_rate_mps * 196.8504)} ft/min`;
  if (typeof data.on_ground === "boolean")
    fields.Status = data.on_ground ? "On ground" : "Airborne";
  if (data.icao24) fields.ICAO24 = data.icao24.toUpperCase();
  return fields;
}

function numericDescription(event, label, unit) {
  const value = event.description?.match(
    new RegExp(`${label} (-?[0-9.]+) ${unit}`),
  )?.[1];
  return value === undefined ? null : Number(value);
}

export function aircraftSummary(event) {
  const facts = aircraftFacts(event);
  return `${facts["Registration country"]} registration · ${facts["Barometric altitude"]} · ${facts["Ground speed"]} · Track ${facts["Ground track"]}`;
}

export function aircraftTransition(previous, current) {
  if (!previous || !current.live || previous.time_key >= current.time_key)
    return null;
  const seconds =
    (Date.parse(current.time_key) - Date.parse(previous.time_key)) / 1000;
  const longitudeDelta =
    ((current.longitude - previous.longitude + 540) % 360) - 180;
  const latitudeDelta = current.latitude - previous.latitude;
  const radians = Math.PI / 180;
  const a =
    Math.sin((latitudeDelta * radians) / 2) ** 2 +
    Math.cos(previous.latitude * radians) *
      Math.cos(current.latitude * radians) *
      Math.sin((longitudeDelta * radians) / 2) ** 2;
  const distanceKm = 6371 * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
  if (
    seconds <= 0 ||
    seconds > 600 ||
    distanceKm > (seconds / 3600) * 1400 + 5 ||
    distanceKm < 0.01
  )
    return null;
  const trackDelta =
    ((current.aircraft_track_deg - previous.aircraft_track_deg + 540) % 360) -
    180;
  return (fraction) => ({
    longitude:
      ((previous.longitude + longitudeDelta * fraction + 540) % 360) - 180,
    latitude: previous.latitude + latitudeDelta * fraction,
    aircraft_track_deg:
      (previous.aircraft_track_deg + trackDelta * fraction + 360) % 360,
  });
}

export function aircraftMotionDuration(previous, current) {
  const elapsed = Date.parse(current.time_key) - Date.parse(previous?.time_key);
  return Number.isFinite(elapsed)
    ? Math.min(30000, Math.max(8000, elapsed))
    : 8000;
}
