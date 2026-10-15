// Local concept expansion: layer discovery works offline without a model or key.
// Terms describe the evidence each layer actually contains, not inferred events.
const concepts = {
  geopolitical:
    "geopolitics politics diplomacy diplomatic elections government sanctions treaty foreign affairs borders international relations news",
  military:
    "military defence defense armies army troops warfare weapons missiles navy war combat conflict forces deployment",
  aviation:
    "aviation aircraft airplane aeroplane planes flights flying air traffic altitude airports jets heading",
  maritime:
    "maritime ships shipping boats vessels sea ocean ports naval transport cargo tanker",
  sentiment:
    "sentiment social media public opinion reactions feelings mood positive negative reddit youtube twitter x posts discussion",
  cyber:
    "cyber cybersecurity hackers hacking ransomware malware phishing ddos attacks threats threat actors exploits vulnerability cve blacklist victims",
  infrastructure:
    "cyber infrastructure ip address addresses ioc indicators scanning scans dshield sans honeypot honeypots threatfox malware servers command control c2 botnet hosts network",
  economic:
    "economic economy economics business finance markets stocks oil gas energy prices trade inflation power electricity sanctions",
  environment:
    "environment environmental climate weather fires wildfire earthquake disaster flood floods humanitarian aid relief drought pollution",
  analysis:
    "analysis intelligence anomalies anomaly patterns assessment evidence investigation insights correlations unusual trends",
  space:
    "space satellite satellites iss international space station orbit orbital tracking hubble telescope tiangong earth observation spacecraft astronomy reconnaissance sarah sar lupe ceres skynet wgs aehf muos gps military satellites",
};
const stop = new Set(
  "a an the of in on for to and with show find me about where is are can i want see track tracking latest live current position positions data".split(
    " ",
  ),
);
const tokens = (text) =>
  text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/)
    .filter((word) => word && !stop.has(word));
const root = (word) =>
  word.length > 4
    ? word.replace(/(?:ing|ies|s)$/, (suffix) => (suffix === "ies" ? "y" : ""))
    : word;

export function searchLayers(query, names) {
  if (!query.trim()) return Object.keys(names).filter((id) => id !== "threat");
  const terms = tokens(query);
  if (!terms.length) return [];
  return Object.keys(concepts)
    .map((id) => {
      const vocabulary = new Set(
        tokens(`${names[id] || ""} ${concepts[id]}`).map(root),
      );
      return {
        id,
        score: terms.reduce(
          (score, term) => score + (vocabulary.has(root(term)) ? 1 : 0),
          0,
        ),
      };
    })
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .map(({ id }) => id);
}
