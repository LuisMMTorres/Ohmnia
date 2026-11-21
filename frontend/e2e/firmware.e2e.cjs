const { chromium } = require("playwright");
const fs = require("node:fs");
const assert = require("node:assert/strict");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(process.env.BASE + "/#simulator");
    const schematic = JSON.parse(fs.readFileSync(process.env.FIRMWARE_PROJECT, "utf8"));
    await page.evaluate(
      (sch) => localStorage.setItem("circuitos.schematic", JSON.stringify(sch)),
      schematic,
    );
    await page.reload();
    const picker = page.getByRole("combobox", { name: "Selecionar componente", exact: true });
    await picker.selectOption("c1");
    const file = page.getByLabel("Carregar firmware da IDE (.hex ou .elf)");
    await file.setInputFiles(process.env.FIRMWARE_HEX);
    await page.getByText("Firmware compilado", { exact: true }).waitFor();
    await file.setInputFiles({
      name: "bad.hex",
      mimeType: "text/plain",
      buffer: Buffer.from(":bad"),
    });
    await page.locator(".properties [role=alert]").waitFor();
    assert.equal(await page.getByText("uno.hex", { exact: true }).count(), 1);
    const submitted = page.waitForResponse(
      (r) => r.url().endsWith("/schematic/simulate") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Simular", exact: true }).click();
    const request = await (await submitted).json();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".simulation-output b")].some((e) =>
          /^(Concluída|Falhou)$/.test(e.textContent),
        ),
      undefined,
      { timeout: 180000 },
    );
    const job = await (
      await page.request.get(process.env.BASE + "/api/v1/simulations/" + request.job_id)
    ).json();
    assert.equal(job.state, "done", JSON.stringify(job.error));
    assert.ok(job.summary.cosim.serial.U1.some((row) => row[1] === "512"));
    await page.reload();
    await picker.selectOption("c1");
    await page.getByText("Firmware compilado", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Retirar firmware e usar código-fonte" }).click();
    await page.getByText("Código-fonte interpretado", { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log("Firmware upload, corrupt-file rejection, simulation, persistence and removal: ok");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
