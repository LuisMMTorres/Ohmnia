// Breadboard side panels: hiding them gives the board room (remembered on reload); clicking a
// part shows its characteristics; parts and bench instruments can be dragged elsewhere.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const base = process.env.BASE || "http://127.0.0.1:8766";
  const shots = process.env.SHOTS;
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const canvasWidth = () => page.locator(".bb-canvas").evaluate((el) => el.clientWidth);
  try {
    await page.goto(base + "/#simulator");
    const imported = await page.request.post(base + "/api/v1/schematic/import", {
      data: { netlist: "Panels divider\nV1 in 0 5\nR1 in out 1k\nR2 out 0 1k\n.op\n.end" },
    });
    assert.equal(imported.ok(), true, await imported.text());
    const circuit = (await imported.json()).schematic;
    await page.evaluate((c) => {
      localStorage.setItem("circuitos.schematic", JSON.stringify(c));
      localStorage.removeItem("circuitos.breadboard.sidePanels");
      sessionStorage.setItem("circuitos.simulator.view", "protoboard");
    }, circuit);
    await page.reload();
    await page.waitForSelector(".bb-layout");
    await page.getByRole("button", { name: "Montar automaticamente", exact: true }).click();
    await page.waitForSelector(".bb-ok");
    if (shots)
      await page.locator(".bb-layout").screenshot({ path: `${shots}/1-paineis-abertos.png` });
    const open = await canvasWidth();

    await page.getByRole("button", { name: "« Esconder", exact: true }).click();
    const leftHidden = await canvasWidth();
    assert.ok(leftHidden > open + 150, `${leftHidden} vs ${open}`);
    assert.equal(await page.getByRole("button", { name: "Montar automaticamente" }).count(), 0);

    await page.getByRole("button", { name: "Esconder »", exact: true }).click();
    const bothHidden = await canvasWidth();
    assert.ok(bothHidden > leftHidden + 200, `${bothHidden} vs ${leftHidden}`);
    if (shots)
      await page.locator(".bb-layout").screenshot({ path: `${shots}/2-paineis-escondidos.png` });

    await page.reload();
    await page.waitForSelector(".bb-layout");
    assert.equal(await page.locator(".bb-collapsed").count(), 2, "choice is remembered");

    await page.getByRole("button", { name: "Mostrar painel de peças", exact: true }).click();
    await page.getByRole("button", { name: "Mostrar painel de conferência", exact: true }).click();
    assert.equal(await page.locator(".bb-collapsed").count(), 0);
    await page.getByRole("button", { name: "Montar automaticamente", exact: true }).waitFor();

    // clicking a part shows its characteristics in the side panel
    await page.locator('[data-bb-item="R1"]').click();
    await page.locator(".bb-characteristics").waitFor();
    assert.match(await page.locator(".bb-selected h3").innerText(), /R1/);
    assert.match(await page.locator(".bb-characteristics").innerText(), /1k/);
    if (shots)
      await page.locator(".bb-layout").screenshot({ path: `${shots}/3-caracteristicas.png` });

    // a hidden side panel opens again when a part is clicked
    await page.getByRole("button", { name: "Esconder »", exact: true }).click();
    await page.locator('[data-bb-item="R2"]').click();
    await page.locator(".bb-characteristics").waitFor();
    assert.match(await page.locator(".bb-selected h3").innerText(), /R2/);

    // drag the bench supply to another spot: the position is kept in the assembly
    const supply = await page.locator('[data-bb-item="V1"] .instrument-face').boundingBox();
    await page.mouse.move(supply.x + 150, supply.y + 60);
    await page.mouse.down();
    await page.mouse.move(supply.x + 350, supply.y + 120, { steps: 8 });
    await page.mouse.up();
    await page.waitForFunction(
      () =>
        !!JSON.parse(localStorage.getItem("circuitos.schematic")).breadboard.instrument_positions
          ?.V1,
    );
    const moved = await page.locator('[data-bb-item="V1"] .instrument-face').boundingBox();
    assert.ok(moved.x > supply.x + 120, `${moved.x} vs ${supply.x}`);

    // drag a resistor by its body to other holes
    const legsBefore = await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("circuitos.schematic")).breadboard.parts.find(
          (p) => p.ref === "R1",
        ).legs,
    );
    const r1 = await page.locator('[data-bb-item="R1"]').boundingBox();
    await page.mouse.move(r1.x + r1.width / 2, r1.y + r1.height / 2);
    await page.mouse.down();
    await page.mouse.move(r1.x + r1.width / 2 + 120, r1.y + r1.height / 2, { steps: 8 });
    await page.mouse.up();
    await page.waitForFunction(
      (before) =>
        JSON.stringify(
          JSON.parse(localStorage.getItem("circuitos.schematic")).breadboard.parts.find(
            (p) => p.ref === "R1",
          ).legs,
        ) !== before,
      JSON.stringify(legsBefore),
    );
    if (shots) await page.locator(".bb-layout").screenshot({ path: `${shots}/4-arrastado.png` });
    assert.deepEqual(errors, []);
    console.log("protoboard OK", { open, leftHidden, bothHidden });
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
