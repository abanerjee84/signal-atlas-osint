import { aircraftFacts } from "./aircraft.js";
import { element, relativeTime, sourceLink } from "./api.js";

export function aircraftIdentity(event) {
  const hex = String(event.aircraft?.icao24 || "").toLowerCase();
  const callsign = String(event.aircraft_callsign || "")
    .trim()
    .toUpperCase();
  return /^[a-f0-9]{6}$/.test(hex) ? { hex, callsign } : null;
}

export function matchedAircraftDetails(event, details) {
  const identity = aircraftIdentity(event);
  if (!identity || details?.icao24 !== identity.hex) return null;
  if (details.callsign && details.callsign !== identity.callsign) return null;
  return details;
}

export function trustedAircraftPhoto(photo) {
  try {
    const image = new URL(photo.url),
      link = new URL(photo.link);
    return image.protocol === "https:" &&
      image.host === "t.plnspttrs.net" &&
      !image.username &&
      !image.password &&
      link.protocol === "https:" &&
      link.host === "www.planespotters.net" &&
      !link.username &&
      !link.password &&
      link.pathname.startsWith("/photo/") &&
      typeof photo.credit === "string" &&
      photo.credit.length
      ? photo
      : null;
  } catch {
    return null;
  }
}

let snapshot = {},
  loadedAt = 0,
  pending = null;
export async function loadAircraftRegistry() {
  if (Date.now() - loadedAt > 20000) {
    pending ||= fetch("/aircraft-details.json", {
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
          snapshot = value.items;
      })
      .catch(() => {})
      .finally(() => {
        loadedAt = Date.now();
        pending = null;
      });
    await pending;
  }
  return snapshot;
}
export async function loadAircraftDetails(event) {
  if (!aircraftIdentity(event)) return null;
  const registry = await loadAircraftRegistry();
  return matchedAircraftDetails(event, registry[aircraftIdentity(event).hex]);
}

export function aircraftDetailCard(event, details, interactive = false) {
  details = matchedAircraftDetails(event, details);
  const facts = aircraftFacts(event);
  const card = element("div", "aircraft-hover-card");
  if (!interactive)
    card.append(
      element(
        "div",
        "hover-kind",
        event.aircraft_callsign || event.title || "Aircraft",
      ),
    );
  if (details?.model || details?.type_code) {
    card.append(
      element("p", "aircraft-model", details.model || details.type_code),
    );
  }
  const photo = trustedAircraftPhoto(details?.photo);
  if (photo) {
    const figure = element("figure", "aircraft-photo");
    const image = element("img");
    image.src = photo.url;
    image.alt = `${details.registration || event.aircraft_callsign || "Aircraft"} · ${details.model || "aircraft photograph"}`;
    image.referrerPolicy = "no-referrer";
    image.decoding = "async";
    image.addEventListener("error", () => figure.remove(), { once: true });
    const caption = element(
      "figcaption",
      "",
      `© ${photo.credit} · Planespotters.net`,
    );
    if (interactive) {
      const link = sourceLink(photo.link, "");
      link.setAttribute("aria-label", "Open credited aircraft photograph");
      link.append(image);
      figure.append(link, caption);
    } else figure.append(image, caption);
    card.append(figure);
  }
  const fields = element("dl", "aircraft-hover-facts");
  const entries = [
    ["Registration", details?.registration],
    ["Country", facts["Registration country"]],
    ["Type", details?.type_code],
    ["Callsign operator", details?.operator],
    [
      "Military",
      details?.military === true ? "Registry flagged military" : null,
    ],
    ["Altitude", facts["Barometric altitude"].split(" · ")[0]],
    [
      "Speed / track",
      `${facts["Ground speed"].split(" · ")[0]} · ${facts["Ground track"]}`,
    ],
    ["Vertical rate", interactive ? facts["Vertical rate"] : null],
    ["ICAO24", facts.ICAO24],
  ];
  for (const [label, value] of entries) {
    if (value)
      fields.append(element("dt", "", label), element("dd", "", value));
  }
  card.append(
    fields,
    element(
      "p",
      "hover-meta",
      `OpenSky position · ${relativeTime(event.time_key)}`,
    ),
  );
  if (details?.operator && interactive)
    card.append(
      element("p", "aircraft-credit", "Operator matched from callsign prefix"),
    );
  if (details) {
    card.append(
      interactive
        ? sourceLink(
            `https://globe.airplanes.live/?icao=${details.icao24}`,
            "Aircraft details on Airplanes.live ↗",
          )
        : element("p", "aircraft-credit", "Aircraft details: Airplanes.live"),
    );
  }
  return card;
}
