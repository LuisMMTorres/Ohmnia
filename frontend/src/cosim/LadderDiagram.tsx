// Ladder diagram drawn from the rungs JSON (the same format the PLC runtime reads).

interface Element {
  type: string;
  var?: string;
  expr?: string;
  name?: string;
  pt?: string;
  pv?: number;
  reset?: string;
}
interface Coil {
  type: string;
  var?: string;
  dst?: string;
  src?: string;
}
interface Rung {
  comment?: string;
  branches?: Element[][];
  coils?: Coil[];
}

const CELL = 92;
const ROW = 46;
const LEFT = 18;

function contact(el: Element, x: number, y: number, key: string) {
  const t = el.type.toUpperCase();
  if (t === "NO" || t === "NC" || t === "P" || t === "N") {
    return (
      <g key={key}>
        <line x1={x} y1={y} x2={x + 34} y2={y} />
        <line x1={x + 34} y1={y - 10} x2={x + 34} y2={y + 10} />
        <line x1={x + 46} y1={y - 10} x2={x + 46} y2={y + 10} />
        <line x1={x + 46} y1={y} x2={x + CELL} y2={y} />
        {t === "NC" && <line x1={x + 32} y1={y + 9} x2={x + 48} y2={y - 9} />}
        {(t === "P" || t === "N") && (
          <text x={x + 40} y={y + 4} textAnchor="middle" className="ld-small">
            {t}
          </text>
        )}
        <text x={x + 40} y={y - 14} textAnchor="middle" className="ld-var">
          {el.var}
        </text>
      </g>
    );
  }
  const label =
    t === "CMP"
      ? (el.expr ?? "")
      : t.startsWith("CT")
        ? `${el.name} PV=${el.pv}`
        : `${el.name} ${el.pt}`;
  return (
    <g key={key}>
      <line x1={x} y1={y} x2={x + 6} y2={y} />
      <rect x={x + 6} y={y - 13} width={CELL - 12} height={26} rx={3} className="ld-box" />
      <text x={x + CELL / 2} y={y - 2} textAnchor="middle" className="ld-small">
        {t === "CMP" ? "COMPARA" : t}
      </text>
      <text x={x + CELL / 2} y={y + 9} textAnchor="middle" className="ld-small">
        {label.length > 16 ? `${label.slice(0, 15)}…` : label}
      </text>
      <line x1={x + CELL - 6} y1={y} x2={x + CELL} y2={y} />
    </g>
  );
}

function coil(c: Coil, x: number, y: number, key: string) {
  const t = c.type.toLowerCase();
  if (t === "move") {
    return (
      <g key={key}>
        <rect x={x} y={y - 13} width={CELL + 30} height={26} rx={3} className="ld-box" />
        <text x={x + (CELL + 30) / 2} y={y + 4} textAnchor="middle" className="ld-small">
          {`${c.dst} := ${(c.src ?? "").slice(0, 16)}`}
        </text>
      </g>
    );
  }
  const mark = { coil: "", ncoil: "/", set: "S", reset: "R" }[t] ?? "?";
  return (
    <g key={key}>
      <path d={`M ${x + 6} ${y - 11} A 12 12 0 0 0 ${x + 6} ${y + 11}`} className="ld-coil" />
      <path d={`M ${x + 22} ${y - 11} A 12 12 0 0 1 ${x + 22} ${y + 11}`} className="ld-coil" />
      <text x={x + 14} y={y + 4} textAnchor="middle" className="ld-small">
        {mark}
      </text>
      <text x={x + 14} y={y - 15} textAnchor="middle" className="ld-var">
        {c.var}
      </text>
    </g>
  );
}

export function LadderDiagram({ source }: { source: string }) {
  let rungs: Rung[];
  try {
    const data = JSON.parse(source) as { rungs?: Rung[] };
    rungs = data.rungs ?? [];
  } catch (e) {
    return <p className="error small">Ladder inválido (JSON): {(e as Error).message}</p>;
  }
  const cols = Math.max(1, ...rungs.flatMap((r) => (r.branches ?? []).map((b) => b.length)));
  const coilX = LEFT + cols * CELL + 20;
  const width = coilX + CELL + 70;
  let y = 52;
  const parts = rungs.map((r, ri) => {
    const branches = r.branches?.length ? r.branches : [[]];
    const top = y;
    const g = (
      <g key={ri}>
        {r.comment && (
          <text x={LEFT + 4} y={top - 34} className="ld-comment">
            {ri + 1}. {r.comment}
          </text>
        )}
        {branches.map((b, bi) => {
          const by = top + bi * ROW;
          return (
            <g key={bi}>
              {b.map((el, ei) => contact(el, LEFT + ei * CELL, by, `${ri}-${bi}-${ei}`))}
              <line x1={LEFT + b.length * CELL} y1={by} x2={coilX - 10} y2={by} />
            </g>
          );
        })}
        {branches.length > 1 && (
          <>
            <line x1={LEFT} y1={top} x2={LEFT} y2={top + (branches.length - 1) * ROW} />
            <line x1={coilX - 10} y1={top} x2={coilX - 10} y2={top + (branches.length - 1) * ROW} />
          </>
        )}
        <line x1={coilX - 10} y1={top} x2={coilX} y2={top} />
        {(r.coils ?? []).map((c, ci) => coil(c, coilX + ci * 44, top, `${ri}-c${ci}`))}
      </g>
    );
    y += branches.length * ROW + (rungs[ri + 1]?.comment ? 56 : 34);
    return g;
  });
  const height = y;
  return (
    <svg className="ladder" viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
      <line x1={LEFT - 6} y1={8} x2={LEFT - 6} y2={height - 10} className="ld-rail" />
      <line x1={width - 8} y1={8} x2={width - 8} y2={height - 10} className="ld-rail" />
      {parts.map((p, i) => (
        <g key={i}>
          <line x1={LEFT - 6} y1={0} x2={LEFT} y2={0} />
          {p}
        </g>
      ))}
    </svg>
  );
}
