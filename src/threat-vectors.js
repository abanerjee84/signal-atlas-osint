import rules from "./attack-vectors.json" with { type: "json" };
import { element, relativeTime } from "./api.js";

export const VECTOR_LABELS = rules.map((rule) => rule.label);
export function knownVectors(labels) {
  const text = labels.join(" · ");
  let vectors = rules
    .filter((rule) => new RegExp(rule.pattern, "i").test(text))
    .map((rule) => rule.label);
  if (vectors.some((label) => /flood|amplification|slow attack/.test(label)))
    vectors = vectors.filter((label) => label !== "DDoS (subtype unspecified)");
  return vectors;
}
export const reputationReason = (label) =>
  /\b(?:blacklist|dnsbl|blocklist|reputation|bad[- ]?ip|bad behavior|anonymizer|TOR)\b/i.test(
    label,
  );

export function renderVectorBreakdown(summary) {
  const body = document.querySelector("#radware-vector-body");
  body.replaceChildren();
  if (!summary) {
    body.append(
      element(
        "p",
        "helper",
        "Waiting for Radware's public-page scraper. Provider health shows collection errors.",
      ),
    );
    return;
  }
  const sampled = Date.parse(summary.observed_at);
  const stale = !Number.isFinite(sampled) || Date.now() - sampled > 120000;
  body.append(
    element(
      "p",
      "helper",
      `Radware · site interval ${summary.interval || "unspecified"} · scraped ${relativeTime(summary.observed_at)}${stale ? " · stale" : ""}`,
    ),
  );
  for (const [key, title] of [
    ["network", "Network attack methods"],
    ["application", "Application violations"],
  ]) {
    body.append(element("h4", "", title));
    const list = element("ul", "vector-breakdown");
    for (const row of (summary[key] || []).slice(0, 20)) {
      if (!Number.isFinite(row.percent) || row.percent < 0 || row.percent > 100)
        continue;
      const item = element("li");
      item.append(
        element("span", "", String(row.name)),
        element("strong", "", `${row.percent}%`),
      );
      list.append(item);
    }
    body.append(list);
  }
  body.append(
    element(
      "p",
      "helper",
      "Global provider percentages, with a separate denominator for each breakdown. These methods are not linked to individual country pairs. Publication and map filters do not change this source-wide snapshot.",
    ),
  );
  const link = element("a", "", "Inspect Radware source");
  link.href = "https://livethreatmap.radware.com/";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  body.append(link);
}
