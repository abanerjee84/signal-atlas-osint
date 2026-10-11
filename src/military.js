import { dateText, element, sourceLink } from "./api.js";

export function renderMilitary(
  result,
  sources,
  { selectEvent, showTopic, analyzeTopic },
) {
  document.querySelector("#military-summary").textContent =
    `${result.report_count} dated reports · ${result.official_count} official announcements · ${result.media_count} media reports · ${result.sources.length} feeds. Selected period, geography and search apply. Topics can overlap.`;
  const status = document.querySelector("#military-source-status");
  status.replaceChildren(element("p", "helper", result.methodology));
  for (const source of sources.filter(
    (s) => s.category === "military" || s.categories?.includes("military"),
  ))
    status.append(
      element(
        "p",
        "helper",
        `${source.name}: ${source.state}${source.error ? " · " + source.error : ""}`,
      ),
    );
  const list = document.querySelector("#military-groups");
  list.replaceChildren();
  if (!result.groups.length)
    list.append(
      element(
        "p",
        "empty-state",
        "No matching defence reports. Widen the observation period or check the sources; an empty result does not establish absence of activity.",
      ),
    );
  for (const group of result.groups) {
    const card = element("article", "military-brief");
    card.append(
      element(
        "h3",
        "",
        group.name.replace(
          "Other official defence reporting",
          "Other defence reporting",
        ),
      ),
      element("p", "helper", group.assessment),
      element(
        "p",
        "helper",
        `Latest ${dateText(group.latest)} · ${
          Object.entries(group.countries)
            .map(([code, count]) => `${code} ${count}`)
            .join(" · ") || "No named country"
        }`,
      ),
    );
    card.append(
      element(
        "p",
        "helper",
        `${group.official_count} official · ${group.media_count} media · ${group.unlocated_count} without country context.`,
      ),
    );
    if (group.period_comparison)
      card.append(
        element(
          "p",
          "helper",
          `Reports in window: ${group.period_comparison.earlier} earlier half → ${group.period_comparison.later} later half. Reporting volume only.`,
        ),
      );
    const buttons = element("div", "brief-actions");
    const mapButton = element("button", "", "Show on map");
    mapButton.addEventListener("click", () => showTopic(group.name));
    const aiButton = element("button", "", "Prepare cited analysis");
    aiButton.addEventListener("click", () => analyzeTopic(group));
    buttons.append(mapButton, aiButton);
    card.append(buttons);
    const details = element("details", "");
    details.append(
      element(
        "summary",
        "",
        `${group.count} source reports · latest ${group.reports.length} shown`,
      ),
    );
    for (const report of group.reports) {
      const row = element("article", "brief-source");
      row.append(
        element("span", "source-chip", report.basis),
        sourceLink(report.source_url, report.title),
        element(
          "p",
          "helper",
          `${report.source_id} · ${dateText(report.published_at)}`,
        ),
        element("p", "post-excerpt", report.excerpt),
      );
      const locate = element("button", "", "Inspect evidence on map");
      locate.addEventListener("click", () =>
        selectEvent(report.event_id, true),
      );
      row.append(locate);
      details.append(row);
    }
    card.append(details);
    list.append(card);
  }
}
