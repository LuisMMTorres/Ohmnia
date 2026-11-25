import { useEffect, useMemo, useState } from "react";
import { api, type Job, type PlotData } from "../api";
import { formatEng } from "../format";
import { addSupplyChannel, removeSources } from "./instruments";
import { allHoles } from "./geometry";
import { emptyBreadboard, type Spec } from "./types";
import { SourceControls } from "../schematic/SourceControls";
import { sourceSettings } from "../schematic/sourceConfig";
import type { Component, Schematic } from "../schematic/types";

export function BenchSupply({
  schematic,
  onChange,
  job,
  spec,
  liveData,
}: {
  schematic: Schematic;
  onChange: (s: Schematic) => void;
  job: Job | null;
  spec: Spec | null;
  liveData?: PlotData | null;
}) {
  const sources = useMemo(
    () => schematic.components.filter((c) => /^[vi](dc|sin|pulse)$/.test(c.kind)),
    [schematic.components],
  );
  const [measured, setMeasured] = useState<{ job: string; currents: Record<string, number> }>({
    job: "",
    currents: {},
  });
  const [error, setError] = useState("");
  useEffect(() => {
    if (job?.state !== "done") return;
    const plot =
      job.plots?.find((p) => p.kind === "op") ?? job.plots?.find((p) => p.kind === "tran");
    if (!plot) return;
    const vectors = sources
      .filter((c) => c.kind.startsWith("v"))
      .map((c) => `i(${c.ref.toLowerCase()})`)
      .filter((n) => plot.vectors.some((v) => v.name === n));
    if (!vectors.length) return;
    let cancelled = false;
    api
      .plot(job.id, plot.name, vectors, "real", 4000)
      .then((data) => {
        if (cancelled) return;
        setMeasured({
          job: job.id,
          currents: Object.fromEntries(
            Object.entries(data.traces).map(([n, v]) => [n, -v.values[v.values.length - 1]!]),
          ),
        });
        setError("");
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [job, sources]);
  const change = (c: Component) =>
    onChange({
      ...schematic,
      components: schematic.components.map((old) => (old.id === c.id ? c : old)),
    });
  const holes = spec ? allHoles(spec.board) : [];
  const connect = (c: Component, terminal: string, hole: string) => {
    const assembly = schematic.breadboard ?? emptyBreadboard();
    if (
      hole &&
      (assembly.parts.some((p) =>
        Object.entries(p.legs).some(
          ([pin, h]) => h === hole && (p.ref !== c.ref || pin !== terminal),
        ),
      ) ||
        assembly.wires.some((w) => w.a === hole || w.b === hole))
    ) {
      setError(`O furo ${hole} já está ocupado. Escolha outro furo do mesmo barramento.`);
      return;
    }
    const part = assembly.parts.find((p) => p.ref === c.ref) ?? {
      ref: c.ref,
      package: c.kind.startsWith("i") ? "fonte-i" : c.kind.endsWith("dc") ? "fonte-cc" : "gerador",
      legs: {},
    };
    const legs = { ...part.legs };
    if (hole) legs[terminal] = hole;
    else delete legs[terminal];
    onChange({
      ...schematic,
      breadboard: {
        ...assembly,
        parts: [...assembly.parts.filter((p) => p.ref !== c.ref), { ...part, legs }],
      },
    });
    setError("");
  };
  if (!sources.length) return null;
  const groups = [...new Set(sources.map((s) => s.params.bench_id ?? s.id))];
  return (
    <section className="bench-instruments" aria-label="Fontes e geradores">
      {groups.map((id) => (
        <div key={id} className="power-supply-face">
          <div className="instrument-brand">
            OHMNIA{" "}
            <span>
              {sources.some((s) => s.params.bench_id === id)
                ? "Fonte CC • 2 canais ajustáveis + 5 V"
                : "Fonte / gerador didático"}
            </span>
          </div>
          <button
            className="secondary"
            onClick={() =>
              onChange(
                removeSources(
                  schematic,
                  sources.filter((s) => (s.params.bench_id ?? s.id) === id).map((s) => s.id),
                ),
              )
            }
          >
            {sources.some((s) => s.params.bench_id === id)
              ? "Remover fonte de bancada"
              : sources.some(
                    (s) =>
                      s.id === id &&
                      (s.params.bench_instrument === "generator" || !s.kind.endsWith("dc")),
                  )
                ? "Remover gerador de sinais"
                : "Remover fonte"}
          </button>
          {sources.some((s) => s.params.bench_id === id) && (
            <fieldset className="supply-channel-switches">
              <legend>Canais em uso</legend>
              {[1, 2, 3].map((channel) => {
                const component = sources.find(
                  (s) => s.params.bench_id === id && s.params.bench_channel === String(channel),
                );
                return (
                  <label className="inline" key={channel}>
                    <input
                      type="checkbox"
                      aria-label={`Usar CH${channel} ${id}`}
                      checked={!!component}
                      disabled={
                        !!component && sources.filter((s) => s.params.bench_id === id).length === 1
                      }
                      onChange={(e) =>
                        onChange(
                          e.target.checked
                            ? addSupplyChannel(schematic, id, channel)
                            : removeSources(schematic, [component!.id]),
                        )
                      }
                    />
                    CH {channel}
                    {channel === 3 ? " · 5 V" : " · ajustável"}
                  </label>
                );
              })}
            </fieldset>
          )}
          <div className="power-channels">
            {sources
              .filter((s) => (s.params.bench_id ?? s.id) === id)
              .map((c) => {
                const current = liveData?.traces[`i(${c.ref.toLowerCase()})`]
                  ? -liveData.traces[`i(${c.ref.toLowerCase()})`]!.values.at(-1)!
                  : measured.job === job?.id
                    ? measured.currents[`i(${c.ref.toLowerCase()})`]
                    : undefined;
                return (
                  <div className="power-channel" key={c.id}>
                    <strong>
                      {c.params.bench_channel ? `CH ${c.params.bench_channel}` : c.ref}{" "}
                      <small>{c.ref}</small>
                    </strong>
                    <div className="instrument-display">
                      <output aria-label={`Valor ajustado ${c.ref}`}>
                        {formatEng(sourceSettings(c).offset, c.kind.startsWith("i") ? "A" : "V")}
                      </output>
                      <output aria-label={`Corrente drenada ${c.ref}`}>
                        {current === undefined ? "— A" : formatEng(current, "A")}
                      </output>
                      <small>
                        {current === undefined
                          ? "Corrente: adicione probe I e simule"
                          : "Corrente fornecida · último ponto da simulação"}
                      </small>
                    </div>
                    <details>
                      <summary>Ajustar canal</summary>
                      <SourceControls component={c} onChange={change} />
                    </details>
                    <div className="binding-posts">
                      <span className="post positive">+</span>
                      <span className="post negative">−</span>
                      <span>Conexões com a protoboard</span>
                    </div>
                    <div className="source-terminal-selects">
                      {["p", "n"].map((terminal) => (
                        <label key={terminal}>
                          Terminal {terminal === "p" ? "+" : "−"} · {c.ref}
                          <select
                            aria-label={`Furo ${c.ref} ${terminal === "p" ? "+" : "−"}`}
                            value={
                              schematic.breadboard?.parts.find((p) => p.ref === c.ref)?.legs[
                                terminal
                              ] ?? ""
                            }
                            disabled={!spec}
                            onChange={(e) => connect(c, terminal, e.target.value)}
                          >
                            <option value="">Desconectado</option>
                            {holes.map((h) => (
                              <option key={h} value={h}>
                                {h}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
