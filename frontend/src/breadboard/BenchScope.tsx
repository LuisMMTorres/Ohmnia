import { disconnectScope, removeScope, scopeProbeName } from "./scopeConnections";
import type { Job } from "../api";
import { InstrumentScope } from "../schematic/InstrumentScope";
import type { Schematic } from "../schematic/types";

export function BenchScope({
  schematic,
  onChange,
  job,
  probeNames,
}: {
  schematic: Schematic;
  onChange: (s: Schematic) => void;
  job: Job | null;
  probeNames: string[];
}) {
  const count = schematic.bench_scope_channels ?? 0;
  if (!count) return null;
  const plot =
    job?.state === "done"
      ? (job.plots?.find((p) => p.kind === "tran") ?? job.plots?.find((p) => p.kind === "op"))
      : undefined;
  return (
    <section className="bench-scope" aria-label="Osciloscópio adicionado">
      <div className="row wrap">
        <h3>Osciloscópio · {count} canais</h3>
        <button className="secondary" onClick={() => onChange(removeScope(schematic))}>
          Remover osciloscópio
        </button>
      </div>
      <div className="row wrap scope-connections-summary">
        {Array.from({ length: count }, (_, i) => {
          const ch = i + 1,
            connection = schematic.bench_scope_connections?.[String(ch)];
          return (
            <div key={ch}>
              <strong>CH {ch}</strong>
              <span>
                {" "}
                +: {connection?.positive ?? "desconectado"} · −:{" "}
                {connection?.negative ?? "desconectado"}
              </span>
              {(connection?.positive || connection?.negative) && (
                <button
                  className="secondary small-btn"
                  onClick={() => onChange(disconnectScope(schematic, ch))}
                >
                  Desconectar CH{ch}
                </button>
              )}
            </div>
          );
        })}
      </div>
      <p className="small muted">
        Conecte as ponteiras pelos bornes + e − da miniatura do osciloscópio ao lado das fontes na
        protoboard.
      </p>
      {plot && job ? (
        <InstrumentScope
          key={`${job.id}-${plot.name}`}
          job={job}
          plot={plot}
          signals={probeNames.map((n) => n.toLowerCase())}
          initialChannels={count}
          channelSignals={
            Object.keys(schematic.bench_scope_connections ?? {}).length
              ? Array.from({ length: count }, (_, i) => {
                  const wire = schematic.bench_scope_connections?.[String(i + 1)];
                  return wire?.positive && wire.negative
                    ? scopeProbeName(i + 1).toLowerCase()
                    : null;
                })
              : undefined
          }
          onChannelsChange={(channels) =>
            onChange({ ...schematic, bench_scope_channels: channels })
          }
        />
      ) : (
        <div className="oscilloscope-face">
          <strong>OHMNIA · Osciloscópio digital</strong>
          <svg
            className="instrument-screen"
            viewBox="0 0 800 230"
            role="img"
            aria-label="Osciloscópio aguardando aquisição"
          >
            <rect width={800} height={230} fill="#07171b" />
            {Array.from({ length: 11 }, (_, i) => (
              <line key={i} x1={i * 80} x2={i * 80} y1={0} y2={230} stroke="#244049" />
            ))}
            {Array.from({ length: 7 }, (_, i) => (
              <line key={i} x1={0} x2={800} y1={i * 38} y2={i * 38} stroke="#244049" />
            ))}
            <text x={400} y={120} textAnchor="middle" fill="#b4d6df" fontSize={16}>
              Aguardando aquisição
            </text>
          </svg>
          <p>
            Conecte probes de tensão ou corrente e simule. Ponto de operação mostra o nível CC
            constante; análise transitória mostra a variação no tempo.
          </p>
          <label>
            Canais
            <select
              aria-label="Canais do instrumento"
              value={count}
              onChange={(e) =>
                onChange({ ...schematic, bench_scope_channels: Number(e.target.value) as 2 | 4 })
              }
            >
              <option value={2}>2 canais</option>
              <option value={4}>4 canais</option>
            </select>
          </label>
        </div>
      )}
    </section>
  );
}
