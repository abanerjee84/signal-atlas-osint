import { test, expect } from "@playwright/test";

test("live infrastructure layer renders clusters, evidence and independent provider filters", async ({
  page,
}) => {
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": "192.0.2.83" });
  await page.addInitScript(() => {
    sessionStorage.setItem("osint.layers", JSON.stringify(["infrastructure"]));
  });
  await page.goto("/");
  const canvas = page.locator(".maplibregl-canvas");
  const controls = page.locator("#infrastructure-controls");
  const layer = page.getByRole("checkbox", { name: /^Cyber infrastructure/ });
  await expect(controls).toBeVisible();
  await expect(page.locator("#infrastructure-status")).toContainText(
    "observations",
  );
  const points = () =>
    canvas.evaluate((node) =>
      JSON.parse(node.dataset.infrastructureHoverPoints || "[]"),
    );
  await expect
    .poll(async () => (await points()).length, { timeout: 20000 })
    .toBeGreaterThan(0);
  const box = await canvas.boundingBox();
  const target = (await points()).find(
    (p) =>
      p.x > 210 && p.x < box.width - 50 && p.y > 100 && p.y < box.height - 40,
  );
  expect(target).toBeTruthy();
  await page.mouse.move(box.x + target.x, box.y + target.y);
  await expect(page.locator(".map-hover-details")).toContainText(
    "infrastructure observations",
  );
  await expect(page.locator(".map-hover-details")).toContainText(
    "provider reports",
  );
  await expect(page.locator(".map-hover-details")).toContainText(
    "not actor or victim attribution",
  );
  await page.locator(".event-button").first().click();
  await expect(page.locator("#event-detail")).toContainText("Provider reports");
  await expect(page.locator("#event-detail")).toContainText(
    "Infrastructure country",
  );
  await expect(page.locator("#event-detail")).toContainText(
    "not actor nationality",
  );
  await expect(
    page.getByRole("link", { name: "Investigate indicator and save evidence" }),
  ).toHaveAttribute("href", /module=cyber&indicator=/);
  await page
    .getByLabel("Observation provider", { exact: true })
    .selectOption("threatfox");
  await expect(page.locator("#infrastructure-status")).toContainText(
    "0 observations",
  );
  await expect(page.locator(".event-button")).toHaveCount(0);
  await expect.poll(async () => (await points()).length).toBe(0);
  await page
    .getByLabel("Observation provider", { exact: true })
    .selectOption("dshield");
  await expect
    .poll(() => page.locator(".event-button").count())
    .toBeGreaterThan(0);
  await expect.poll(async () => (await points()).length).toBeGreaterThan(0);
  await layer.uncheck();
  await expect(controls).toBeHidden();
  await expect.poll(async () => (await points()).length).toBe(0);
});
