import { api, element, dateText, sourceLink } from "./api.js";

export function createMonitoringWorkflows({
  onGeometry,
  onObservation,
  onRefresh,
  getAt,
  getBounds,
}) {
  const panel = document.querySelector("#investigations-panel");
  const $ = (selector) => panel.querySelector(selector);
  const token = () => document.querySelector("#operator-token").value;
  const empty = () => ({ type: "FeatureCollection", features: [] });
  let sceneItems = [];
  panel.innerHTML = `
    <h2>Investigation tools</h2>
    <p id="workflow-status" role="status">Choose a workflow. Protected actions use Operator access above.</p>
    <label for="workflow-case">Case ID for evidence attachments (optional)</label>
    <input id="workflow-case" maxlength="32" placeholder="Existing investigation case ID" />
    <a href="/advanced.html">Open investigation cases</a>
    <details><summary>Source coverage and setup</summary><div id="workflow-capabilities"></div></details>
    <details id="watch-tools"><summary>Spatial and entity watches</summary>
      <form id="watch-form">
        <label for="watch-name">Watch name</label><input id="watch-name" required maxlength="150" />
        <label for="watch-geometry">Area or route geometry (GeoJSON, optional for an entity watch)</label><textarea id="watch-geometry" rows="3"></textarea>
        <button type="button" id="watch-map-area">Use map bounds</button>
        <label for="watch-radius">Point radius or route corridor (km)</label><input id="watch-radius" type="number" value="5" min="0" max="1000" step="0.1" />
        <label for="watch-entity">Exact entity ID (optional)</label><input id="watch-entity" maxlength="512" />
        <label for="watch-source">Source ID (optional)</label><input id="watch-source" maxlength="100" />
        <label for="watch-mode">Alert when</label><select id="watch-mode"><option value="enter">Entity enters the area</option><option value="new_match">A new matching observation arrives</option></select>
        <label class="check-label"><input id="watch-existing" type="checkbox" /> Include fresh retained observations</label>
        <button type="submit">Save watch</button>
      </form>
      <div class="workflow-actions"><button id="watch-refresh">Load watches</button><button id="watch-evaluate">Evaluate now</button></div>
      <div id="watch-list"></div>
    </details>
    <details id="alert-tools"><summary>Retained alerts</summary><button id="alerts-refresh">Load alerts</button><div id="alerts-list"></div></details>
    <details id="history-tools"><summary>Entity observation history</summary>
      <form id="entity-history-form"><label for="history-source">Source ID</label><input id="history-source" required maxlength="100" />
      <label for="history-entity">Entity ID</label><input id="history-entity" required maxlength="512" />
      <label for="history-hours">Look back (hours)</label><input id="history-hours" type="number" min="1" max="168" value="24" />
      <button>Load history and trail</button></form><div id="history-results"></div>
    </details>
    <details id="imagery-tools"><summary>Imagery and measured change</summary>
      <form id="imagery-form"><label for="imagery-provider">Catalog</label><select id="imagery-provider"><option value="sentinel2">Sentinel-2 optical imagery</option><option value="opera-water">OPERA surface-water products</option><option value="opera-disturbance">OPERA disturbance products</option></select>
        <label for="imagery-bbox">Area: west, south, east, north</label><input id="imagery-bbox" required />
        <button type="button" id="imagery-map-area">Use map bounds</button>
        <label for="imagery-start">Acquired after (UTC)</label><input id="imagery-start" type="datetime-local" required />
        <label for="imagery-end">Acquired before (UTC)</label><input id="imagery-end" type="datetime-local" required />
        <label for="imagery-cloud">Maximum cloud cover (%)</label><input id="imagery-cloud" type="number" value="40" min="0" max="100" />
        <button>Search scenes</button>
      </form><div class="workflow-actions"><button id="scenes-refresh">Load retained scenes</button><button id="scene-footprints">Show footprints</button></div><div id="scene-list"></div>
      <form id="comparison-form"><label for="comparison-kind">Comparison</label><select id="comparison-kind"><option value="water">Classified surface-water change</option><option value="ndvi">Reflectance-derived NDVI change</option></select>
        <label for="water-classes">Water classes from the product specification</label><input id="water-classes" value="1,2" />
        <label for="valid-classes">Valid classes from the product specification</label><input id="valid-classes" value="0,1,2,3" />
        <p class="muted">Select Before and After from one product collection. Comparisons use a small area, quality masks and a bounded download budget. Catalog availability alone is not a detected event.</p>
        <button>Compare selected acquisitions</button>
      </form><div id="comparison-results"></div>
    </details>
    <details id="asset-tools"><summary>Infrastructure and supplier references</summary>
      <form id="asset-import-form"><label for="asset-kind">Asset kind</label><select id="asset-kind"><option value="supplier">Reviewed suppliers</option><option value="power-plant">Power plants</option><option value="data-center">Data centers</option><option value="cable">Submarine cables</option></select>
      <label for="asset-source">Source ID</label><input id="asset-source" required pattern="[a-z][a-z0-9_-]{1,70}" />
      <label for="asset-name">Dataset name</label><input id="asset-name" required maxlength="200" />
      <label for="asset-version">Dataset version</label><input id="asset-version" required maxlength="100" />
      <label for="asset-license">License or permission basis</label><input id="asset-license" required maxlength="500" />
      <label for="asset-url">Original dataset URL</label><input id="asset-url" type="url" required />
      <label for="asset-file">Published or authorized GeoJSON</label><input id="asset-file" type="file" accept=".json,.geojson,application/json" required />
      <p class="muted">Features need stable IDs and names. Split large exports into requests below 64 KiB. Reference locations do not establish operating state or dependency.</p><button>Import reference features</button></form>
      <button id="assets-refresh">Show retained reference geometry</button><div id="asset-results"></div>
    </details>
    <details id="exposure-tools"><summary>Asset exposure by proximity</summary>
      <form id="exposure-form"><label for="exposure-kind">Asset kind</label><select id="exposure-kind"><option value="supplier">Suppliers</option><option value="power-plant">Power plants</option><option value="data-center">Data centers</option><option value="cable">Cables</option></select>
      <label for="exposure-radius">Nearby observation radius (km)</label><input id="exposure-radius" type="number" min="0.1" max="500" step="0.1" value="50" /><button>Find nearby observations</button></form><div id="exposure-results"></div>
    </details>
    <details id="recon-tools"><summary>Passive lookups and entity enrichment</summary>
      <form id="recon-form"><label for="recon-kind">Public record lookup</label><select id="recon-kind"><option value="dns">DNS</option><option value="rdap">RDAP registration</option><option value="certificates">Certificate transparency</option><option value="wikidata">Wikidata entity candidates</option><option value="sanctions">OFAC SDN text candidates</option></select>
      <label for="recon-target">Domain, public IP or entity name</label><input id="recon-target" required maxlength="200" /><button>Read public records</button></form><div id="recon-results"></div>
    </details>
    <details id="sample-tools"><summary>Authorized sample and assessment imports</summary>
      <form id="sample-import-form"><label for="sample-kind">Export format</label><select id="sample-kind"><option value="wastewater_export">Wastewater sample features</option><option value="published_assessments">Published emergency assessment features</option><option value="tinygs">Authorized TinyGS reception records</option></select>
      <label for="sample-license">Permission basis</label><input id="sample-license" required minlength="10" maxlength="500" />
      <label for="sample-file">Authorized JSON or CSV export</label><input id="sample-file" type="file" accept=".json,.geojson,.csv,application/json,text/csv" required />
      <p class="muted">Samples require original IDs, acquisition/sample dates, values, units, quality and source links. Published assessments need geometry, product type and method. Provider download restrictions remain in force.</p><button>Import authorized observations</button></form>
    </details>
    <button id="workflow-clear-geometry">Clear investigation overlay</button>
  `;
  const status = (message) => {
    $("#workflow-status").textContent = message;
    if (panel.hidden)
      document.querySelector("#monitor-message").textContent = message;
  };
  function showTools(value) {
    panel.hidden = !value;
    document.querySelector("#observations-panel").hidden = value;
    document
      .querySelector("#show-observations")
      .setAttribute("aria-pressed", String(!value));
    document
      .querySelector("#show-investigations")
      .setAttribute("aria-pressed", String(value));
  }
  document
    .querySelector("#show-investigations")
    .addEventListener("click", () => showTools(true));
  document
    .querySelector("#show-observations")
    .addEventListener("click", () => showTools(false));
  async function request(path, body) {
    if (!token()) {
      document.querySelector("#operator-access").open = true;
      document.querySelector("#operator-token").focus();
      throw new Error(
        "Enter the local administrator token in Operator access.",
      );
    }
    return api(`monitoring/${path}`, {
      token: token(),
      ...(body === undefined ? {} : { body }),
    });
  }
  function action(selector, handler, event = "click") {
    $(selector).addEventListener(event, async (e) => {
      e.preventDefault();
      const button =
        e.currentTarget.tagName === "FORM"
          ? e.currentTarget.querySelector("button:not([type='button'])")
          : e.currentTarget;
      button.disabled = true;
      status("Working…");
      try {
        await handler(e);
      } catch (error) {
        status(error.message);
      } finally {
        button.disabled = false;
      }
    });
  }
  const inspect = (item) => {
    showTools(false);
    onObservation(item);
  };
  function summary(container, result) {
    container.replaceChildren();
    const facts = element("dl", "workflow-facts");
    for (const [key, value] of Object.entries(result)) {
      if (
        value == null ||
        typeof value === "object" ||
        ["id", "cached"].includes(key)
      )
        continue;
      facts.append(
        element("dt", "", key.replaceAll("_", " ")),
        element("dd", "", String(value)),
      );
    }
    container.append(facts);
  }
  function attachButton(kind, id) {
    const button = element("button", "", "Attach to case");
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const caseId = $("#workflow-case").value.trim();
        if (!/^[a-f0-9]{32}$/.test(caseId))
          throw new Error(
            "Enter an existing case ID above before attaching evidence.",
          );
        await request("evidence", { case_id: caseId, kind, reference_id: id });
        status("Immutable evidence snapshot attached to the case.");
      } catch (error) {
        status(error.message);
      } finally {
        button.disabled = false;
      }
    });
    return button;
  }
  function bounds() {
    const b = getBounds();
    if (!b || b[2] - b[0] > 10 || b[3] - b[1] > 10 || b[0] >= b[2])
      throw new Error(
        "Zoom into a non-wrapping area smaller than 10 by 10 degrees.",
      );
    return b.map((value) => Math.round(value * 100000) / 100000);
  }
  function parseBbox() {
    const b = $("#imagery-bbox").value.split(",").map(Number);
    if (b.length !== 4 || b.some((value) => !Number.isFinite(value)))
      throw new Error("Enter west, south, east and north as four coordinates.");
    return b;
  }
  async function readFile(selector) {
    const file = $(selector).files[0];
    if (!file || file.size > 60000)
      throw new Error(
        "Choose a JSON/GeoJSON export below 60 kB, or split it into smaller batches.",
      );
    return JSON.parse(await file.text());
  }
  async function loadWatches() {
    const data = await request("watches");
    const list = $("#watch-list");
    list.replaceChildren();
    for (const row of data.items) {
      const node = element("div", "workflow-row");
      node.append(
        element("strong", "", row.name),
        element(
          "p",
          "muted",
          `${row.enabled ? "Enabled" : "Disabled"} · ${row.config.mode} · ${row.config.cooldown_seconds}s cooldown`,
        ),
      );
      const toggle = element("button", "", row.enabled ? "Disable" : "Enable");
      toggle.addEventListener("click", async () => {
        try {
          await request(`watches/${row.id}/enabled`, { enabled: !row.enabled });
          await loadWatches();
        } catch (e) {
          status(e.message);
        }
      });
      node.append(toggle);
      list.append(node);
    }
    status(
      data.items.length
        ? `${data.items.length} saved watches.`
        : "No saved watches. Collection continues independently of this panel.",
    );
  }
  action("#watch-map-area", () => {
    const [w, s, e, n] = bounds();
    $("#watch-geometry").value = JSON.stringify({
      type: "Polygon",
      coordinates: [
        [
          [w, s],
          [e, s],
          [e, n],
          [w, n],
          [w, s],
        ],
      ],
    });
    status("Map bounds copied into the watch geometry.");
  });
  action(
    "#watch-form",
    async () => {
      await request("watches", {
        name: $("#watch-name").value,
        geometry: $("#watch-geometry").value.trim()
          ? JSON.parse($("#watch-geometry").value)
          : null,
        radius_km: Number($("#watch-radius").value),
        entity_id: $("#watch-entity").value.trim(),
        source_id: $("#watch-source").value.trim(),
        mode: $("#watch-mode").value,
        include_existing: $("#watch-existing").checked,
      });
      await loadWatches();
      status(
        "Watch saved. The collector evaluates new retained observations every 15 seconds.",
      );
    },
    "submit",
  );
  action("#watch-refresh", loadWatches);
  action("#watch-evaluate", async () => {
    const d = await request("watches/evaluate", {});
    status(
      `${d.alerts_created} alerts created. Load Retained alerts to inspect them.`,
    );
  });
  action("#alerts-refresh", async () => {
    const data = await request("alerts");
    const list = $("#alerts-list");
    list.replaceChildren();
    for (const row of data.items) {
      const node = element("div", "workflow-row");
      node.append(
        element("strong", "", row.name),
        element("p", "", row.snapshot.observation.title),
        element("p", "muted", dateText(row.triggered_at)),
      );
      const view = element("button", "", "Inspect evidence");
      view.addEventListener("click", () => inspect(row.snapshot.observation));
      node.append(view, attachButton("alert", row.id));
      if (!row.acknowledged_at) {
        const ack = element("button", "", "Acknowledge");
        ack.addEventListener("click", async () => {
          try {
            await request(`alerts/${row.id}/acknowledge`, {});
            ack.remove();
            status("Alert acknowledged.");
          } catch (e) {
            status(e.message);
          }
        });
        node.append(ack);
      }
      list.append(node);
    }
    status(
      `${data.items.length} retained alerts${data.truncated ? "; response capped" : ""}.`,
    );
  });
  async function history(source, entity, hours = 24) {
    const query = new URLSearchParams({
      source_id: source,
      entity_id: entity,
      hours: String(hours),
    });
    if (getAt()) query.set("at", getAt());
    const d = await request(`entity-history?${query}`);
    onGeometry(d.trail);
    const list = $("#history-results");
    list.replaceChildren();
    for (const item of d.items.slice(-150)) {
      const button = element("button", "observation-row");
      button.append(
        element("strong", "", item.title),
        element("small", "", dateText(item.observed_at)),
      );
      button.addEventListener("click", () => inspect(item));
      list.append(button);
    }
    status(
      `${d.items.length} retained positions/versions${d.truncated ? "; response capped" : ""}. Trails stop at dateline crossings and long observation gaps.`,
    );
  }
  action(
    "#entity-history-form",
    () =>
      history(
        $("#history-source").value.trim(),
        $("#history-entity").value.trim(),
        Number($("#history-hours").value),
      ),
    "submit",
  );
  $("#imagery-start").value = new Date(Date.now() - 30 * 86400000)
    .toISOString()
    .slice(0, 16);
  $("#imagery-end").value = new Date().toISOString().slice(0, 16);
  action("#imagery-map-area", () => {
    $("#imagery-bbox").value = bounds().join(",");
    status("Map bounds copied into the imagery query.");
  });
  function renderScenes(data) {
    sceneItems = data.items;
    const list = $("#scene-list");
    list.replaceChildren();
    for (const item of sceneItems) {
      const row = element("div", "workflow-row");
      row.append(
        element("strong", "", item.native_id),
        element(
          "p",
          "muted",
          `${dateText(item.acquired_at)}${item.metadata.cloud_percent != null ? ` · ${item.metadata.cloud_percent}% cloud` : ""}`,
        ),
      );
      for (const [name, label] of [
        ["before", "Before"],
        ["after", "After"],
      ]) {
        const field = element("label", "check-label");
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `scene-${name}`;
        radio.value = item.id;
        field.append(radio, document.createTextNode(label));
        row.append(field);
      }
      if (item.assets.thumbnail) {
        const button = element("button", "", "Load preview");
        button.addEventListener("click", async () => {
          button.disabled = true;
          try {
            if (!token())
              throw new Error("Enter the local administrator token first.");
            const response = await fetch(
              `/api/monitoring/scenes/${item.id}/preview`,
              { headers: { Authorization: `Bearer ${token()}` } },
            );
            if (!response.ok)
              throw new Error(
                "Preview unavailable; open the original scene reference.",
              );
            const image = element("img", "workflow-preview");
            image.alt = `Acquisition preview for ${item.native_id}`;
            const url = URL.createObjectURL(await response.blob());
            image.onload = () => URL.revokeObjectURL(url);
            image.src = url;
            row.append(image);
            button.remove();
          } catch (e) {
            status(e.message);
            button.disabled = false;
          }
        });
        row.append(button);
      }
      row.append(
        sourceLink(item.metadata.source_url, "Original scene reference"),
        attachButton("scene", item.id),
      );
      list.append(row);
    }
    status(
      `${data.items.length} acquisition-dated catalog records${data.truncated ? "; more may be available" : ""}. These records establish product availability, not detected damage.`,
    );
  }
  action(
    "#imagery-form",
    async () => {
      renderScenes(
        await request("scenes/search", {
          provider: $("#imagery-provider").value,
          bbox: parseBbox(),
          start: $("#imagery-start").value + "Z",
          end: $("#imagery-end").value + "Z",
          max_cloud: Number($("#imagery-cloud").value),
          limit: 20,
        }),
      );
    },
    "submit",
  );
  action("#scenes-refresh", async () => renderScenes(await request("scenes")));
  action("#scene-footprints", () => {
    onGeometry({
      type: "FeatureCollection",
      features: sceneItems
        .filter((r) => r.geometry)
        .map((r) => ({
          type: "Feature",
          geometry: r.geometry,
          properties: { title: r.native_id, acquired_at: r.acquired_at },
        })),
    });
    status(
      "Retained acquisition footprints shown on the investigation overlay.",
    );
  });
  action(
    "#comparison-form",
    async () => {
      const before = $("input[name='scene-before']:checked")?.value,
        after = $("input[name='scene-after']:checked")?.value;
      if (!before || !after)
        throw new Error("Choose one Before and one After acquisition.");
      const d = await request("scenes/compare", {
        before_id: before,
        after_id: after,
        kind: $("#comparison-kind").value,
        bbox: parseBbox(),
        water_classes: $("#water-classes").value.split(",").map(Number),
        valid_classes: $("#valid-classes").value.split(",").map(Number),
      });
      summary($("#comparison-results"), d);
      $("#comparison-results").append(attachButton("analysis", d.id));
      status(
        "Measurement retained with source acquisitions, units, quality coverage and method.",
      );
    },
    "submit",
  );
  action(
    "#asset-import-form",
    async () => {
      const d = await readFile("#asset-file");
      const result = await request("assets/import", {
        source_id: $("#asset-source").value,
        name: $("#asset-name").value,
        kind: $("#asset-kind").value,
        version: $("#asset-version").value,
        license: $("#asset-license").value,
        source_url: $("#asset-url").value,
        features: d.features || d,
      });
      status(`${result.stored} versioned reference features imported.`);
      onRefresh();
    },
    "submit",
  );
  action("#assets-refresh", async () => {
    const d = await request("assets");
    onGeometry({
      type: "FeatureCollection",
      features: d.items
        .filter((r) => r.geometry)
        .map((r) => ({
          type: "Feature",
          geometry: r.geometry,
          properties: { title: r.name, kind: r.kind, version: r.version },
        })),
    });
    const list = $("#asset-results");
    list.replaceChildren();
    for (const item of d.items.slice(0, 100)) {
      const row = element("div", "workflow-row");
      row.append(
        element("strong", "", item.name),
        element("p", "muted", `${item.kind} · ${item.version}`),
        attachButton("asset", item.id),
      );
      list.append(row);
    }
    status(
      `${d.items.length} versioned reference features${d.truncated ? "; response capped" : ""}.`,
    );
  });
  action(
    "#exposure-form",
    async () => {
      const d = await request("exposure", {
        kind: $("#exposure-kind").value,
        radius_km: Number($("#exposure-radius").value),
        hours: 24,
      });
      const list = $("#exposure-results");
      list.replaceChildren(
        element("p", "muted", d.basis),
        attachButton("analysis", d.id),
      );
      for (const item of d.items) {
        const row = element("div", "workflow-row");
        row.append(element("strong", "", item.asset.name));
        for (const observation of item.nearby_observations) {
          row.append(
            sourceLink(observation.source_url, observation.title),
            element(
              "p",
              "muted",
              `${observation.distance_km} km · ${dateText(observation.observed_at)} · ${observation.precision}`,
            ),
          );
        }
        list.append(row);
      }
      status(
        `${d.items.length} assets with nearby observations${d.truncated ? "; incomplete response coverage" : ""}. Proximity is not a confirmed impact.`,
      );
    },
    "submit",
  );
  action(
    "#recon-form",
    async () => {
      const d = await request("recon", {
        kind: $("#recon-kind").value,
        target: $("#recon-target").value.trim(),
      });
      const list = $("#recon-results");
      summary(list, d);
      if (d.lookup_id) list.append(attachButton("lookup", d.lookup_id));
      for (const r of d.candidates || d.certificates || d.answers || []) {
        const row = element("div", "workflow-row");
        row.append(
          element(
            "strong",
            "",
            r.label ||
              r.name ||
              r.common_name ||
              r.data ||
              r.id ||
              "Public record",
          ),
        );
        if (r.description || r.match)
          row.append(element("p", "muted", r.description || r.match));
        if (r.source_url) row.append(sourceLink(r.source_url, "Source record"));
        if (d.kind === "wikidata" && d.lookup_id) {
          const retain = element("button", "", "Retain candidate graph");
          retain.addEventListener("click", async () => {
            retain.disabled = true;
            try {
              const caseId = $("#workflow-case").value.trim();
              const result = await request("enrichment/retain", {
                lookup_id: d.lookup_id,
                candidate_id: r.id,
                ...(caseId ? { case_id: caseId } : {}),
              });
              status(
                `${result.relationship_ids.length} source-claimed relationships retained. The candidate remains unverified.`,
              );
            } catch (error) {
              status(error.message);
            } finally {
              retain.disabled = false;
            }
          });
          row.append(retain);
        }
        for (const relation of r.relations || [])
          row.append(
            element(
              "p",
              "",
              `${relation.relation}: ${typeof relation.value === "object" ? relation.value.id || JSON.stringify(relation.value) : relation.value}`,
            ),
          );
        list.append(row);
      }
      status(
        `Passive ${d.kind} records loaded${d.cached ? " from cache" : ""}. Candidate names and relationships require analyst verification.`,
      );
    },
    "submit",
  );
  action(
    "#sample-import-form",
    async () => {
      const file = $("#sample-file").files[0];
      if (!file || file.size > 60000)
        throw new Error(
          "Choose an authorized export below 60 kB, or split it into smaller batches.",
        );
      const payload = file.name.toLowerCase().endsWith(".csv")
        ? { csv_text: await file.text() }
        : null;
      let records = payload;
      if (!records) {
        const d = await readFile("#sample-file");
        records = { records: d.features || d.records || d };
      }
      const result = await request("observations/import", {
        kind: $("#sample-kind").value,
        permission_basis: $("#sample-license").value,
        ...records,
      });
      status(`${result.stored} authorized source observations retained.`);
      onRefresh();
    },
    "submit",
  );
  action("#workflow-clear-geometry", () => {
    onGeometry(empty());
    status("Investigation overlay cleared.");
  });
  return {
    catalog(data) {
      const list = $("#workflow-capabilities");
      list.replaceChildren();
      for (const item of data.capabilities || []) {
        const row = element("div", "workflow-row");
        row.append(element("strong", "", item.name));
        for (const id of item.sources) {
          const source = data.sources.find((r) => r.source_id === id);
          if (source)
            row.append(
              element(
                "p",
                "muted",
                `${source.name}: ${source.state || "never_run"}${source.access_requirement ? ` · ${source.access_requirement}` : ""}`,
              ),
            );
        }
        if (!item.sources.length)
          row.append(
            element("p", "muted", "Local workflow; requires operator access."),
          );
        list.append(row);
      }
    },
    inspectActions(container, item) {
      if (!item.source_id || !item.entity_id) return;
      const button = element("button", "", "Inspect entity history");
      button.addEventListener("click", async () => {
        showTools(true);
        $("#history-tools").open = true;
        $("#history-source").value = item.source_id;
        $("#history-entity").value = item.entity_id;
        try {
          await history(item.source_id, item.entity_id);
        } catch (e) {
          status(e.message);
        }
      });
      container.append(button);
      if (/^[a-f0-9]{64}$/.test(item.id || ""))
        container.append(attachButton("observation", item.id));
    },
  };
}
