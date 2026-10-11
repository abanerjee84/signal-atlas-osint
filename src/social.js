import { dateText, element, sourceLink } from "./api.js";

export function renderSocial(result, sources) {
  const social = Array.isArray(result.posts);
  document.querySelector("#social-controls").hidden = !social;
  document
    .querySelector("#sentiment-platform")
    .parentElement.querySelector('[for="sentiment-platform"]').hidden =
    result.platform === "youtube";
  document.querySelector("#sentiment-platform").hidden =
    result.platform === "youtube";
  document.querySelector("#social-posts-section").hidden = !social;
  const network = result.discussion_network;
  document.querySelector("#social-network-section").hidden =
    !network?.edges.length;
  if (!social) return;
  document.querySelector("#reddit-browser-import").hidden = ![
    "all",
    "reddit",
  ].includes(result.platform);
  const coverage = document.querySelector("#social-coverage");
  coverage.replaceChildren(
    element(
      "p",
      "",
      `${result.known_origin_count} known origins · ${result.unknown_origin_count} unknown. ${result.geography_basis}.`,
    ),
  );
  coverage.append(
    element(
      "p",
      "",
      result.platform === "youtube"
        ? "YouTube RSS supplies upload titles/descriptions, not viewer comments."
        : "Keyless public Reddit, Mastodon and Lemmy feeds, plus public Telegram channel previews. Shared links and channel publications are sampled discourse, not representative opinion. Reddit archives can lag; RSS retirement is announced for 13 November 2026. YouTube uploads are separate from comments. X has no permitted public collector connected.",
    ),
  );
  const health = element("details", "");
  health.append(element("summary", "", "Social source health"));
  coverage.append(health);
  for (const source of sources.filter(
    (s) =>
      s.platform &&
      (result.platform === "all"
        ? s.category === "sentiment"
        : s.platform === result.platform),
  )) {
    health.append(
      element(
        "p",
        "social-source-status",
        `${source.name}: ${source.state}${source.error ? " · " + source.error : ""}${source.last_success ? " · " + dateText(source.last_success) : ""}`,
      ),
    );
  }
  const list = document.querySelector("#social-posts");
  const knownSources = new Set(sources.map((source) => source.source_id));
  for (const [identifier, count] of Object.entries(result.sources || {})) {
    if (!knownSources.has(identifier))
      health.append(
        element(
          "p",
          "social-source-status",
          `${identifier.replaceAll("_", " ")}: ${count} collected records · current service has no collection status for this source`,
        ),
      );
  }
  list.replaceChildren();
  document.querySelector("#social-post-count").textContent =
    `${result.posts.length} displayed of ${result.dataset_count} analyzed feed records. Latest ${result.post_limit} shown; comments and uploads have separate datasets.`;
  if (!result.posts.length)
    list.append(
      element(
        "p",
        "empty-state",
        "No matching public feed records. Check the period, topic, platform and source health.",
      ),
    );
  for (const post of result.posts) {
    const card = element("article", "social-post");
    card.dataset.reportId = post.report_id;
    card.tabIndex = -1;
    const header = element("div", "social-post-header");
    header.append(
      element("span", "source-chip", `${post.platform} · ${post.content_type}`),
      element(
        "span",
        `sentiment-label ${post.label || "unscored"}`,
        post.label ? `${post.label} ${post.score.toFixed(2)}` : "Not scored",
      ),
    );
    card.append(
      header,
      sourceLink(post.url, post.title),
      element(
        "p",
        "helper",
        `${post.author || post.community || post.source_id} · ${dateText(post.published_at)} · ${post.language}`,
      ),
      element(
        "p",
        "post-excerpt",
        post.text.slice(0, 350) + (post.text.length > 350 ? "…" : ""),
      ),
      element(
        "p",
        "helper",
        `Origin: ${post.origin_country || "unknown"}. Text countries: ${post.mentioned_countries.join(", ") || "none"}. Thread context: ${post.context_countries.join(", ") || "none"}.`,
      ),
    );
    if (post.relations.length) {
      const links = element("div", "post-links");
      for (const relation of post.relations)
        links.append(sourceLink(relation.target_url, "Open linked thread"));
      card.append(links);
    }
    list.append(card);
  }
  const evidence = document.querySelector("#social-relation-list");
  evidence.replaceChildren();
  document.querySelector("#social-relations-label").textContent =
    `${network?.edges.length || 0} evidenced thread connections`;
  const nodes = new Map((network?.nodes || []).map((node) => [node.id, node]));
  for (const edge of network?.edges || []) {
    const row = element("p", "relation-evidence");
    row.append(
      sourceLink(nodes.get(edge.source).url, "Comment"),
      document.createTextNode(" → "),
      sourceLink(nodes.get(edge.target).url, "Thread"),
      document.createTextNode(` · ${edge.kind}`),
    );
    evidence.append(row);
  }
}

export function focusSocialPost(reportId) {
  const card = [...document.querySelectorAll(".social-post")].find(
    (node) => node.dataset.reportId === reportId,
  );
  if (card) {
    card.scrollIntoView({ block: "nearest", behavior: "auto" });
    card.focus();
  }
}
