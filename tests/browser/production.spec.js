import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { test, expect } from "@playwright/test";

test("production bundle renders geography and events under the deployment CSP", async ({
  page,
}) => {
  const suffix = randomUUID()
    .replaceAll("-", "")
    .slice(0, 24)
    .match(/.{4}/g)
    .join(":");
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8:${suffix}` });
  const url = process.env.OSINT_PRODUCTION_URL;
  test.skip(
    !url,
    "Run a production preview and set OSINT_PRODUCTION_URL to test the built bundle.",
  );
  const source = readFileSync(
    new URL("../../deploy/nginx-headers.conf", import.meta.url),
    "utf8",
  );
  const policy = source.match(/Content-Security-Policy "([^"]+)"/)[1];
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.route(url + "/", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      headers: { ...response.headers(), "content-security-policy": policy },
    });
  });
  await page.goto(url);
  await expect(page.locator('#map canvas[data-rendered="true"]')).toBeVisible();
  await expect
    .poll(async () =>
      Number(
        await page.locator("#map canvas").getAttribute("data-observations"),
      ),
    )
    .toBeGreaterThan(0);
  await page.locator("#sentiment-tab").click();
  await expect(page.locator("#sentiment-chart canvas")).toBeVisible();
  expect(errors).toEqual([]);
});
