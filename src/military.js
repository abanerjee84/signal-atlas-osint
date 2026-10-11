import { dateText, element, sourceLink } from "./api.js";
import { reportSummary } from "./report-preview.js";

export function renderMilitary(
  result,
  sources,
  { selectEvent, showTopic, analyzeTopic },
) {
  document.querySelector("#military-summary").textContent =
    `${result.report_count} reports · ${result.sources.length} sources`;
  const status = document.querySelector("#military-source-status");
  status.replaceChildren(
    element(
      "p",
      "helper",
      "Official statements and news reporting are labelled separately. Topics overlap; country links show places discussed, not force movements.",
    ),
  );
  for (const source of sources.filter(
    (s) => s.category === "military" || s.categories?.includes("military"),
  ))
    status.append(
      element(
        "p",
        "helper",
        `${source.name}: ${source.state === "ok" ? "Available" : "Update unavailable"}`,
      ),
    );
  const list = document.querySelector("#military-groups");
  list.replaceChildren();
  if (!result.groups.length) {
    const empty = element(
      "div",
      "empty-state",
      "No military reports match this view.",
    );
    const action = element("button", "", "Show all topics");
    action.addEventListener("click", () => showTopic());
    empty.append(action);
    list.append(empty);
  }
  for (const group of result.groups) {
    const card = element("article", "military-brief");
    const heading = element("div", "military-topic-heading");
    heading.append(
      element(
        "h3",
        "",
        group.name.replace(
          "Other official defence reporting",
          "Other defence reporting",
        ),
      ),
      element(
        "span",
        "report-count-chip",
        `${group.count} ${group.count === 1 ? "report" : "reports"}`,
      ),
    );
    card.append(
      heading,
      element(
        "p",
        "military-topic-summary",
        group.reports[0]
          ? reportSummary(group.reports[0], 240)
          : "Open the reports to explore this topic.",
      ),
    );
    card.append(
      element(
        "p",
        "military-topic-meta",
        `${group.official_count} official statements · ${group.media_count} news reports`,
      ),
    );
    const buttons = element("div", "brief-actions");
    const mapButton = element(
      "button",
      "primary-topic-action",
      "Show topic links",
    );
    mapButton.dataset.militaryTopic = group.name;
    mapButton.setAttribute("aria-pressed", "false");
    mapButton.title =
      "Show the countries discussed in this topic. Select individual reports below to locate their evidence.";
    mapButton.addEventListener("click", () => showTopic(group.name));
    const aiButton = element("button", "", "Analyze sources");
    aiButton.addEventListener("click", () => analyzeTopic(group));
    buttons.append(mapButton, aiButton);
    card.append(buttons);
    const details = element("details", "military-report-list");
    details.append(
      element("summary", "", `Read reports (${group.reports.length} recent)`),
    );
    for (const report of group.reports) {
      const row = element("article", "brief-source");
      const label =
        report.basis === "Official announcement"
          ? "Official statement"
          : "News report";
      let publisher = sources.find(
        (s) => s.source_id === report.source_id,
      )?.name;
      if (!publisher) {
        try {
          publisher = new URL(report.source_url).hostname.replace(/^www\./, "");
        } catch {
          publisher = "Source";
        }
      }
      row.append(
        element("span", "source-chip", label),
        sourceLink(report.source_url, report.title),
        element(
          "p",
          "military-topic-meta",
          `${publisher} · ${dateText(report.published_at)}`,
        ),
      );
      const summary = reportSummary({
        description: report.excerpt,
        title: report.title,
      });
      if (summary !== report.title)
        row.append(element("p", "post-excerpt", summary));
      const locate = element("button", "", "View report on map");
      locate.addEventListener("click", () =>
        selectEvent(report.event_id, true),
      );
      row.append(locate);
      details.append(row);
    }
    card.append(details);
    if (group.period_comparison) {
      const trend = element("details", "military-trend");
      trend.append(
        element("summary", "", "Reporting trend"),
        element(
          "p",
          "helper",
          `${group.period_comparison.earlier} reports in the earlier half of this period; ${group.period_comparison.later} in the later half. This measures coverage, not conflict intensity.`,
        ),
      );
      card.append(trend);
    }
    list.append(card);
  }
}
