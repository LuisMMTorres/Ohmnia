// Bench instruments drawn after the usual look of a regulated DC bench supply and of a
// function generator: front panel with displays, knobs and binding posts. Own drawings; no
// manufacturer is implied. The binding posts sit where the leads of the breadboard view start
// (top edge, spread over 18…262 px), so the wires never cross the panel.

const W = 280;
const H = 142;

/** x of terminal i of n along the top edge (same rule as the breadboard view). */
export function postX(i: number, n: number): number {
  return 18 + (i * 244) / Math.max(1, n - 1 || 1);
}

function post(x: number, color: string, key: string) {
  return (
    <g key={key}>
      <circle cx={x} cy={0} r={9} style={{ fill: "#3d4248", stroke: "#22262a" }} />
      <circle cx={x} cy={0} r={6.5} style={{ fill: color, stroke: "#00000055" }} />
      <circle cx={x} cy={0} r={2} style={{ fill: "#d9d9d9" }} />
    </g>
  );
}

function seg(x: number, y: number, w: number, text: string, color: string, key: string) {
  return (
    <g key={key}>
      <rect x={x} y={y} width={w} height={22} rx={2} style={{ fill: "#140d0d" }} />
      <text
        x={x + w - 5}
        y={y + 17}
        textAnchor="end"
        fontSize={15}
        fontFamily="'DSEG7 Classic', 'Courier New', monospace"
        style={{ fill: color, letterSpacing: "1px" }}
      >
        {text}
      </text>
    </g>
  );
}

function knob(cx: number, cy: number, r: number, label: string, key: string) {
  return (
    <g key={key}>
      <circle cx={cx} cy={cy} r={r + 2} style={{ fill: "#2b2f33" }} />
      <circle cx={cx} cy={cy} r={r} style={{ fill: "#4a5056", stroke: "#1d2023" }} />
      <line x1={cx} y1={cy} x2={cx} y2={cy - r + 2} style={{ stroke: "#e8e8e8", strokeWidth: 2 }} />
      <text x={cx} y={cy + r + 10} textAnchor="middle" fontSize={6.5} style={{ fill: "#d6dade" }}>
        {label}
      </text>
    </g>
  );
}

/** Regulated DC bench supply with one section (V and A displays, two knobs) per channel. */
export function BenchSupplyArt({
  title,
  channels,
  readings,
  amps = [],
}: {
  title: string;
  channels: number;
  readings: string[];
  /** Current delivered by each channel in the last simulation (text for the display). */
  amps?: string[];
}) {
  const n = channels * 2;
  const secW = (W - 16) / channels;
  return (
    <>
      <rect
        x={0}
        y={-4}
        width={W}
        height={H + 4}
        rx={7}
        style={{ fill: "#e4e7ea", stroke: "#6b737a", strokeWidth: 2 }}
      />
      <rect x={6} y={12} width={W - 12} height={H - 18} rx={4} style={{ fill: "#30353a" }} />
      {Array.from({ length: channels }, (_, c) => {
        const x0 = 8 + c * secW;
        const dw = Math.min(secW - 18, 86);
        const cx = x0 + secW / 2;
        return (
          <g key={c}>
            {channels > 1 && (
              <text x={cx} y={26} textAnchor="middle" fontSize={7.5} style={{ fill: "#9fd2ff" }}>
                CH{c + 1}
              </text>
            )}
            {seg(cx - dw / 2, 30, dw, readings[c] ?? "--.--", "#ff3b30", `v${c}`)}
            {seg(cx - dw / 2, 56, dw, amps[c] ?? "-.---", "#3ddc5c", `a${c}`)}
            <text x={cx + dw / 2 + 2} y={45} fontSize={7} style={{ fill: "#d6dade" }}>
              V
            </text>
            <text x={cx + dw / 2 + 2} y={71} fontSize={7} style={{ fill: "#d6dade" }}>
              A
            </text>
            {knob(cx - secW / 5, 98, Math.min(11, secW / 8), "TENSÃO", `kv${c}`)}
            {knob(cx + secW / 5, 98, Math.min(11, secW / 8), "CORRENTE", `ki${c}`)}
          </g>
        );
      })}
      {Array.from({ length: n }, (_, i) =>
        post(postX(i, n), i % 2 ? "#1b1b1b" : "#d32f2f", `p${i}`),
      )}
      <rect x={W - 34} y={H - 18} width={22} height={10} rx={2} style={{ fill: "#c62828" }} />
      <text x={12} y={H - 9} fontSize={8} style={{ fill: "#d6dade" }}>
        {title.slice(0, 52)}
      </text>
    </>
  );
}

/** Function generator: LCD with the waveform, keypad, main knob and the output posts. */
export function GeneratorArt({ title, terminals }: { title: string; terminals: number }) {
  return (
    <>
      <rect
        x={0}
        y={-4}
        width={W}
        height={H + 4}
        rx={7}
        style={{ fill: "#e4e7ea", stroke: "#6b737a", strokeWidth: 2 }}
      />
      <rect x={6} y={12} width={W - 12} height={H - 18} rx={4} style={{ fill: "#3a4148" }} />
      <rect
        x={16}
        y={24}
        width={130}
        height={62}
        rx={3}
        style={{ fill: "#9fc7a4", stroke: "#1f2a22" }}
      />
      <path
        d="M 24 58 C 34 32, 44 32, 54 58 S 74 84, 84 58 S 104 32, 114 58 S 134 84, 140 66"
        style={{ fill: "none", stroke: "#1d3b22", strokeWidth: 2 }}
      />
      <text x={22} y={80} fontSize={8} style={{ fill: "#1d3b22" }}>
        GERADOR DE FUNÇÕES
      </text>
      {Array.from({ length: 12 }, (_, i) => (
        <rect
          key={i}
          x={160 + (i % 4) * 19}
          y={26 + Math.floor(i / 4) * 17}
          width={14}
          height={11}
          rx={2}
          style={{ fill: i < 4 ? "#f2a33a" : "#cfd3d6" }}
        />
      ))}
      {knob(250, 108, 13, "AJUSTE", "k")}
      <text x={16} y={106} fontSize={7} style={{ fill: "#d6dade" }}>
        SAÍDA: sinal (vermelho) · terra (preto)
      </text>
      <text x={16} y={H - 9} fontSize={8} style={{ fill: "#d6dade" }}>
        {title.slice(0, 40)}
      </text>
      {Array.from({ length: terminals }, (_, i) =>
        post(postX(i, terminals), i % 2 ? "#1b1b1b" : "#d32f2f", `p${i}`),
      )}
    </>
  );
}
