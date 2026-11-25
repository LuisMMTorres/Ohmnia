// BASE: isolated server; generic RC fixture has no catalogue dependencies.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
  const errors = [], frames = [], sessions = new Set();
  let ordinaryRuns = 0;
  page.on("pageerror", e => errors.push(String(e)));
  page.on("request", r => { if (r.url().endsWith("/schematic/simulate")) ordinaryRuns++; });
  page.on("response", async r => {
    if (r.url().endsWith("/advance") && r.ok()) {
      sessions.add(r.url().split("/").at(-2));
      frames.push(await r.json());
    }
  });
  const fixture = JSON.parse(fs.readFileSync(process.env.PROJECT || path.join(__dirname, "fixtures/interactive-bench.json"), "utf8"));
  const connections = fixture.bench_scope_connections["1"];
  const poll = async predicate => { for (let n=0;n<100;n++) { if (await predicate()) return; await new Promise(r=>setTimeout(r,100)); } throw new Error("Condition timed out; last frame: " + JSON.stringify(frames.at(-1)?.time)); };
  const last = name => frames.at(-1)?.data.traces[name]?.values.at(-1);
  try {
    await page.goto(process.env.BASE + "/#simulator");
    await page.evaluate(s => { localStorage.setItem("circuitos.schematic", JSON.stringify(s)); sessionStorage.setItem("circuitos.simulator.view", "protoboard"); }, fixture);
    await page.reload();
    await page.getByRole("button", {name:"Iniciar bancada",exact:true}).click();
    await poll(()=>frames.length>2);
    const bench = page.getByRole("region", {name:"Bancada interativa",exact:true});
    await page.getByLabel("Adicionar instrumento", {exact:true}).selectOption("multimeter");
    await bench.getByLabel("Ponteira +", {exact:true}).selectOption(connections.positive);
    await bench.getByLabel("Ponteira − / COM", {exact:true}).selectOption(connections.negative);
    await page.locator('[data-bb-item="SW1"] [data-actuator]').first().click();
    await poll(()=>last("v(out)")>4.53);
    assert.ok(Math.abs(last("v(out)")-50/11)<.02);
    assert.ok(await bench.locator("polyline[data-channel='1']").getAttribute("points"));
    const points = (await bench.locator("polyline[data-channel='1']").getAttribute("points")).split(" ").map(s=>s.split(",").map(Number));
    assert.ok(points.filter(([x,y])=>x>=70 && x<=950 && y>=25 && y<=385).length>1,"The live signal is outside the oscilloscope screen");
    await poll(async()=>/4[,\.]5/.test(await bench.getByTestId("meter-reading").textContent()));
    const voltage = await bench.getByTestId("meter-reading").textContent();
    assert.match(voltage,/4[,\.]5/);
    await bench.getByRole("button", {name:"Pausar bancada",exact:true}).click();
    await new Promise(r=>setTimeout(r,600)); const paused=frames.length;
    await new Promise(r=>setTimeout(r,600)); assert.equal(frames.length,paused);
    await bench.getByRole("button", {name:"Continuar bancada",exact:true}).click();
    await poll(()=>frames.length>paused);
    await bench.getByRole("button", {name:"HOLD",exact:true}).click();
    const held=await bench.getByTestId("meter-reading").textContent();
    await bench.locator("summary").filter({hasText:"Ajustar canal"}).first().click();
    await bench.getByLabel("Tensão/corrente ajustada (V)", {exact:true}).fill("3");
    await poll(()=>Math.abs(last("v(out)")-30/11)<.01);
    assert.equal(await bench.getByTestId("meter-reading").textContent(),held);
    await bench.getByRole("button", {name:"Liberar HOLD",exact:true}).click();
    await bench.getByLabel("Medida", {exact:true}).selectOption("current");
    await bench.getByLabel("Ramo medido", {exact:true}).selectOption("i(r2)");
    assert.ok(Math.abs(last("i(r2)")-3/11000)<1e-6);
    await bench.getByLabel("Canais do osciloscópio", {exact:true}).selectOption("4");
    assert.equal(await bench.getByLabel("Sinal CH4", {exact:true}).count(),1);
    await bench.getByLabel("Canais do osciloscópio", {exact:true}).selectOption("2");
    await bench.getByLabel("Amplitude A/B", {exact:true}).check();
    await bench.getByRole("button", {name:"Run",exact:true}).waitFor();
    const frozen = await bench.locator("polyline[data-channel='1']").getAttribute("points");
    const count = frames.length;
    await poll(()=>frames.length>count+2);
    assert.equal(await bench.locator("polyline[data-channel='1']").getAttribute("points"),frozen,"Cursor measurement did not freeze the scope acquisition");
    await bench.getByRole("button", {name:"Run",exact:true}).click();
    const board=await page.locator(".circuit-workspace").boundingBox(), dock=await bench.boundingBox();
    assert.ok(dock.x>=board.x+board.width,"Instrument dock overlaps the board");
    await bench.evaluate(el=>el.scrollTop=0);
    await page.screenshot({path:path.join(process.env.SHOTS,"interactive-bench.png"),fullPage:true});
    await page.locator('[data-bb-item="SW1"] [data-actuator]').first().click();
    await poll(()=>last("v(out)")<.001);
    assert.equal(sessions.size,1,"Operating the bench restarted its transient session");
    assert.equal(ordinaryRuns,0,"A switch click started an ordinary simulation");
    const stopped=page.waitForResponse(r=>r.request().method()==="DELETE" && r.url().includes("/bench/"));
    await bench.getByRole("button", {name:"Parar bancada",exact:true}).click();
    assert.equal((await stopped).status(),204);
    assert.deepEqual(errors,[]);
    assert.ok(frames.every((f,i)=>!i || f.time>frames[i-1].time));
    console.log("PASS: continuous time, switch, source adjustment, oscilloscope, multimeter V/A, HOLD, pause/resume, layout and cleanup.");
  } catch(e) {
    await page.screenshot({path:path.join(process.env.SHOTS,"failure.png"),fullPage:true});
    console.error(await page.locator("select").evaluateAll(items=>items.map(s=>({aria:s.getAttribute("aria-label"),labels:[...s.labels].map(l=>l.textContent.slice(0,90))}))));
    throw e;
  } finally { await browser.close(); }
})().catch(e=>{ console.error(e); process.exit(1); });
