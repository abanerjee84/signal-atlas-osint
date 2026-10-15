import { test, expect } from "@playwright/test";

// Synthetic responses exist only in this browser context, never in the live DB.
const record = {
  record_id: "1".repeat(32),
  indicator_id: "2".repeat(32),
  title: "Synthetic DShield fixture",
  source_id: "dshield",
  source_family: "sans_isc",
  original_url: "https://isc.sans.edu/api/",
  normalized_value: "8.8.8.8",
  received_at: "2026-10-15T09:00:00Z",
  payload: {
    kind: "scan",
    period_start: "2026-10-15T00:00:00Z",
    period_end: "2026-10-16T00:00:00Z",
    received_at: "2026-10-15T09:00:00Z",
    report_count: 12,
    target_count: 3,
    references: [],
  },
};

async function connect(
  page,
  radar = {
    data: [],
    meta: {
      configured: false,
      basis: "Global provider protocol percentages, not attack counts.",
    },
  },
) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let result = { data: [], meta: { total: 0 } };
    if (url.pathname === "/api/v1/cyber/observations")
      result = {
        data: url.searchParams.get("provider") === "threatfox" ? [] : [record],
        meta: {
          total: url.searchParams.get("provider") === "threatfox" ? 0 : 1,
        },
      };
    else if (url.pathname === `/api/v1/cyber/indicators/${record.indicator_id}`)
      result = {
        data: {
          normalized_value: "8.8.8.8",
          source_families: ["sans_isc"],
          observations: [record],
          malware_candidates: [],
        },
        meta: {},
      };
    else if (url.pathname === "/api/v1/cyber/ddos") result = radar;
    else if (url.pathname === "/api/v1/cyber/enrich") {
      await route.fulfill({
        status: 409,
        json: { message: "Set OSINT_GREYNOISE_API_KEY to use GreyNoise" },
      });
      return;
    }
    await route.fulfill({ json: result });
  });
  await page.goto("/advanced.html");
  await page
    .getByLabel("Server access token")
    .fill("synthetic-browser-fixture");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.locator('button[data-module="cyber"]').click();
}

test("provider history has explicit units, country uncertainty, filters and evidence", async ({
  page,
}) => {
  await connect(page);
  await page
    .getByRole("combobox", { name: "Indicators", exact: true })
    .selectOption("observations");
  await expect(
    page.getByRole("button", { name: record.title, exact: true }),
  ).toBeVisible();
  await expect(page.locator("#summary")).toContainText(
    "Actor and target geography remain unknown",
  );
  await page.getByRole("button", { name: record.title, exact: true }).click();
  await expect(page.locator("#detail")).toContainText("Provider reports");
  await expect(page.locator("#detail")).toContainText("12");
  await expect(page.locator("#detail")).toContainText("Target hosts");
  await expect(page.locator("#detail")).toContainText(
    "Multiple sightings are not independent verification",
  );
  await expect(
    page.getByRole("button", { name: "Save observation to case" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "All observation providers" })
    .selectOption("threatfox");
  await expect(page.locator("#results")).toContainText(
    "No records match this view",
  );
  await page.setViewportSize({ width: 900, height: 900 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("unconfigured Radar and GreyNoise provide useful empty/error states", async ({
  page,
}) => {
  await connect(page);
  await page
    .getByRole("combobox", { name: "Indicators", exact: true })
    .selectOption("ddos");
  await expect(page.locator("#results")).toContainText("backend API token");
  await expect(page.locator("#pagination")).toBeHidden();
  await page.getByRole("button", { name: "Look up an indicator" }).click();
  await page
    .getByLabel("IP, domain, URL, file hash, CVE or AS number")
    .fill("8.8.8.8");
  await page.getByLabel("Provider", { exact: true }).selectOption("greynoise");
  await page.locator('#action-form button[type="submit"]').click();
  await expect(page.locator("#action-form [role=alert]")).toContainText(
    "OSINT_GREYNOISE_API_KEY",
  );
});

test("Radar plots percentages with readable measurements and no incident-count pagination", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await connect(page, {
    data: [
      {
        protocol: "TCP",
        percentage: 30,
        start_at: "2026-10-15T08:00:00Z",
        end_at: "2026-10-15T09:00:00Z",
      },
      {
        protocol: "UDP",
        percentage: 70,
        start_at: "2026-10-15T08:00:00Z",
        end_at: "2026-10-15T09:00:00Z",
      },
    ],
    meta: {
      configured: true,
      basis: "Global provider protocol percentages, not attack counts.",
    },
  });
  await page
    .getByRole("combobox", { name: "Indicators", exact: true })
    .selectOption("ddos");
  await expect(page.locator("#visual canvas")).toBeVisible();
  await expect(page.locator("#results")).toContainText("TCP: 30%");
  await expect(page.locator("#results")).toContainText("UDP: 70%");
  await expect(page.locator("#pagination")).toBeHidden();
  expect(errors).toEqual([]);
});
