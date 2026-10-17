import { test, expect } from "@playwright/test";

// Reference layers must read as published context, not as more observations.
// That covers two things a screenshot alone would not catch: that the row's
// controls stay attached to their label in a 248px panel, and that a reference
// point answers hover with a card that says what kind of thing it is.

async function referenceRows(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll("#layers .layer-row-reference")].map(
      (row) => {
        const rect = row.getBoundingClientRect();
        const label = row.querySelector(".layer-copy > span");
        const labelBox = label.getBoundingClientRect();
        const info = row.querySelector(".layer-info").getBoundingClientRect();
        const note = row.querySelector(".layer-note").getBoundingClientRect();
        const badge = row.querySelector(".layer-count-reference");
        const panel = document
          .querySelector("#left-panel")
          .getBoundingClientRect();
        const middle = (box) => box.top + box.height / 2;
        return {
          layer: row.querySelector("input").dataset.layer,
          rowHeight: Math.round(rect.height),
          overflowsPanel: rect.right > panel.right + 0.5,
          infoSize: `${Math.round(info.width)}x${Math.round(info.height)}`,
          // The defect this guards: a 34px control floating beside a tall wrapped
          // row, detached from the label it belongs to.
          infoOnLabelLine: Math.abs(middle(info) - middle(labelBox)) < 12,
          infoRightOfLabel: info.left >= labelBox.right - 1,
          noteBelowLabel: note.top >= labelBox.bottom - 1,
          noteWithinRow: note.right <= rect.right + 0.5,
          badgeOnNoteLine:
            !!badge && badge.getBoundingClientRect().top >= note.top,
          labelTruncated: label.scrollWidth > label.clientWidth + 1,
          label: label.textContent,
        };
      },
    ),
  );
}

test("reference row controls stay attached to their label", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector("#layers .layer-row-reference");
  await page.waitForTimeout(1200);
  const rows = await referenceRows(page);
  expect(rows.length).toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.overflowsPanel, row.layer).toBe(false);
    expect(row.infoSize, row.layer).toBe("17x17");
    expect(row.infoOnLabelLine, row.layer).toBe(true);
    expect(row.infoRightOfLabel, row.layer).toBe(true);
    expect(row.noteBelowLabel, row.layer).toBe(true);
    expect(row.noteWithinRow, row.layer).toBe(true);
    expect(row.badgeOnNoteLine, row.layer).toBe(true);
    expect(row.labelTruncated, `${row.layer} label truncated`).toBe(false);
    expect(row.rowHeight, `${row.layer} row should stay compact`).toBeLessThan(
      84,
    );
  }
});

test("a reference point answers hover with a summary card", async ({
  page,
}) => {
  test.setTimeout(90000);
  await page.goto("/");
  await page.waitForFunction(
    () => document.querySelector("#map canvas")?.dataset.ready === "true",
    { timeout: 45000 },
  );
  await page.locator("#layers input[data-layer='ports']").check();
  await page.waitForFunction(
    () =>
      Number(
        document.querySelector("#map canvas")?.dataset.referenceLoaded || "0",
      ) > 0 &&
      document.querySelector("#map canvas")?.dataset.referenceHoverPoint,
    { timeout: 25000 },
  );

  // Hover real rendered ports until one answers. Which port the map picks can
  // change between frames, so this retries rather than depending on one pixel.
  let card = null;
  for (let attempt = 0; attempt < 12 && !card; attempt++) {
    const point = await page.evaluate(() => {
      const canvas = document.querySelector("#map canvas");
      const value = canvas.dataset.referenceHoverPoint;
      if (!value) return null;
      const [x, y] = value.split(",").map(Number);
      const rect = canvas.getBoundingClientRect();
      return { x: rect.x + x, y: rect.y + y };
    });
    if (!point) break;
    await page.mouse.move(point.x - 7, point.y - 7);
    await page.mouse.move(point.x, point.y);
    await page.waitForTimeout(250);
    card = await page.evaluate(() => {
      const el = document.querySelector(".event-hover-card");
      if (!el) return null;
      return {
        kind: el.querySelector(".hover-kind")?.textContent,
        title: el.querySelector("strong")?.textContent,
        fields: [...el.querySelectorAll("dt")].map(
          (dt, i) =>
            dt.textContent + " = " + el.querySelectorAll("dd")[i]?.textContent,
        ),
        caveat: el.querySelector(".hover-location")?.textContent,
        link: el.querySelector("a")?.href,
      };
    });
  }

  expect(card, "a port should produce a hover summary card").toBeTruthy();
  expect(card.title, "the card names the feature").toBeTruthy();
  expect(card.kind).toContain("not an observation");
  const fields = Object.fromEntries(card.fields.map((f) => f.split(" = ")));
  expect(
    fields.Country,
    "resolved country when the boundary test covers it",
  ).toBeTruthy();
  expect(fields.Source).toContain("Natural Earth");
  expect(fields.Licence).toBe("Public domain");
  expect(card.caveat, "the card repeats the layer's stated limit").toBeTruthy();
  expect(card.link).toContain("naturalearthdata");
});

test("reference points grow with zoom so they stay reachable", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForFunction(
    () => document.querySelector("#map canvas")?.dataset.ready === "true",
    { timeout: 45000 },
  );
  await page.locator("#layers input[data-layer='ports']").check();
  await page.waitForFunction(
    () =>
      Number(
        document.querySelector("#map canvas")?.dataset.referenceLoaded || "0",
      ) > 0,
    { timeout: 25000 },
  );
  // The world view alone must not leave 3px dots that a pointer cannot find.
  const before = await page.getAttribute(
    "#map canvas",
    "data-reference-hover-point",
  );
  expect(before).toBeTruthy();
  for (let i = 0; i < 3; i++) {
    await page.locator(".maplibregl-ctrl-zoom-in").click();
    await page.waitForTimeout(600);
  }
  const after = await page.getAttribute(
    "#map canvas",
    "data-reference-hover-point",
  );
  expect(after).toBeTruthy();
  expect(after).not.toBe(before);
});
