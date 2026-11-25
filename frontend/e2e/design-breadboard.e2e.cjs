// Run against an isolated server with the reviewed-catalogue test fixture.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  try {
    const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
    const parts = await (await page.request.get(process.env.BASE + "/api/v1/schematic/parts?kind=zener")).json();
    const pendingPart = parts.find(part => part.part_number === "1N5231B");
    assert.ok(pendingPart, "Unverified catalogue fixture missing");
    // Equivalent to choosing the pending Zener in the component lock controls.
    await page.route("**/api/v1/design/**", async route => {
      if (route.request().method() !== "POST" || !route.request().url().includes("/DM-ZEN")) return route.continue();
      const body = route.request().postDataJSON();
      body.locks = {...body.locks, DZ1: pendingPart.id};
      return route.continue({postData: JSON.stringify(body)});
    });
    const errors = [];
    page.on("pageerror", error => errors.push(String(error)));
    await page.goto(process.env.BASE + "/#design");
    for (const moduleId of ["DM-CHAVE", "DM-OPA", "DM-ZEN"]) {
      await page.goto(process.env.BASE + "/#design");
      await page.reload();
      console.log("Checking", moduleId);
      const response = page.waitForResponse(r => r.url().endsWith(`/design/${moduleId}/breadboard`) && r.request().method() === "POST", {timeout: 120000});
      response.catch(() => {});
      await page.getByLabel("Circuito", { exact: true }).selectOption(moduleId);
      const tab = page.locator("nav[aria-label='Partes do projeto']").getByRole("button", { name: "Protoboard", exact: true });
      await tab.click();
      console.log("Requested breadboard", moduleId);
      const result = await (await response).json();
      assert.equal(result.available, true, JSON.stringify(result));
      fs.writeFileSync(path.join(process.env.SHOTS, moduleId + ".json"), JSON.stringify(result));
      const report = result.assembly.report;
      if (moduleId === "DM-ZEN") {
        const pending = report.issues.filter(i => i.kind === "sem_pinagem");
        assert.equal(report.ok, false, "An unverified Zener must not be certified");
        assert.ok(pending.length, JSON.stringify(report));
        await page.getByText(report.summary, { exact: true }).first().waitFor({ timeout: 30000 });
        assert.ok(result.assembly.guide.filter(s => s.refs.some(ref => ["Za", "Zb"].includes(ref)))
          .every(s => s.text.includes("a verificar") && !s.holes.length));
      } else {
        assert.equal(report.ok, true, JSON.stringify(report));
        await page.getByText(/Montagem confere com o esquemático:/).first().waitFor();
      }
      await page.locator(".bb-design svg").first().waitFor();
      await page.screenshot({ path: path.join(process.env.SHOTS, moduleId + ".png"), fullPage: true });
      console.log(moduleId, "assembly status:", report.ok, "parts:", result.schematic.breadboard.parts.length);
    }
    assert.deepEqual(errors, []);
    console.log("Design breadboard: sourced connections and unverified-pinout warning passed");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
