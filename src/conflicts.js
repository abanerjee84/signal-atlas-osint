import types from "./conflict-types.json" with { type: "json" };

export const CONFLICT_TYPES = types;
const rules = types.map((type) => [type, new RegExp(type.pattern, "i")]);
const plain = (value) =>
  String(value || "")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

export function conflictType(event) {
  if (!["military", "geopolitical"].includes(event.category)) return null;
  const tags = Array.isArray(event.tags) ? event.tags : [];
  const tagged = types.find((type) => tags.includes(`conflict:${type.id}`));
  if (tagged) return tagged;
  const title = plain(event.title);
  if (
    /\b(?:earthquake|magnitude|wildfire|hurricane|tsunami|labou?r strike|workers.*strike)\b/i.test(
      title,
    )
  )
    return null;
  return (
    rules.find(([, rule]) => rule.test(title))?.[0] ||
    (event.category === "military"
      ? types.find((type) => type.id === "conflict")
      : null)
  );
}

export function conflictSummary(event) {
  const text = plain(event.ai_summary || event.description || event.title);
  // A source excerpt, not an uncited generated assessment.
  if (text.length <= 360) return text;
  const sentence = text.slice(0, 360).match(/^(.{80,}[.!?])\s/);
  return sentence
    ? sentence[1]
    : text.slice(0, 357).replace(/\s+\S*$/, "") + "…";
}
