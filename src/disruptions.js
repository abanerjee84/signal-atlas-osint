// Internet-disruption observations, drawn on the map.
//
// These records are country-level aggregates over a measurement window, not
// located incidents. The marker is placed at the same country reference point the
// rest of the product uses, and every surface that shows one states the window,
// the aggregation method and the underlying datasource. Nothing here reduces a
// median-of-prefixes figure to "the internet went down here", and a protocol
// share is never presented as an outage measurement.

// What the marker means, stated wherever the layer is described.
export const DISRUPTION_BASIS =
  "Country-level network availability aggregate over the stated measurement window. The marker sits at the country reference point, not at a located incident.";

export const DISRUPTION_LIMITATION =
  "A country aggregate is not a located outage and does not identify an affected network, operator or site. An empty country is not evidence that nothing happened there.";

const LOCATION_PRECISION = "regional";

// The score is a provider median over its own units, so it is only meaningful
// relative to other rows from the same datasource and window. Sizing by rank
// within the response avoids implying a cross-datasource magnitude comparison.
function rankedSizes(records) {
  const scores = records
    .map((row) => row.score)
    .filter((value) => Number.isFinite(value));
  const sorted = [...scores].sort((a, b) => a - b);
  return new Map(
    records.map((row) => [
      row.id,
      Number.isFinite(row.score) && sorted.length > 1
        ? 0.25 + 0.75 * (sorted.indexOf(row.score) / (sorted.length - 1))
        : 0.5,
    ]),
  );
}

export function disruptionFeatures(records, places) {
  const sizes = rankedSizes(records);
  const features = [];
  const unresolved = [];
  for (const row of records) {
    const place = places[row.country];
    if (!place) {
      // An aggregate we cannot place is reported, never guessed onto a neighbour.
      unresolved.push(row.country);
      continue;
    }
    const [longitude, latitude] = place.center;
    features.push({
      type: "Feature",
      properties: {
        id: row.id,
        country: row.country,
        name: row.name,
        score: row.score,
        size: sizes.get(row.id),
        method: row.method,
        datasource: row.datasource,
        start_at: row.start_at,
        end_at: row.end_at,
        measurement_from: row.measurement_from,
        measurement_until: row.measurement_until,
        uncertainty: row.uncertainty,
        original_url: row.original_url,
        retrieved_at: row.retrieved_at,
        basis: DISRUPTION_BASIS,
        location_precision: LOCATION_PRECISION,
      },
      geometry: { type: "Point", coordinates: [longitude, latitude] },
    });
  }
  return { features, unresolved: [...new Set(unresolved)].sort() };
}

// One line per field, shared by the popup and the layer note so the two cannot
// drift apart. Anything the provider did not supply is shown as absent.
export function disruptionFields(properties) {
  return [
    ["Country", properties.name || properties.country || "Unknown"],
    [
      "Score (provider units)",
      Number.isFinite(properties.score)
        ? properties.score.toFixed(1)
        : "Not supplied",
    ],
    ["Aggregation", properties.method || "Not stated"],
    ["Datasource", properties.datasource || "Not stated"],
    [
      "Measurement window",
      `${(properties.measurement_from || "?").slice(0, 16).replace("T", " ")} to ${(properties.measurement_until || "?").slice(0, 16).replace("T", " ")} UTC`,
    ],
    [
      "Event window",
      `${(properties.start_at || "?").slice(0, 16).replace("T", " ")} to ${(properties.end_at || "?").slice(0, 16).replace("T", " ")} UTC`,
    ],
    [
      "Uncertainty",
      properties.uncertainty == null
        ? "Not supplied by the provider"
        : String(properties.uncertainty),
    ],
    ["Location basis", properties.basis || DISRUPTION_BASIS],
    [
      "Location precision",
      `${properties.location_precision} — country aggregate, not a point incident`,
    ],
    [
      "Retrieved",
      properties.retrieved_at
        ? properties.retrieved_at.slice(0, 19).replace("T", " ") + " UTC"
        : "Unknown",
    ],
  ];
}

// The provider returns the measurement window as an object; render it as a range
// and never collapse a missing window into a bare "now".
export function measurementLabel(period) {
  if (!period) return "measurement window not stated";
  if (typeof period === "string")
    return `measured ${period.slice(0, 16).replace("T", " ")}`;
  const from = period.from
    ? String(period.from).slice(0, 16).replace("T", " ")
    : "?";
  const until = period.until
    ? String(period.until).slice(0, 16).replace("T", " ")
    : "?";
  return `measured ${from} to ${until} UTC`;
}

export const DISRUPTION_STATE = {
  needsToken: "Enter your local access token in Settings to load this layer.",
  loading: "Loading retained observations…",
  empty:
    "No observations retained in this response. That is not evidence that no disruption occurred.",
  unauthorised:
    "The stored access token was refused, so this layer is unavailable.",
  failed: (message) => `Could not load observations: ${message}`,
};

// The hover card for one country aggregate. Shows the same fields as the panel
// and always keeps the original provider reference visible.
export function disruptionCard(properties, link) {
  const card = document.createElement("div");
  card.className = "event-hover-card";
  // Same structure the report and reference cards use, so every hover on this
  // map is read the same way.
  const kind = document.createElement("div");
  kind.className = "hover-kind";
  kind.textContent = "Country aggregate · not a located incident";
  const title = document.createElement("strong");
  title.textContent =
    properties.name || properties.country || "Unknown country";
  const facts = document.createElement("dl");
  facts.className = "orbital-hover-card";
  for (const [label, value] of disruptionFields(properties)) {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    facts.append(term, detail);
  }
  card.append(kind, title, facts);
  if (properties.original_url) card.append(link(properties.original_url));
  return card;
}
