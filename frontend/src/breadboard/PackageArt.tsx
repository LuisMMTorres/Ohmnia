// Real-looking packages drawn on the breadboard (top view), from the leg positions.
import { useId, type ReactNode } from "react";
import { BAND_COLORS, P } from "./geometry";
import type { PackageSpec, PartView } from "./types";
import type { Glow } from "../schematic/symbols";

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
  /** Simulated brightness of a LED (halo around the dome). */
  glow?: Glow;
  /** Push-button held pressed (true), released (false); undefined for other parts. */
  pressed?: boolean;
}

const deg = (a: Pt, b: Pt) => (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;
const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);
const mid = (a: Pt, b: Pt): Pt => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

function Leg({ at }: { at: Pt }) {
  return <circle cx={at[0]} cy={at[1]} r={2.6} className="bb-leg" />;
}

/** Short labels ("1 C", "K", "+") sit in one line next to the leg. */
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

/**
 * Pin number next to the leg and the pin name written outwards, perpendicular to the row of
 * legs (as on a datasheet pinout): long names ("2IN−", "THRES") of legs 0.1" apart no longer
 * run into each other.
 */
function PinNameLabel({ at, pin, name, dir }: { at: Pt; pin: string; name: string; dir: Pt }) {
  let a = (Math.atan2(dir[1], dir[0]) * 180) / Math.PI;
  // keep the text upright: names pointing left or up are turned half a turn, anchored at the end
  const flip = a > 90 || a <= -90;
  if (flip) a += 180;
  const x = at[0] + dir[0] * 15;
  const y = at[1] + dir[1] * 15;
  return (
    <g className="bb-pin-label">
      <text
        x={at[0] + dir[0] * 8.5}
        y={at[1] + dir[1] * 8.5}
        textAnchor="middle"
        dominantBaseline="central"
        className="bb-leg-label bb-pin-number"
      >
        {pin}
      </text>
      <text
        transform={`translate(${x} ${y}) rotate(${a})`}
        textAnchor={flip ? "end" : "start"}
        dominantBaseline="central"
        className="bb-leg-label"
      >
        {name}
      </text>
    </g>
  );
}

function labelOf(view: PartView | undefined, pin: string): string {
  const l = view?.labels[pin];
  if (!l || l === pin) return pin;
  return /^\d+$/.test(pin) ? `${pin} ${l}` : l;
}

/** Name of a numbered leg written perpendicular to the row of legs (two characters or more). */
export function longPinName(view: PartView | undefined, pin: string): string | null {
  const l = view?.labels[pin];
  return l && l !== pin && /^\d+$/.test(pin) && l.length >= 2 ? l : null;
}

export function PackageArt({
  pkg,
  legs,
  view,
  refName,
  selected,
  bad,
  showLabels,
  color,
  glow,
  pressed,
}: Props) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
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
      body = (
        <ElectrolyticCan
          plus={legs["+"] ?? first}
          minus={legs["-"] ?? last}
          marking={view?.title ?? ""}
          uid={uid}
        />
      );
    } else if (pkg.body === "tact") {
      const w = len + P * 0.9;
      body = (
        <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>
          <rect x={-w / 2} y={-w / 2 - 2} width={w} height={w * 0.8} rx={2} className="bb-tact" />
          <circle
            cx={0}
            cy={-w * 0.1 - 2}
            r={w * (pressed ? 0.18 : 0.22)}
            className={`bb-tact-cap${pressed ? " pressed" : ""}`}
          />
          {pressed !== undefined && (
            // the whole button top is clickable: press / release it
            <rect
              data-actuator={refName}
              x={-w / 2}
              y={-w / 2 - 2}
              width={w}
              height={w * 0.8}
              className="bb-actuator"
            >
              <title>{`${refName}: ${pressed ? "apertado — clique para soltar" : "solto — clique para apertar"}`}</title>
            </rect>
          )}
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
          {glow && glow.level > 0.02 && !glow.burnt && (
            <circle
              cx={0}
              cy={-10}
              r={w * (0.7 + 0.5 * Math.min(glow.level, 1))}
              fill={glow.color}
              fillOpacity={0.15 + 0.6 * Math.min(glow.level, 1)}
              className="bb-glow"
            />
          )}
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
  } else if (
    pkg.style === "inline" &&
    (pkg.body.startsWith("pot") || pkg.body.startsWith("trimpot"))
  ) {
    // millimetres to pixels at this drawing's scale (the preview spreads the legs further)
    const span = (pkg.pins.length - 1) * pkg.pitch * P;
    const mm = ((span > 0 ? len / span : 1) * P) / 2.54;
    body = (
      <g transform={`translate(${center[0]} ${center[1]}) rotate(${angle})`}>
        <PotBody kind={pkg.body} mm={mm} marking={view?.title ?? ""} uid={uid} />
      </g>
    );
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
          const name = longPinName(view, pin);
          return name ? (
            <PinNameLabel key={pin} at={at} pin={pin} name={name} dir={dir} />
          ) : (
            <LegLabel key={pin} at={at} text={labelOf(view, pin)} dir={dir} />
          );
        })}
    </g>
  );
}

/**
 * Aluminium electrolytic capacitor standing on its two legs, seen from the front as it sits on
 * a breadboard: cylindrical sleeve with the negative stripe ("−" signs) on the side of the −
 * leg, capacitance and rated voltage printed on the sleeve, aluminium top with the K-shaped
 * vent, rubber seal at the base and the + leg longer (bent) than the − leg. The can is always
 * drawn upright (or leaning left when the legs run down a column) and mirrored so the stripe
 * stays over the − leg.
 */
function ElectrolyticCan({
  plus,
  minus,
  marking,
  uid,
}: {
  plus: Pt;
  minus: Pt;
  marking: string;
  uid: string;
}) {
  let angle = deg(plus, minus);
  const c = mid(plus, minus);
  const len = Math.max(dist(plus, minus), 1);
  // keep the can upright: if + is to the right of − (or below it), turn the frame half a turn
  // and put the stripe on the left
  const cos = Math.cos((angle * Math.PI) / 180);
  const sin = Math.sin((angle * Math.PI) / 180);
  const flip = cos < -1e-6 || (Math.abs(cos) <= 1e-6 && sin > 0);
  if (flip) angle += 180;
  const m = flip ? -1 : 1; // local x of the − leg is m * len / 2
  const w = len + P * 0.75; // can diameter
  const yb = -9; // bottom of the sleeve (rubber seal just under it); the legs show below
  const h = 2 * P - 6; // sleeve height
  const yt = yb - h; // top of the sleeve
  const ry = w * 0.16; // half-height of the top ellipse (slight top-down view)
  const xm = (m * len) / 2;
  const xp = -xm;
  const stripeW = w * 0.32;
  const sx0 = m > 0 ? w / 2 - stripeW : -w / 2;
  // depth of the sleeve's lower edge where the stripe meets the blue
  const edge = ry * Math.sqrt(1 - ((w / 2 - stripeW) / (w / 2)) ** 2);
  const [cap, volt] = marking.replace(/u/g, "µ").split(" ");
  const g = `elco-${uid}`;
  const valueX = m > 0 ? -stripeW / 2 - 3.5 : stripeW / 2 - 3.5;
  return (
    <g transform={`translate(${c[0]} ${c[1]}) rotate(${angle})`}>
      <defs>
        <linearGradient id={`${g}-body`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#0f2350" />
          <stop offset="0.3" stopColor="#3a63b8" />
          <stop offset="0.55" stopColor="#24478f" />
          <stop offset="1" stopColor="#0c1c42" />
        </linearGradient>
        <linearGradient id={`${g}-stripe`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor={m > 0 ? "#b8c4dc" : "#8e9ab3"} />
          <stop offset="1" stopColor={m > 0 ? "#8e9ab3" : "#c9d3e6"} />
        </linearGradient>
        <linearGradient id={`${g}-top`} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#f4f6f8" />
          <stop offset="1" stopColor="#9da3aa" />
        </linearGradient>
      </defs>
      {/* legs: − straight, + longer, with the slack bent */}
      <path d={`M ${xm} 0 V ${yb}`} className="bb-elco-leg" />
      <path
        d={`M ${xp} 0 V -1.5 L ${xp - m * 3} -3.5 L ${xp} -5.5 L ${xp - m * 3} -7.5 V ${yb}`}
        className="bb-elco-leg"
      />
      {/* rubber seal */}
      <ellipse cx={0} cy={yb} rx={w / 2 - 0.8} ry={ry * 0.8} className="bb-elco-seal" />
      {/* sleeve, rounded bottom edge, and the negative stripe */}
      <path
        d={`M ${-w / 2} ${yt} V ${yb} A ${w / 2} ${ry} 0 0 0 ${w / 2} ${yb} V ${yt} Z`}
        fill={`url(#${g}-body)`}
        className="bb-elco"
      />
      <path
        d={
          m > 0
            ? `M ${sx0} ${yt} V ${yb + edge} A ${w / 2} ${ry} 0 0 0 ${w / 2} ${yb} V ${yt} Z`
            : `M ${-w / 2} ${yt} V ${yb} A ${w / 2} ${ry} 0 0 0 ${sx0 + stripeW} ${yb + edge} V ${yt} Z`
        }
        fill={`url(#${g}-stripe)`}
        className="bb-elco-stripe"
      />
      {[0.25, 0.5, 0.75].map((f) => (
        <text
          key={f}
          x={sx0 + stripeW / 2}
          y={yt + h * f + 2.6}
          textAnchor="middle"
          className="bb-elco-sign"
        >
          −
        </text>
      ))}
      {/* capacitance and rated voltage, printed along the sleeve */}
      {cap && (
        <text
          transform={`translate(${valueX} ${(yt + yb) / 2}) rotate(-90)`}
          textAnchor="middle"
          className="bb-elco-text"
        >
          {cap}
        </text>
      )}
      {volt && (
        <text
          transform={`translate(${valueX + 5.5} ${(yt + yb) / 2}) rotate(-90)`}
          textAnchor="middle"
          className="bb-elco-text"
        >
          {volt}
        </text>
      )}
      {/* aluminium top with the K-shaped safety vent */}
      <ellipse cx={0} cy={yt} rx={w / 2} ry={ry} fill={`url(#${g}-top)`} className="bb-elco-top" />
      <path
        d={`M ${-w * 0.12} ${yt - ry * 0.55} V ${yt + ry * 0.55} M ${-w * 0.12} ${yt} L ${
          w * 0.14
        } ${yt - ry * 0.6} M ${-w * 0.12} ${yt} L ${w * 0.14} ${yt + ry * 0.6}`}
        className="bb-elco-vent"
      />
    </g>
  );
}

/** The package alone, legs labelled: shown next to the schematic symbol. */
export function PackagePreview({ pkg, view }: { pkg: PackageSpec; view?: PartView }) {
  const legs: Record<string, Pt> = {};
  const ox = 30;
  const twoRows = pkg.style === "dip" || pkg.style === "board";
  const pot = pkg.body.startsWith("pot") || pkg.body.startsWith("trimpot");
  const oy = pkg.style === "board" ? 150 : twoRows ? 92 : pot ? 104 : 40;
  const minDr = Math.min(0, ...pkg.offsets.map(([dr]) => dr));
  const step = pkg.style === "board" ? P : P * 1.6;
  const gap = pkg.style === "board" ? 7 * P : 3 * P;
  pkg.pins.forEach((pin, i) => {
    const [dr, dc] = pkg.offsets[i] ?? [i, 0];
    legs[pin] = [ox + (dr - minDr) * step, oy + (twoRows && dc < 0 ? -gap : 0)];
  });
  const w = Math.max(...Object.values(legs).map((p) => p[0])) + 30;
  // names written outwards from the legs need about 45 px beyond each row
  const h = pkg.style === "board" ? 200 : twoRows ? 140 : pot ? 160 : 66;
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

/**
 * Potentiometers and trimpots seen from above as they stand on the breadboard, sized from the
 * Bourns drawings (legs at y = 0, the body behind them):
 *
 * * ``trimpot-3386``: blue 9.53 mm square body, white rotor with the screwdriver slot;
 * * ``trimpot-3362``: blue 6.6 mm square body, rotor with a cross slot;
 * * ``trimpot-3296``: blue 9.53 × 4.83 mm multiturn body with the brass adjusting screw;
 * * ``pot-9mm``: PTV09A, 10 mm metal frame with the 6 mm insulated shaft (flat side);
 * * ``pot-17mm``: PDB181, 17 mm round metal case with the knurled 6 mm shaft;
 * * ``pot``: older generic drawing, as the 9 mm one.
 */
function PotBody({
  kind,
  mm,
  marking,
  uid,
}: {
  kind: string;
  mm: number;
  marking: string;
  uid: string;
}) {
  const g = `pot-${uid}`;
  const print = marking.replace(/\s/g, "").slice(0, 8);
  if (kind.startsWith("trimpot")) {
    const multi = kind === "trimpot-3296";
    const small = kind === "trimpot-3362";
    const w = (small ? 6.6 : 9.53) * mm;
    const h = (multi ? 4.83 : small ? 6.99 : 9.53) * mm;
    const y0 = -h + 1.2 * mm;
    const r = (small ? 2.3 : 3.0) * mm;
    const cx = multi ? w / 2 - 1.6 * mm : 0;
    const cy = multi ? y0 + h / 2 : y0 + h * 0.52;
    return (
      <>
        <defs>
          <linearGradient id={`${g}-blue`} x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#3f7fd6" />
            <stop offset="1" stopColor="#1d4f9c" />
          </linearGradient>
          <radialGradient id={`${g}-brass`}>
            <stop offset="0" stopColor="#f6dc8a" />
            <stop offset="1" stopColor="#b8862b" />
          </radialGradient>
        </defs>
        <rect
          x={-w / 2}
          y={y0}
          width={w}
          height={h}
          rx={0.6 * mm}
          fill={`url(#${g}-blue)`}
          className="bb-pot-case"
        />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill={multi ? `url(#${g}-brass)` : "#f1f1ee"}
          className="bb-pot-rotor"
        />
        <line x1={cx - r * 0.7} y1={cy} x2={cx + r * 0.7} y2={cy} className="bb-pot-slot" />
        {small && (
          <line x1={cx} y1={cy - r * 0.7} x2={cx} y2={cy + r * 0.7} className="bb-pot-slot" />
        )}
        {!small && (
          <text
            x={multi ? -w / 2 + 1 * mm : 0}
            y={multi ? cy + 1.1 * mm : y0 + 1.3 * mm}
            textAnchor={multi ? "start" : "middle"}
            className="bb-pot-text"
          >
            {print}
          </text>
        )}
      </>
    );
  }
  if (kind === "pot-17mm") {
    const R = 8.5 * mm;
    const cy = -R - 0.6 * mm;
    return (
      <>
        <defs>
          <radialGradient id={`${g}-case`} cx="0.4" cy="0.35">
            <stop offset="0" stopColor="#e9ecef" />
            <stop offset="1" stopColor="#8d949b" />
          </radialGradient>
        </defs>
        <rect x={-6 * mm} y={cy} width={12 * mm} height={-cy} className="bb-pot-frame" />
        <circle cx={0} cy={cy} r={R} fill={`url(#${g}-case)`} className="bb-pot-case" />
        <circle cx={0} cy={cy} r={3.6 * mm} className="bb-pot-bush" />
        <circle cx={0} cy={cy} r={3 * mm} className="bb-pot-knurl" />
        <line x1={0} y1={cy - 2.6 * mm} x2={0} y2={cy - 0.6 * mm} className="bb-pot-slot" />
        <text x={0} y={cy + R - 1.4 * mm} textAnchor="middle" className="bb-pot-text dark">
          {print}
        </text>
      </>
    );
  }
  // PTV09A (and the older generic drawing): 10 mm frame, 6 mm shaft with its flat side
  const w = 10 * mm;
  const y0 = -11 * mm;
  return (
    <>
      <rect
        x={-w / 2}
        y={y0}
        width={w}
        height={-y0 - 0.6 * mm}
        rx={0.8 * mm}
        className="bb-pot-frame"
      />
      <rect
        x={-w / 2 + 0.8 * mm}
        y={y0 + 0.8 * mm}
        width={w - 1.6 * mm}
        height={-y0 - 2.2 * mm}
        rx={0.6 * mm}
        className="bb-pot-black"
      />
      <path
        d={`M ${-3 * mm} ${y0 + 5.5 * mm} A ${3 * mm} ${3 * mm} 0 1 1 ${3 * mm} ${y0 + 5.5 * mm} Z`}
        className="bb-pot-shaft"
        transform={`rotate(-90 0 ${y0 + 5.5 * mm})`}
      />
      <text x={0} y={-1.6 * mm} textAnchor="middle" className="bb-pot-text">
        {print}
      </text>
    </>
  );
}
