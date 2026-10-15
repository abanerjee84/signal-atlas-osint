// Infrastructure observations retain provider units and separate location provenance.
const object = (value) => {
  if (value && typeof value === "object") return value;
  try {
    return JSON.parse(value || "null") || {};
  } catch {
    return {};
  }
};
const timestamp = (value) =>
  value
    ? new Date(value).toISOString().replace("T", " ").slice(0, 19) + " UTC"
    : "Not supplied";

export function infrastructureFacts(record) {
  const observation = object(
    record.cyber_observation ||
      record.reports?.[0]?.metadata?.cyber_observation,
  );
  const geo = object(
    record.infrastructure_geo ||
      record.reports?.[0]?.metadata?.infrastructure_geo,
  );
  const rows = [
    ["Indicator", observation.indicator_value || "Not supplied"],
    ["Observation", observation.kind || "Provider indicator"],
    ["Provider family", observation.source_family || record.source_id],
  ];
  for (const [label, value] of [
    ["Provider reports", observation.report_count],
    ["Target hosts", observation.target_count],
    ["Matching requests", observation.request_count],
    ["Port", observation.port],
    ["Malware association", observation.malware_name || undefined],
  ])
    if (value !== null && value !== undefined)
      rows.push([label, String(value)]);
  if (observation.period_start)
    rows.push([
      "Reporting interval",
      `${timestamp(observation.period_start)} to ${timestamp(observation.period_end)}`,
    ]);
  if (observation.first_seen)
    rows.push(["First seen", timestamp(observation.first_seen)]);
  if (observation.last_seen)
    rows.push(["Last seen", timestamp(observation.last_seen)]);
  rows.push(["Retrieved", timestamp(observation.received_at)]);
  rows.push([
    "Infrastructure country",
    geo.country_code || "Unknown; no supported location",
  ]);
  if (geo.retrieved_at)
    rows.push(["Country estimate retrieved", timestamp(geo.retrieved_at)]);
  if (geo.expires_at && Date.parse(geo.expires_at) < Date.now())
    rows.push(["Country estimate", "Cached estimate is stale"]);
  return rows;
}

export function infrastructureSummary(record) {
  return (
    infrastructureFacts(record)
      .filter(([label]) =>
        [
          "Provider reports",
          "Target hosts",
          "Matching requests",
          "Malware association",
        ].includes(label),
      )
      .map(([label, value]) => `${value} ${label.toLowerCase()}`)
      .join(" · ") || "Provider indicator; no actor attribution"
  );
}
