import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ComplexForm, Job, Measurements, PlotData, PlotInfo, watchJob } from "../api";
import { SignalPlot, Trace } from "../components/SignalPlot";
import { EXAMPLES } from "../examples";
import { formatEng } from "../format";

const KIND_LABEL: Record<string, string> = {
  op: "Ponto de operação",
  tran: "Transitória",
  ac: "CA (frequência)",
  dc: "Varredura CC",
  noise: "Ruído",
  other: "Outra",
};

const STATE_LABEL: Record<Job["state"], string> = {
  queued: "Na fila",
  running: "Simulando",
  done: "Concluída",
  failed: "Falhou",
  cancelled: "Cancelada",
};

export function SimulatorPage() {
  const firstExample = Object.keys(EXAMPLES)[0] ?? "";
  const [netlist, setNetlist] = useState(EXAMPLES[firstExample] ?? "");
  const [job, setJob] = useState<Job | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [plotName, setPlotName] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [form, setForm] = useState<ComplexForm>("mag_db");
  const [data, setData] = useState<PlotData | null>(null);
  const [measures, setMeasures] = useState<Measurements[]>([]);

  const running = job?.state === "queued" || job?.state === "running";
  const plots = job?.plots ?? [];
  const plot: PlotInfo | undefined = plots.find((p) => p.name === plotName);

  useEffect(() => {
    if (job?.state === "done" && job.plots && !job.plots.some((p) => p.name === plotName)) {
      const preferred = job.plots.find((p) => p.kind === "tran") ?? job.plots[0];
      setPlotName(preferred?.name ?? null);
    }
  }, [job, plotName]);

  useEffect(() => {
    if (!plot) return;
    const vectors = plot.vectors.filter((v) => v.name !== plot.scale).map((v) => v.name);
    const voltages = vectors.filter((v) => v.startsWith("v("));
    setSelected((voltages.length ? voltages : vectors).slice(0, 3));
  }, [plot]);

  // Only probes that exist in the current plot (the selection can lag one render behind).
  const probes = useMemo(
    () => (plot ? selected.filter((s) => plot.vectors.some((v) => v.name === s)) : []),
    [plot, selected],
  );

  useEffect(() => {
    if (!job || job.state !== "done" || !plot || probes.length === 0) {
      setData(null);
      setMeasures([]);
      return;
    }
    let cancelled = false;
    api
      .plot(job.id, plot.name, probes, form)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setRequestError(e.message));
    if (plot.kind === "tran") {
      Promise.all(probes.map((v) => api.measures(job.id, plot.name, v)))
        .then((m) => !cancelled && setMeasures(m))
        .catch(() => !cancelled && setMeasures([]));
    } else {
      setMeasures([]);
    }
    return () => {
      cancelled = true;
    };
  }, [job, plot, probes, form]);

  useEffect(() => {
    if (!job || !running) return;
    return watchJob(job.id, setJob);
  }, [job?.id, running]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(async () => {
    setRequestError(null);
    setData(null);
    setMeasures([]);
    setPlotName(null);
    try {
      setJob(await api.submit(netlist));
    } catch (e) {
      setRequestError((e as Error).message);
    }
  }, [netlist]);

  const cancel = useCallback(async () => {
    if (job) setJob(await api.cancel(job.id));
  }, [job]);

  const traces: Trace[] = useMemo(
    () =>
      data
        ? Object.entries(data.traces).map(([name, v]) => ({ name, unit: v.unit, values: v.values }))
        : [],
    [data],
  );

  return (
    <main className="two-col">
      <section className="panel editor">
        <div className="row">
          <label htmlFor="example">Exemplo</label>
          <select
            id="example"
            onChange={(e) => setNetlist(EXAMPLES[e.target.value] ?? netlist)}
            defaultValue={firstExample}
          >
            {Object.keys(EXAMPLES).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </div>
        <label htmlFor="netlist">Netlist SPICE</label>
        <textarea
          id="netlist"
          spellCheck={false}
          value={netlist}
          onChange={(e) => setNetlist(e.target.value)}
        />
        <div className="row">
          <button onClick={run} disabled={running}>
            Simular
          </button>
          <button className="secondary" onClick={cancel} disabled={!running}>
            Cancelar
          </button>
        </div>
        {job && (
          <div className="status" aria-live="polite">
            <div className="row">
              <strong>{STATE_LABEL[job.state]}</strong>
              <span className="muted">
                {job.state === "done" && job.elapsed_s != null
                  ? `${formatEng(job.elapsed_s, "s")} · ${job.backend}`
                  : job.message}
              </span>
            </div>
            <progress value={job.progress} max={1} />
          </div>
        )}
        {(requestError || job?.error) && (
          <div className="error" role="alert">
            <strong>{job?.error?.message ?? requestError}</strong>
            {job?.error?.suggestions.length ? (
              <ul>
                {job.error.suggestions.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            ) : null}
            {job?.error?.log && (
              <details>
                <summary>Registro do simulador</summary>
                <pre>{job.error.log}</pre>
              </details>
            )}
          </div>
        )}
      </section>

      <section className="panel results">
        {plots.length === 0 ? (
          <p className="muted">Rode uma simulação para ver os sinais.</p>
        ) : (
          <>
            <div className="tabs" role="tablist">
              {plots.map((p) => (
                <button
                  key={p.name}
                  role="tab"
                  aria-selected={p.name === plotName}
                  className={p.name === plotName ? "tab active" : "tab"}
                  onClick={() => setPlotName(p.name)}
                >
                  {KIND_LABEL[p.kind] ?? p.kind}
                </button>
              ))}
            </div>
            {plot && (
              <>
                <fieldset className="vectors">
                  <legend>Ponteiras de prova</legend>
                  {plot.vectors
                    .filter((v) => v.name !== plot.scale)
                    .map((v) => (
                      <label key={v.name}>
                        <input
                          type="checkbox"
                          checked={selected.includes(v.name)}
                          onChange={(e) =>
                            setSelected((s) =>
                              e.target.checked ? [...s, v.name] : s.filter((n) => n !== v.name),
                            )
                          }
                        />
                        {v.name}
                      </label>
                    ))}
                </fieldset>
                {plot.kind === "ac" && (
                  <div className="row">
                    <label htmlFor="form">Grandeza</label>
                    <select
                      id="form"
                      value={form}
                      onChange={(e) => setForm(e.target.value as ComplexForm)}
                    >
                      <option value="mag_db">Módulo (dB)</option>
                      <option value="mag">Módulo</option>
                      <option value="phase_deg">Fase (graus)</option>
                      <option value="real">Parte real</option>
                      <option value="imag">Parte imaginária</option>
                    </select>
                  </div>
                )}
                {plot.kind === "op" && data ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Grandeza</th>
                        <th>Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {traces.map((t) => (
                        <tr key={t.name}>
                          <td>{t.name}</td>
                          <td>{formatEng(t.values[0] ?? NaN, t.unit, 4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : data?.x ? (
                  <SignalPlot
                    x={data.x.values}
                    xUnit={data.x.unit}
                    xLabel={data.x_name === "frequency" ? "Frequência" : "Tempo"}
                    xLog={plot.kind === "ac"}
                    traces={traces}
                  />
                ) : null}
                {data?.decimated && (
                  <p className="muted small">
                    Exibição reduzida por mínimo/máximo; os picos são preservados.
                  </p>
                )}
                {measures.length > 0 && (
                  <table>
                    <thead>
                      <tr>
                        <th>Sinal</th>
                        <th>Média</th>
                        <th>RMS</th>
                        <th>Pico</th>
                        <th>Pico a pico</th>
                      </tr>
                    </thead>
                    <tbody>
                      {measures.map((m) => (
                        <tr key={m.vector}>
                          <td>{m.vector}</td>
                          <td>{formatEng(m.mean.value, m.mean.unit, 4)}</td>
                          <td>{formatEng(m.rms.value, m.rms.unit, 4)}</td>
                          <td>{formatEng(m.peak.value, m.peak.unit, 4)}</td>
                          <td>{formatEng(m.peak_to_peak.value, m.peak_to_peak.unit, 4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </>
        )}
      </section>
    </main>
  );
}
