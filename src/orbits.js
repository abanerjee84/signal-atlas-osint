import {
  twoline2satrec,
  json2satrec,
  propagate,
  gstime,
  eciToGeodetic,
  degreesLat,
  degreesLong,
} from "satellite.js";

const MAX_AGE = 14 * 86400000;
export function prepareOrbits(snapshot) {
  return (snapshot?.items || []).flatMap((item) => {
    try {
      const epoch = Date.parse(item.epoch);
      if (
        !Number.isFinite(epoch) ||
        (!item.omm &&
          (!item.tle1?.startsWith("1 ") || !item.tle2?.startsWith("2 ")))
      )
        return [];
      const record = item.omm
        ? json2satrec(item.omm)
        : twoline2satrec(item.tle1, item.tle2);
      if (record.error || !Number.isFinite(record.no) || record.no <= 0)
        return [];
      return [
        {
          ...item,
          record,
          epochTime: epoch,
          role:
            item.role ||
            ([25544, 48274].includes(item.catalog_id) ? "station" : "civil"),
          inclination_deg:
            item.inclination_deg ?? (record.inclo * 180) / Math.PI,
          eccentricity: item.eccentricity ?? record.ecco,
        },
      ];
    } catch {
      return [];
    }
  });
}

export function orbitalPositions(orbits, time = new Date()) {
  if (!Number.isFinite(time.getTime())) return [];
  const sidereal = gstime(time);
  return orbits.flatMap((orbit) => {
    if (Math.abs(time.getTime() - orbit.epochTime) > MAX_AGE) return [];
    try {
      const result = propagate(orbit.record, time);
      if (!result?.position || !result?.velocity || orbit.record.error)
        return [];
      const geo = eciToGeodetic(result.position, sidereal);
      const latitude = degreesLat(geo.latitude),
        longitude = degreesLong(geo.longitude);
      const speed = Math.hypot(
        result.velocity.x,
        result.velocity.y,
        result.velocity.z,
      );
      if (
        ![latitude, longitude, geo.height, speed].every(Number.isFinite) ||
        geo.height < 80 ||
        geo.height > 50000
      )
        return [];
      return [
        {
          event_id: `orbit-${orbit.catalog_id}`,
          category: "space",
          title: orbit.name,
          name: orbit.name,
          catalog_id: orbit.catalog_id,
          purpose: orbit.purpose,
          role: orbit.role,
          operator: orbit.operator || "Not specified",
          operator_country: orbit.operator_country || "",
          mission_url: orbit.mission_url || "",
          mission_basis: orbit.mission_basis || "Public mission description",
          element_basis: orbit.element_basis || "Public catalogue elements",
          inclination_deg: orbit.inclination_deg,
          eccentricity: orbit.eccentricity,
          latitude,
          longitude,
          altitude_km: geo.height,
          speed_kms: speed,
          epoch: orbit.epoch,
          period_minutes: orbit.period_minutes,
          source: orbit.source,
          source_url: orbit.source_url,
          time_key: time.toISOString(),
          icon:
            orbit.catalog_id === 25544
              ? "iss"
              : orbit.role === "military"
                ? "satellite-military"
                : orbit.role === "navigation"
                  ? "satellite-navigation"
                  : "satellite",
        },
      ];
    } catch {
      return [];
    }
  });
}

// Split at the dateline instead of drawing false continent-spanning chords.
export function splitGroundTrack(points) {
  const parts = [];
  let line = [];
  for (const point of points) {
    if (!point) {
      if (line.length > 1) parts.push(line);
      line = [];
      continue;
    }
    const previous = line.at(-1);
    if (previous && Math.abs(point[0] - previous[0]) > 180) {
      const boundary = previous[0] > 0 ? 180 : -180;
      const unwrapped = point[0] + (previous[0] > 0 ? 360 : -360);
      const fraction = (boundary - previous[0]) / (unwrapped - previous[0]);
      const latitude = previous[1] + fraction * (point[1] - previous[1]);
      line.push([boundary, latitude]);
      if (line.length > 1) parts.push(line);
      line = [[-boundary, latitude]];
    }
    line.push(point);
  }
  if (line.length > 1) parts.push(line);
  return parts;
}

export function orbitalTrajectories(orbits, time = new Date()) {
  if (!Number.isFinite(time.getTime()))
    return { type: "FeatureCollection", features: [] };
  const features = [];
  for (const orbit of orbits) {
    for (const [phase, first, last] of [
      ["past", -15, 0],
      ["future", 0, 90],
    ]) {
      const points = [];
      for (let minute = first; minute <= last; minute += 1.5) {
        const at = new Date(time.getTime() + minute * 60000);
        const item = orbitalPositions([orbit], at)[0];
        points.push(item ? [item.longitude, item.latitude] : null);
      }
      const coordinates = splitGroundTrack(points);
      if (coordinates.length)
        features.push({
          type: "Feature",
          properties: {
            event_id: `orbit-${orbit.catalog_id}`,
            role: orbit.role,
            phase,
          },
          geometry: { type: "MultiLineString", coordinates },
        });
    }
  }
  return { type: "FeatureCollection", features };
}

export const orbitalRole = (role) =>
  ({
    military: "Military",
    navigation: "Navigation · dual use",
    station: "Crewed station",
    civil: "Civil / science",
  })[role] || "Civil / science";

export function orbitalLabel(name) {
  return String(name)
    .replace(/^PRAETORIAN SDA[_ ]/i, "SDA ")
    .replace(/^USA \d+ \((MILSTAR-[\d ]+)\)$/i, "$1")
    .replace(/ \(USA \d+\)$/i, "")
    .replace(/ \(([A-Z])\)$/i, " $1");
}

const countryNames = new Intl.DisplayNames(["en"], { type: "region" });
export function orbitalCountry(item) {
  const code = item.operator_country;
  if (code === "INT") return "International collaboration";
  if (!/^[A-Z]{2}$/.test(code || "")) return "Unknown";
  return countryNames.of(code);
}

function inRing(point, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i],
      [xj, yj] = ring[j];
    if (
      yi > point[1] !== yj > point[1] &&
      point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi
    )
      inside = !inside;
  }
  return inside;
}
export function filterOrbitalPositions(
  items,
  { country, world, q = "", bbox, scope = "all" } = {},
) {
  const geometry = country
    ? world?.features.find((feature) => feature.properties.code === country)
        ?.geometry
    : null;
  return items.filter((item) => {
    if (scope === "defence" && !["military", "station"].includes(item.role))
      return false;
    if (scope === "military" && item.role !== "military") return false;
    if (scope === "navigation" && item.role !== "navigation") return false;
    if (
      q &&
      !`${item.name} ${item.purpose} ${item.catalog_id} ${item.operator || ""} ${orbitalRole(item.role)}`
        .toLowerCase()
        .includes(q.toLowerCase())
    )
      return false;
    if (bbox) {
      const [west, south, east, north] = bbox;
      const inside =
        west <= east
          ? item.longitude >= west && item.longitude <= east
          : item.longitude >= west || item.longitude <= east;
      if (!inside || item.latitude < south || item.latitude > north)
        return false;
    }
    if (country) {
      if (!geometry) return false;
      const polygons =
        geometry.type === "Polygon"
          ? [geometry.coordinates]
          : geometry.coordinates;
      if (
        !polygons.some(
          (rings) =>
            inRing([item.longitude, item.latitude], rings[0]) &&
            !rings
              .slice(1)
              .some((ring) => inRing([item.longitude, item.latitude], ring)),
        )
      )
        return false;
    }
    return true;
  });
}

export function orbitalFacts(item) {
  return {
    "NORAD catalogue": item.catalog_id,
    Mission: item.purpose,
    Type: orbitalRole(item.role),
    Operator: item.operator || "Not specified",
    "Country of origin": orbitalCountry(item),
    Altitude: `${item.altitude_km.toFixed(1)} km`,
    "Orbital speed": `${item.speed_kms.toFixed(2)} km/s`,
    "Orbital period": `${item.period_minutes} min`,
    Inclination: `${Number(item.inclination_deg).toFixed(2)}°`,
    "Element age": (() => {
      const hours = Math.max(
        0,
        (Date.parse(item.time_key) - Date.parse(item.epoch)) / 3600000,
      );
      return hours < 24
        ? `${hours.toFixed(1)} hours`
        : `${(hours / 24).toFixed(1)} days`;
    })(),
    "Tracking basis": item.element_basis || "Public catalogue elements",
    "Ground position": `${item.latitude.toFixed(2)}°, ${item.longitude.toFixed(2)}°`,
    "Position time": item.time_key.slice(0, 19).replace("T", " ") + " UTC",
    "Elements epoch": item.epoch.slice(0, 19).replace("T", " ") + " UTC",
    Source: item.source,
  };
}
