import { chromium } from "@playwright/test";
const browser = await chromium.launch({
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
page.on("console", (message) => console.log(message.type(), message.text()));
page.on("pageerror", (error) => console.log("PAGE ERROR", error.message));
page.on("requestfailed", (request) =>
  console.log("REQUEST FAILED", request.url(), request.failure()),
);
await page.goto("http://127.0.0.1:5173");
await page.waitForTimeout(6000);
console.log(
  await page
    .locator("#map canvas")
    .evaluate((node) => ({
      dataset: { ...node.dataset },
      size: [node.width, node.height],
    })),
);
await page.screenshot({ path: "docs/map-probe.png" });
await browser.close();
