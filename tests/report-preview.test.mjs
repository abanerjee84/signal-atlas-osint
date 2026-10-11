import test from "node:test";
import assert from "node:assert/strict";
import { countryReportPreviews, reportSummary } from "../src/report-preview.js";

test("an isolated country report supplies a summary without any country-to-country edge", () => {
  const report = {
    report_id: "one",
    title: "South Sudan forces report a deployment",
    excerpt: "The source describes a deployment in South Sudan.",
    countries: ["SS"],
    published_at: "2026-10-11T01:00:00Z",
  };
  const previews = countryReportPreviews("SS", "South Sudan", [report], [], []);
  assert.equal(previews.length, 1);
  assert.equal(reportSummary(previews[0]), report.excerpt);
  assert.equal(
    countryReportPreviews("FR", "France", [report], [], []).length,
    0,
  );
});

test("country previews use retained event evidence and remove duplicate headlines", () => {
  const report = { title: "Army deployment in South Sudan", countries: ["SS"] };
  const event = {
    ...report,
    category: "military",
    country_code: "SS",
    description: "A dated source report.",
  };
  assert.equal(
    countryReportPreviews("SS", "South Sudan", [report], [event], []).length,
    1,
  );
  assert.equal(
    countryReportPreviews("SS", "South Sudan", [], [event], [])[0].description,
    event.description,
  );
});

test("summaries remain source wording, bounded and plain text", () => {
  assert.equal(
    reportSummary({
      description: "<p>Reported   shelling</p>",
      title: "A heading",
    }),
    "Reported shelling",
  );
  const text = "A source reports military deployments near the border. ".repeat(
    10,
  );
  const summary = reportSummary({ description: text }, 100);
  assert(summary.length <= 101);
  assert(summary.endsWith("…"));
  assert(text.startsWith(summary.slice(0, -1)));
});
