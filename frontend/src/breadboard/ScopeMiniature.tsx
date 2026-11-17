import { holeXY } from "./geometry";
import type { BoardSpec } from "./types";
import type { Schematic } from "../schematic/types";
const COLORS = ["#e8c832", "#29aee0", "#d65a9f", "#55ac65"];
export function ScopeMiniature({
  x,
  y,
  schematic,
  board,
  onConnect,
  readOnly,
}: {
  x: number;
  y: number;
  schematic: Schematic;
  board: BoardSpec;
  onConnect: (ch: number, terminal: "positive" | "negative") => void;
  readOnly?: boolean;
}) {
  const count = schematic.bench_scope_channels ?? 0;
  return (
    <g className="scope-miniature" aria-label="Miniatura do osciloscópio">
      <rect
        x={x}
        y={y}
        width={280}
        height={168}
        rx={9}
        fill="#cbd5dc"
        stroke="#536574"
        strokeWidth={2}
      />
      <text x={x + 12} y={y + 19} fill="#142e41" fontSize={11}>
        OHMNIA · Osciloscópio · {count} canais
      </text>
      <rect x={x + 12} y={y + 29} width={171} height={66} rx={4} fill="#102b33" />
      {Array.from({ length: 5 }, (_, i) => (
        <line
          key={i}
          x1={x + 20 + i * 38}
          x2={x + 20 + i * 38}
          y1={y + 34}
          y2={y + 90}
          stroke="#355660"
        />
      ))}
      <text x={x + 31} y={y + 65} fill="#b4d6df" fontSize={10}>
        Conecte as ponteiras
      </text>
      <circle cx={x + 226} cy={y + 61} r={23} fill="#a7b1bb" stroke="#435563" strokeWidth={3} />
      {Array.from({ length: count }, (_, index) => {
        const ch = index + 1,
          cx = x + 34 + index * 66;
        return (
          <g key={ch}>
            <text x={cx} y={y + 113} textAnchor="middle" fill="#142e41" fontSize={10}>
              CH {ch}
            </text>
            {(["positive", "negative"] as const).map((terminal, n) => {
              const px = cx + (n ? 12 : -12),
                py = y + 135;
              const hole = schematic.bench_scope_connections?.[String(ch)]?.[terminal];
              const point = hole ? holeXY(board, hole) : null;
              const label = `Conectar CH${ch} ${terminal === "positive" ? "+" : "−"}`;
              return (
                <g key={terminal}>
                  {point && (
                    <path
                      d={`M ${px} ${py} C ${px} ${py - 40}, ${point[0]} ${point[1] + 40}, ${point[0]} ${point[1]}`}
                      stroke={COLORS[index]}
                      strokeDasharray={n ? "5 4" : undefined}
                      className="bb-lead-wire"
                    />
                  )}
                  {point && (
                    <circle
                      cx={point[0]}
                      cy={point[1]}
                      r={5}
                      fill={COLORS[index]}
                      pointerEvents="none"
                    />
                  )}
                  <circle
                    cx={px}
                    cy={py}
                    r={8}
                    fill={n ? "#17232f" : COLORS[index]}
                    stroke="#536574"
                    role="button"
                    tabIndex={readOnly ? -1 : 0}
                    aria-label={label}
                    style={{ cursor: readOnly ? "default" : "pointer" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!readOnly) onConnect(ch, terminal);
                    }}
                    onKeyDown={(e) => {
                      if (!readOnly && (e.key === "Enter" || e.key === " ")) {
                        e.preventDefault();
                        e.stopPropagation();
                        onConnect(ch, terminal);
                      }
                    }}
                  >
                    <title>{label}: clique e depois escolha o furo</title>
                  </circle>
                  <text x={px} y={y + 157} fill="#142e41" fontSize={9} textAnchor="middle">
                    {n ? "−" : "+"}
                  </text>
                </g>
              );
            })}
          </g>
        );
      })}
    </g>
  );
}
