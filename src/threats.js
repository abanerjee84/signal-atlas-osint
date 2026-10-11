// Tags preserve the same explicit report roles on both current and older APIs.
export function threatFacts(event) {
  const tags = event.tags || [];
  const value = (prefix) =>
    tags.find((tag) => tag.startsWith(prefix))?.slice(prefix.length);
  return {
    actor: event.threat?.actor || value("actor:") || "Unknown actor",
    attacker_country:
      event.threat?.attacker_country || value("attributed-country:") || null,
    victim_countries:
      event.threat?.victim_countries ||
      tags
        .filter((tag) => tag.startsWith("victim-country:"))
        .map((tag) => tag.slice(15)),
    attack_kind:
      event.threat?.attack_kind ||
      value("attack-kind:") ||
      "Reported cyber activity",
    classification:
      event.threat?.classification ||
      value("threat-classification:") ||
      "reported_attack",
    traffic_origin_country:
      event.threat?.traffic_origin_country ||
      value("traffic-origin-country:") ||
      null,
    traffic_target_country:
      event.threat?.traffic_target_country ||
      value("traffic-target-country:") ||
      null,
    detection_country:
      event.threat?.detection_country || value("detection-country:") || null,
  };
}

const roles = (facts) =>
  facts.classification === "reported_attack"
    ? [facts.attacker_country, ...facts.victim_countries].filter(Boolean)
    : [
        facts.traffic_origin_country,
        facts.traffic_target_country,
        facts.detection_country,
      ].filter(Boolean);

export function threatCaption(facts) {
  return facts.classification === "reported_attack"
    ? `${facts.actor} · ${facts.attack_kind}. Reported attribution: ${facts.attacker_country || "unknown"} → ${facts.victim_countries.join(", ") || "unknown targets"}.`
    : facts.classification === "detection"
      ? `Provider detection · ${facts.attack_kind} · ${facts.detection_country || "unknown country"}. Actor unknown.`
      : `Sampled traffic · ${facts.attack_kind}. Infrastructure: ${facts.traffic_origin_country || "unknown origin"} → ${facts.traffic_target_country || "unknown target"}. Actor unknown.`;
}

export function buildThreatNetwork(events, places, selection = {}) {
  const byCode = new Map(places.map((place) => [place.code, place]));
  const inBounds = (code) => {
    const place = byCode.get(code);
    if (!place) return false;
    if (!selection.bbox) return true;
    const [west, south, east, north] = selection.bbox;
    const [x, y] = place.center;
    return (
      y >= south &&
      y <= north &&
      (west <= east ? x >= west && x <= east : x >= west || x <= east)
    );
  };
  const rows = events.filter((event) => {
    const facts = threatFacts(event);
    const codes = roles(facts);
    return (
      (!selection.country || codes.includes(selection.country)) &&
      (!selection.bbox || codes.some(inBounds)) &&
      (!selection.q ||
        `${event.title} ${event.description} ${facts.actor}`
          .toLowerCase()
          .includes(selection.q.toLowerCase()))
    );
  });
  const groups = new Map();
  let unknownOrigin = 0,
    unknownVictim = 0;
  for (const event of rows) {
    const facts = threatFacts(event);
    const traffic = facts.classification === "observed_traffic";
    if (facts.classification === "reported_attack") {
      if (!facts.attacker_country) unknownOrigin++;
      if (!facts.victim_countries.length) unknownVictim++;
    }
    const targets = traffic
      ? [facts.traffic_target_country]
      : facts.victim_countries;
    for (const victim of targets) {
      const origin = traffic
        ? facts.traffic_origin_country
        : facts.attacker_country;
      if (
        !origin ||
        !byCode.has(origin) ||
        !byCode.has(victim) ||
        (origin === victim && !traffic)
      )
        continue;
      const id = `${origin}:${victim}:${traffic ? event.source_id : facts.actor}:${traffic ? facts.attack_kind : "report"}`;
      const edge = groups.get(id) || {
        id,
        kind: traffic
          ? "observed_traffic_to_target"
          : "reported_attacker_to_victim",
        from: origin,
        to: victim,
        actor: facts.actor,
        source_id: event.source_id,
        domestic: origin === victim,
        count: 0,
        from_coordinates: byCode.get(origin).center,
        to_coordinates: byCode.get(victim).center,
        titles: [],
        event_ids: [],
        source_urls: [],
        basis: traffic
          ? "Sampled provider traffic origin → destination. Infrastructure geography, not actor nationality or confirmed compromise. Country centers are illustrative."
          : "Reported country attribution → explicitly described target country. Automated extraction; unverified. Country centers are illustrative.",
      };
      // Identical syndicated delivery of a URL cannot count as another attack.
      if (
        traffic
          ? edge.event_ids.includes(event.event_id)
          : edge.source_urls.includes(event.source_url)
      )
        continue;
      edge.count++;
      edge.titles.push(event.title);
      edge.event_ids.push(event.event_id);
      edge.source_urls.push(event.source_url);
      groups.set(id, edge);
    }
  }
  return {
    edges: [...groups.values()],
    report_count: rows.filter(
      (event) => threatFacts(event).classification === "reported_attack",
    ).length,
    observation_count: rows.filter(
      (event) => threatFacts(event).classification !== "reported_attack",
    ).length,
    unknown_origin_count: unknownOrigin,
    unknown_victim_count: unknownVictim,
    events: rows,
    classification: "reports_and_sampled_detections",
  };
}

// The running service may predate this layer. Merge its bounded role evidence
// without presenting unrelated fallback-category counts as threat activity.
export function threatCountryActivity(base, network, places, layers) {
  const physical = [...layers].some(
    (id) => !["analysis", "threat"].includes(id),
  );
  const items = new Map(
    base.items.map((item) => [
      item.country,
      {
        ...item,
        categories: physical ? { ...item.categories } : {},
        mentions: physical ? item.mentions : 0,
        mention_sources: physical ? item.mention_sources : 0,
        records: physical ? item.records : 0,
        intelligence_records: physical ? item.intelligence_records : 0,
        supported_records: physical ? item.supported_records : 0,
        layer_count: physical ? item.layer_count : 0,
      },
    ]),
  );
  const sources = new Map(),
    seen = new Set();
  for (const event of layers.has("threat") ? network?.events || [] : []) {
    const facts = threatFacts(event);
    for (const code of new Set(roles(facts))) {
      const key = `${code}:${facts.classification === "reported_attack" ? event.source_url : event.event_id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const place = places.find((place) => place.code === code);
      if (!place) continue;
      const row = items.get(code) || {
        country: code,
        name: place.name,
        mentions: 0,
        mention_sources: 0,
        records: 0,
        intelligence_records: 0,
        supported_records: 0,
        layer_count: 0,
        categories: {},
        score: null,
        samples: 0,
      };
      row.mentions++;
      row.records++;
      row.intelligence_records++;
      row.categories.threat = (row.categories.threat || 0) + 1;
      row.layer_count = Object.keys(row.categories).length;
      items.set(code, row);
      const set = sources.get(code) || new Set();
      set.add(event.source_id);
      sources.set(code, set);
    }
  }
  for (const [code, set] of sources)
    items.get(code).mention_sources += set.size;
  if (layers.has("cyber")) {
    for (const item of items.values()) {
      if (item.categories.threat) {
        item.categories.cyber =
          (item.categories.cyber || 0) + item.categories.threat;
        delete item.categories.threat;
      }
      item.layer_count = Object.keys(item.categories).length;
    }
  }
  return {
    ...base,
    items: [...items.values()],
    methodology: {
      ...base.methodology,
      mentions:
        base.methodology.mentions +
        " Threat activity adds up to 500 published reports (deduplicated by URL) and 300 sampled detections (deduplicated by observation ID). Traffic location does not identify an actor.",
      intelligence:
        base.methodology.intelligence +
        " Threat counts describe reported country roles and provider traffic geography in a bounded sample, not verified responsibility or global attack totals.",
    },
  };
}

export function threatTimeline(base, network, layers, interval = "hour") {
  const items = base.items.filter((item) => layers.has(item.category));
  const buckets = new Map();
  for (const event of layers.has("threat") ? network?.events || [] : []) {
    const field =
      { event: "time_key", published: "published_at", ingested: "ingested_at" }[
        base.time_basis
      ] || "time_key";
    const date = new Date(event[field]);
    if (!Number.isFinite(date.getTime())) continue;
    const time =
      date.toISOString().slice(0, interval === "day" ? 10 : 13) +
      (interval === "day" ? "" : ":00:00Z");
    const bucket = buckets.get(time) || { time, category: "threat", count: 0 };
    bucket.count++;
    buckets.set(time, bucket);
  }
  return {
    ...base,
    items: [...items, ...buckets.values()]
      .map((item) =>
        layers.has("cyber") && item.category === "threat"
          ? { ...item, category: "cyber" }
          : item,
      )
      .reduce((merged, item) => {
        const existing = merged.find(
          (row) =>
            row.category === item.category &&
            row.time.replace(/Z$/, "") === item.time.replace(/Z$/, ""),
        );
        if (existing) existing.count += item.count;
        else merged.push({ ...item });
        return merged;
      }, [])
      .sort((a, b) => a.time.localeCompare(b.time)),
  };
}
