import { type ReactNode, useEffect, useMemo, useState } from "react";
import { bench, catalog, ComponentSummary, CurvesOut, Quantity } from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { fitScale } from "../components/benchScale";
import { OutsidePoints } from "../components/OutsidePoints";
import { SignalPlot, Trace } from "../components/SignalPlot";
import { formatRaw } from "../format";
import { num } from "./BenchPage";

function list(text: string, unit: string): Quantity[] | null {
  const values = text
    .split(/[;\s]+/)
    .filter(Boolean)
    .map((t) => ({ value: num(t), unit }));
  return values.length && values.every((v) => !Number.isNaN(v.value)) ? values : null;
}

function text(value: number, digits = 4): string {
  return formatRaw(Number(value.toPrecision(digits)), "");
}

interface Field {
  label: string;
  value: string;
  set: (v: string) => void;
}

/** Shared layout of the transistor benches: inputs, datasheet selector, output curves. */
function CurvesLayout(props: {
  selector: ReactNode;
  title: string;
  intro: ReactNode;
  fields: Field[];
  components: ComponentSummary[];
  componentId: string;
  setComponentId: (id: string) => void;
  onFit: () => void;
  result: CurvesOut | null;
  fitWarnings: string[];
  error: string | null;
  xLabel: string;
  yUnit: string;
}) {
  const { result } = props;
  const { traces, scale } = useMemo(() => {
    if (!result) return { traces: [] as Trace[], scale: null };
    const curves = Object.entries(result.curves).map(([label, vec]) => ({
      name: label,
      unit: props.yUnit,
      values: vec.values,
    }));
    const xMax = result.x.values[result.x.values.length - 1] ?? 0;
    const scale = fitScale(
      curves.map((c) => c.values),
      result.markers,
      xMax,
      false,
    );
    const markers = scale.inside.map((m) => ({
      name: m.label,
      unit: props.yUnit,
      points: true,
      values: result.x.values.map((v) => (Math.abs(v - m.v.value) < 1e-12 ? m.i.value : null)),
    }));
    return { traces: [...curves, ...markers] as Trace[], scale };
  }, [result, props.yUnit]);
  const fitSteps = result?.steps.filter((s) => s.id.endsWith("_fit")) ?? [];
  const otherSteps = result?.steps.filter((s) => !s.id.endsWith("_fit")) ?? [];
  return (
    <main className="two-col">
      <section className="panel editor">
        {props.selector}
        <h2>{props.title}</h2>
        <p className="small muted">{props.intro}</p>
        {props.fields.map((f) => (
          <label key={f.label}>
            {f.label}
            <input value={f.value} onChange={(e) => f.set(e.target.value)} />
          </label>
        ))}
        <label>
          Comparar com o datasheet de
          <select value={props.componentId} onChange={(e) => props.setComponentId(e.target.value)}>
            <option value="">nenhum</option>
            {props.components.map((d) => (
              <option key={d.id} value={d.id}>
                {d.part_number} ({d.manufacturer})
              </option>
            ))}
          </select>
        </label>
        <button disabled={!props.componentId} onClick={props.onFit}>
          Ajustar ao datasheet
        </button>
        {result && (
          <details>
            <summary>Modelo SPICE equivalente</summary>
            <pre className="small">{result.spice_model}</pre>
          </details>
        )}
      </section>
      <section className="panel">
        {props.error && (
          <div className="error" role="alert">
            {props.error}
          </div>
        )}
        {result && (
          <>
            <SignalPlot
              x={result.x.values}
              xUnit="V"
              xLabel={props.xLabel}
              traces={traces}
              height={420}
              yRange={scale?.range}
            />
            <OutsidePoints items={scale?.outside ?? []} />
            {[...props.fitWarnings, ...result.warnings]
              .filter((w, i, all) => all.indexOf(w) === i)
              .map((w) => (
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
            <CalcSteps steps={otherSteps} />
          </>
        )}
      </section>
    </main>
  );
}

function useComponents(category: string) {
  const [items, setItems] = useState<ComponentSummary[]>([]);
  useEffect(() => {
    catalog
      .list({ category })
      .then(setItems)
      .catch(() => undefined);
  }, [category]);
  return items;
}

/** BD-TBJ: output characteristics IC × VCE for several base currents. */
export function BjtBench({ selector }: { selector: ReactNode }) {
  const [is_, setIs] = useState("1e-14");
  const [bf, setBf] = useState("200");
  const [br, setBr] = useState("2");
  const [vaf, setVaf] = useState("80");
  const [ib, setIb] = useState("10; 20; 30; 40; 50");
  const [vmax, setVmax] = useState("10");
  const [componentId, setComponentId] = useState("");
  const [result, setResult] = useState<CurvesOut | null>(null);
  const [fitResult, setFitResult] = useState<CurvesOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const components = useComponents("bjt");

  const body = (fit: boolean) => {
    const ibs = list(ib, "uA");
    if (!ibs) {
      setError("Correntes de base inválidas");
      return null;
    }
    return {
      model: {
        IS: { value: num(is_), unit: "A" },
        BF: num(bf),
        BR: num(br),
        VAF: { value: num(vaf), unit: "V" },
      },
      ib: ibs,
      vce_max: { value: num(vmax), unit: "V" },
      component_id: componentId || null,
      fit,
    };
  };

  useEffect(() => {
    const b = body(false);
    if (!b) return;
    const handle = window.setTimeout(() => {
      bench
        .bjt(b)
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [is_, bf, br, vaf, ib, vmax, componentId]);

  const fit = () => {
    const b = body(true);
    if (!b) return;
    bench
      .bjt(b)
      .then((r) => {
        setFitResult(r);
        setBf(text(r.model.BF as number));
      })
      .catch((e: Error) => setError(e.message));
  };
  const shown =
    result && fitResult
      ? {
          ...result,
          steps: [...fitResult.steps.filter((s) => s.id.endsWith("_fit")), ...result.steps],
        }
      : result;
  const edit = (setter: (v: string) => void) => (v: string) => {
    setFitResult(null);
    setter(v);
  };

  return (
    <CurvesLayout
      selector={selector}
      title="Bancada: transistor bipolar"
      intro={
        <>
          Curvas de saída I<sub>C</sub> × V<sub>CE</sub> com I<sub>B</sub> constante, pelo modelo de
          transporte (Ebers-Moll) com efeito Early, o mesmo do SPICE. PNP é mostrado em módulo. O
          ajuste ao datasheet toma o ganho B<sub>F</sub> do h<sub>FE</sub>.
        </>
      }
      fields={[
        { label: "Corrente de saturação IS (A)", value: is_, set: edit(setIs) },
        { label: "Ganho direto BF", value: bf, set: edit(setBf) },
        { label: "Ganho reverso BR", value: br, set: edit(setBr) },
        { label: "Tensão de Early VAF (V)", value: vaf, set: edit(setVaf) },
        { label: "Correntes de base IB (µA, separadas por ;)", value: ib, set: setIb },
        { label: "VCE máxima no gráfico (V)", value: vmax, set: setVmax },
      ]}
      components={components}
      componentId={componentId}
      setComponentId={(id) => {
        setFitResult(null);
        setComponentId(id);
      }}
      onFit={fit}
      result={shown}
      fitWarnings={fitResult?.warnings ?? []}
      error={error}
      xLabel="Tensão coletor-emissor"
      yUnit="A"
    />
  );
}

/** BD-FET: output characteristics ID × VDS for several gate voltages. */
export function MosfetBench({ selector }: { selector: ReactNode }) {
  const [vto, setVto] = useState("3");
  const [kp, setKp] = useState("2");
  const [lambda, setLambda] = useState("0,01");
  const [vgs, setVgs] = useState("4; 4,5; 5; 5,5; 6");
  const [vmax, setVmax] = useState("10");
  const [componentId, setComponentId] = useState("");
  const [result, setResult] = useState<CurvesOut | null>(null);
  const [fitResult, setFitResult] = useState<CurvesOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const components = useComponents("mosfet");

  const body = (fit: boolean) => {
    const v = list(vgs, "V");
    if (!v) {
      setError("Tensões de porta inválidas");
      return null;
    }
    return {
      model: {
        VTO: { value: num(vto), unit: "V" },
        KP: { value: num(kp), unit: "A/V**2" },
        LAMBDA: { value: num(lambda), unit: "1/V" },
      },
      vgs: v,
      vds_max: { value: num(vmax), unit: "V" },
      component_id: componentId || null,
      fit,
    };
  };

  useEffect(() => {
    const b = body(false);
    if (!b) return;
    const handle = window.setTimeout(() => {
      bench
        .mosfet(b)
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vto, kp, lambda, vgs, vmax, componentId]);

  const fit = () => {
    const b = body(true);
    if (!b) return;
    bench
      .mosfet(b)
      .then((r) => {
        setFitResult(r);
        setVto(text((r.model.VTO as Quantity).value));
        setKp(text((r.model.KP as Quantity).value));
      })
      .catch((e: Error) => setError(e.message));
  };
  const shown =
    result && fitResult
      ? {
          ...result,
          steps: [...fitResult.steps.filter((s) => s.id.endsWith("_fit")), ...result.steps],
        }
      : result;
  const edit = (setter: (v: string) => void) => (v: string) => {
    setFitResult(null);
    setter(v);
  };

  return (
    <CurvesLayout
      selector={selector}
      title="Bancada: MOSFET canal N"
      intro={
        <>
          Curvas de saída I<sub>D</sub> × V<sub>DS</sub> pelo modelo quadrático (SPICE nível 1):
          corte, triodo e saturação com modulação do canal λ. O ajuste ao datasheet toma V
          <sub>T</sub> de V<sub>GS(th)</sub> e K<sub>P</sub> de R<sub>DS(on)</sub>.
        </>
      }
      fields={[
        { label: "Tensão de limiar VT (V)", value: vto, set: edit(setVto) },
        { label: "Transcondutância KP (A/V²)", value: kp, set: edit(setKp) },
        { label: "Modulação do canal λ (1/V)", value: lambda, set: edit(setLambda) },
        { label: "Tensões de porta VGS (V, separadas por ;)", value: vgs, set: setVgs },
        { label: "VDS máxima no gráfico (V)", value: vmax, set: setVmax },
      ]}
      components={components}
      componentId={componentId}
      setComponentId={(id) => {
        setFitResult(null);
        setComponentId(id);
      }}
      onFit={fit}
      result={shown}
      fitWarnings={fitResult?.warnings ?? []}
      error={error}
      xLabel="Tensão dreno-fonte"
      yUnit="A"
    />
  );
}
