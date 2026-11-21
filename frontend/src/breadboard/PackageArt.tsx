// Real-looking packages drawn on the breadboard (top view), from the leg positions.
import type { ReactNode } from "react";
import { BAND_COLORS, P } from "./geometry";
import type { PackageSpec, PartView } from "./types";

type Pt = [number, number];

interface Props {
  pkg: PackageSpec;
  legs: Record<string, Pt>; // package pin -> pixel position
  view?: PartView;
  refName: string;
  selected?: boolean;
  bad?: boolean;
  showLabels?: boolean;
  /** Body colour of a LED (its emitted colour). */
  color?: string;
}

const deg = (a: Pt, b: Pt) => (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;
const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);
const mid = (a: Pt, b: Pt): Pt => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

function Leg({ at }: { at: Pt }) {
  return <circle cx={at[0]} cy={at[1]} r={2.6} className="bb-leg" />;
}

/** Text label of a leg ("1 C"), placed away from the body along `dir` (unit vector). */
function LegLabel({ at, text, dir }: { at: Pt; text: string; dir: Pt }) {
  return (
    <text
      x={at[0] + dir[0] * 9}
      y={at[1] + dir[1] * 9 + 3}
      textAnchor="middle"
      className="bb-leg-label"
    >
      {text}
    </text>
  );
}

function labelOf(view: PartView | undefined, pin: string): string {
  const l = view?.labels[pin];
  if (!l || l === pin) return pin;
  return /^\d+$/.test(pin) ? `${pin} ${l}` : l;
}

export function PackageArt({ pkg, legs, view, refName, selected, bad, showLabels, color }: Props) {
  const pins = pkg.pins.filter((p) => legs[p]);
  const pts = pins.map((p) => legs[p]!);
  if (!pts.length) return null;
  const first = pts[0]!;
  const last = pts[pts.length - 1]!;
  const angle = pts.length > 1 ? deg(first, last) : 0;
  const center = pts.length > 1 ? mid(first, last) : first;
  const len = pts.length > 1 ? dist(first, last) : 0;
  const cls = `bb-part${selected ? " selected" : ""}${bad ? " bad" : ""}`;
  const title = `${refName}${view?.title ? ` · ${view.title}` : ""}`;
  // "front" of the part on screen: perpendicular to the leg axis, pointing down/right
  const rad = (angle * Math.PI) / 180;
  const front: Pt = [-Math.sin(rad), Math.cos(rad)];
  let body: ReactNode = null;

  if (pkg.style === "axial") {
    const bodyLen = Math.min(Math.max(len - 10, 12), pkg.body === "glass" ? 26 : 36);
    const th = pkg.body === "glass" ? 7 : 9;
    let inner: ReactNode;
    if (pkg.body === "resistor") {
      const bands = view?.bands ?? [];
      const xs = [-bodyLen / 2 + 6, -bodyLen / 2 + 11, -bodyLen / 2 + 16, -bodyLen / 2 + 21];
      inner = (
        <>
          <rect
            x={-bodyLen / 2}
            y={-th / 2}
            width={bodyLen}
            height={th}
            rx={4}
            className="bb-res"
          />
          {bands.map((b, i) => (
            <rect
              key={i}
              x={i === bands.length - 1 && bands.length > 3 ? bodyLen / 2 - 7 : xs[i]!}
              y={-th / 2}
              width={3}
              height={th}
              fill={BAND_COLORS[b] ?? "#999"}
            />
          ))}
        </>
      );
    } else if (pkg.body === "inductor") {
      inner = (
        <rect x={-bodyLen / 2} y={-th / 2} width={bodyLen} height={th} rx={5} className="bb-ind" />
      );
    } else {
      // diodes: the band marks pin 1 (cathode) end
      inner = (
        <>
          <rect
            x={-bodyLen / 2}
            y={-th / 2}
            width={bodyLen}
            height={th}
            rx={2}
            className={pkg.body === "glass" ? "bb-glass" : "bb-diode"}
          />
          <rect
            x={-bodyLen / 2 + 3}
            y={-th / 2}
            width={4}
            height={th}
            className={pkg.body === "glass" ? "bb-glass-band" : "bb-diode-band"}
          />
        </>
      );
    }
    // pin 1 is `first`: the local x axis runs from pin 1 to pin 2
    body = (
      <>
        <line x1={first[0]} y1={first[1]} x2={last[0]} y2={last[1]} className="bb-lead" />
        <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>{inner}</g>
      </>
    );
  } else if (pkg.style === "radial") {
    if (pkg.body === "electrolytic") {
      const r = Math.max(len / 2 + 3, P * 0.7);
      const minus = legs["-"];
      body = (
        <>
          <circle cx={center[0]} cy={center[1]} r={r} className="bb-elco" />
          {minus && (
            <path
              d={`M ${center[0]} ${center[1]} L ${minus[0] + (minus[0] - center[0]) * 0.9} ${
                minus[1] + (minus[1] - center[1]) * 0.9
              }`}
              className="bb-elco-stripe"
            />
          )}
          {minus && (
            <text x={minus[0]} y={minus[1] - 5} textAnchor="middle" className="bb-elco-sign">
              −
            </text>
          )}
        </>
      );
    } else if (pkg.body === "tact") {
      const w = len + P * 0.9;
      body = (
        <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>
          <rect x={-w / 2} y={-w / 2 - 2} width={w} height={w * 0.8} rx={2} className="bb-tact" />
          <circle cx={0} cy={-w * 0.1 - 2} r={w * 0.22} className="bb-tact-cap" />
        </g>
      );
    } else if (pkg.body === "led") {
      // 5 mm LED seen from the side: coloured epoxy dome on a rim, the rim cut flat on the
      // cathode side (second leg)
      const w = len + P * 0.9;
      const fill = color ?? "#ff2a1a";
      body = (
        <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>
          <path
            d={`M ${-w / 2 - 2} -2 H ${w / 2 - 1} V -5 H ${-w / 2 - 2} Z`}
            style={{ fill, stroke: "#00000055", strokeWidth: 0.8 }}
          />
          <path
            d={`M ${-w / 2 + 1} -5 V -10 A ${w / 2 - 1} ${w / 2 - 1} 0 0 1 ${w / 2 - 1} -10 V -5 Z`}
            style={{ fill, fillOpacity: 0.75, stroke: "#00000066", strokeWidth: 0.8 }}
          />
          <path
            d={`M ${-w / 4} -9 A ${w / 4} ${w / 4} 0 0 1 0 ${-9 - w / 4}`}
            style={{ fill: "none", stroke: "#ffffffaa", strokeWidth: 1.4 }}
          />
        </g>
      );
    } else {
      const w = len + P * 0.9;
      body = (
        <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>
          <ellipse
            cx={0}
            cy={-4}
            rx={w / 2}
            ry={6}
            className={pkg.body === "ceramic" ? "bb-ceramic" : "bb-film"}
          />
        </g>
      );
    }
  } else if (pkg.style === "inline") {
    const w = len + P * 0.9;
    let inner: ReactNode;
    if (pkg.body === "to92") {
      inner = (
        <path
          d={`M ${-w / 2} 3 L ${w / 2} 3 A ${w / 2} ${w / 2.2} 0 0 0 ${-w / 2} 3 Z`}
          className="bb-to92"
        />
      );
    } else {
      const tab = pkg.body === "to220" || pkg.body === "to247";
      inner = (
        <>
          {tab && <rect x={-w / 2} y={-17} width={w} height={8} rx={1} className="bb-tab" />}
          <rect x={-w / 2} y={-10} width={w} height={13} rx={1.5} className="bb-epoxy" />
        </>
      );
    }
    body = (
      <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>
        {inner}
        <text x={0} y={-2} textAnchor="middle" className="bb-part-text">
          {(view?.part_number ?? refName).slice(0, 10)}
        </text>
      </g>
    );
  } else if (pkg.style === "dip") {
    const half = pkg.pins.length / 2;
    const p1 = legs[pkg.pins[0]!];
    const pn = legs[pkg.pins[half - 1]!];
    const top = legs[pkg.pins[pkg.pins.length - 1]!];
    if (p1 && pn && top) {
      const x0 = Math.min(p1[0], pn[0]) - P * 0.45;
      const x1 = Math.max(p1[0], pn[0]) + P * 0.45;
      const y0 = top[1] + 5;
      const y1 = p1[1] - 5;
      body =
        pkg.body === "tact" ? (
          <>
            <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx={2} className="bb-tact" />
            <circle
              cx={(x0 + x1) / 2}
              cy={(y0 + y1) / 2}
              r={Math.min(x1 - x0, y1 - y0) * 0.3}
              className="bb-tact-cap"
            />
          </>
        ) : (
          <>
            <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx={2} className="bb-epoxy" />
            <path
              d={`M ${x0} ${(y0 + y1) / 2 - 5} A 5 5 0 0 1 ${x0} ${(y0 + y1) / 2 + 5}`}
              className="bb-notch"
            />
            <circle cx={x0 + 6} cy={y1 - 6} r={2} className="bb-dot" />
            <text
              x={(x0 + x1) / 2}
              y={(y0 + y1) / 2 + 3}
              textAnchor="middle"
              className="bb-part-text light"
            >
              {(view?.part_number ?? view?.title ?? refName).slice(0, 12)}
            </text>
          </>
        );
    }
  }

  if (pkg.style === "board") body = <BoardBody pkg={pkg} legs={legs} />;

  return (
    <g className={cls} data-ref={refName}>
      <title>{title}</title>
      {body}
      {pts.map((p, i) => (
        <Leg key={i} at={p} />
      ))}
      {showLabels &&
        pkg.style !== "board" &&
        pins.map((pin) => {
          const at = legs[pin]!;
          let dir: Pt = front;
          if (pkg.style === "dip") {
            const inLower = pkg.pins.indexOf(pin) < pkg.pins.length / 2;
            dir = [0, inLower ? 1 : -1];
          }
          return <LegLabel key={pin} at={at} text={labelOf(view, pin)} dir={dir} />;
        })}
    </g>
  );
}

/** The package alone, legs labelled: shown next to the schematic symbol. */
export function PackagePreview({ pkg, view }: { pkg: PackageSpec; view?: PartView }) {
  const legs: Record<string, Pt> = {};
  const ox = 30;
  const twoRows = pkg.style === "dip" || pkg.style === "board";
  const oy = pkg.style === "board" ? 150 : twoRows ? 70 : 40;
  const minDr = Math.min(0, ...pkg.offsets.map(([dr]) => dr));
  const step = pkg.style === "board" ? P : P * 1.6;
  const gap = pkg.style === "board" ? 7 * P : 3 * P;
  pkg.pins.forEach((pin, i) => {
    const [dr, dc] = pkg.offsets[i] ?? [i, 0];
    legs[pin] = [ox + (dr - minDr) * step, oy + (twoRows && dc < 0 ? -gap : 0)];
  });
  const w = Math.max(...Object.values(legs).map((p) => p[0])) + 30;
  const h = pkg.style === "board" ? 200 : twoRows ? 100 : 66;
  if (pkg.style === "offboard") return null;
  return (
    <svg
      className="bb-preview"
      viewBox={`0 0 ${w} ${h}`}
      width={pkg.style === "board" ? w : w * 1.7}
      height={pkg.style === "board" ? h : h * 1.7}
      role="img"
    >
      <PackageArt pkg={pkg} legs={legs} view={view} refName={view?.ref ?? ""} showLabels />
    </svg>
  );
}

/** Groups of consecutive legs along one header (a gap of one hole splits them). */
function headerGroups(xs: number[]): [number, number][] {
  const sorted = [...xs].sort((a, b) => a - b);
  const out: [number, number][] = [];
  for (const x of sorted) {
    const last = out[out.length - 1];
    if (last && x - last[1] <= P * 1.2) last[1] = x;
    else out.push([x, x]);
  }
  return out;
}

/** Development board seen from above, its two headers over the legs (Arduino Uno, ESP32). */
function BoardBody({ pkg, legs }: { pkg: PackageSpec; legs: Record<string, Pt> }) {
  const lower: { pin: string; at: Pt; silk: string }[] = [];
  const upper: typeof lower = [];
  pkg.pins.forEach((pin, i) => {
    const at = legs[pin];
    if (!at) return;
    const row = (pkg.offsets[i]?.[1] ?? 0) < 0 ? upper : lower;
    row.push({ pin, at, silk: pkg.silk?.[i] ?? pin });
  });
  if (!lower.length || !upper.length) return null;
  const xs = [...lower, ...upper].map((l) => l.at[0]);
  const yl = lower[0]!.at[1];
  const yu = upper[0]!.at[1];
  const uno = pkg.body === "board-uno";
  const x0 = Math.min(...xs) - P * (uno ? 1.6 : 1.2);
  const x1 = Math.max(...xs) + P * (uno ? 1.2 : 1.4);
  const y0 = yu - P * (uno ? 2.6 : 1.4);
  const y1 = yl + P * (uno ? 2.6 : 1.4);
  const pcb = uno ? "#0f7d8c" : "#202326";
  const midY = (y0 + y1) / 2;
  const first = lower[0]!;
  return (
    <g className="bb-board-part">
      <rect
        x={x0}
        y={y0}
        width={x1 - x0}
        height={y1 - y0}
        rx={uno ? 6 : 3}
        style={{ fill: pcb, stroke: "#0b3a40", strokeWidth: 1.2, opacity: 0.96 }}
      />
      {uno ? (
        <>
          {/* USB-B and power jack on the left edge, ATmega328P in DIP-28, reset button */}
          <rect
            x={x0 - 12}
            y={y0 + 8}
            width={40}
            height={30}
            rx={2}
            style={{ fill: "#b9c0c6", stroke: "#59636c" }}
          />
          <rect x={x0 - 8} y={y1 - 34} width={34} height={24} rx={3} style={{ fill: "#1d1f22" }} />
          <rect
            x={(x0 + x1) / 2 - 10}
            y={midY - 10}
            width={(x1 - x0) * 0.42}
            height={22}
            rx={2}
            style={{ fill: "#1b1b1b" }}
          />
          <text
            x={(x0 + x1) / 2 + 26}
            y={midY + 4}
            fontSize={7}
            textAnchor="middle"
            style={{ fill: "#ddd" }}
          >
            ATmega328P
          </text>
          <rect
            x={x0 + 46}
            y={y0 + 10}
            width={10}
            height={10}
            rx={2}
            style={{ fill: "#d9d9d9", stroke: "#666" }}
          />
          <text
            x={x0 + 50}
            y={midY + 4}
            fontSize={11}
            fontWeight={700}
            textAnchor="middle"
            style={{ fill: "#f4f4f4" }}
          >
            UNO
          </text>
        </>
      ) : (
        <>
          {/* ESP32-WROOM module (metal can and PCB antenna), micro-USB, EN and BOOT */}
          <rect
            x={x0 + 4}
            y={midY - 22}
            width={30}
            height={44}
            rx={1}
            style={{ fill: "#1b3d6b" }}
          />
          <path
            d={`M ${x0 + 8} ${midY - 16} h 22 v 6 h -22 v 6 h 22 v 6 h -22 v 6 h 22`}
            style={{ fill: "none", stroke: "#d4b44a", strokeWidth: 1 }}
          />
          <rect
            x={x0 + 34}
            y={midY - 22}
            width={60}
            height={44}
            rx={2}
            style={{ fill: "#c3c9cf", stroke: "#7b858e" }}
          />
          <text
            x={x0 + 64}
            y={midY + 3}
            fontSize={7}
            textAnchor="middle"
            style={{ fill: "#2b3640" }}
          >
            ESP32-WROOM
          </text>
          <rect
            x={x1 - 10}
            y={midY - 9}
            width={16}
            height={18}
            rx={2}
            style={{ fill: "#b9c0c6", stroke: "#59636c" }}
          />
          <rect x={x1 - 34} y={midY - 22} width={9} height={9} rx={2} style={{ fill: "#d9d9d9" }} />
          <rect x={x1 - 34} y={midY + 13} width={9} height={9} rx={2} style={{ fill: "#d9d9d9" }} />
          <text x={x1 - 40} y={midY - 14} fontSize={5.5} textAnchor="end" style={{ fill: "#ddd" }}>
            EN
          </text>
          <text x={x1 - 40} y={midY + 20} fontSize={5.5} textAnchor="end" style={{ fill: "#ddd" }}>
            BOOT
          </text>
        </>
      )}
      {[
        { row: lower, y: yl },
        { row: upper, y: yu },
      ].map(({ row, y }) =>
        headerGroups(row.map((l) => l.at[0])).map(([a, b]) => (
          <rect
            key={`${y}-${a}`}
            x={a - P * 0.5}
            y={y - P * 0.5}
            width={b - a + P}
            height={P}
            style={{ fill: "#151515" }}
          />
        )),
      )}
      {[...lower.map((l) => ({ ...l, dy: -12 })), ...upper.map((l) => ({ ...l, dy: 12 }))].map(
        (l) => (
          <text
            key={l.pin}
            x={l.at[0]}
            y={l.at[1] + l.dy}
            fontSize={5}
            textAnchor={l.dy < 0 ? "start" : "end"}
            transform={`rotate(-90 ${l.at[0]} ${l.at[1] + l.dy})`}
            dominantBaseline="central"
            style={{ fill: "#f2f2f2" }}
          >
            {l.silk}
          </text>
        ),
      )}
      {/* pin 1 mark */}
      <path d={`M ${first.at[0] - 4} ${yl + 11} l 4 -5 l 4 5 z`} style={{ fill: "#ffd54a" }} />
      <text
        x={first.at[0] - 7}
        y={yl + 4}
        fontSize={6}
        textAnchor="end"
        style={{ fill: "#ffd54a" }}
      >
        1
      </text>
    </g>
  );
}
