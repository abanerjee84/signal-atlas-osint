import { element, relativeTime, sourceLink } from "./api.js";
import { vesselFacts } from "./vessels.js";
import { countryFlagImage } from "./country-flags.js";

// A hull glyph is small, so a vessel card has to carry what a report card
// carries or the pointer reads nothing at all. The feed reports a course and a
// speed and self-reported identity, and the card must say so rather than imply
// the AIS name is verified.
export function vesselHoverCard(event, interactive = false) {
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
  card.append(
    fields,
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
  if (interactive && event.source_url)
    card.append(
      sourceLink(event.source_url, "Open the feed's original record"),
    );
  return card;
}
