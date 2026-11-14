import { type ReactNode, useEffect, useMemo, useState } from "react";
import { bench, CalcStep, catalog, ComponentSummary, ZenerBenchIn, ZenerBenchOut } from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { fitScale } from "../components/benchScale";
import { OutsidePoints } from "../components/OutsidePoints";
import { SignalPlot, Trace } from "../components/SignalPlot";
import { formatRaw } from "../format";
import { num } from "./BenchPage";

function text(value: number, digits = 4): string {
  return formatRaw(Number(value.toPrecision(digits)), "");
}

/** BD-ZENER: reverse I×V curve of a didactic Zener model, optionally fitted to a datasheet. */
export function ZenerBench({ selector }: { selector: ReactNode }) {
  const [vz0, setVz0] = useState("5");
  const [rz, setRz] = useState("2");
  const [isr, setIsr] = useState("1");
  const [nr, setNr] = useState("1,5");
  const [tc, setTc] = useState("0,03");
  const [temps, setTemps] = useState("25; 100");
  const [izOp, setIzOp] = useState("");
  const [logScale, setLogScale] = useState(false);
  const [componentId, setComponentId] = useState("");
  const [zeners, setZeners] = useState<ComponentSummary[]>([]);
  const [result, setResult] = useState<ZenerBenchOut | null>(null);
  const [fitSteps, setFitSteps] = useState<CalcStep[]>([]);
  const [fitWarnings, setFitWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    catalog
      .list({ category: "diode.zener" })
      .then(setZeners)
      .catch(() => undefined);
  }, []);

  const request = (fit: boolean): ZenerBenchIn | null => {
    const temperatures = temps
      .split(/[;\s]+/)
      .filter(Boolean)
      .map((t) => ({ value: num(t), unit: "degC" }));
    if (temperatures.length === 0 || temperatures.some((t) => Number.isNaN(t.value))) {
      setError("Temperaturas inválidas");
      return null;
    }
    return {
      model: {
        VZ0: { value: num(vz0), unit: "V" },
        Rz: { value: num(rz), unit: "ohm" },
        Is_r: { value: num(isr), unit: "uA" },
        n_r: num(nr),
        TC: { value: num(tc), unit: "percent/K" },
        forward: {
          Is: { value: 10, unit: "nA" },
          n: 1.8,
          Rs: { value: 0.05, unit: "ohm" },
        },
      },
      temperatures,
      points: 600,
      component_id: componentId || null,
      iz_op: izOp.trim() ? { value: num(izOp), unit: "mA" } : null,
      fit,
    };
  };

  useEffect(() => {
    const body = request(false);
    if (!body) return;
    const handle = window.setTimeout(() => {
      bench
        .zener(body)
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vz0, rz, isr, nr, tc, temps, izOp, componentId]);

  const edit = (setter: (v: string) => void) => (v: string) => {
    setFitSteps([]);
    setFitWarnings([]);
    setter(v);
  };

  const fit = () => {
    const body = request(true);
    if (!body) return;
    bench
      .zener(body)
      .then((r) => {
        setVz0(text(r.model.VZ0.value));
        setRz(text(r.model.Rz.value));
        setTc(text(r.model.TC.value, 3));
        setFitSteps(r.steps.filter((s) => s.id.endsWith("_fit")));
        setFitWarnings(r.warnings);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  };

  const { traces, scale } = useMemo(() => {
    if (!result) return { traces: [] as Trace[], scale: null };
    const clean = (values: number[]) => values.map((v) => (logScale && !(v > 0) ? null : v));
    const curves = Object.entries(result.curves).map(([label, vec]) => ({
      name: `Modelo, ${label}`,
      unit: "A",
      values: clean(vec.values),
    }));
    const xMax = result.v.values[result.v.values.length - 1] ?? 0;
    const scale = fitScale(
      curves.map((c) => c.values),
      result.markers,
      xMax,
      logScale,
    );
    const markers = scale.inside.map((m) => ({
      name: m.label,
      unit: "A",
      points: true,
      values: result.v.values.map((v) => (Math.abs(v - m.v.value) < 1e-12 ? m.i.value : null)),
    }));
    return { traces: [...curves, ...markers] as Trace[], scale };
  }, [result, logScale]);

  const warnings = [...fitWarnings, ...(result?.warnings ?? [])].filter(
    (w) => !(fitSteps.length && w.startsWith("Os pontos do datasheet")),
  );

  return (
    <main className="two-col">
      <section className="panel editor">
        {selector}
        <h2>Bancada: diodo Zener</h2>
        <p className="small muted">
          Modelo equivalente: fonte V<sub>Z0</sub> em série com um diodo (joelho exponencial) e R
          <sub>z</sub>. Valores didáticos e ajustáveis; o botão abaixo calibra V<sub>Z0</sub> e R
          <sub>z</sub> pelo ponto de teste do datasheet (V<sub>Z</sub> e Z<sub>ZT</sub> em I
          <sub>ZT</sub>).
        </p>
        <label>
          Tensão da fonte de ruptura VZ0 (V, a 27 °C)
          <input value={vz0} onChange={(e) => edit(setVz0)(e.target.value)} />
        </label>
        <label>
          Resistência Rz (Ω)
          <input value={rz} onChange={(e) => edit(setRz)(e.target.value)} />
        </label>
        <label>
          Corrente de saturação do joelho Is,r (µA)
          <input value={isr} onChange={(e) => edit(setIsr)(e.target.value)} />
        </label>
        <label>
          Coeficiente de emissão do joelho nr
          <input value={nr} onChange={(e) => edit(setNr)(e.target.value)} />
        </label>
        <label>
          Coeficiente de temperatura TC (%/K)
          <input value={tc} onChange={(e) => edit(setTc)(e.target.value)} />
        </label>
        <label>
          Temperaturas (°C, separadas por ;)
          <input value={temps} onChange={(e) => setTemps(e.target.value)} />
        </label>
        <label>
          Corrente de operação IZ (mA; vazio = IZT do datasheet ou 10 mA)
          <input value={izOp} onChange={(e) => setIzOp(e.target.value)} />
        </label>
        <label>
          Comparar com o datasheet de
          <select
            value={componentId}
            onChange={(e) => {
              setFitSteps([]);
              setFitWarnings([]);
              setComponentId(e.target.value);
            }}
          >
            <option value="">nenhum</option>
            {zeners.map((d) => (
              <option key={d.id} value={d.id}>
                {d.part_number} ({d.manufacturer})
              </option>
            ))}
          </select>
        </label>
        <button disabled={!componentId} onClick={fit}>
          Ajustar ao datasheet
        </button>
        <label className="inline">
          <input
            type="checkbox"
            checked={logScale}
            onChange={(e) => setLogScale(e.target.checked)}
          />
          Corrente em escala logarítmica
        </label>
        {result && (
          <details>
            <summary>Subcircuito SPICE equivalente</summary>
            <pre className="small">{result.spice_model}</pre>
          </details>
        )}
      </section>
      <section className="panel">
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {result && (
          <>
            <SignalPlot
              x={result.v.values}
              xUnit="V"
              xLabel="Tensão reversa"
              yLog={logScale}
              traces={traces}
              height={420}
              yRange={scale?.range}
            />
            <OutsidePoints items={scale?.outside ?? []} />
            {warnings.map((w) => (
              <p key={w} className="small note">
                {w}
              </p>
            ))}
            {fitSteps.length > 0 && (
              <>
                <h3>Ajuste ao datasheet</h3>
                <CalcSteps steps={fitSteps} />
              </>
            )}
            <h3>Memória de cálculo</h3>
            <CalcSteps steps={result.steps} />
          </>
        )}
      </section>
    </main>
  );
}
