// AIS reports one position per vessel per cycle, so repeated observations for
// the same MMSI must not become several vessels; keep only the latest of each.
export function eligibleVessel(event) {
  return (
    event.category === "maritime" &&
    Number.isFinite(event.vessel_course_deg) &&
    event.vessel_course_deg >= 0 &&
    event.vessel_course_deg < 360 &&
    Number.isFinite(event.latitude) &&
    Number.isFinite(event.longitude)
  );
}

// The connector tags every observation ["ais", "<mmsi>"]; the MMSI is the
// vessel's identity, not the stored report id.
export function vesselId(event) {
  return event.tags?.includes("ais")
    ? event.tags[event.tags.indexOf("ais") + 1] || event.event_id
    : event.event_id;
}

export function latestVessel(events) {
  const latest = new Map();
  for (const event of events.filter(eligibleVessel)) {
    const identifier = vesselId(event);
    const previous = latest.get(identifier);
    if (!previous || event.time_key > previous.time_key)
      latest.set(identifier, event);
  }
  return [...latest.values()];
}

// The AIS type code is self-reported, so the family name travels beside the
// code that produced it instead of standing in for a verified survey.
const SHIP_TYPE_RANGES = [
  [20, 29, "Wing in ground"],
  [30, 30, "Fishing"],
  [31, 31, "Towing"],
  [32, 32, "Towing (large)"],
  [33, 33, "Dredging"],
  [34, 34, "Diving"],
  [35, 39, "Military"],
  [40, 49, "High-speed craft"],
  [50, 50, "Pilot"],
  [51, 51, "Search and rescue"],
  [52, 52, "Tug"],
  [53, 53, "Port tender"],
  [54, 54, "Anti-pollution"],
  [55, 55, "Law enforcement"],
  [56, 57, "Local use"],
  [58, 58, "Medical transport"],
  [59, 59, "Noncombatant ship"],
  [60, 69, "Passenger"],
  [70, 79, "Cargo"],
  [80, 89, "Tanker"],
  [90, 99, "Other"],
];

export function vesselTypeLabel(code) {
  if (!Number.isInteger(code) || code <= 0 || code > 255) return null;
  const family = SHIP_TYPE_RANGES.find(
    ([start, end]) => code >= start && code <= end,
  );
  return `${code} · ${family ? family[2] : "Reserved"}`;
}

const countryNames = new Intl.DisplayNames(["en"], { type: "region" });
// The flag state derives from the registered MMSI prefix, which the operator
// chooses; presenting it as a name must keep it readable as registration, not
// ownership. A code with no name resolves to itself, which stays unknown.
export function vesselFlagName(flag) {
  const code = String(flag);
  if (!/^[A-Z]{2}$/.test(code)) return null;
  try {
    const name = countryNames.of(code);
    return name && name !== code ? name : null;
  } catch {
    return null;
  }
}

export function vesselFacts(event) {
  const name = String(event.title || "").replace(/^Vessel\s+/, "") || "Unknown";
  const fields = {
    Name: name === String(event.tags?.[1]) ? "Unnamed" : name,
    MMSI: event.tags?.[1] || "Unknown",
    "Flag state": vesselFlagName(event.vessel_flag) || "Unknown",
    "Vessel type": vesselTypeLabel(event.vessel_type) || "Unknown",
    "Ground speed": Number.isFinite(event.vessel_speed_kn)
      ? `${event.vessel_speed_kn.toFixed(1)} kn · ${Math.round(
          event.vessel_speed_kn * 1.852,
        )} km/h`
      : "Unknown",
    Course: Number.isFinite(event.vessel_course_deg)
      ? `${String(Math.round(event.vessel_course_deg)).padStart(3, "0")}°`
      : "Unknown",
  };
  return fields;
}

export function vesselSummary(event) {
  const facts = vesselFacts(event);
  return `${facts["Name"]} · ${facts["Flag state"]} · ${facts["Vessel type"]} · ${facts["Ground speed"]} · Course ${facts["Course"]}`;
}
