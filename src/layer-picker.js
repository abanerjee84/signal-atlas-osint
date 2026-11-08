import { element } from "./api.js";
import { REFERENCE_LAYER_IDS } from "./reference-layers.js";

// Broad views already have a category switch. Do not offer a second switch
// for the same subject just because its records use a different API.
export const PRIMARY_LAYER_ALIASES = {
  aircraft: "aviation",
  vessels: "maritime",
  military: "military",
  diplomacy: "geopolitical",
  economy: "economic",
  environment: "environment",
  cyber: "cyber",
  threats: "cyber",
  infrastructure: "infrastructure",
  discussion: "sentiment",
};

const topics = [
  ["world", "News & politics"],
  ["conflict", "Conflict & defence"],
  ["transport", "Aircraft, ships & rail"],
  ["sensors", "Cameras & radio"],
  ["environment", "Weather & environment"],
  ["cyber", "Cyber & networks"],
  ["space", "Space"],
  ["places", "Reference places"],
];

export function layerTopic(id, group = "") {
  if (REFERENCE_LAYER_IDS.includes(id) || group === "Reference assets")
    return "places";
  if (
    id === "space" ||
    ["ground-stations", "satellite-receptions"].includes(id)
  )
    return "space";
  if (["cctv", "radio", "radio-receptions"].includes(id)) return "sensors";
  if (["aviation", "maritime", "gnss"].includes(id) || group === "Air & sea")
    return "transport";
  if (id === "environment" || group === "Environment") return "environment";
  if (
    ["cyber", "infrastructure", "disruptions"].includes(id) ||
    group === "Cyber"
  )
    return "cyber";
  if (id === "military" || group === "Conflict") return "conflict";
  return "world";
}

export function createLayerPicker(root) {
  const searchInput = document.querySelector("#layer-search");
  const selectedButton = document.querySelector("#layer-show-selected");
  let selectedOnly = false,
    rows = [],
    baseMatches = null,
    query = "",
    renderedPrimary = false;
  const groupState = new Map(),
    detailState = new Map();
  const isOn = (row) => row.node.querySelector("input").checked;

  function render() {
    for (const node of renderedPrimary
      ? root.querySelectorAll(".layer-topic")
      : [])
      groupState.set(node.dataset.layerTopic, node.open);
    for (const node of renderedPrimary
      ? root.querySelectorAll(".layer-topic-more")
      : [])
      detailState.set(node.dataset.topicMore, node.open);
    root.replaceChildren();
    for (const [id, name] of topics) {
      const members = rows.filter((row) => row.topic === id);
      if (!members.length) continue;
      const group = element("details", "layer-topic");
      group.dataset.layerTopic = id;
      group.open = groupState.get(id) ?? members.some(isOn);
      const summary = element("summary");
      summary.append(
        element("span", "", name),
        element("span", "layer-topic-count"),
      );
      group.append(summary);
      const primary = members.filter((row) => row.primary),
        specific = members.filter((row) => !row.primary);
      for (const row of primary) group.append(row.node);
      if (specific.length && primary.length) {
        const more = element("details", "layer-topic-more");
        more.dataset.topicMore = id;
        more.open = detailState.get(id) ?? specific.some(isOn);
        more.append(
          element("summary", "", `More ${name.toLowerCase()} layers`),
        );
        for (const row of specific) more.append(row.node);
        group.append(more);
      } else for (const row of specific) group.append(row.node);
      root.append(group);
    }
    renderedPrimary ||= rows.some((row) => row.primary);
    search(query, baseMatches);
  }

  function search(value = "", matches = baseMatches) {
    query = value;
    baseMatches = matches;
    const terms = value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let found = 0;
    for (const row of rows) {
      const words = `${row.id} ${row.name}`.toLowerCase();
      const match =
        !terms.length ||
        (row.primary && matches?.includes(row.id)) ||
        terms.every((term) => words.includes(term));
      row.node.hidden = !match || (selectedOnly && !isOn(row));
      if (!row.node.hidden) found++;
    }
    for (const group of root.querySelectorAll(".layer-topic")) {
      const members = rows.filter(
        (row) => row.topic === group.dataset.layerTopic,
      );
      group.hidden = !members.some((row) => !row.node.hidden);
      const count = members.filter(isOn).length;
      group.querySelector(".layer-topic-count").textContent = count
        ? `${count} on`
        : "";
      const more = group.querySelector(".layer-topic-more");
      if (more) {
        more.hidden = !members.some((row) => !row.primary && !row.node.hidden);
        if (terms.length || selectedOnly) more.open = !more.hidden;
      }
      if ((terms.length || selectedOnly) && !group.hidden) group.open = true;
    }
    const on = rows.filter(isOn).length;
    document.querySelector("#layer-selection-summary").textContent =
      `${on} ${on === 1 ? "layer" : "layers"} on`;
    selectedButton.textContent = selectedOnly
      ? `Selected (${on})`
      : "Selected only";
    selectedButton.setAttribute("aria-pressed", String(selectedOnly));
    const result = document.querySelector("#layer-search-result");
    result.hidden = !terms.length && !selectedOnly;
    result.textContent = found
      ? `${found} matching ${found === 1 ? "layer" : "layers"}`
      : selectedOnly
        ? "No selected layers match. Turn off Selected only to browse all layers."
        : "No matching layers. Try cameras, aircraft, weather or cyber.";
    return found;
  }
  selectedButton.addEventListener("click", () => {
    selectedOnly = !selectedOnly;
    search(query);
  });
  return {
    setRows(value) {
      rows = value;
      render();
    },
    search,
    selectionChanged() {
      search(query);
    },
  };
}
