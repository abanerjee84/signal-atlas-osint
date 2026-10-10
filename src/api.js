export async function api(path, { signal, token, body } = {}) {
  const response = await fetch(`/api/${path}`, {
    signal,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    method: body ? "POST" : "GET",
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(
      `Server returned an unreadable response (${response.status})`,
    );
  }
  if (!response.ok)
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : `Request failed (${response.status})`,
    );
  return payload;
}

export function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = String(text);
  return node;
}

export function sourceLink(url, title) {
  const link = element("a", "", title);
  try {
    const parsed = new URL(url, window.location.origin);
    if (!["https:", "http:"].includes(parsed.protocol))
      return element("span", "", "Invalid source reference");
    link.href = parsed.href;
  } catch {
    return element("span", "", "Invalid source reference");
  }
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

export const dateText = (value) =>
  value
    ? new Date(value).toISOString().replace("T", " ").slice(0, 19) + " UTC"
    : "Unknown";

export function relativeTime(value) {
  const minutes = Math.floor((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 0) return "Future-dated";
  if (minutes < 1) return "<1m ago";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}
