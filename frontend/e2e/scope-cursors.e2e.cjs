// BASE points to an initialized Ohmnia server. PROJECT contains the ramp/divider fixture.
const {chromium} = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
    const errors = [];
    page.on("pageerror", error => errors.push(String(error)));
    const schematic = JSON.parse(fs.readFileSync(process.env.PROJECT || path.join(__dirname, "fixtures/scope-cursors.json"), "utf8"));
    async function acquire(project) {
      await page.goto(process.env.BASE + "/#simulator");
      await page.evaluate(s => localStorage.setItem("circuitos.schematic", JSON.stringify(s)), project);
      await page.reload();
      const submitted = page.waitForResponse(r => r.url().endsWith("/schematic/simulate") && r.request().method() === "POST");
      await page.getByRole("button", {name: "Simular", exact: true}).click();
      const id = (await (await submitted).json()).job_id;
      for (let n = 0; ; n++) {
        const job = await (await page.request.get(process.env.BASE + "/api/v1/simulations/" + id)).json();
        if (job.state === "done") break;
        assert.notEqual(job.state, "failed", JSON.stringify(job.error));
        assert.ok(n < 100, "simulation timeout");
        await page.waitForTimeout(200);
      }
      await page.getByRole("tab", {name: "Osciloscópio de bancada", exact: true}).click();
      await page.locator("polyline[data-channel='1']").waitFor({state: "attached"});
    }
    await acquire(schematic);
    await page.getByLabel("Sinal CH1", {exact: true}).selectOption("v(in)");
    await page.getByLabel("Sinal CH2", {exact: true}).selectOption("v(out)");
    await page.getByRole("button", {name: "Autoset", exact: true}).click();
    const fullData = page.waitForResponse(r => r.url().includes("max_points=2000000"));
    await page.getByLabel("Tempo A/B", {exact: true}).check();
    await fullData;
    await page.getByLabel("Tempo A (s)", {exact: true}).fill("0.001");
    await page.getByLabel("Tempo B (s)", {exact: true}).fill("0.003");
    const readings = page.getByRole("region", {name: "Leituras dos cursores"});
    const rows = readings.locator("tbody tr");
    await page.waitForTimeout(100);
    assert.match(await page.getByLabel("Diferença de tempo", {exact: true}).textContent(), /2 ms/);
    assert.deepEqual(await rows.nth(0).locator("td").allTextContents(), ["CH1 · v(in) (DC)", "2 V", "-2 V", "-4 V", "0 V", "0 V"]);
    assert.deepEqual(await rows.nth(1).locator("td").allTextContents(), ["CH2 · v(out) (DC)", "1 V", "-1 V", "-2 V", "-1 V", "1 V"]);
    await page.getByLabel("Tempo B (s)").fill("0.001");
    assert.match(await readings.textContent(), /1\/\|Δt\|: —/);
    await page.getByLabel("Tempo B (s)").fill("0.003");
    await page.getByLabel("Amplitude A/B", {exact: true}).check();
    await page.getByLabel("Canal dos cursores de amplitude").selectOption("CH2");
    await page.getByLabel("Amplitude A (V)").fill("-0.25");
    await page.getByLabel("Amplitude B (V)").fill("0.75");
    assert.match(await page.getByLabel("Diferença de amplitude", {exact: true}).textContent(), /1 V/);
    // Drag in SVG coordinates, including its responsive transform and border.
    async function drag(key, from, to) {
      const coords = await page.locator(".scope-measurement-overlay").evaluate((svg, points) => {
        const m = svg.getScreenCTM();
        return points.map(([x,y]) => { const p = new DOMPoint(x,y).matrixTransform(m); return [p.x,p.y]; });
      }, [from, to]);
      assert.ok(await page.locator(`[data-cursor='${key}']`).count());
      await page.mouse.move(...coords[0]); await page.mouse.down();
      await page.mouse.move(...coords[1], {steps: 8}); await page.mouse.up();
    }
    await drag("ta", [290, 350], [510, 350]);
    assert.ok(Math.abs(Number(await page.getByLabel("Tempo A (s)").inputValue()) - 0.002) < 1e-5);
    const before = Number(await page.getByLabel("Amplitude B (V)").inputValue());
    const scale = Number(await page.locator(".scope-channel-grid fieldset").nth(1).locator('input[type=number]').first().inputValue());
    const y = 205 - before / scale * 45;
    await drag("yb", [850, y], [850, y + 25]);
    assert.ok(Number(await page.getByLabel("Amplitude B (V)").inputValue()) < before);
    await page.getByLabel("Canais do osciloscópio").selectOption("4");
    for (let i = 2; i < 4; i++) {
      const channel = page.locator(".scope-channel-grid fieldset").nth(i);
      await channel.getByLabel("Ativar canal").check();
      await page.getByLabel("Sinal CH" + (i + 1), {exact: true}).selectOption(i === 2 ? "v(in)" : "v(out)");
    }
    await page.waitForFunction(() => document.querySelectorAll('.scope-cursor-readouts tbody tr').length === 4);
    await page.getByLabel("Canais do osciloscópio").selectOption("2");
    await page.setViewportSize({width: 700, height: 1000});
    await page.getByRole("button", {name: "Reposicionar cursores"}).click();
    assert.ok(await page.locator('[data-cursor="ta"]').count());
    await page.screenshot({path: process.env.SHOT || "scope-cursors.png", fullPage: true});
    // CC has no fabricated time axis; horizontal measurements remain available.
    const op = structuredClone(schematic);
    op.components[0].kind = "vdc"; op.components[0].params = {dc: "2.5"};
    op.analyses = [{kind: "op", params: {}, enabled: true}];
    await acquire(op);
    assert.equal(await page.getByLabel("Tempo A/B", {exact: true}).isDisabled(), true);
    await page.getByLabel("Amplitude A/B", {exact: true}).check();
    assert.match(await page.getByRole("region", {name: "Leituras dos cursores"}).textContent(), /2,5 V/);
    assert.deepEqual(errors, []);
    console.log("Cursor numeric readouts, channel deltas, zero dt, pointer dragging, responsive layout and CC passed");
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exit(1);});
