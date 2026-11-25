import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { request, type Job, type PlotData, type PlotInfo } from "../api";
import { formatEng } from "../format";
import { InstrumentScope } from "../schematic/InstrumentScope";
import { MANUAL_SWITCH_KINDS } from "../schematic/switches";
import type { Schematic } from "../schematic/types";
import { netAtHole } from "./connections";
import { meterReadings } from "./meter";
import type { ResolveOut, Spec } from "./types";
import "./interactiveBench.css";

interface Snapshot {
  time: number;
  data: { x: { unit: string; values: number[] }; traces: PlotData["traces"] };
}
const source = (kind: string) => /^[vi](dc|sin|pulse|pwl)$/.test(kind);
const controls = (sch: Schematic) =>
  Object.fromEntries(
    sch.components.flatMap((c) =>
      source(c.kind)
        ? [[c.ref, c.params]]
        : MANUAL_SWITCH_KINDS.has(c.kind)
          ? [[c.ref, { state: c.params.state ?? "0" }]]
          : [],
    ),
  );
/** Instrument positions, probe placement and live controls do not change electrical topology. */
export function benchTopology(sch: Schematic) {
  return JSON.stringify({
    components: sch.components.map((c) => ({
      ...c,
      params: source(c.kind)
        ? {}
        : MANUAL_SWITCH_KINDS.has(c.kind)
          ? { ...c.params, state: "" }
          : c.params,
    })),
    wires: sch.wires,
    labels: sch.labels,
    params: sch.params,
    temperature: sch.temperature,
    analyses: sch.analyses,
    sweep: sch.sweep,
    directives: sch.directives,
    assembly: sch.breadboard && {
      parts: sch.breadboard.parts,
      wires: sch.breadboard.wires.map((w) => [w.a, w.b]),
      rails_split: sch.breadboard.rails_split,
    },
  });
}

export function InteractiveBench({
  schematic,
  spec,
  resolved,
  onActiveChange,
  onSnapshot,
  instruments,
  onChange,
  meter,
  onMeterChange,
}: {
  schematic: Schematic;
  spec: Spec | null;
  resolved: ResolveOut | null;
  onActiveChange: (active: boolean) => void;
  onSnapshot: (data: PlotData | null) => void;
  instruments: ReactNode;
  onChange: (next: Schematic) => void;
  meter: boolean;
  onMeterChange: (enabled: boolean) => void;
}) {
  const [id, setId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [windowSeconds, setWindowSeconds] = useState("0.01");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [quantity, setQuantity] = useState("voltage");
  const [mode, setMode] = useState("dc");
  const [positive, setPositive] = useState("");
  const [negative, setNegative] = useState("");
  const [branch, setBranch] = useState("");
  const [held, setHeld] = useState<ReturnType<typeof meterReadings>>(null);
  const latest = useRef({ schematic, onActiveChange, onSnapshot });
  latest.current = { schematic, onActiveChange, onSnapshot };
  const session = useRef<string | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);
  const baseline = useRef("");
  const sent = useRef<Record<string, Record<string, string>>>({});
  const inFlight = useRef(false);
  const close = (key: string) => {
    void fetch(`/api/v1/bench/${key}`, { method: "DELETE", keepalive: true }).catch(() => {});
  };
  const stop = () => {
    generation.current++;
    if (session.current) close(session.current);
    session.current = null;
    setId(null);
    setRunning(false);
    latest.current.onActiveChange(false);
    latest.current.onSnapshot(null);
  };
  useEffect(() => {
    mounted.current = true;
    const release = () => {
      if (session.current) close(session.current);
    };
    window.addEventListener("pagehide", release);
    return () => {
      window.removeEventListener("pagehide", release);
      mounted.current = false;
      release();
      session.current = null;
      latest.current.onActiveChange(false);
      latest.current.onSnapshot(null);
    };
  }, []);
  const start = async () => {
    setBusy(true);
    setError("");
    setSnapshot(null);
    setHeld(null);
    const token = ++generation.current;
    const sch = latest.current.schematic;
    try {
      const interval = Number(windowSeconds);
      if (!Number.isFinite(interval) || interval < 1e-6 || interval > 1)
        throw new Error("Informe um intervalo entre 1 µs e 1 s.");
      const result = await request<{ id: string }>("/bench", {
        method: "POST",
        body: JSON.stringify({ schematic: sch, window_s: interval }),
      });
      if (!mounted.current || token !== generation.current) {
        close(result.id);
        return;
      }
      session.current = result.id;
      baseline.current = benchTopology(sch);
      sent.current = controls(sch);
      setId(result.id);
      setRunning(true);
      latest.current.onActiveChange(true);
    } catch (e) {
      if (mounted.current && token === generation.current) setError((e as Error).message);
    } finally {
      if (mounted.current && token === generation.current) setBusy(false);
    }
  };
  useEffect(() => {
    if (!id || !running) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (inFlight.current) {
        timer = setTimeout(() => void tick(), 50);
        return;
      }
      inFlight.current = true;
      try {
        const sch = latest.current.schematic;
        if (benchTopology(sch) !== baseline.current)
          throw new Error(
            "Circuito ou fiação alterados. Inicie novamente para aplicar a nova montagem.",
          );
        const current = controls(sch);
        const changed = Object.fromEntries(
          Object.entries(current).filter(
            ([ref, params]) => JSON.stringify(params) !== JSON.stringify(sent.current[ref]),
          ),
        );
        const out = await request<Snapshot>(`/bench/${id}/advance`, {
          method: "POST",
          body: JSON.stringify({ controls: changed }),
        });
        if (session.current !== id) return;
        sent.current = current;
        setSnapshot(out);
        latest.current.onSnapshot({
          plot: "live",
          kind: "tran",
          x: out.data.x,
          x_name: "time",
          traces: out.data.traces,
          decimated: false,
        });
        if (!cancelled) timer = setTimeout(() => void tick(), 200);
      } catch (e) {
        if (session.current !== id) return;
        setError((e as Error).message);
        close(id);
        session.current = null;
        setId(null);
        setRunning(false);
        latest.current.onActiveChange(false);
        latest.current.onSnapshot(null);
      } finally {
        inFlight.current = false;
      }
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id, running]);
  // Pausing also permits parameter edits; a topology edit is detected before resuming.
  const holes = [
    ...new Set([
      ...(schematic.breadboard?.parts.flatMap((p) => Object.values(p.legs)) ?? []),
      ...(schematic.breadboard?.wires.flatMap((w) => [w.a, w.b]) ?? []),
    ]),
  ].sort();
  const times = snapshot?.data.x.values ?? [];
  const nodeValues = (hole: string): number[] => {
    if (!hole || !spec || !resolved || !schematic.breadboard)
      throw new Error("Selecione os dois furos das ponteiras.");
    const node = netAtHole(spec.board, schematic.breadboard, resolved, hole);
    if (node === "0") return times.map(() => 0);
    const values = snapshot?.data.traces[`v(${node})`]?.values;
    if (!values) throw new Error("Aguardando aquisição neste nó.");
    return values;
  };
  let reading: ReturnType<typeof meterReadings> = null,
    meterError = "";
  try {
    if (snapshot) {
      const reference = quantity === "voltage" ? nodeValues(negative) : [];
      const values =
        quantity === "voltage"
          ? nodeValues(positive).map((v, i) => v - reference[i]!)
          : (snapshot.data.traces[branch]?.values ?? []);
      reading = meterReadings(times, values);
    }
  } catch (e) {
    meterError = (e as Error).message;
  }
  const displayed = held ?? reading;
  const unit = quantity === "voltage" ? "V" : "A";
  const scopeData = useMemo(() => {
    const traces: PlotData["traces"] = {};
    if (snapshot && spec && resolved && schematic.breadboard) {
      for (const [channel, wire] of Object.entries(schematic.bench_scope_connections ?? {})) {
        if (!wire.positive || !wire.negative) continue;
        try {
          const value = (hole: string) => {
            const node = netAtHole(spec.board, schematic.breadboard!, resolved, hole);
            return node === "0"
              ? snapshot.data.x.values.map(() => 0)
              : snapshot.data.traces[`v(${node})`]?.values;
          };
          const a = value(wire.positive),
            b = value(wire.negative);
          if (a && b)
            traces[`osc_ch${channel}`] = { unit: "V", values: a.map((v, i) => v - b[i]!) };
        } catch {
          /* Disconnected probes have no trace. */
        }
      }
    }
    return {
      plot: "live",
      kind: "tran",
      x: snapshot?.data.x ?? null,
      x_name: "time",
      traces,
      decimated: false,
    } satisfies PlotData;
  }, [snapshot, spec, resolved, schematic]);
  const plot: PlotInfo = {
    name: "live",
    title: "Bancada interativa",
    kind: "tran",
    scale: "time",
    vectors: Object.entries(scopeData.traces).map(([name, v]) => ({
      name,
      unit: v.unit,
      length: v.values.length,
      complex: false,
    })),
  };
  const job: Job = {
    id: id ?? "stopped-bench",
    state: "running",
    progress: 0,
    message: "Bancada interativa",
  };
  return (
    <section className="interactive-bench panel" aria-label="Bancada interativa">
      <div className="row wrap">
        <strong>Bancada interativa</strong>
        <label>
          Intervalo de aquisição (s)
          <input
            type="number"
            min="0.000001"
            max="1"
            step="any"
            value={windowSeconds}
            disabled={!!id || busy}
            onChange={(e) => setWindowSeconds(e.target.value)}
          />
        </label>
        {!id ? (
          <button disabled={busy || !spec || !resolved} onClick={() => void start()}>
            {busy ? "Iniciando…" : "Iniciar bancada"}
          </button>
        ) : (
          <>
            <button onClick={() => setRunning((v) => !v)}>
              {running ? "Pausar bancada" : "Continuar bancada"}
            </button>
            <button className="secondary" onClick={stop}>
              Parar bancada
            </button>
          </>
        )}
        <button
          className="secondary"
          onClick={() => {
            onMeterChange(!meter);
            setHeld(null);
          }}
        >
          {meter ? "Retirar multímetro" : "Adicionar multímetro"}
        </button>
        <output aria-live="off" data-testid="bench-time">
          {id ? (running ? "Em execução" : "Pausada") : "Parada"} · tempo simulado:{" "}
          {formatEng(snapshot?.time ?? 0, "s")}
        </output>
      </div>
      <p className="small muted">
        Opere as chaves na placa e ajuste as fontes/geradores nos seus painéis. A bancada mantém o
        estado elétrico entre aquisições. Mudanças de fiação ou tipo de onda exigem reiniciar. A
        velocidade depende do circuito.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {meter && (
        <fieldset className="live-multimeter">
          <legend>OHMNIA · Multímetro virtual</legend>
          <div className="row wrap">
            <label>
              Medida
              <select
                aria-label="Medida"
                value={quantity}
                onChange={(e) => {
                  setQuantity(e.target.value);
                  setHeld(null);
                }}
              >
                <option value="voltage">Tensão entre ponteiras</option>
                <option value="current">Corrente de um ramo</option>
              </select>
            </label>
            <label>
              Modo
              <select
                aria-label="Modo do multímetro"
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value);
                  setHeld(null);
                }}
              >
                <option value="dc">CC · média</option>
                <option value="instant">Valor instantâneo</option>
                <option value="ac">CA · eficaz sem componente CC</option>
              </select>
            </label>
            {quantity === "voltage" ? (
              <>
                {[
                  ["Ponteira +", positive, setPositive],
                  ["Ponteira − / COM", negative, setNegative],
                ].map(([label, value, setter]) => (
                  <label key={label as string}>
                    {label as string}
                    <select
                      aria-label={label as string}
                      value={value as string}
                      onChange={(e) => {
                        (setter as (v: string) => void)(e.target.value);
                        setHeld(null);
                      }}
                    >
                      <option value="">Selecione o furo</option>
                      {holes.map((h) => (
                        <option key={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </>
            ) : (
              <label>
                Ramo medido
                <select
                  aria-label="Ramo medido"
                  value={branch}
                  onChange={(e) => {
                    setBranch(e.target.value);
                    setHeld(null);
                  }}
                >
                  <option value="">Selecione o componente</option>
                  {Object.entries(snapshot?.data.traces ?? {})
                    .filter(
                      ([key]) =>
                        /^i\([^)]*\)$/.test(key) &&
                        schematic.components.some((c) => key === `i(${c.ref.toLowerCase()})`),
                    )
                    .map(([key]) => (
                      <option key={key}>{key}</option>
                    ))}
                </select>
              </label>
            )}
            <button
              className="secondary"
              disabled={!reading}
              onClick={() => setHeld(held ? null : reading)}
            >
              {held ? "Liberar HOLD" : "HOLD"}
            </button>
          </div>
          <output className="multimeter-display" data-testid="meter-reading">
            {displayed
              ? formatEng(
                  mode === "dc"
                    ? displayed.mean
                    : mode === "instant"
                      ? displayed.instant
                      : displayed.acRms,
                  unit,
                )
              : "—"}
            {held ? " · HOLD" : ""}
          </output>
          {displayed && (
            <p>
              Média CC: {formatEng(displayed.mean, unit)} · Eficaz total:{" "}
              {formatEng(displayed.rms, unit)} · Janela: {formatEng(displayed.duration, "s")}
            </p>
          )}
          <p className="small muted">
            {meterError ||
              (quantity === "current"
                ? "Corrente positiva entrando pelo primeiro pino do componente. O sensor ideal é inserido em série; não é uma ligação em paralelo entre furos."
                : "Medição ideal de alta impedância; selecione os furos + e COM da protoboard.")}
          </p>
        </fieldset>
      )}
      {id && !!schematic.bench_scope_channels && (
        <InstrumentScope
          job={job}
          plot={plot}
          signals={Object.keys(scopeData.traces)}
          initialChannels={schematic.bench_scope_channels === 4 ? 4 : 2}
          channelSignals={Array.from({ length: schematic.bench_scope_channels }, (_, i) =>
            scopeData.traces[`osc_ch${i + 1}`] ? `osc_ch${i + 1}` : null,
          )}
          liveData={scopeData}
          onChannelsChange={(count) => onChange({ ...schematic, bench_scope_channels: count })}
        />
      )}
      {id && instruments}
    </section>
  );
}
