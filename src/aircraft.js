// Only explicit ADS-B classes and a reported ground track qualify for the map.
export function eligibleAircraft(event) {
  return (
    event.category === "aviation" &&
    [4, 5].includes(event.aircraft_category) &&
    Number.isFinite(event.aircraft_track_deg) &&
    event.aircraft_track_deg >= 0 &&
    event.aircraft_track_deg < 360 &&
    Number.isFinite(event.latitude) &&
    Number.isFinite(event.longitude)
  );
}

export function latestAircraft(events) {
  const latest = new Map();
  for (const event of events.filter(eligibleAircraft)) {
    const identifier = event.tags?.includes("ads-b")
      ? event.tags[event.tags.indexOf("ads-b") + 1] || event.event_id
      : event.event_id;
    const previous = latest.get(identifier);
    if (!previous || event.time_key > previous.time_key)
      latest.set(identifier, event);
  }
  return [...latest.values()];
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
