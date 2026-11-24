import { deviceFace } from "./DeviceFaces";
import type { Motion } from "./DeviceFaces";
import { BenchSupplyArt, GeneratorArt } from "./SupplyFaces";

/** Didactic device bodies; no manufacturer specifications are implied. */
export function InstrumentFace({
  x,
  y,
  title,
  kind,
  motion,
  channels = 1,
  readings = [],
  amps = [],
  terminals = 2,
}: {
  x: number;
  y: number;
  title: string;
  kind: string;
  motion?: Motion;
  /** Bench supply: number of channels drawn on one panel and the voltage of each. */
  channels?: number;
  readings?: string[];
  /** Bench supply: current delivered by each channel (ammeter text). */
  amps?: string[];
  terminals?: number;
}) {
  const face = deviceFace(kind);
  if (face)
    return (
      <g transform={`translate(${x},${y})`} className="instrument-face device-face">
        <rect x={-6} y={-16} width={300} height={176} rx={8} className="device-frame" />
        <text x={0} y={-4} fontSize={10} style={{ fill: "#142e41" }}>
          {title.slice(0, 48)}
        </text>
        {face.draw(motion)}
      </g>
    );
  if (/^[vi]dc$/.test(kind))
    return (
      <g transform={`translate(${x},${y})`} className="instrument-face">
        <BenchSupplyArt title={title} channels={channels} readings={readings} amps={amps} />
      </g>
    );
  if (/^[vi](sin|pulse|pwl)$/.test(kind))
    return (
      <g transform={`translate(${x},${y})`} className="instrument-face">
        <GeneratorArt title={title} terminals={terminals} />
      </g>
    );
  const source = /^[vi](dc|sin|pulse|pwl)$/.test(kind);
  const board = /arduino|esp32|stm32/.test(kind);
  return (
    <g
      transform={`translate(${x},${y})`}
      className={`instrument-face ${board ? "controller-board" : ""}`}
    >
      <rect
        width={280}
        height={142}
        rx={9}
        style={{ fill: board ? "#17685d" : "#dce1e5", stroke: "#536574" }}
        stroke="#536574"
        strokeWidth={2}
      />
      <text x={12} y={20} fill={board ? "#fff" : "#142e41"} fontSize={11}>
        {title.slice(0, 40)}
      </text>
      {board ? (
        <>
          <rect x={96} y={44} width={75} height={55} rx={4} style={{ fill: "#202831" }} />
          <rect x={0} y={52} width={35} height={34} style={{ fill: "#b7bec3" }} stroke="#51606a" />
          <text x={110} y={76} fill="#ddd" fontSize={10}>
            MCU
          </text>
          {Array.from({ length: 16 }, (_, i) => (
            <g key={i}>
              <rect x={15 + i * 16} y={28} width={9} height={10} style={{ fill: "#192128" }} />
              <rect x={15 + i * 16} y={111} width={9} height={10} style={{ fill: "#192128" }} />
            </g>
          ))}
          <circle cx={236} cy={58} r={4} fill="#b7e151" />
        </>
      ) : (
        <>
          <rect x={12} y={32} width={166} height={72} rx={4} style={{ fill: "#102b33" }} />
          <text x={23} y={54} fill="#8febd0" fontSize={12}>
            {source ? "FONTE / GERADOR" : "DISPOSITIVO"}
          </text>
          <text x={23} y={79} fill="#8febd0" fontSize={10}>
            Configuração no painel
          </text>
          <circle cx={220} cy={66} r={24} fill="#a7b1bb" stroke="#435563" strokeWidth={3} />
          <line x1={220} y1={46} x2={220} y2={59} stroke="#263b4b" strokeWidth={3} />
          <circle cx={251} cy={124} r={5} fill="#c0dca1" />
        </>
      )}
    </g>
  );
}
