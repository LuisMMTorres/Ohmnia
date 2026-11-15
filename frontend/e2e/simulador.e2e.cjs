const { chromium } = require("playwright");
/**
 * E2E of the free simulator (phase 7): every example simulates, Bode/FFT/Monte Carlo/worst
 * case/STEP views render, a SPICE netlist imports, and a circuit drawn from scratch gives the
 * expected operating point. Run with scripts/e2e.sh (needs the built front end and ngspice).
 * Set SHOTS=<dir> to also save the screenshots used in the phase report.
 */
const assert = require("node:assert/strict");
const BASE = process.env.BASE || "http://127.0.0.1:8766";
const OUT = process.env.SHOTS || "";
(async () => {
  let b;
  try {
    b = await chromium.launch();
    const p = await b.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    const errs = [];
    p.on("pageerror", (e) => errs.push(String(e)));
    p.on("response", (r) => {
      if (r.status() >= 400) errs.push(`HTTP ${r.status()} ${r.url()}`);
    });
    p.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    await p.goto(BASE + "/#simulator");
    await p.evaluate(() => localStorage.clear());
    await p.reload();
    await p.waitForSelector(".schematic-canvas", { timeout: 20000 });
    const shot = async (n) => {
      await p.waitForTimeout(700);
      if (OUT) await p.screenshot({ path: OUT + n, fullPage: true });
      console.log("ok", n);
    };
    const example = async (name) => {
      await p.selectOption('select[aria-label="Exemplos"]', name);
      await p.waitForTimeout(400);
    };
    const simulate = async () => {
      await p.click('button:text-is("Simular")');
      await p.waitForSelector("text=/^(Concluída|Falhou)$/", { timeout: 300000 });
      if (await p.locator('b:text-is("Falhou")').count())
        throw new Error("simulation failed: " + (await p.locator(".error").first().innerText()));
      await p.waitForTimeout(1200);
    };
    const field = (scope, re) =>
      p
        .locator(scope + " label")
        .filter({ hasText: re })
        .first()
        .locator("select, input")
        .first();
    const mode = async (m) => {
      await p.click(`.results-view button[role=tab]:text-is("${m}")`);
      await p.waitForTimeout(800);
    };
    const analysis = async (re) => {
      const sel = p.locator(".results-view select").first();
      const opts = await sel.locator("option").allTextContents();
      const o = opts.find((t) => re.test(t));
      await sel.selectOption({ label: o });
      await p.waitForTimeout(600);
    };

    await example("Filtro RC passa-baixas");
    await simulate();
    await shot("01-rc-esquematico-osciloscopio.png");
    await analysis(/frequência/i);
    await mode("Bode");
    await shot("02-rc-bode.png");

    await example("Retificador em ponte com filtro");
    await simulate();
    await shot("03-ponte-osciloscopio.png");
    await mode("FFT / THD");
    await field(".results-view", /^Sinal/).selectOption({ label: "i(v1)" });
    await p.click('.results-view button:text-is("Calcular")');
    await p.waitForSelector("text=THD =", { timeout: 30000 });
    assert.match(await p.locator(".results-view").innerText(), /f₀ = 60 Hz/);
    await shot("04-ponte-fft-thd.png");

    await example("Filtro RC: Monte Carlo");
    await simulate();
    await mode("Bode");
    await shot("05-rc-monte-carlo-bode.png");
    await mode("Estatística");
    await field(".results-view", /^Sinal/).selectOption({ label: "v(out)" });
    await field(".results-view", /^Medida/).selectOption("mag_db_at");
    await field(".results-view", /^em/).fill("1k");
    await p.click('.results-view button:text-is("Calcular")');
    await p.waitForTimeout(1500);
    await shot("06-rc-monte-carlo-histograma.png");

    // worst case on the same circuit, configured through the sweep panel
    await p.click('button.tab:text-is("Varredura, Monte Carlo e pior caso")');
    await field(".analysis-panel", /^Tipo/).selectOption("worstcase");
    await field(".analysis-panel", /^Análise da medida/).selectOption("ac");
    await field(".analysis-panel", /^Sinal/).fill("v(out)");
    await field(".analysis-panel", /^Medida/).selectOption("mag_db_at");
    await field(".analysis-panel", /^Em x/).fill("1k");
    await simulate();
    await mode("Pior caso");
    {
      // analytic extremes of |H(1 kHz)| with R ±5 % and C ±10 % (see docs/validacao/simulador.md)
      const t = await p.locator(".results-view").innerText();
      assert.match(t, /pior caso mínimo -3,676/);
      assert.match(t, /máximo -2,379/);
    }
    await shot("07-rc-pior-caso.png");

    await example("RLC série: STEP de R");
    await simulate();
    await shot("08-rlc-step.png");

    await example("Ruído térmico com varredura de temperatura");
    await simulate();
    {
      const t = await p.locator(".results-view").innerText();
      assert.match(t, /Ruído/);
      assert.match(t, /onoise_spectrum/);
      assert.ok((await p.locator(".results-view .u-over").count()) > 0, "noise curves plotted");
    }
    await shot("09-ruido-temperatura.png");

    await example("Amplificador emissor comum");
    await simulate();
    await shot("10-emissor-comum-tran.png");
    await analysis(/operação/i);
    await shot("11-emissor-comum-op.png");

    // import a SPICE netlist
    await p.click('button:text-is("Importar netlist")');
    await p.fill(
      ".import-box textarea",
      `Divisor com amp-op ideal (importado)
V1 in 0 SIN(0 1 1k)
R1 in n1 10k
R2 n1 out 47k
E1 out 0 0 n1 1e5
.tran 0 3m 0 5u
.end`,
    );
    await p.click('.import-box button:text-is("Importar")');
    await p.waitForTimeout(800);
    await simulate();
    await shot("12-netlist-importada.png");

    // draw a circuit from scratch: V source, resistor, wires, ground, probe
    await p.click('button:text-is("Novo")');
    await p.click('button:text-is("Enquadrar")').catch(() => {});
    const at = async (gx, gy, opts) => {
      // map grid coords through the current view transform
      const pt = await p.evaluate(
        ([gx, gy]) => {
          const s = document.querySelector(".schematic-canvas");
          const g = s.querySelector(":scope > g");
          const m = g.getScreenCTM();
          const P = s.createSVGPoint();
          P.x = gx * 20;
          P.y = gy * 20;
          const r = P.matrixTransform(m);
          return [r.x, r.y];
        },
        [gx, gy],
      );
      await p.mouse.click(pt[0], pt[1], opts);
    };
    await p.click('.palette-item:text-is("Fonte de tensão CC")');
    await at(0, 0);
    await p.click('.palette-item:text-is("Resistor")');
    await at(4, -4);
    await p.click('.palette-item:text-is("Resistor")');
    await at(8, 0, {});
    await p.keyboard.press("r");
    await p.click('.palette-item:text-is("Terra")');
    await at(0, 4);
    await p.click('.palette-item:text-is("Terra")');
    await at(8, 4);
    await p.click('.tool:text-is("Fio (W)")');
    await at(0, -2);
    await at(0, -4);
    await at(2, -4);
    await at(6, -4);
    await at(8, -4);
    await at(8, -2);
    await at(0, 2);
    await at(0, 4);
    await at(8, 2);
    await at(8, 4);
    await p.click('.tool:text-is("Ponta V")');
    await at(8, -4);
    await p.click('.tool:text-is("Selecionar")');
    await p.click('button.tab:text-is("Análises")');
    await p.click('button:text-is("+ Ponto de operação (.op)")');
    await simulate();
    await analysis(/operação/i);
    await shot("13-desenho-do-zero-op.png");
    const txt = await p.locator(".results-view").innerText();
    // default source 5 V across two equal default resistors
    assert.match(txt, /v\(n00\d\)\s+2,5 V/);
    assert.deepEqual(errs, [], "console errors or failed requests");
    console.log("E2E simulador: ok");
  } finally {
    await b?.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
