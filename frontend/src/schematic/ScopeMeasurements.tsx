import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type PointerEvent,
} from "react";
import { formatEng } from "../format";
import { amplitudeAtY, amplitudeY, cursorDelta, sampleAt } from "./cursorMath";
import "./scopeMeasurements.css";

export interface MeasurementChannel {
  name: string;
  signal: string;
  unit: string;
  color: string;
  values: number[];
  scale: number;
  position: number;
  ac: boolean;
}
type Marker = "ta" | "tb" | "ya" | "yb";
const COLORS = { a: "#ffb347", b: "#a6b5ff" };
const read = (value: number | null, unit: string) =>
  value == null ? "—" : formatEng(value, unit, 7);

function CursorNumberInput({
  label,
  unit,
  value,
  onChange,
}: {
  label: string;
  unit: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);
  return (
    <label>
      {label} ({unit})
      <input
        aria-label={`${label} (${unit})`}
        type="number"
        step="any"
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          if (Number.isFinite(event.target.valueAsNumber)) onChange(event.target.valueAsNumber);
        }}
        onBlur={() => {
          if (!draft || !Number.isFinite(Number(draft))) setDraft(String(value));
        }}
      />
    </label>
  );
}

export function ScopeMeasurements({
  children,
  channels,
  times,
  start,
  timeDiv,
  operatingPoint,
  onEnabledChange,
}: {
  children: ReactNode;
  channels: MeasurementChannel[];
  times: number[];
  start: number;
  timeDiv: number;
  operatingPoint: boolean;
  onEnabledChange: (enabled: boolean) => void;
}) {
  const [timeOn, setTimeOn] = useState(false);
  const [amplitudeOn, setAmplitudeOn] = useState(false);
  const [reference, setReference] = useState("");
  const [positions, setPositions] = useState<Partial<Record<Marker, number>>>({});
  const dragging = useRef<Marker | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const clip = useId().replace(/:/g, "");
  const enabled = timeOn || amplitudeOn;
  useEffect(() => {
    onEnabledChange(enabled);
  }, [enabled, onEnabledChange]);
  // Cache AC offsets once per acquisition, rather than scanning full traces on every drag.
  const means = useMemo(
    () =>
      new Map(
        channels.map((channel) => [
          channel.name,
          channel.ac && channel.values.length
            ? channel.values.reduce((sum, value) => sum + value, 0) / channel.values.length
            : 0,
        ]),
      ),
    [channels],
  );
  const sample = (channel: MeasurementChannel, time: number, op = false) =>
    sampleAt(times, channel.values, time, op, channel.ac, means.get(channel.name));
  const ref = channels.find((c) => c.name === reference) ?? channels[0];
  useEffect(() => {
    setPositions((old) => ({ ta: old.ta, tb: old.tb }));
  }, [ref?.name, ref?.signal, ref?.unit, ref?.ac]);
  const ta = positions.ta ?? start + timeDiv * 2.5;
  const tb = positions.tb ?? start + timeDiv * 7.5;
  const ya = positions.ya ?? (ref ? amplitudeAtY(250, ref.scale, ref.position) : 0);
  const yb = positions.yb ?? (ref ? amplitudeAtY(160, ref.scale, ref.position) : 1);
  const deltaT = tb - ta;
  const move = (event: PointerEvent<SVGElement>) => {
    const key = dragging.current,
      surface = svg.current;
    if (!key || !surface) return;
    const matrix = surface.getScreenCTM();
    if (!matrix) return;
    const point = surface.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    const value = key.startsWith("t")
      ? start + ((Math.max(70, Math.min(950, local.x)) - 70) / 88) * timeDiv
      : ref
        ? amplitudeAtY(Math.max(25, Math.min(385, local.y)), ref.scale, ref.position)
        : 0;
    setPositions((old) => ({ ...old, [key]: value }));
  };
  const capture = (event: PointerEvent<SVGElement>, key: Marker) => {
    event.preventDefault();
    dragging.current = key;
    svg.current?.setPointerCapture(event.pointerId);
    move(event);
  };
  const input = (label: string, key: Marker, value: number, unit: string) => (
    <CursorNumberInput
      label={label}
      unit={unit}
      value={value}
      onChange={(next) => setPositions((old) => ({ ...old, [key]: next }))}
    />
  );
  return (
    <div className="scope-measurements">
      <fieldset className="scope-cursor-controls">
        <legend>Cursores de medição</legend>
        <label>
          <input
            type="checkbox"
            checked={timeOn}
            disabled={operatingPoint}
            onChange={(event) => setTimeOn(event.target.checked)}
          />
          Tempo A/B
        </label>
        <label>
          <input
            type="checkbox"
            checked={amplitudeOn}
            onChange={(event) => setAmplitudeOn(event.target.checked)}
          />
          Amplitude A/B
        </label>
        <button type="button" disabled={!enabled} onClick={() => setPositions({})}>
          Reposicionar cursores
        </button>
        {operatingPoint && (
          <span className="small">CC: sem eixo temporal; use os cursores de amplitude.</span>
        )}
      </fieldset>
      <div className="scope-acquisition">
        {children}
        <svg
          ref={svg}
          className="scope-measurement-overlay"
          viewBox="0 0 1000 440"
          aria-label="Cursores arrastáveis de medição"
          onPointerMove={move}
          onPointerUp={() => {
            dragging.current = null;
          }}
          onPointerCancel={() => {
            dragging.current = null;
          }}
          onLostPointerCapture={() => {
            dragging.current = null;
          }}
        >
          <defs>
            <clipPath id={clip}>
              <rect x={70} y={25} width={880} height={360} />
            </clipPath>
          </defs>
          <g clipPath={`url(#${clip})`}>
            {timeOn &&
              !operatingPoint &&
              (
                [
                  ["a", ta],
                  ["b", tb],
                ] as const
              ).map(([key, time]) => {
                const x = 70 + ((time - start) / timeDiv) * 88;
                return (
                  <g key={key}>
                    <line
                      x1={x}
                      x2={x}
                      y1={25}
                      y2={385}
                      stroke={COLORS[key]}
                      strokeDasharray="7 4"
                    />
                    <text x={x + 6} y={43} fill={COLORS[key]} fontSize={16}>
                      T{key.toUpperCase()}
                    </text>
                    <line
                      data-cursor={`t${key}`}
                      x1={x}
                      x2={x}
                      y1={25}
                      y2={385}
                      className="scope-cursor-time"
                      onPointerDown={(event) => capture(event, `t${key}`)}
                    />
                    {channels.map((channel) => {
                      const value = sample(channel, time);
                      return value == null ? null : (
                        <circle
                          key={channel.name}
                          cx={x}
                          cy={amplitudeY(value, channel.scale, channel.position)}
                          r={5}
                          stroke={COLORS[key]}
                          fill={channel.color}
                        />
                      );
                    })}
                  </g>
                );
              })}
            {amplitudeOn &&
              ref &&
              (
                [
                  ["a", ya],
                  ["b", yb],
                ] as const
              ).map(([key, value]) => {
                const y = amplitudeY(value, ref.scale, ref.position);
                return (
                  <g key={key}>
                    <line
                      x1={70}
                      x2={950}
                      y1={y}
                      y2={y}
                      stroke={COLORS[key]}
                      strokeDasharray="4 4"
                    />
                    <text x={78} y={y - 7} fill={COLORS[key]} fontSize={16}>
                      Y{key.toUpperCase()} · {ref.name}
                    </text>
                    <line
                      data-cursor={`y${key}`}
                      x1={70}
                      x2={950}
                      y1={y}
                      y2={y}
                      className="scope-cursor-amplitude"
                      onPointerDown={(event) => capture(event, `y${key}`)}
                    />
                  </g>
                );
              })}
          </g>
        </svg>
      </div>
      {enabled && (
        <section className="scope-cursor-readouts" aria-label="Leituras dos cursores">
          {timeOn && !operatingPoint && (
            <>
              <div className="scope-cursor-inputs">
                {input("Tempo A", "ta", ta, "s")}
                {input("Tempo B", "tb", tb, "s")}
                <output aria-label="Diferença de tempo">Δt (B − A): {read(deltaT, "s")}</output>
                <output>1/|Δt|: {deltaT ? read(1 / Math.abs(deltaT), "Hz") : "—"}</output>
              </div>
              <div className="table-scroll">
                <table className="params cursors">
                  <caption>Valores dos canais nos cursores de tempo</caption>
                  <thead>
                    <tr>
                      <th>Canal / sinal</th>
                      <th>Em A</th>
                      <th>Em B</th>
                      <th>Δ amplitude (B − A)</th>
                      {channels.length > 1 && ref && (
                        <>
                          <th>Δ para {ref.name} em A</th>
                          <th>Δ para {ref.name} em B</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {channels.map((channel) => {
                      const a = sample(channel, ta);
                      const b = sample(channel, tb);
                      return (
                        <tr key={channel.name}>
                          <td>
                            {channel.name} · {channel.signal} ({channel.ac ? "AC" : "DC"})
                          </td>
                          <td>{read(a, channel.unit)}</td>
                          <td>{read(b, channel.unit)}</td>
                          <td>{read(cursorDelta(a, b), channel.unit)}</td>
                          {channels.length > 1 && ref && (
                            <>
                              <td>
                                {read(
                                  channel.unit === ref.unit
                                    ? cursorDelta(sample(ref, ta), a)
                                    : null,
                                  channel.unit,
                                )}
                              </td>
                              <td>
                                {read(
                                  channel.unit === ref.unit
                                    ? cursorDelta(sample(ref, tb), b)
                                    : null,
                                  channel.unit,
                                )}
                              </td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {amplitudeOn && (
            <div className="scope-cursor-inputs">
              <label>
                Canal de referência
                <select
                  aria-label="Canal dos cursores de amplitude"
                  value={ref?.name ?? ""}
                  onChange={(event) => {
                    setReference(event.target.value);
                    setPositions((old) => ({ ta: old.ta, tb: old.tb }));
                  }}
                >
                  {channels.map((channel) => (
                    <option key={channel.name} value={channel.name}>
                      {channel.name} · {channel.signal} ({channel.unit})
                    </option>
                  ))}
                </select>
              </label>
              {ref ? (
                <>
                  {input("Amplitude A", "ya", ya, ref.unit)}
                  {input("Amplitude B", "yb", yb, ref.unit)}
                  <output aria-label="Diferença de amplitude">
                    Δ amplitude (B − A): {read(yb - ya, ref.unit)}
                  </output>
                </>
              ) : (
                <span>Nenhum canal ativo com dados.</span>
              )}
            </div>
          )}
          {operatingPoint && (
            <div className="table-scroll">
              <table className="params cursors">
                <caption>Níveis CC dos canais ativos</caption>
                <thead>
                  <tr>
                    <th>Canal / sinal</th>
                    <th>Nível</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((channel) => (
                    <tr key={channel.name}>
                      <td>
                        {channel.name} · {channel.signal}
                      </td>
                      <td>{read(sample(channel, 0, true), channel.unit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="small">
            Arraste as linhas ou digite os valores. Leituras interpoladas entre amostras da
            simulação; fora da aquisição: —. AC remove a média; posição e escala não alteram as
            amplitudes medidas. 1/|Δt| representa uma frequência apenas quando o intervalo
            corresponde a um período. Diferenças entre canais são exibidas somente para unidades
            iguais.
          </p>
        </section>
      )}
    </div>
  );
}
