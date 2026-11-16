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

export function PackageArt({ pkg, legs, view, refName, selected, bad, showLabels }: Props) {
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
      body = (
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

  return (
    <g className={cls} data-ref={refName}>
      <title>{title}</title>
      {body}
      {pts.map((p, i) => (
        <Leg key={i} at={p} />
      ))}
      {showLabels &&
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
  const oy = pkg.style === "dip" ? 70 : 40;
  pkg.pins.forEach((pin, i) => {
    const [dr, dc] = pkg.offsets[i] ?? [i, 0];
    legs[pin] =
      pkg.style === "dip"
        ? [ox + dr * P * 1.6, oy + (dc < 0 ? -3 * P : 0)]
        : [ox + dr * P * 1.6, oy];
  });
  const w = Math.max(...Object.values(legs).map((p) => p[0])) + 30;
  const h = pkg.style === "dip" ? 100 : 66;
  if (pkg.style === "offboard") return null;
  return (
    <svg
      className="bb-preview"
      viewBox={`0 0 ${w} ${h}`}
      width={w * 1.7}
      height={h * 1.7}
      role="img"
    >
      <PackageArt pkg={pkg} legs={legs} view={view} refName={view?.ref ?? ""} showLabels />
    </svg>
  );
}
