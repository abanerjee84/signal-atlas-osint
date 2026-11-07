import { element, relativeTime, sourceLink } from "./api.js";
import { vesselFacts } from "./vessels.js";
import { countryFlagImage } from "./country-flags.js";

// The Global Fishing Watch registry snapshot (public/vessel-details.json) is a
// whole-fleet file of resolved identities; treat it like the aircraft registry:
// serve a cached copy and revalidate in the background.
let registry = {},
  registryLoadedAt = 0,
  registryPending = null;
const REGISTRY_TTL = 60000;
export function vesselRegistry() {
  return registry;
}
export function vesselRegistryFor(event, items = registry) {
  const mmsi = String(
    Array.isArray(event.tags) ? event.tags[1] : event.vessel_mmsi || "",
  );
  return /^\d{6,9}$/.test(mmsi) ? items[mmsi] || null : null;
}
export function refreshVesselRegistry() {
  if (Date.now() - registryLoadedAt <= REGISTRY_TTL)
    return registryPending || Promise.resolve();
  registryPending ||= fetch("/vessel-details.json", {
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  })
    .then(async (response) => {
      if (!response.ok) return;
      const value = await response.json();
      if (
        value.items &&
        typeof value.items === "object" &&
        !Array.isArray(value.items)
      )
        registry = value.items;
    })
    .catch(() => {})
    .finally(() => {
      registryLoadedAt = Date.now();
      registryPending = null;
    });
  return registryPending;
}
export async function loadVesselDetails(event) {
  const cached = vesselRegistryFor(event);
  if (cached) return cached;
  await refreshVesselRegistry();
  return vesselRegistryFor(event);
}
// Registry rows only appear when they add something the AIS feed lacks; the
// registry source (flag registers of record, ownership from public registries)
// outranks the self-reported AIS fields it duplicates.
export function vesselRegistryRows(event, details) {
  if (!details || details.available === false) return [];
  const facts = vesselFacts(event);
  const rows = [];
  if (details.shipname && details.shipname !== facts.Name)
    rows.push(["Registered as", details.shipname]);
  if (details.owners?.length)
    rows.push([
      details.owners.length > 1 ? "Owners" : "Owner",
      details.owners
        .map(
          (owner) =>
            `${owner.name}${owner.flag ? ` (${owner.flag})` : ""}${
              owner.year_from ? `, from ${owner.year_from}` : ""
            }`,
        )
        .join(" · "),
    ]);
  if (details.length_m) rows.push(["Length", `${details.length_m} m`]);
  if (details.tonnage_gt) rows.push(["Tonnage", `${details.tonnage_gt} GT`]);
  if (details.types?.length && details.types[0] !== facts["Vessel type"])
    rows.push(["Registry classification", details.types.join(", ")]);
  return rows;
}

// A hull glyph is small, so a vessel card has to carry what a report card
// carries or the pointer reads nothing at all. The feed reports a course and a
// speed and self-reported identity, and the card must say so rather than imply
// the AIS name is verified.
export function vesselHoverCard(event, interactive = false, details = null) {
  const facts = vesselFacts(event);
  const card = element("div", "vessel-hover-card");
  if (!interactive) {
    const kind = element("div", "hover-kind", "Tracked vessel");
    if (event.vessel_flag)
      kind.append(
        countryFlagImage(event.vessel_flag, `${facts["Flag state"]} flag`),
      );
    card.append(kind);
  }
  const fields = element("dl", "vessel-hover-facts");
  for (const [label, value] of [
    ["Name", facts.Name],
    ["MMSI", facts.MMSI],
    ["Flag state", facts["Flag state"]],
    ["Type", facts["Vessel type"] || "Unknown"],
    ["Ground speed", facts["Ground speed"]],
    ["Course", facts.Course],
  ])
    if (value) fields.append(element("dt", "", label), element("dd", "", value));
  const registryRows = details ? vesselRegistryRows(event, details) : [];
  for (const [label, value] of registryRows)
    if (value) fields.append(element("dt", "", label), element("dd", "", value));
  card.append(fields);
  if (registryRows.length)
    card.append(
      element(
        "p",
        "hover-meta vessel-registry-meta",
        "Registry identity · Global Fishing Watch",
      ),
    );
  card.append(
    element(
      "p",
      "hover-meta",
      `AIS position · ${relativeTime(event.time_key)}`,
    ),
    element(
      "p",
      "hover-hint",
      "Self-reported AIS position; the reported name, flag and type are unverified and an apparent gap can mean receiver coverage, not a dark ship.",
    ),
  );
  if (registryRows.length)
    card.append(
      element(
        "p",
        "hover-hint",
        "Ownership is matched from public registers of record (may be dated); it can differ from the flag or the apparent operator.",
      ),
    );
  if (interactive && event.source_url)
    card.append(
      sourceLink(event.source_url, "Open the feed's original record"),
    );
  return card;
}
