import { test, expect } from "@playwright/test";

// Reference layers must be tellable apart on the map, not just different in the
// panel. Each layer gets its own pictogram, and the military layer further
// separates naval from air facilities, which is the distinction that matters.

const REFERENCE_LAYERS = ["bases", "nuclear", "spaceports", "ports"];

// Enable the reference layers and wait for the map to be ready.
async function enableReferenceLayers(page) {
  await page.goto("/");
  await page.waitForFunction(
    () => document.querySelector("#map canvas")?.dataset.ready === "true",
    { timeout: 45000 },
  );
  for (const id of REFERENCE_LAYERS)
    await page.locator(`#layers input[data-layer='${id}']`).check();
  await page.waitForTimeout(3500);
}

const mapState = (page) =>
  page.evaluate(() => {
    const d = document.querySelector("#map canvas").dataset;
    return {
      iconDrawn: Number(d.referenceIconDrawn),
      dotDrawn: Number(d.referenceDotDrawn),
      icons: JSON.parse(d.referenceIcons),
      images: JSON.parse(d.referenceImages),
    };
  });

test("each reference layer has its own pictogram in the panel", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector("#layers .layer-row-reference");
  const glyphs = await page.$$eval("#layers .layer-row-reference", (rows) =>
    rows.map((row) => {
      const canvas = row.querySelector("canvas.layer-symbol");
      const pixels = canvas
        .getContext("2d")
        .getImageData(0, 0, canvas.width, canvas.height).data;
      let painted = 0;
      let signature = 0;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] > 0) painted += 1;
        if (index % 28 === 3)
          signature =
            (signature * 31 +
              pixels[index - 3] +
              pixels[index - 2] +
              pixels[index - 1]) >>>
            0;
      }
      return {
        layer: row.querySelector("input").dataset.layer,
        painted,
        signature,
      };
    }),
  );
  for (const glyph of glyphs)
    expect(
      glyph.painted,
      `${glyph.layer} has a drawn pictogram`,
    ).toBeGreaterThan(200);
  const signatures = glyphs.map((glyph) => glyph.signature);
  expect(
    new Set(signatures).size,
    "no two reference layers share a pictogram",
  ).toBe(signatures.length);
});

test("every pictogram is registered and each layer selects its own", async ({
  page,
}) => {
  await enableReferenceLayers(page);
  const { images, icons } = await mapState(page);
  // Six pictograms exist: three military subtypes plus nuclear, spaceport and port.
  expect(images).toHaveLength(6);
  for (const [kind, registered] of images)
    expect(registered, `${kind} pictogram is in the style`).toBe(true);

  const byLayer = Object.fromEntries(icons);
  expect(byLayer.nuclear).toBe("ref-nuclear");
  expect(byLayer.spaceports).toBe("ref-spaceport");
  expect(byLayer.ports).toBe("ref-port");
  // The military layer selects on facility type rather than a single image.
  const bases = JSON.stringify(byLayer.bases);
  expect(bases).toContain("ref-naval");
  expect(bases).toContain("ref-air");
  expect(bases).toContain("ref-military");
  // Ports must not fall through to a military pictogram.
  expect(byLayer.ports).not.toBe(byLayer.nuclear);
  expect(byLayer.ports).not.toBe("ref-military");
});

test("dots carry the world view and pictograms take over when zoomed", async ({
  page,
}) => {
  await enableReferenceLayers(page);
  const wide = await mapState(page);
  expect(wide.dotDrawn, "dots render at world zoom").toBeGreaterThan(0);
  expect(
    wide.iconDrawn,
    "pictograms stay hidden below their zoom threshold",
  ).toBe(0);

  // Centre the map on a feature the map itself reported, so zooming cannot drift
  // off the only thing in view.
  await page.waitForFunction(
    () => document.querySelector("#map canvas")?.dataset.referenceHoverPoint,
    { timeout: 25000 },
  );
  const geometry = await page.evaluate(() => {
    const canvas = document.querySelector("#map canvas");
    const rect = canvas.getBoundingClientRect();
    const [x, y] = canvas.dataset.referenceHoverPoint.split(",").map(Number);
    return {
      centreX: rect.x + rect.width / 2,
      centreY: rect.y + rect.height / 2,
      featureX: rect.x + x,
      featureY: rect.y + y,
    };
  });
  await page.mouse.move(geometry.featureX, geometry.featureY);
  await page.mouse.down();
  await page.mouse.move(geometry.centreX, geometry.centreY, { steps: 16 });
  await page.mouse.up();
  await page.waitForTimeout(1200);
  for (let step = 0; step < 4; step++) {
    await page.locator(".maplibregl-ctrl-zoom-in").click();
    await page.waitForTimeout(750);
  }
  await page.waitForTimeout(2000);

  const near = await mapState(page);
  expect(near.iconDrawn, "pictograms render once zoomed in").toBeGreaterThan(0);
  expect(near.dotDrawn, "dots stop above the pictogram threshold").toBe(0);
});
