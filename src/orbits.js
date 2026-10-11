import {
  twoline2satrec,
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
        !item.tle1?.startsWith("1 ") ||
        !item.tle2?.startsWith("2 ")
      )
        return [];
      const record = twoline2satrec(item.tle1, item.tle2);
      return record.error ? [] : [{ ...item, record, epochTime: epoch }];
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
          latitude,
          longitude,
          altitude_km: geo.height,
          speed_kms: speed,
          epoch: orbit.epoch,
          period_minutes: orbit.period_minutes,
          source: orbit.source,
          source_url: orbit.source_url,
          time_key: time.toISOString(),
          icon: orbit.catalog_id === 25544 ? "iss" : "satellite",
        },
      ];
    } catch {
      return [];
    }
  });
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
  { country, world, q = "", bbox } = {},
) {
  const geometry = country
    ? world?.features.find((feature) => feature.properties.code === country)
        ?.geometry
    : null;
  return items.filter((item) => {
    if (
      q &&
      !`${item.name} ${item.purpose} ${item.catalog_id}`
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
    Altitude: `${item.altitude_km.toFixed(1)} km`,
    "Orbital speed": `${item.speed_kms.toFixed(2)} km/s`,
    "Orbital period": `${item.period_minutes} min`,
    "Ground position": `${item.latitude.toFixed(2)}°, ${item.longitude.toFixed(2)}°`,
    "Position time": item.time_key.slice(0, 19).replace("T", " ") + " UTC",
    "Elements epoch": item.epoch.slice(0, 19).replace("T", " ") + " UTC",
    Source: item.source,
  };
}
