// Reference layers: versioned static asset geometry.
//
// A reference layer is not an observation. It is published geometry that changes
// only when its registry is revised, so it carries a registry version, a publisher
// and a licence classification instead of a collection timestamp. Reference
// geometry never contributes to event counts, activity measures or anomaly
// statistics, and it never renders as current without a known registry version.
//
// Nothing here fabricates a location. Every entry either points at a public
// registry file or is computed from astronomy (the terminator), and each states
// which of the two it is.

const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;

const wrap = (value) => {
  const v = ((((value + 180) % 360) + 360) % 360) - 180;
  return Object.is(v, -0) ? 0 : v;
};

// Low-precision solar position (Meeus). Accurate to a fraction of a degree, which
// is far finer than a terminator line drawn at world-map scale.
export function subsolarPoint(date) {
  const n = date.getTime() / 86400000 + 2440587.5 - 2451545.0;
  const meanLongitude = (280.46 + 0.9856474 * n) % 360;
  const anomaly = ((357.528 + 0.9856003 * n) % 360) * RAD;
  const ecliptic =
    (meanLongitude + 1.915 * Math.sin(anomaly) + 0.02 * Math.sin(2 * anomaly)) *
    RAD;
  const obliquity = (23.439 - 4e-7 * n) * RAD;
  const rightAscension =
    Math.atan2(Math.cos(obliquity) * Math.sin(ecliptic), Math.cos(ecliptic)) *
    DEG;
  const declination = Math.asin(Math.sin(obliquity) * Math.sin(ecliptic)) * DEG;
  const sidereal = (((280.46061837 + 360.98564736629 * n) % 360) + 360) % 360;
  // The subsolar meridian is the one whose local sidereal time equals the sun's.
  return { latitude: declination, longitude: wrap(rightAscension - sidereal) };
}

// Hour angle from local noon to sunset. Clamped just short of 180 so that a
// parallel in polar daylight still yields a vanishingly thin night interval
// rather than none: that keeps every strip two-sided, which in turn removes
// every special case from the strip builder. The clamp is a hundredth of a
// degree wide, which cannot be seen at map scale.
function sunsetHourAngle(latitude, sun) {
  const ratio = Math.max(
    -1,
    Math.min(1, -Math.tan(latitude * RAD) * Math.tan(sun.latitude * RAD)),
  );
  return Math.min(Math.acos(ratio) * DEG, 179.999);
}

// Move a polygon by a whole turn so it sits inside the map. Shifting the polygon
// rather than individual points is what keeps it from tearing apart.
function intoMap(ring) {
  const centre =
    ring.reduce((total, point) => total + point[0], 0) / ring.length;
  const turn = Math.round(centre / 360);
  return turn
    ? ring.map(([longitude, latitude]) => [longitude - turn * 360, latitude])
    : ring;
}

// The night region as a stack of latitude strips. At every parallel the sun is up
// between longitude-H and longitude+H, so night is the arc between the other two
// longitudes. Strips are cut wherever they cross the map's own edge, so each quad
// is at most 180 degrees wide and the output is always valid GeoJSON: no
// antimeridian case, no hole winding, no polygon spanning the globe.
export function nightStrips(date, strips = 72) {
  const sun = subsolarPoint(date);
  // The night arc on one parallel, in continuous degrees anchored on the sun.
  const arc = (latitude) => {
    const hour = sunsetHourAngle(latitude, sun);
    return [sun.longitude + hour, sun.longitude + 360 - hour];
  };
  const features = [];
  for (let index = 0; index < strips; index++) {
    const south = -90 + (180 * index) / strips;
    const north = -90 + (180 * (index + 1)) / strips;
    const [lowFrom, lowTo] = arc(south);
    const [highFrom, highTo] = arc(north);
    // One shared set of cut lines for both parallels keeps the quads in register.
    // Cuts sit on absolute multiples of 180 so each resulting piece is at most
    // half a turn wide and therefore always lands inside the map.
    const lowest = Math.min(lowFrom, highFrom);
    const highest = Math.max(lowTo, highTo);
    const lines = [lowest];
    for (let edge = Math.ceil(lowest / 180) * 180; edge < highest; edge += 180)
      lines.push(edge);
    lines.push(highest);
    for (let i = 0; i < lines.length - 1; i++) {
      const from = lines[i];
      const to = lines[i + 1];
      const lower = [Math.max(from, lowFrom), Math.min(to, lowTo)];
      const upper = [Math.max(from, highFrom), Math.min(to, highTo)];
      if (lower[1] - lower[0] <= 1e-9 || upper[1] - upper[0] <= 1e-9) continue;
      features.push({
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [
            intoMap([
              [lower[0], south],
              [lower[1], south],
              [upper[1], north],
              [upper[0], north],
            ]),
          ],
        },
      });
    }
  }
  return features;
}

// The terminator itself, one line per strip edge, cut at the same meridians.
export function terminatorLines(date, strips = 72) {
  const sun = subsolarPoint(date);
  const features = [];
  for (let index = 0; index <= strips; index++) {
    const latitude = -90 + (180 * index) / strips;
    const hour = sunsetHourAngle(latitude, sun);
    const from = sun.longitude - hour;
    const to = sun.longitude + hour;
    const lines = [from];
    for (let edge = Math.ceil(from / 180) * 180; edge < to; edge += 180)
      lines.push(edge);
    lines.push(to);
    for (let i = 0; i < lines.length - 1; i++)
      features.push({
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: intoMap([
            [lines[i], latitude],
            [lines[i + 1], latitude],
          ]),
        },
      });
  }
  return features;
}
// The registry every reference layer declares. `computed` entries derive from
// astronomy and carry no third-party licence; `file` entries are served from
// /reference and must state their own terms.
export const REFERENCE_REGISTRY = {
  terminator: {
    id: "terminator",
    label: "Day/night terminator",
    category: "terminator",
    computed: true,
    basis:
      "Subsolar point computed from the solar ephemeris; the boundary is the 90-degree solar zenith angle.",
    precision: "great-circle approximation, better than 0.5 degrees",
    registry: {
      version: "solar-ephemeris-low-precision",
      publisher: "Computed locally",
      license: "Computed output, no third-party data",
      retrieved: null,
    },
    limitation:
      "Astronomical twilight is not drawn, so the shaded band is wider than civil twilight. Carries no operational claim.",
    summary: "Computed locally · no twilight gradient",
  },
  bases: {
    id: "bases",
    label: "Military installations",
    category: "military",
    file: "/reference/military-bases.geojson",
    basis:
      "OpenStreetMap military features carrying a published name; areas reduced to the centroid OpenStreetMap publishes for them.",
    precision: "point",
    registry: {
      version: "2026-10",
      publisher: "OpenStreetMap contributors",
      license: "ODbL 1.0",
      retrieved: "2026-10-17",
      url: "https://www.openstreetmap.org/copyright",
    },
    summary: "OSM named military features",
    limitation:
      "A mapped facility is not activity, attribution or evidence that anything happened there, and coverage is uneven between countries. Disused features are included and labelled.",
  },
  nuclear: {
    id: "nuclear",
    label: "Nuclear power plants",
    category: "nuclear",
    file: "/reference/nuclear-facilities.geojson",
    basis:
      "OpenStreetMap power plants tagged as nuclear, at facility level rather than per reactor unit.",
    precision: "point",
    registry: {
      version: "2026-10",
      publisher: "OpenStreetMap contributors",
      license: "ODbL 1.0",
      retrieved: "2026-10-17",
      url: "https://www.openstreetmap.org/copyright",
    },
    summary: "OSM nuclear plants, not an irradiator list",
    limitation:
      "A crowd-mapped facility list, not a regulator inventory, covering nuclear power plants only. It is not a radiation measurement and never evidence of a release, a test or an accident.",
  },
  spaceports: {
    id: "spaceports",
    label: "Space launch facilities",
    category: "spaceport",
    file: "/reference/spaceports.geojson",
    basis: "OpenStreetMap spaceport features, reduced to published centroids.",
    precision: "point",
    registry: {
      version: "2026-10",
      publisher: "OpenStreetMap contributors",
      license: "ODbL 1.0",
      retrieved: "2026-10-17",
      url: "https://www.openstreetmap.org/copyright",
    },
    summary: "OSM spaceports",
    limitation:
      "A launch site is not a launch. No schedule, vehicle, payload, operator or readiness is implied, and the registry is crowd-sourced.",
  },
  ports: {
    id: "ports",
    label: "Ports and terminals",
    category: "port",
    file: "/reference/ports.geojson",
    basis: "Natural Earth 10m port registry; one published point per port.",
    precision: "point",
    registry: {
      version: "2026-10",
      publisher: "Natural Earth",
      license: "Public domain",
      retrieved: "2026-10-16",
      url: "https://www.naturalearthdata.com/about/terms-of-use/",
    },
    limitation:
      "A port location is not its throughput, condition or openness, and a berth's use is not inferred. Coastal points the boundary test cannot resolve show no country rather than a guessed one.",
    summary: "Natural Earth · published points",
  },
};

export const REFERENCE_LAYER_IDS = Object.keys(REFERENCE_REGISTRY);

export function isReferenceLayer(id) {
  return Object.hasOwn(REFERENCE_REGISTRY, id);
}

export function referenceRegistry(id) {
  return REFERENCE_REGISTRY[id]?.registry ?? null;
}

// FR-WS-06: basis, freshness and limitations sit next to the control.
export function referenceExplanation(id) {
  const entry = REFERENCE_REGISTRY[id];
  if (!entry) return null;
  const { version, publisher, license, retrieved, url } = entry.registry;
  const rows = [
    ["Class", "Reference layer — published geometry, not an observation"],
    ["Basis", entry.basis],
    ["Location precision", entry.precision],
    ["Registry version", version || "unknown"],
    ["Publisher", publisher],
    ["Licence", license],
    ["Retrieved", retrieved || "computed at runtime"],
  ];
  if (url) rows.push(["Licence terms", url]);
  rows.push(["Limits", entry.limitation]);
  return rows;
}

// The hover card for one reference feature. Deliberately small, and it always
// says what kind of thing this is before it says anything about the place: a
// published coordinate is not an observation of anything happening there.
export function referenceCard(id, properties, link) {
  const entry = REFERENCE_REGISTRY[id];
  const card = document.createElement("div");
  card.className = "event-hover-card";
  // Same structure the report and aircraft cards use, so a reference point is
  // read the same way as any other thing on the map.
  card.append(
    Object.assign(document.createElement("div"), {
      className: "hover-kind",
      textContent: "Reference location · not an observation",
    }),
  );
  const title = document.createElement("strong");
  title.textContent = properties.name || properties.title || entry.label;
  card.append(title);

  const rows = [];
  rows.push(["Country", properties.country || "Not supplied"]);
  for (const [key, label] of [
    ["facility_type", "Type"],
    ["status", "Status"],
    ["use", "Use"],
    ["capacity", "Capacity"],
  ])
    if (properties[key]) rows.push([label, String(properties[key])]);
  rows.push([
    "Source",
    `${entry.registry.publisher} · ${entry.registry.version}`,
  ]);
  rows.push(["Licence", entry.registry.license]);

  const facts = document.createElement("dl");
  facts.className = "orbital-hover-card";
  for (const [label, value] of rows) {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    facts.append(term, detail);
  }
  card.append(facts);

  const caveat = document.createElement("p");
  caveat.className = "hover-location";
  // The card's closing line states what the point is not, matching the
  // reference point to the layer's own panel note.
  caveat.textContent = entry.limitation;
  card.append(caveat);

  const terms = link(entry.registry.url || properties.source_url || "");
  if (terms) card.append(terms);
  return card;
}

// Computed layers such as the terminator have no points to hover, so they are
// skipped here and never given a card they could not fill honestly.
export function referencePointLayers() {
  return REFERENCE_LAYER_IDS.filter((id) => !REFERENCE_REGISTRY[id].computed);
}

export function referenceData(id, date = new Date()) {
  const entry = REFERENCE_REGISTRY[id];
  if (!entry) return null;
  if (entry.computed) {
    const stamp = {
      registry_version: entry.registry.version,
      license: entry.registry.license,
    };
    return {
      type: "FeatureCollection",
      features: [
        ...nightStrips(date).map((feature) => ({
          ...feature,
          properties: { ...stamp, kind: "night" },
        })),
        ...terminatorLines(date).map((feature) => ({
          ...feature,
          properties: { ...stamp, kind: "boundary" },
        })),
      ],
    };
  }
  return null;
}
