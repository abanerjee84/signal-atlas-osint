import { element } from "./api.js";
import { conflictType } from "./conflicts.js";

export function reportSummary(record, limit = 280) {
  const text = (
    [
      record.excerpt,
      record.description,
      record.hover_summary,
      record.title,
    ].find((value) => typeof value === "string" && value.trim()) || ""
  )
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit + 1);
  const end = cut.lastIndexOf(" ");
  return cut.slice(0, end > limit / 2 ? end : limit).trimEnd() + "…";
}

export function countryReportPreviews(
  code,
  name,
  reports = [],
  events = [],
  edges = [],
) {
  const unique = new Map();
  const countryName = new RegExp(
    `(?<!\\w)${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\w)`,
    "i",
  );
  const add = (report) => {
    if (!report.title) return;
    const key = report.title;
    if (!unique.has(key)) unique.set(key, report);
  };
  reports
    .filter((r) => r.countries?.includes(code) || r.country_code === code)
    .forEach(add);
  events
    .filter(
      (r) =>
        r.category === "military" &&
        (r.country_code === code ||
          r.news?.mentioned_countries?.includes(code) ||
          countryName.test(String(r.title + " " + (r.description || "")))),
    )
    .forEach(add);
  if (!unique.size)
    for (const edge of edges.filter((e) => e.from === code || e.to === code))
      for (let i = 0; i < (edge.titles || []).length; i++)
        add({
          title: edge.titles[i],
          source_url: edge.urls?.[i],
          event_id: edge.event_ids?.[i],
        });
  return [...unique.values()].slice(0, 2);
}

export function appendReportPreview(card, record, { metadata = true } = {}) {
  const summary = element("p", "hover-summary", reportSummary(record));
  card.append(summary);
  if (!metadata) return;
  let source = record.hover_source || record.source_id || "";
  try {
    source = new URL(record.source_url).hostname.replace(/^www\./, "");
  } catch {
    /* Stored source label remains. */
  }
  const date = record.published_at;
  const when =
    date && Number.isFinite(Date.parse(date))
      ? new Intl.DateTimeFormat("en-GB", {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "UTC",
        }).format(new Date(date)) + " UTC"
      : "";
  card.append(
    element("p", "hover-meta", [source, when].filter(Boolean).join(" · ")),
  );
}

export function reportHoverCard(record) {
  const card = element("div", "event-hover-card");
  const kind =
    record.conflict_label ||
    conflictType(record)?.label ||
    {
      military: "Military report",
      geopolitical: "Geopolitical report",
      threat: "Cyber evidence",
      cyber: "Cyber report",
      economic: "Economy & energy",
      environment: "Environment",
      maritime: "Maritime report",
    }[record.category] ||
    "Source report";
  card.append(element("div", "hover-kind", kind));
  appendReportPreview(card, record);
  const regional =
    record.location_precision === "regional" ||
    record.location_precision === "unknown";
  card.append(
    element(
      "p",
      "hover-location",
      regional ? "Country context" : "Approximate reported location",
    ),
  );
  card.append(
    element("p", "hover-hint", "Select the marker to read the report"),
  );
  return card;
}
