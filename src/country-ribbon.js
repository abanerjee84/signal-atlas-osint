import { element } from "./api.js";
import { CATEGORY_NAMES, symbolCanvas } from "./layer-symbols.js";

export function createCountryRibbon({
  selectCountry,
  readSession,
  saveSession,
}) {
  const root = document.querySelector("#country-ribbon");
  const list = document.querySelector("#country-ranking");
  let data = null;
  let mode = readSession("osint.countryRank", "mentions");
  if (!["mentions", "sentiment", "intelligence"].includes(mode))
    mode = "mentions";
  let collapsed = readSession(
    "osint.countryRibbonCollapsed",
    matchMedia("(max-width: 850px)").matches,
  );
  const updateCollapse = () => {
    root.classList.toggle("collapsed", collapsed);
    document.querySelector("#country-ribbon-body").hidden = collapsed;
    const button = document.querySelector("#country-ribbon-toggle");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute(
      "aria-label",
      `${collapsed ? "Expand" : "Collapse"} country leaderboard`,
    );
    button.textContent = collapsed ? "›" : "‹";
  };
  updateCollapse();
  document
    .querySelector("#country-ribbon-toggle")
    .addEventListener("click", () => {
      collapsed = !collapsed;
      saveSession("osint.countryRibbonCollapsed", collapsed);
      updateCollapse();
    });
  for (const button of root.querySelectorAll("[data-country-rank]")) {
    button.addEventListener("click", () => {
      mode = button.dataset.countryRank;
      saveSession("osint.countryRank", mode);
      render();
    });
  }
  document
    .querySelector("#country-tone-order")
    .addEventListener("change", render);
  document
    .querySelector("#country-ribbon-reset")
    .addEventListener("click", () => selectCountry(""));
  const toolbar = document.querySelector(".map-toolbar");
  new ResizeObserver(() =>
    root.style.setProperty("--toolbar-height", `${toolbar.offsetHeight}px`),
  ).observe(toolbar);

  function render() {
    for (const button of root.querySelectorAll("[data-country-rank]"))
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.countryRank === mode),
      );
    document.querySelector("#country-tone-controls").hidden =
      mode !== "sentiment";
    if (!data) return;
    const toneOrder = document.querySelector("#country-tone-order").value;
    const eligible = data.items.filter((r) =>
      mode === "mentions"
        ? r.mentions > 0
        : mode === "intelligence"
          ? r.layer_count > 0
          : r.samples > 0 && Number.isFinite(r.score),
    );
    eligible.sort((a, b) => {
      if (mode === "mentions")
        return (
          b.mentions - a.mentions ||
          b.mention_sources - a.mention_sources ||
          a.country.localeCompare(b.country)
        );
      if (mode === "intelligence")
        return (
          b.layer_count - a.layer_count ||
          b.supported_records - a.supported_records ||
          b.intelligence_records - a.intelligence_records ||
          a.country.localeCompare(b.country)
        );
      // Prioritize samples of at least five texts, and visibly label smaller ones.
      return (
        Number(a.samples < 5) - Number(b.samples < 5) ||
        (toneOrder === "negative" ? a.score - b.score : b.score - a.score) ||
        b.samples - a.samples ||
        a.country.localeCompare(b.country)
      );
    });
    const selected = data.selected_country || "";
    document.querySelector("#country-ribbon-reset").hidden = !selected;
    document.querySelector("#country-ranking-status").textContent =
      `${eligible.length} countries · filtered period`;
    document.querySelector("#country-ranking-scope").textContent =
      mode === "sentiment"
        ? `${data.sentiment.platform === "all" ? { news: "News", public: "Public posts", official: "Official wording" }[data.sentiment.kind] : data.sentiment.platform} · ${data.sentiment.geography === "origin" && (data.sentiment.kind === "public" || data.sentiment.platform !== "all") ? "declared origin" : "country context"}`
        : mode === "mentions"
          ? "Country references in reports"
          : "Layers → supported → records";
    const focused = document.activeElement?.dataset.countryRankCode;
    list.replaceChildren();
    const shown = eligible.slice(0, 12);
    const selectedRow = eligible.find((row) => row.country === selected);
    if (selectedRow && !shown.includes(selectedRow)) shown.push(selectedRow);
    const maximum = Math.max(1, ...eligible.map((row) => row.mentions));
    for (const row of shown) {
      const li = element("li");
      li.value = eligible.indexOf(row) + 1;
      const button = element("button", "country-rank-row");
      button.dataset.countryRankCode = row.country;
      button.setAttribute("aria-pressed", String(row.country === selected));
      const heading = element("span", "country-rank-heading");
      heading.append(
        element(
          "span",
          "country-rank-number",
          String(li.value).padStart(2, "0"),
        ),
        element("span", "country-rank-code", row.country),
        element("span", "country-rank-name", row.name),
      );
      button.append(heading);
      let details;
      if (mode === "mentions") {
        details = `${row.mentions.toLocaleString()} refs · ${row.mention_sources} sources`;
        const bar = element("span", "country-mention-bar");
        const fill = element("span");
        fill.style.width = `${(row.mentions / maximum) * 100}%`;
        bar.append(fill);
        bar.setAttribute("aria-hidden", "true");
        button.append(bar);
      } else if (mode === "sentiment") {
        const thin = row.samples < 5;
        details = `${row.score >= 0 ? "+" : ""}${row.score.toFixed(2)} · n=${row.samples}${thin ? " · thin" : ""}`;
        button.classList.toggle("thin-sample", thin);
        const bar = element("span", "country-tone-bar");
        const fill = element("span", row.score < 0 ? "negative" : "positive");
        fill.style.width = `${Math.min(1, Math.abs(row.score)) * 50}%`;
        fill.style.left = `${row.score < 0 ? 50 - Math.min(1, Math.abs(row.score)) * 50 : 50}%`;
        bar.append(fill);
        bar.setAttribute("aria-hidden", "true");
        button.append(bar);
      } else {
        details = `${row.layer_count} layers · ${row.intelligence_records.toLocaleString()} records`;
        const layers = element("span", "country-layer-strip");
        for (const [category, count] of Object.entries(row.categories).sort(
          ([a], [b]) => a.localeCompare(b),
        )) {
          const symbol = symbolCanvas(category);
          symbol.title = `${CATEGORY_NAMES[category]}: ${count}`;
          layers.append(symbol);
        }
        button.append(layers);
      }
      button.append(element("span", "country-rank-value", details));
      button.setAttribute(
        "aria-label",
        `${row.name}. Rank ${li.value}. ${details}. Select country.`,
      );
      button.title = `${row.name}\n${details}${mode === "intelligence" ? `\n${row.supported_records} verified or corroborated records` : ""}`;
      button.addEventListener("click", () => selectCountry(row.country, true));
      li.append(button);
      list.append(li);
    }
    if (!shown.length)
      list.append(
        element(
          "li",
          "country-rank-empty",
          mode === "sentiment"
            ? "No scored country samples in this dataset."
            : "No country activity matches these filters.",
        ),
      );
    const method = document.querySelector("#country-ranking-method");
    method.textContent = data.methodology[mode];
    if (mode === "sentiment")
      method.append(" Samples with at least 5 texts rank first.");
    if (mode === "mentions" && data.report_truncated)
      method.append(
        ` Latest ${data.report_sample.toLocaleString()} of ${data.report_available.toLocaleString()} distinct reports sampled.`,
      );
    if (mode === "sentiment" && data.sentiment.truncated)
      method.append(
        ` Sentiment uses a bounded sample of ${data.sentiment.available_count.toLocaleString()} available texts.`,
      );
    document.querySelector("#country-ranking-note").textContent =
      mode === "sentiment"
        ? "Wording tone · thin <5 texts"
        : mode === "intelligence"
          ? "Coverage breadth · not threat level"
          : "Mentions indicate context";
    if (focused)
      list
        .querySelector(`[data-country-rank-code="${focused}"]`)
        ?.focus({ preventScroll: true });
  }
  render();
  return {
    setData(value) {
      data = value;
      render();
    },
    setBusy(value) {
      list.setAttribute("aria-busy", String(value));
    },
    setError() {
      data = null;
      list.replaceChildren(
        element(
          "li",
          "country-rank-empty",
          "Country comparison unavailable. Refresh to retry.",
        ),
      );
      document.querySelector("#country-ranking-status").textContent =
        "Unavailable";
    },
  };
}
