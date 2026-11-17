const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } });
  const base = process.env.BASE || "http://127.0.0.1:8766";
  const simulate = async () => {
    await page.getByRole("button", { name: "Simular", exact: true }).click();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".simulation-output b")].some(
          (el) => el.textContent === "Concluída",
        ),
      undefined,
      { timeout: 120000 },
    );
  };
  const open = async (sch) => {
    await page.evaluate((circuit) => {
      localStorage.setItem("circuitos.schematic", JSON.stringify(circuit));
      sessionStorage.setItem("circuitos.simulator.view", "protoboard");
    }, sch);
    await page.reload();
    await page.waitForSelector(".bb-layout");
  };
  const points = async (selector) => {
    await page.waitForSelector(selector, { state: "attached" });
    return (await page.locator(selector).getAttribute("points"))
      .split(" ")
      .map((pair) => pair.split(",").map(Number));
  };
  try {
    await page.goto(base + "/#simulator");
    const imported = await page.request.post(base + "/api/v1/schematic/import", {
      data: { netlist: "DC divider\nV1 in 0 5\nR1 in out 1k\nR2 out 0 1k\n.op\n.end" },
    });
    assert.equal(imported.ok(), true, await imported.text());
    const sch = (await imported.json()).schematic;
    sch.probes = [{ id: "dc-v", kind: "v", name: "CH1", target: { net: "out" } }];
    sch.bench_scope_channels = 2;
    await open(sch);
    const mounted = page.waitForResponse(
      (r) => r.url().endsWith("/breadboard/auto") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Montar automaticamente", exact: true }).click();
    assert.equal((await (await mounted).json()).report.ok, true);
    await simulate();
    let coords = await points('.bench-scope polyline[data-channel="1"]');
    assert.equal(coords.length, 2);
    assert.equal(coords[0][1], coords[1][1]);
    assert.ok(coords[0][0] < coords[1][0]);
    assert.ok(coords[0][1] >= 25 && coords[0][1] <= 385, "DC line is visible in the screen");
    assert.match(
      await page.locator(".bench-scope").getByLabel("Leitura CH1", { exact: true }).innerText(),
      /2,5 V/,
    );
    await page.getByRole("tab", { name: "Osciloscópio de bancada", exact: true }).click();
    coords = await points('.results-view polyline[data-channel="1"]');
    assert.equal(coords[0][1], coords[1][1]);
    if (process.env.SHOTS)
      await page
        .locator(".bench-scope")
        .screenshot({ path: process.env.SHOTS + "scope-dc-op.png" });
    const assembled = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("circuitos.schematic")),
    );
    await open({
      ...assembled,
      analyses: [{ kind: "tran", params: { tstop: "1m", tmax: "10u" }, enabled: true }],
    });
    await simulate();
    coords = await points('.bench-scope polyline[data-channel="1"]');
    assert.ok(coords.length > 2);
    const ys = coords.map((p) => p[1]);
    assert.ok(Math.max(...ys) - Math.min(...ys) < 1e-5, "DC transient remains horizontal");
    await open({ ...assembled, probes: [{ id: "dc-i", kind: "i", component: "V1", pin: "p" }] });
    await simulate();
    coords = await points('.bench-scope polyline[data-channel="1"]');
    assert.equal(coords[0][1], coords[1][1]);
    assert.match(
      await page.locator(".bench-scope").getByLabel("Leitura CH1", { exact: true }).innerText(),
      /2,5 mA/,
    );
    await open({ ...assembled, probes: [] });
    await simulate();
    assert.match(await page.locator('.bench-scope p[role="status"]').innerText(), /Nenhuma probe/);
    assert.equal(await page.locator(".bench-scope polyline").count(), 0);
    console.log("DC oscilloscope E2E: ok (OP, constant transient, current probe, no probe)");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
