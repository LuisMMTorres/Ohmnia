/** Results of a schematic simulation: oscilloscope, Bode, FFT/THD, XY, statistics, worst case. */
import { useEffect, useMemo, useState } from "react";
import {
  api,
  download,
  schematicApi,
  type ComplexForm,
  type Job,
  type Measurements,
  type PlotInfo,
  type SpectrumOut,
  type StatisticsOut,
} from "../api";
import { formatEng } from "../format";
import { Histogram, StemPlot, XYPlot } from "./charts";
import { Scope, TRACE_COLORS, valueAt, type Cursors, type ScopeTrace } from "./Scope";
import type { MeasureKind } from "./types";

type Mode = "scope" | "bode" | "fft" | "xy" | "stats" | "worst" | "table";

const KIND_LABEL: Record<string, string> = {
  op: "Ponto de operação",
  tran: "Transitória",
  ac: "Frequência (AC)",
  dc: "Varredura CC",
  noise: "Ruído",
  other: "Outra",
};
const X_LABEL: Record<string, string> = { s: "tempo", Hz: "frequência" };

const MEASURE_LABEL: Record<MeasureKind, string> = {
  final: "valor final / ponto de operação",
  mean: "média",
  rms: "RMS",
  max: "máximo",
  min: "mínimo",
  pp: "pico a pico",
  at: "valor em x",
  mag_db_at: "módulo (dB) em f",
  phase_at: "fase (°) em f",
  frequency: "frequência",
};

interface Props {
  job: Job;
  probeNames: string[];
  onJobUpdate: (job: Job) => void;
}

function q(m: { value: number; unit: string } | null | undefined, digits = 4): string {
  if (!m) return "—";
  if (m.unit === "" || m.unit === "dimensionless")
    return `${(m.value * 100).toFixed(2).replace(".", ",")} %`;
  return formatEng(m.value, m.unit, digits);
}

export function ResultsView({ job, probeNames, onJobUpdate }: Props) {
  const plots = useMemo(() => job.plots ?? [], [job.plots]);
  const bases = useMemo(() => {
    const seen = new Map<string, PlotInfo>();
    for (const p of plots) if (!seen.has(p.base ?? p.name)) seen.set(p.base ?? p.name, p);
    return [...seen.entries()];
  }, [plots]);
  const multi = (job.runs?.length ?? 0) > 1;
  const [base, setBase] = useState<string>("");
  const [run, setRun] = useState<number | "all">("all");
  const [expressionNames, setExpressionNames] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [modeChoice, setMode] = useState<Mode>("scope");
  const [form, setForm] = useState<ComplexForm>("mag_db");
  const [loaded, setLoaded] = useState<{ key: string; traces: ScopeTrace[]; phase: ScopeTrace[] }>({
    key: "",
    traces: [],
    phase: [],
  });
  const [cursors, setCursors] = useState<Cursors>({ a: null, b: null });
  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const [measures, setMeasures] = useState<Measurements[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [exprName, setExprName] = useState("");
  const [expr, setExpr] = useState("");
  const [figFormat, setFigFormat] = useState<"svg" | "png" | "pdf">("svg");

  // default plot: the transient, else the first
  useEffect(() => {
    if (!bases.some(([b]) => b === base)) {
      const pref = bases.find(([, p]) => p.kind === "tran") ?? bases[0];
      if (pref) setBase(pref[0]);
    }
  }, [bases, base]);

  const group = useMemo(() => plots.filter((p) => (p.base ?? p.name) === base), [plots, base]);
  const kind = group[0]?.kind ?? "op";
  const shown = useMemo(
    () => (run === "all" ? group : group.filter((p) => (p.run ?? 0) === run)),
    [group, run],
  );
  const first = shown[0] ?? group[0];
  useEffect(() => {
    setExpressionNames([]);
    setSelected([]);
  }, [job.id]);
  const vectorNames = useMemo(
    () =>
      first
        ? first.vectors
            .filter(
              (v) =>
                v.name !== first.scale &&
                ([...probeNames, ...expressionNames].some(
                  (name) => name.toLowerCase() === v.name.toLowerCase(),
                ) ||
                  (kind === "noise" && /^(o|i)noise_(spectrum|total)$/.test(v.name))),
            )
            .map((v) => v.name)
        : [],
    [first, probeNames, expressionNames, kind],
  );

  // Offer only explicit probes and expressions added by the user.
  useEffect(() => {
    setSelected(vectorNames);
  }, [vectorNames]);

  // the stored mode may not fit the analysis shown (e.g. Bode on a transient): normalise it
  // synchronously so no request or plot is ever made with a stale combination
  const scaled = !!first?.scale;
  const mode = useMemo((): Mode => {
    const m = modeChoice;
    // .op and scalar plots (e.g. total noise, which has no x vector) are tables
    if (kind === "op" || !scaled)
      return multi ? (m === "stats" || m === "worst" ? m : "table") : "table";
    if (kind === "ac" && (m === "scope" || m === "fft" || m === "table")) return "bode";
    if (kind !== "ac" && m === "bode") return "scope";
    if (kind !== "tran" && m === "fft") return "scope";
    if (m === "table") return kind === "ac" ? "bode" : "scope";
    return m;
  }, [modeChoice, kind, multi, scaled]);
  useEffect(() => {
    setCursors({ a: null, b: null });
    setZoom(null);
  }, [kind, base]);
  const viewKey = `${job.id}|${base}|${mode}|${String(run)}`;

  // load traces
  useEffect(() => {
    if (!first || !selected.length || !["scope", "bode", "table"].includes(mode)) return;
    let cancelled = false;
    const key = viewKey;
    const formFor: ComplexForm = mode === "bode" ? "mag_db" : form;
    Promise.all(
      shown.slice(0, 60).map(async (p) => {
        const names = selected.filter((s) => p.vectors.some((v) => v.name === s));
        if (!names.length) return { p, data: null, ph: null };
        const data = await api.plot(job.id, p.name, names, formFor, 4000);
        const ph =
          mode === "bode" ? await api.plot(job.id, p.name, names, "phase_deg", 4000) : null;
        return { p, data, ph };
      }),
    )
      .then((rows) => {
        if (cancelled) return;
        const out: ScopeTrace[] = [];
        const outPh: ScopeTrace[] = [];
        rows.forEach(({ p, data, ph }, ri) => {
          if (!data) return;
          const x = data.x?.values ?? [0];
          const suffix = shown.length > 1 ? ` · ${p.run_label || `#${p.run}`}` : "";
          Object.entries(data.traces).forEach(([name, v], vi) => {
            const color =
              shown.length > 1 && (selected.length === 1 || shown.length <= 8)
                ? TRACE_COLORS[ri % TRACE_COLORS.length]
                : TRACE_COLORS[vi % TRACE_COLORS.length];
            out.push({
              name: name + suffix,
              unit: v.unit,
              x,
              y: v.values,
              color,
              width: shown.length > 8 ? 1 : 1.5,
            });
            const pv = ph?.traces[name];
            if (pv) outPh.push({ name: name + suffix, unit: "deg", x, y: pv.values, color });
          });
        });
        setLoaded({ key, traces: out, phase: outPh });
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [job.id, first, shown, selected, mode, form, viewKey]);

  const traces = selected.length && loaded.key === viewKey ? loaded.traces : [];
  const phase = loaded.key === viewKey ? loaded.phase : [];

  // measurements (transient, one run)
  const window_ = useMemo((): [number, number] | null => {
    if (cursors.a != null && cursors.b != null)
      return [Math.min(cursors.a, cursors.b), Math.max(cursors.a, cursors.b)];
    return zoom;
  }, [cursors, zoom]);
  useEffect(() => {
    if (kind !== "tran" || mode !== "scope" || !first) {
      setMeasures([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      selected
        .filter((s) => first.vectors.some((v) => v.name === s))
        .map((v) => api.measures(job.id, first.name, v, window_?.[0], window_?.[1])),
    )
      .then((m) => !cancelled && setMeasures(m))
      .catch(() => !cancelled && setMeasures([]));
    return () => {
      cancelled = true;
    };
  }, [job.id, first, selected, kind, mode, window_]);

  const xUnit = first?.scale ? (first.vectors.find((v) => v.name === first.scale)?.unit ?? "") : "";
  const xLabel = X_LABEL[xUnit] ?? first?.scale ?? "x";
  const xLog = kind === "ac" || kind === "noise";

  const addExpression = async () => {
    if (!first || !expr.trim()) return;
    try {
      const info = await schematicApi.expression(job.id, first.name, expr, exprName);
      setExpressionNames((names) => [...names, info.name]);
      onJobUpdate(await api.status(job.id));
      setSelected((s) => [...s.filter((n) => n !== info.name), info.name]);
      setExpr("");
      setExprName("");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const exportFigure = async () => {
    if (!first) return;
    try {
      const blob = await schematicApi.figure(job.id, {
        plot: first.name,
        vectors: selected,
        kind: mode === "bode" ? "bode" : "time",
        format: figFormat,
        all_runs: run === "all" && multi,
        start: zoom?.[0] ?? null,
        stop: zoom?.[1] ?? null,
      });
      download(blob, `${first.base ?? first.name}.${figFormat}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!first) return <p className="muted">Sem resultados.</p>;
  const modes: [Mode, string][] = [];
  if (kind === "op" || !scaled) modes.push(["table", "Valores"]);
  if (kind === "ac") modes.push(["bode", "Bode"]);
  if (kind !== "op" && scaled) modes.push(["scope", kind === "tran" ? "Osciloscópio" : "Curvas"]);
  if (kind === "tran") modes.push(["fft", "FFT / THD"]);
  if (kind !== "op" && scaled) modes.push(["xy", "XY"]);
  if (multi) modes.push(["stats", "Estatística"]);
  if (job.summary?.kind === "worstcase") modes.push(["worst", "Pior caso"]);

  return (
    <div className="results-view">
      <div className="row wrap">
        <label className="inline">
          Análise{" "}
          <select value={base} onChange={(e) => setBase(e.target.value)}>
            {bases.map(([b, p]) => (
              <option key={b} value={b}>
                {KIND_LABEL[p.kind] ?? p.kind} ({b})
              </option>
            ))}
          </select>
        </label>
        {multi && (
          <label className="inline">
            Execução{" "}
            <select
              value={String(run)}
              onChange={(e) => setRun(e.target.value === "all" ? "all" : Number(e.target.value))}
            >
              <option value="all">todas ({job.runs?.length})</option>
              {job.runs?.map((r) => (
                <option key={r.index} value={r.index}>
                  {r.label || `#${r.index}`}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="tabs" role="tablist">
          {modes.map(([m, label]) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={mode === m ? "tab active" : "tab"}
              onClick={() => setMode(m)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {mode !== "stats" && mode !== "worst" && mode !== "fft" && (
        <details className="vectors-box" open>
          <summary>Sinais ({selected.length})</summary>
          {vectorNames.length === 0 && (
            <p className="small muted">
              Nenhuma ponta de prova disponível nesta análise. Adicione pontas no circuito e simule
              novamente.
            </p>
          )}
          <div className="vectors">
            {vectorNames.map((n) => (
              <label key={n}>
                <input
                  type="checkbox"
                  checked={selected.includes(n)}
                  onChange={(e) =>
                    setSelected((s) => (e.target.checked ? [...s, n] : s.filter((x) => x !== n)))
                  }
                />{" "}
                {n}
              </label>
            ))}
          </div>
          {kind !== "op" && (
            <div className="row wrap expr-row">
              <input
                placeholder="nome (opcional)"
                value={exprName}
                onChange={(e) => setExprName(e.target.value)}
                style={{ width: 120 }}
              />
              <input
                className="grow"
                placeholder="expressão: v(out)*i(r1), integ(p(q1)), movavg(v(out), 1m), v(a,b)…"
                value={expr}
                onChange={(e) => setExpr(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void addExpression()}
              />
              <button type="button" onClick={() => void addExpression()}>
                Adicionar sinal
              </button>
            </div>
          )}
        </details>
      )}
      {error && <p className="error">{error}</p>}

      {mode === "table" && <OpTable traces={traces} />}

      {(mode === "scope" || mode === "bode") && traces.length > 0 && (
        <>
          {kind === "ac" && mode === "scope" && (
            <label className="inline small">
              Forma{" "}
              <select value={form} onChange={(e) => setForm(e.target.value as ComplexForm)}>
                <option value="mag_db">módulo (dB)</option>
                <option value="mag">módulo</option>
                <option value="phase_deg">fase (°)</option>
                <option value="real">parte real</option>
                <option value="imag">parte imaginária</option>
              </select>
            </label>
          )}
          <Scope
            traces={traces}
            xUnit={xUnit}
            xLabel={xLabel}
            xLog={xLog}
            height={mode === "bode" ? 260 : 380}
            cursors={cursors}
            onCursor={(k, x) => setCursors((c) => ({ ...c, [k]: x }))}
            onZoom={setZoom}
          />
          {mode === "bode" && phase.length > 0 && (
            <Scope
              traces={phase}
              xUnit={xUnit}
              xLabel={xLabel}
              xLog
              height={220}
              cursors={cursors}
              onCursor={(k, x) => setCursors((c) => ({ ...c, [k]: x }))}
            />
          )}
          <CursorTable
            traces={mode === "bode" ? [...traces, ...phase] : traces}
            cursors={cursors}
            unit={xUnit}
          />
          {measures.length > 0 && <MeasureTable rows={measures} windowed={window_} />}
          <div className="row wrap">
            <a
              className="button secondary"
              href={schematicApi.csvUrl(
                job.id,
                first.name,
                selected,
                mode === "bode" ? "mag_db" : form,
              )}
            >
              CSV
            </a>
            <select value={figFormat} onChange={(e) => setFigFormat(e.target.value as "svg")}>
              <option value="svg">SVG</option>
              <option value="png">PNG</option>
              <option value="pdf">PDF</option>
            </select>
            <button type="button" className="secondary" onClick={() => void exportFigure()}>
              Exportar figura
            </button>
            <span className="small muted">
              Clique: cursor A · Shift+clique: cursor B · arraste: zoom · duplo clique: desfaz o
              zoom
            </span>
          </div>
        </>
      )}

      {mode === "fft" && (
        <FftPanel job={job} plot={first} vectorNames={vectorNames} initial={selected[0]} />
      )}
      {mode === "xy" && (
        <XyPanel job={job} plot={first} vectorNames={vectorNames} selected={selected} />
      )}
      {mode === "stats" && (
        <StatsPanel job={job} kind={kind} vectorNames={vectorNames} initial={selected[0]} />
      )}
      {mode === "worst" && <WorstCase summary={job.summary ?? {}} />}
      {job.summary?.cosim != null && <SerialMonitor cosim={job.summary.cosim as CosimSummary} />}
    </div>
  );
}

interface CosimSummary {
  step?: number;
  controllers?: string[];
  serial?: Record<string, [number, string][]>;
}

function SerialMonitor({ cosim }: { cosim: CosimSummary }) {
  const serial = cosim.serial ?? {};
  const refs = cosim.controllers ?? [];
  return (
    <details className="serial-monitor" open>
      <summary>
        Co-simulação ({refs.join(", ") || "sem controlador"}; passo{" "}
        {cosim.step != null ? `${(cosim.step * 1e3).toLocaleString("pt-BR")} ms` : "?"})
      </summary>
      {Object.keys(serial).length === 0 && <p className="small muted">Sem saída serial.</p>}
      {Object.keys(serial).map((ref) => {
        const lines = serial[ref] ?? [];
        return (
          <div key={ref}>
            <h4>Monitor serial de {ref}</h4>
            {lines.length === 0 ? (
              <p className="small muted">Sem saída serial.</p>
            ) : (
              <pre className="serial-lines">
                {lines
                  .map(
                    ([t, text]) =>
                      `[${t.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} s] ${text}`,
                  )
                  .join("\n")}
              </pre>
            )}
          </div>
        );
      })}
    </details>
  );
}

function OpTable({ traces }: { traces: ScopeTrace[] }) {
  return (
    <table className="params">
      <thead>
        <tr>
          <th>Sinal</th>
          <th>Valor</th>
        </tr>
      </thead>
      <tbody>
        {traces.map((t) => (
          <tr key={t.name}>
            <td>{t.name}</td>
            <td className="num">{t.y[0] == null ? "—" : formatEng(t.y[0], t.unit, 5)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CursorTable({
  traces,
  cursors,
  unit,
}: {
  traces: ScopeTrace[];
  cursors: Cursors;
  unit: string;
}) {
  const { a, b } = cursors;
  if (a == null && b == null) return null;
  const dx = a != null && b != null ? b - a : null;
  return (
    <table className="params cursors">
      <thead>
        <tr>
          <th>Sinal</th>
          <th>A = {a == null ? "—" : formatEng(a, unit, 4)}</th>
          <th>B = {b == null ? "—" : formatEng(b, unit, 4)}</th>
          <th>
            B − A{" "}
            {dx != null && (
              <span className="muted">
                (Δx = {formatEng(dx, unit, 4)}
                {dx !== 0 && unit === "s" ? `, 1/Δx = ${formatEng(1 / Math.abs(dx), "Hz", 4)}` : ""}
                )
              </span>
            )}
          </th>
        </tr>
      </thead>
      <tbody>
        {traces.slice(0, 16).map((t) => {
          const va = a == null ? null : valueAt(t, a);
          const vb = b == null ? null : valueAt(t, b);
          return (
            <tr key={t.name}>
              <td>{t.name}</td>
              <td className="num">{va == null ? "—" : formatEng(va, t.unit, 4)}</td>
              <td className="num">{vb == null ? "—" : formatEng(vb, t.unit, 4)}</td>
              <td className="num">
                {va == null || vb == null ? "—" : formatEng(vb - va, t.unit, 4)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function MeasureTable({
  rows,
  windowed,
}: {
  rows: Measurements[];
  windowed: [number, number] | null;
}) {
  return (
    <div className="measure-table">
      <p className="small muted">
        Medições{" "}
        {windowed
          ? `de ${formatEng(windowed[0], "s", 4)} a ${formatEng(windowed[1], "s", 4)} (cursores ou zoom)`
          : "no registro todo"}
      </p>
      <table className="params">
        <thead>
          <tr>
            <th>Sinal</th>
            <th>Média</th>
            <th>RMS</th>
            <th>Pico</th>
            <th>Pico a pico</th>
            <th>Frequência</th>
            <th>Razão cíclica</th>
            <th>Subida</th>
            <th>Descida</th>
            <th>Sobressinal</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.vector}>
              <td>{m.vector}</td>
              <td className="num">{q(m.mean)}</td>
              <td className="num">{q(m.rms)}</td>
              <td className="num">{q(m.peak)}</td>
              <td className="num">{q(m.peak_to_peak)}</td>
              <td className="num">{q(m.frequency)}</td>
              <td className="num">{q(m.duty_cycle)}</td>
              <td className="num">{q(m.rise_time)}</td>
              <td className="num">{q(m.fall_time)}</td>
              <td className="num">{q(m.overshoot)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FftPanel({
  job,
  plot,
  vectorNames,
  initial,
}: {
  job: Job;
  plot: PlotInfo;
  vectorNames: string[];
  initial?: string;
}) {
  const [vector, setVector] = useState(initial ?? vectorNames[0] ?? "");
  const [f0, setF0] = useState("");
  const [periods, setPeriods] = useState("1");
  const [nh, setNh] = useState("50");
  const [out, setOut] = useState<SpectrumOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    try {
      const params: Record<string, string> = { vector, periods, n_harmonics: nh };
      if (f0.trim()) params.f0 = f0;
      setOut(await schematicApi.spectrum(job.id, plot.name, params));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
      setOut(null);
    }
  };
  useEffect(() => {
    if (vector) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vector, plot.name]);
  return (
    <div>
      <div className="row wrap">
        <label className="inline">
          Sinal{" "}
          <select value={vector} onChange={(e) => setVector(e.target.value)}>
            {vectorNames.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <label className="inline">
          f₀ (Hz){" "}
          <input
            value={f0}
            onChange={(e) => setF0(e.target.value)}
            placeholder="automática"
            style={{ width: 100 }}
          />
        </label>
        <label className="inline">
          Períodos{" "}
          <input
            value={periods}
            onChange={(e) => setPeriods(e.target.value)}
            style={{ width: 60 }}
          />
        </label>
        <label className="inline">
          Harmônicos{" "}
          <input value={nh} onChange={(e) => setNh(e.target.value)} style={{ width: 60 }} />
        </label>
        <button type="button" onClick={() => void run()}>
          Calcular
        </button>
        <button
          type="button"
          className="secondary"
          onClick={async () => {
            const blob = await schematicApi.figure(job.id, {
              plot: plot.name,
              vectors: [vector],
              kind: "spectrum",
              format: "svg",
              f0: out?.f0 ?? null,
              periods: Number(periods) || 1,
            });
            download(blob, "espectro.svg");
          }}
        >
          Exportar figura
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {out && (
        <>
          <p>
            f₀ = <b>{formatEng(out.f0, "Hz", 5)}</b> · THD ={" "}
            <b>{(out.thd * 100).toFixed(3).replace(".", ",")} %</b> · RMS ={" "}
            {formatEng(out.rms, out.unit, 4)} · CC = {formatEng(out.dc, out.unit, 4)} · janela{" "}
            {formatEng(out.window_start, "s", 4)} a {formatEng(out.window_stop, "s", 4)} (últimos{" "}
            {periods} período(s), amostragem coerente)
          </p>
          <StemPlot
            x={out.frequency.values}
            y={out.amplitude.values}
            xUnit="Hz"
            yUnit={out.unit}
            marks={out.harmonics.map((h) => h.frequency)}
          />
          <table className="params">
            <thead>
              <tr>
                <th>n</th>
                <th>f</th>
                <th>Amplitude (pico)</th>
                <th>% da fundamental</th>
              </tr>
            </thead>
            <tbody>
              {out.harmonics.slice(0, 15).map((h) => (
                <tr key={h.k}>
                  <td>{h.k}</td>
                  <td className="num">{formatEng(h.frequency, "Hz", 4)}</td>
                  <td className="num">{formatEng(h.amplitude, out.unit, 4)}</td>
                  <td className="num">{h.percent.toFixed(3).replace(".", ",")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function XyPanel({
  job,
  plot,
  vectorNames,
  selected,
}: {
  job: Job;
  plot: PlotInfo;
  vectorNames: string[];
  selected: string[];
}) {
  const [xv, setXv] = useState(vectorNames[0] ?? "");
  const [curves, setCurves] = useState<{ name: string; x: number[]; y: number[] }[]>([]);
  const [units, setUnits] = useState<[string, string]>(["", ""]);
  useEffect(() => {
    const ys = selected.filter((s) => s !== xv);
    if (!xv || !ys.length) return;
    api
      .plot(job.id, plot.name, [xv, ...ys], "real", 20000)
      .then((d) => {
        const x = d.traces[xv]?.values ?? [];
        setCurves(ys.map((n) => ({ name: n, x, y: d.traces[n]?.values ?? [] })));
        setUnits([d.traces[xv]?.unit ?? "", d.traces[ys[0]!]?.unit ?? ""]);
      })
      .catch(() => setCurves([]));
  }, [job.id, plot.name, xv, selected]);
  return (
    <div>
      <label className="inline">
        Eixo x{" "}
        <select value={xv} onChange={(e) => setXv(e.target.value)}>
          {vectorNames.map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
      </label>{" "}
      <span className="small muted">eixo y: os sinais marcados</span>
      {curves.length > 0 && (
        <XYPlot
          curves={curves}
          xUnit={units[0]}
          yUnit={units[1]}
          xLabel={xv}
          yLabel={curves.map((c) => c.name).join(", ")}
        />
      )}
    </div>
  );
}

function StatsPanel({
  job,
  kind,
  vectorNames,
  initial,
}: {
  job: Job;
  kind: string;
  vectorNames: string[];
  initial?: string;
}) {
  const [vector, setVector] = useState(initial ?? vectorNames[0] ?? "");
  const [measure, setMeasure] = useState<MeasureKind>(
    kind === "ac" ? "mag_db_at" : kind === "tran" ? "rms" : "final",
  );
  const [at, setAt] = useState("1k");
  const [start, setStart] = useState("");
  const [out, setOut] = useState<StatisticsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    try {
      const params: Record<string, string> = { analysis: kind, vector, kind: measure };
      if (["at", "mag_db_at", "phase_at"].includes(measure)) params.at = at;
      if (start.trim()) params.start = start;
      setOut(await schematicApi.statistics(job.id, params));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
      setOut(null);
    }
  };
  useEffect(() => {
    if (vector) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vector, measure, kind]);
  const s = out?.stats;
  return (
    <div>
      <div className="row wrap">
        <label className="inline">
          Sinal{" "}
          <select value={vector} onChange={(e) => setVector(e.target.value)}>
            {vectorNames.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <label className="inline">
          Medida{" "}
          <select value={measure} onChange={(e) => setMeasure(e.target.value as MeasureKind)}>
            {(Object.keys(MEASURE_LABEL) as MeasureKind[]).map((m) => (
              <option key={m} value={m}>
                {MEASURE_LABEL[m]}
              </option>
            ))}
          </select>
        </label>
        {["at", "mag_db_at", "phase_at"].includes(measure) && (
          <label className="inline">
            em <input value={at} onChange={(e) => setAt(e.target.value)} style={{ width: 80 }} />
          </label>
        )}
        {["mean", "rms", "max", "min", "pp", "frequency"].includes(measure) && (
          <label className="inline">
            a partir de{" "}
            <input
              value={start}
              onChange={(e) => setStart(e.target.value)}
              placeholder="início"
              style={{ width: 80 }}
            />
          </label>
        )}
        <button type="button" onClick={() => void run()}>
          Calcular
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {out && s && (
        <>
          <p>
            {out.values.length} execuções · média <b>{formatEng(s.mean, out.unit, 5)}</b> · desvio
            padrão {formatEng(s.std, out.unit, 4)} · mín. {formatEng(s.min, out.unit, 5)} · máx.{" "}
            {formatEng(s.max, out.unit, 5)}
            {out.nominal != null && <> · nominal {formatEng(out.nominal, out.unit, 5)}</>}
          </p>
          <Histogram
            edges={out.histogram.edges}
            counts={out.histogram.counts}
            unit={out.unit}
            nominal={out.nominal}
            label={`${vector}: ${MEASURE_LABEL[measure]}`}
          />
          <details>
            <summary>Valor por execução</summary>
            <table className="params">
              <tbody>
                {out.values.map((v) => (
                  <tr key={v.run}>
                    <td>{v.label || `#${v.run}`}</td>
                    <td className="num">
                      {v.value == null ? v.error : formatEng(v.value, out.unit, 5)}
                    </td>
                    <td className="small muted">
                      {Object.entries(job.runs?.[v.run]?.values ?? {})
                        .map(([k, x]) => `${k} = ${x}`)
                        .join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </div>
  );
}

interface Sensitivity {
  parameter: string;
  nominal: number;
  low: number;
  high: number;
  source: string;
  measure_at_high: number;
  delta: number;
  direction: string;
}

function WorstCase({ summary }: { summary: Record<string, unknown> }) {
  const rows = (summary.sensitivities as Sensitivity[] | undefined) ?? [];
  const m = summary.measure as { vector: string; kind: MeasureKind } | undefined;
  const fmt = (v: unknown) => (typeof v === "number" ? v.toPrecision(6).replace(".", ",") : "—");
  const fmtP = (v: unknown) => (typeof v === "number" ? formatEng(v, "", 4) : "—");
  return (
    <div>
      <p>
        Medida: <b>{m ? `${m.vector}, ${MEASURE_LABEL[m.kind]}` : "—"}</b> · nominal{" "}
        <b>{fmt(summary.nominal)}</b> · pior caso mínimo <b>{fmt(summary.min)}</b> · máximo{" "}
        <b>{fmt(summary.max)}</b>
      </p>
      <table className="params">
        <thead>
          <tr>
            <th>Parâmetro</th>
            <th>Mín.</th>
            <th>Nominal</th>
            <th>Máx.</th>
            <th>Medida no máx.</th>
            <th>Efeito</th>
            <th>Sentido no máximo</th>
            <th>Fonte da faixa</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.parameter}>
              <td>{r.parameter}</td>
              <td className="num">{fmtP(r.low)}</td>
              <td className="num">{fmtP(r.nominal)}</td>
              <td className="num">{fmtP(r.high)}</td>
              <td className="num">{fmt(r.measure_at_high)}</td>
              <td className="num">{fmt(r.delta)}</td>
              <td>{r.direction === "+" ? "no máximo" : "no mínimo"}</td>
              <td className="small">{r.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
