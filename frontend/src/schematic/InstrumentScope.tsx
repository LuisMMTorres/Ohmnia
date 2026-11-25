import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Job, type PlotData, type PlotInfo } from "../api";
import { ScopeMeasurements } from "./ScopeMeasurements";
import { scopePoints } from "./scopeGeometry";
import { formatEng } from "../format";

const COLORS = ["#ffe15b", "#65d7ff", "#ff8cc8", "#98ed8e"];
interface Channel {
  signal: string;
  enabled: boolean;
  scale: number;
  position: number;
  coupling: "DC" | "AC";
}
export function InstrumentScope({
  job,
  plot,
  signals,
  initialChannels = 2,
  onChannelsChange,
  channelSignals,
  liveData,
}: {
  job: Job;
  plot: PlotInfo;
  signals: string[];
  initialChannels?: 2 | 4;
  onChannelsChange?: (count: 2 | 4) => void;
  channelSignals?: (string | null)[];
  liveData?: PlotData;
}) {
  const operatingPoint = plot.kind === "op";
  const availableSignals = useMemo(
    () =>
      signals.filter((name) =>
        plot.vectors.some((v) => v.name === name && ["V", "A"].includes(v.unit)),
      ),
    [signals, plot],
  );
  const signalUnit = (name: string) => plot.vectors.find((v) => v.name === name)?.unit ?? "V";
  const [count, setCount] = useState<number>(initialChannels);
  useEffect(() => setCount(initialChannels), [initialChannels]);
  const [channels, setChannels] = useState<Channel[]>(() =>
    Array.from({ length: 4 }, (_, i) => ({
      signal: channelSignals ? (channelSignals[i] ?? "") : (availableSignals[i] ?? ""),
      enabled: i < initialChannels,
      scale: 1,
      position: 0,
      coupling: "DC",
    })),
  );
  const [timeDiv, setTimeDiv] = useState(0.001);
  const [start, setStart] = useState(0);
  const [trigger, setTrigger] = useState(-1);
  const [level, setLevel] = useState(0);
  const [slope, setSlope] = useState("rising");
  const [stopped, setStopped] = useState(false);
  const [autoRangeLive, setAutoRangeLive] = useState(true);
  const [measuring, setMeasuring] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PlotData | null>(null);
  const [error, setError] = useState("");
  const live = liveData !== undefined;
  const handleMeasuring = useCallback(
    (enabled: boolean) => {
      setMeasuring(enabled);
      if (enabled && live) setStopped(true);
    },
    [live],
  );
  const autosetDone = useRef(false);
  const autoset = useCallback((out: PlotData) => {
    const times = out.x?.values;
    if (times?.length && times[times.length - 1]! > times[0]!)
      setTimeDiv((times[times.length - 1]! - times[0]!) / 10);
    setChannels((old) =>
      old.map((ch) => {
        const values = out.traces[ch.signal]?.values ?? [];
        const max = values.reduce((m, v) => Math.max(m, Math.abs(v)), 0);
        return { ...ch, scale: max ? Number((max / 3).toPrecision(2)) : 1, position: 0 };
      }),
    );
  }, []);
  useEffect(() => {
    setChannels((old) =>
      old.map((ch, i) => ({
        ...ch,
        signal: channelSignals
          ? (channelSignals[i] ?? "")
          : availableSignals.includes(ch.signal)
            ? ch.signal
            : (availableSignals[i] ?? ""),
      })),
    );
  }, [availableSignals, channelSignals]);
  const namesKey = JSON.stringify([
    ...new Set(
      channels
        .slice(0, count)
        .filter((c) => c.enabled && c.signal)
        .map((c) => c.signal),
    ),
  ]);
  const names = useMemo<string[]>(() => JSON.parse(namesKey) as string[], [namesKey]);
  useEffect(() => {
    if (!liveData || stopped) return;
    setData(liveData);
    const times = liveData.x?.values ?? [];
    if (times.length) setStart(Math.max(times[0]!, times.at(-1)! - timeDiv * 10));
    if (!autosetDone.current && liveData.x?.values.length && Object.keys(liveData.traces).length) {
      autosetDone.current = true;
      autoset(liveData);
    }
    if (autoRangeLive)
      setChannels((old) =>
        old.map((ch) => {
          const values = liveData.traces[ch.signal]?.values ?? [];
          const center =
            ch.coupling === "AC" && values.length
              ? values.reduce((sum, v) => sum + v, 0) / values.length
              : 0;
          const peak = values.reduce((m, v) => Math.max(m, Math.abs(v - center)), 0);
          return peak > Math.abs(ch.scale) * 3.8
            ? { ...ch, scale: Number((peak / 3).toPrecision(2)) }
            : ch;
        }),
      );
  }, [liveData, stopped, autoset, autoRangeLive, timeDiv]);
  useEffect(() => {
    if (liveData || (stopped && !measuring) || !names.length) return;
    setLoading(true);
    let cancelled = false;
    api
      .plot(job.id, plot.name, names, "real", measuring ? 2_000_000 : 10000)
      .then((out) => {
        if (!cancelled) {
          setData(out);
          if (!autosetDone.current) {
            autosetDone.current = true;
            autoset(out);
          }
          setError("");
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [job.id, plot.name, names, stopped, autoset, measuring, liveData]);
  const update = (i: number, changes: Partial<Channel>) => {
    if (changes.scale !== undefined || changes.position !== undefined) setAutoRangeLive(false);
    setChannels((old) => old.map((c, n) => (n === i ? { ...c, ...changes } : c)));
  };
  let windowStart =
    liveData && !stopped
      ? Math.max(data?.x?.values[0] ?? 0, (data?.x?.values.at(-1) ?? 0) - timeDiv * 10)
      : start;
  const triggerSignal = channels[trigger]?.signal;
  const tx = data?.x?.values ?? [];
  const ty = triggerSignal ? data?.traces[triggerSignal]?.values : undefined;
  if (ty) {
    const crossing = ty.findIndex(
      (v, i) =>
        i > 0 &&
        tx[i]! >= start &&
        (slope === "rising" ? ty[i - 1]! < level && v >= level : ty[i - 1]! > level && v <= level),
    );
    if (crossing >= 0) windowStart = Math.max(0, tx[crossing]! - 2 * timeDiv);
  }
  return (
    <section className="oscilloscope-face" aria-label="Osciloscópio de bancada">
      <header className="scope-instrument-header">
        <strong>OHMNIA · Osciloscópio digital</strong>
        <span>Instrumento didático · {plot.run_label || "execução atual"}</span>
      </header>
      <div className="row wrap scope-controls">
        {liveData && (
          <label className="inline">
            <input
              type="checkbox"
              checked={autoRangeLive}
              onChange={(e) => setAutoRangeLive(e.target.checked)}
            />
            Ampliar escala automaticamente
          </label>
        )}
        <label>
          Modelo
          <select
            aria-label="Canais do osciloscópio"
            value={count}
            onChange={(e) => {
              const next = Number(e.target.value) as 2 | 4;
              setCount(next);
              onChannelsChange?.(next);
            }}
          >
            <option value={2}>2 canais</option>
            <option value={4}>4 canais</option>
          </select>
        </label>
        <label>
          Tempo/div (s)
          <input
            type="number"
            min={1e-12}
            step="any"
            disabled={operatingPoint}
            value={timeDiv}
            onChange={(e) => e.target.valueAsNumber > 0 && setTimeDiv(e.target.valueAsNumber)}
          />
        </label>
        <label>
          Início (s)
          <input
            type="number"
            min={0}
            step="any"
            disabled={operatingPoint || (live && !stopped)}
            value={start}
            onChange={(e) =>
              Number.isFinite(e.target.valueAsNumber) && setStart(e.target.valueAsNumber)
            }
          />
        </label>
        <button onClick={() => setStopped(!stopped)}>{stopped ? "Run" : "Stop"}</button>
        <button disabled={!data} onClick={() => data && autoset(data)}>
          Autoset
        </button>
      </div>
      <ScopeMeasurements
        key={`${job.id}-${plot.name}`}
        channels={channels.slice(0, count).flatMap((ch, i) => {
          const values =
            ch.enabled && names.includes(ch.signal) ? data?.traces[ch.signal]?.values : undefined;
          return values?.length
            ? [
                {
                  name: `CH${i + 1}`,
                  signal: ch.signal,
                  unit: signalUnit(ch.signal),
                  color: COLORS[i]!,
                  values,
                  scale: ch.scale,
                  position: ch.position,
                  ac: ch.coupling === "AC",
                },
              ]
            : [];
        })}
        times={tx}
        start={windowStart}
        timeDiv={timeDiv}
        operatingPoint={operatingPoint}
        onEnabledChange={handleMeasuring}
      >
        <svg
          viewBox="0 0 1000 440"
          className="instrument-screen"
          role="img"
          aria-label="Traços dos canais conectados"
        >
          <defs>
            <clipPath id="scope-screen-clip">
              <rect x={70} y={25} width={880} height={360} />
            </clipPath>
          </defs>
          <rect width={1000} height={440} fill="#07171b" rx={6} />
          {Array.from({ length: 11 }, (_, i) => (
            <line
              key={`x${i}`}
              x1={70 + i * 88}
              x2={70 + i * 88}
              y1={25}
              y2={385}
              stroke="#244049"
            />
          ))}
          {Array.from({ length: 9 }, (_, i) => (
            <line
              key={`y${i}`}
              x1={70}
              x2={950}
              y1={25 + i * 45}
              y2={25 + i * 45}
              stroke="#244049"
            />
          ))}
          <g clipPath="url(#scope-screen-clip)">
            {channels.slice(0, count).map((ch, i) => {
              const values = ch.enabled ? data?.traces[ch.signal]?.values : undefined;
              if (!values || !names.includes(ch.signal)) return null;
              const points = scopePoints(
                tx,
                values,
                ch.scale,
                ch.position,
                ch.coupling === "AC",
                windowStart,
                timeDiv,
                operatingPoint,
              );
              return (
                <polyline
                  key={i}
                  data-channel={i + 1}
                  points={points.map((p) => `${p.x},${p.y}`).join(" ")}
                  fill="none"
                  stroke={COLORS[i]}
                  strokeWidth={2}
                />
              );
            })}
          </g>
          <text x={70} y={415} fill="#b4d6df" fontSize={14}>
            {operatingPoint
              ? "Ponto de operação CC · nível constante (sem aquisição temporal)"
              : `${formatEng(timeDiv, "s")}/div · ${formatEng(windowStart, "s")} a ${formatEng(windowStart + 10 * timeDiv, "s")}`}
          </text>
          <text x={800} y={415} fill="#b4d6df" fontSize={14}>
            {stopped ? "STOP" : "DADOS DA SIMULAÇÃO"}
          </text>
        </svg>
      </ScopeMeasurements>
      {measuring && loading && <p role="status">Carregando aquisição para medição…</p>}
      {measuring && plot.vectors.some((v) => names.includes(v.name) && v.length > 2_000_000) && (
        <p role="status">
          Aquisição acima de 2 milhões de pontos: as leituras usam amostras reduzidas.
        </p>
      )}
      <div className="scope-channel-grid">
        {channels.slice(0, count).map((ch, i) => (
          <fieldset key={i} style={{ borderColor: COLORS[i] }}>
            <legend style={{ color: COLORS[i] }}>CH {i + 1}</legend>
            {operatingPoint && (
              <output aria-label={`Leitura CH${i + 1}`}>
                {ch.enabled && data?.traces[ch.signal]?.values.length
                  ? formatEng(
                      ch.coupling === "AC" ? 0 : data.traces[ch.signal]!.values[0]!,
                      signalUnit(ch.signal),
                    )
                  : "—"}
              </output>
            )}

            <label>
              <input
                type="checkbox"
                checked={ch.enabled}
                onChange={(e) => update(i, { enabled: e.target.checked })}
              />
              Ativar canal
            </label>
            <label>
              Ponteira / sinal
              <select
                aria-label={`Sinal CH${i + 1}`}
                disabled={!!channelSignals}
                value={ch.signal}
                onChange={(e) => update(i, { signal: e.target.value })}
              >
                <option value="">Desconectado</option>
                {availableSignals.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              {signalUnit(ch.signal)}/div
              <input
                type="number"
                min={1e-12}
                step="any"
                value={ch.scale}
                onChange={(e) =>
                  e.target.valueAsNumber > 0 && update(i, { scale: e.target.valueAsNumber })
                }
              />
            </label>
            <label>
              Posição (div)
              <input
                type="number"
                step="any"
                value={ch.position}
                onChange={(e) =>
                  Number.isFinite(e.target.valueAsNumber) &&
                  update(i, { position: e.target.valueAsNumber })
                }
              />
            </label>
            <label>
              Acoplamento
              <select
                value={ch.coupling}
                onChange={(e) => update(i, { coupling: e.target.value as "DC" | "AC" })}
              >
                <option>DC</option>
                <option>AC</option>
              </select>
            </label>
          </fieldset>
        ))}
      </div>
      <div className="row wrap scope-controls">
        <label>
          Trigger
          <select
            disabled={operatingPoint}
            value={trigger}
            onChange={(e) => setTrigger(Number(e.target.value))}
          >
            <option value={-1}>Livre</option>
            {channels.slice(0, count).map((_, i) => (
              <option key={i} value={i}>
                CH {i + 1}
              </option>
            ))}
          </select>
        </label>
        <label>
          Nível ({signalUnit(channels[trigger]?.signal ?? "")})
          <input
            type="number"
            step="any"
            disabled={operatingPoint}
            value={level}
            onChange={(e) =>
              Number.isFinite(e.target.valueAsNumber) && setLevel(e.target.valueAsNumber)
            }
          />
        </label>
        <label>
          Borda
          <select
            disabled={operatingPoint}
            value={slope}
            onChange={(e) => setSlope(e.target.value)}
          >
            <option value="rising">Subida</option>
            <option value="falling">Descida</option>
          </select>
        </label>
      </div>
      {!availableSignals.length && (
        <p role="status">
          Nenhuma probe de tensão ou corrente disponível. Conecte uma probe ao circuito e simule
          novamente.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p className="small">
        As ponteiras selecionam probes do circuito simulado. Acoplamento AC remove a média dos
        dados; trigger e Run/Stop operam sobre a aquisição simulada.
      </p>
    </section>
  );
}
