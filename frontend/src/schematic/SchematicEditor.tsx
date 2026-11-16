/** SVG schematic editor: grid, placement, drag, rotation, orthogonal wires, labels and probes. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GRID,
  junctions,
  key,
  nextRef,
  onSegment,
  pinPositions,
  route,
  segmentDistance,
  simplify,
} from "./geometry";
import { SymbolBody, valueText } from "./symbols";
import type { Component, Point, Probe, ProbeKind, Schematic, SymbolDef } from "./types";

export type Tool =
  | { kind: "select" }
  | { kind: "place"; symbol: string }
  | { kind: "wire" }
  | { kind: "label" }
  | { kind: "probe"; probe: ProbeKind };

export type Selection =
  | { kind: "component"; id: string }
  | { kind: "wire"; id: string }
  | { kind: "label"; id: string }
  | null;

interface Props {
  schematic: Schematic;
  library: Record<string, SymbolDef>;
  tool: Tool;
  setTool: (t: Tool) => void;
  selection: Selection;
  setSelection: (s: Selection) => void;
  onChange: (s: Schematic) => void;
  probeColors: Record<string, string>;
}

const uid = (p: string) => `${p}${Math.random().toString(36).slice(2, 9)}`;

export function SchematicEditor({
  schematic: sch,
  library,
  tool,
  setTool,
  selection,
  setSelection,
  onChange,
  probeColors,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ x: -12, y: -10, scale: 1 });
  const [cursor, setCursor] = useState<Point>([0, 0]);
  const [wire, setWire] = useState<Point[] | null>(null);
  const [verticalFirst, setVerticalFirst] = useState(false);
  const [diffStart, setDiffStart] = useState<Point | null>(null);
  const drag = useRef<{
    kind: "component" | "pan";
    id?: string;
    start: Point;
    origin: Point;
    snapshot: Schematic;
    moved: boolean;
    client: [number, number];
  } | null>(null);

  // ------------------------------------------------------------------ coordinates
  const toGrid = useCallback(
    (clientX: number, clientY: number): [number, number] => {
      const svg = svgRef.current;
      if (!svg) return [0, 0];
      const r = svg.getBoundingClientRect();
      return [
        view.x + (clientX - r.left) / (GRID * view.scale),
        view.y + (clientY - r.top) / (GRID * view.scale),
      ];
    },
    [view],
  );
  const snap = (p: [number, number]): Point => [Math.round(p[0]), Math.round(p[1])];

  const pins = useMemo(() => {
    const out: { comp: Component; pin: string; at: Point }[] = [];
    for (const c of sch.components)
      for (const [pin, at] of Object.entries(pinPositions(c, library[c.kind])))
        out.push({ comp: c, pin, at });
    return out;
  }, [sch.components, library]);

  const dots = useMemo(() => junctions(sch, library), [sch, library]);
  // pins with nothing attached get an open-circle marker (as in usual schematic editors)
  const openPins = useMemo(() => {
    const count = new Map<string, number>();
    for (const q of pins) count.set(key(q.at), (count.get(key(q.at)) ?? 0) + 1);
    return pins.filter(
      (q) =>
        (count.get(key(q.at)) ?? 0) < 2 &&
        !sch.labels.some((l) => l.x === q.at[0] && l.y === q.at[1]) &&
        !sch.wires.some((w) =>
          w.points.some((b, i) =>
            i === 0 ? key(b) === key(q.at) : onSegment(q.at, w.points[i - 1]!, b),
          ),
        ),
    );
  }, [pins, sch.labels, sch.wires]);

  // ------------------------------------------------------------------ hit tests
  const hitComponent = (p: [number, number]): Component | undefined => {
    for (const c of [...sch.components].reverse()) {
      const pp = Object.values(pinPositions(c, library[c.kind]));
      const xs = [c.x, ...pp.map((q) => q[0])];
      const ys = [c.y, ...pp.map((q) => q[1])];
      const pad = 0.6;
      if (
        p[0] >= Math.min(...xs) - pad &&
        p[0] <= Math.max(...xs) + pad &&
        p[1] >= Math.min(...ys) - pad &&
        p[1] <= Math.max(...ys) + pad
      )
        return c;
    }
    return undefined;
  };
  const hitWire = (p: [number, number]) =>
    sch.wires.find((w) =>
      w.points.slice(1).some((b, i) => segmentDistance(p, w.points[i]!, b) < 0.35),
    );
  const hitLabel = (p: [number, number]) =>
    sch.labels.find((l) => Math.abs(l.x - p[0]) < 0.8 && Math.abs(l.y - p[1]) < 0.8);
  const nearestPin = (c: Component, p: [number, number]) => {
    let best = "";
    let dist = Infinity;
    for (const [name, at] of Object.entries(pinPositions(c, library[c.kind]))) {
      const d = Math.hypot(at[0] - p[0], at[1] - p[1]);
      if (d < dist) [best, dist] = [name, d];
    }
    return best;
  };
  const isConnectionPoint = (p: Point) =>
    pins.some((q) => key(q.at) === key(p)) ||
    sch.labels.some((l) => l.x === p[0] && l.y === p[1]) ||
    sch.wires.some((w) => w.points.some((q, i) => i > 0 && onSegment(p, w.points[i - 1]!, q)));

  // ------------------------------------------------------------------ actions
  const addProbe = (probe: Omit<Probe, "id">) =>
    onChange({ ...sch, probes: [...sch.probes, { id: uid("p"), ...probe }] });

  const finishWire = (points: Point[]) => {
    const pts = simplify(points);
    if (pts.length >= 2) onChange({ ...sch, wires: [...sch.wires, { id: uid("w"), points: pts }] });
    setWire(null);
  };

  const place = (symbol: string, at: Point) => {
    const sym = library[symbol];
    if (!sym) return;
    const comp: Component = {
      id: uid("c"),
      kind: symbol,
      ref: nextRef(sch, symbol === "ground" ? "GND" : sym.prefix),
      x: at[0],
      y: at[1],
      rot: 0,
      mirror: false,
      params: {},
      part_id: null,
    };
    onChange({ ...sch, components: [...sch.components, comp] });
    setSelection({ kind: "component", id: comp.id });
  };

  const moveComponent = (base: Schematic, id: string, to: Point): Schematic => {
    const comp = base.components.find((c) => c.id === id);
    if (!comp) return base;
    const dx = to[0] - comp.x;
    const dy = to[1] - comp.y;
    if (!dx && !dy) return base;
    const old = Object.values(pinPositions(comp, library[comp.kind])).map(key);
    const oldSet = new Set(old);
    // rubber-band: wire ends on the moved pins follow, keeping the segment orthogonal
    const wires = base.wires.map((w) => {
      const pts = w.points.map((p) => [...p] as Point);
      const ends = [0, pts.length - 1];
      let changed = false;
      for (const i of ends) {
        const pi0 = pts[i]!;
        if (!oldSet.has(key(pi0))) continue;
        const j = i === 0 ? 1 : pts.length - 2;
        const pj = pts[j]!;
        const horizontal = pj[1] === pi0[1];
        const pi: Point = [pi0[0] + dx, pi0[1] + dy];
        pts[i] = pi;
        if (pts.length > 2) {
          if (horizontal) pts[j] = [pj[0], pi[1]];
          else pts[j] = [pi[0], pj[1]];
        } else if (pi[0] !== pj[0] && pi[1] !== pj[1]) {
          const corner: Point = horizontal ? [pi[0], pj[1]] : [pj[0], pi[1]];
          pts.splice(i === 0 ? 1 : pts.length - 1, 0, corner);
        }
        changed = true;
      }
      return changed ? { ...w, points: simplify(pts) } : w;
    });
    return {
      ...base,
      wires,
      components: base.components.map((c) => (c.id === id ? { ...c, x: to[0], y: to[1] } : c)),
    };
  };

  const rotateSelected = useCallback(() => {
    if (selection?.kind !== "component") return;
    onChange({
      ...sch,
      components: sch.components.map((c) =>
        c.id === selection.id ? { ...c, rot: ((c.rot + 90) % 360) as Component["rot"] } : c,
      ),
    });
  }, [selection, sch, onChange]);

  const mirrorSelected = useCallback(() => {
    if (selection?.kind !== "component") return;
    onChange({
      ...sch,
      components: sch.components.map((c) =>
        c.id === selection.id ? { ...c, mirror: !c.mirror } : c,
      ),
    });
  }, [selection, sch, onChange]);

  const deleteSelected = useCallback(() => {
    if (!selection) return;
    if (selection.kind === "component") {
      const comp = sch.components.find((c) => c.id === selection.id);
      onChange({
        ...sch,
        components: sch.components.filter((c) => c.id !== selection.id),
        probes: sch.probes.filter((p) => !comp || p.component !== comp.ref),
      });
    } else if (selection.kind === "wire") {
      onChange({ ...sch, wires: sch.wires.filter((w) => w.id !== selection.id) });
    } else {
      onChange({ ...sch, labels: sch.labels.filter((l) => l.id !== selection.id) });
    }
    setSelection(null);
  }, [selection, sch, onChange, setSelection]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.key === "Escape") {
        setWire(null);
        setDiffStart(null);
        setTool({ kind: "select" });
      } else if (e.key === "r" || e.key === "R") rotateSelected();
      else if (e.key === "m" || e.key === "M") mirrorSelected();
      else if (e.key === "Delete" || e.key === "Backspace") deleteSelected();
      else if (e.key === "w" || e.key === "W") setTool({ kind: "wire" });
      else if (e.key === " " && wire) {
        e.preventDefault();
        setVerticalFirst((v) => !v);
      } else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rotateSelected, mirrorSelected, deleteSelected, setTool, wire]);

  // ------------------------------------------------------------------ pointer
  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    const raw = toGrid(e.clientX, e.clientY);
    const p = snap(raw);
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      drag.current = {
        kind: "pan",
        start: [view.x, view.y],
        origin: p,
        snapshot: sch,
        moved: false,
        client: [e.clientX, e.clientY],
      };
      (e.target as Element).setPointerCapture?.(e.pointerId);
      return;
    }
    if (e.button !== 0) return;
    if (tool.kind === "place") {
      place(tool.symbol, p);
      if (!e.shiftKey) setTool({ kind: "select" });
      return;
    }
    if (tool.kind === "wire") {
      if (!wire) setWire([p]);
      else {
        const pts = [...wire.slice(0, -1), ...route(wire[wire.length - 1]!, p, verticalFirst)];
        if (e.detail >= 2 || isConnectionPoint(p)) finishWire(pts);
        else setWire([...pts.slice(0, -1), p]);
      }
      return;
    }
    if (tool.kind === "label") {
      const id = uid("l");
      onChange({ ...sch, labels: [...sch.labels, { id, name: "out", x: p[0], y: p[1] }] });
      setSelection({ kind: "label", id });
      setTool({ kind: "select" });
      return;
    }
    if (tool.kind === "probe") {
      const pk = tool.probe;
      if (pk === "i" || pk === "p") {
        const c = hitComponent(raw);
        if (c && c.kind !== "ground")
          addProbe({ kind: pk, component: c.ref, pin: pk === "i" ? nearestPin(c, raw) : null });
        return;
      }
      if (!isConnectionPoint(p)) return;
      if (pk === "v") addProbe({ kind: "v", target: { at: p } });
      else if (!diffStart) setDiffStart(p);
      else {
        addProbe({ kind: "vdiff", target: { at: diffStart }, reference: { at: p } });
        setDiffStart(null);
      }
      return;
    }
    // select
    const lb = hitLabel(raw);
    if (lb) {
      setSelection({ kind: "label", id: lb.id });
      return;
    }
    const c = hitComponent(raw);
    if (c) {
      setSelection({ kind: "component", id: c.id });
      drag.current = {
        kind: "component",
        id: c.id,
        start: [c.x, c.y],
        origin: p,
        snapshot: sch,
        moved: false,
        client: [e.clientX, e.clientY],
      };
      (e.target as Element).setPointerCapture?.(e.pointerId);
      return;
    }
    const w = hitWire(raw);
    if (w) {
      setSelection({ kind: "wire", id: w.id });
      return;
    }
    setSelection(null);
    drag.current = {
      kind: "pan",
      start: [view.x, view.y],
      origin: p,
      snapshot: sch,
      moved: false,
      client: [e.clientX, e.clientY],
    };
  };

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const raw = toGrid(e.clientX, e.clientY);
    setCursor(snap(raw));
    const d = drag.current;
    if (!d) return;
    if (d.kind === "pan") {
      const dx = (e.clientX - d.client[0]) / (GRID * view.scale);
      const dy = (e.clientY - d.client[1]) / (GRID * view.scale);
      setView((v) => ({ ...v, x: d.start[0] - dx, y: d.start[1] - dy }));
      return;
    }
    const p = snap(raw);
    const to: Point = [d.start[0] + p[0] - d.origin[0], d.start[1] + p[1] - d.origin[1]];
    if (to[0] !== d.start[0] || to[1] !== d.start[1] || d.moved) {
      d.moved = true;
      onChange(moveComponent(d.snapshot, d.id!, to));
    }
  };

  const onPointerUp = () => {
    drag.current = null;
  };

  const onWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    const [gx, gy] = toGrid(e.clientX, e.clientY);
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setView((v) => {
      const scale = Math.min(4, Math.max(0.25, v.scale * factor));
      const k = v.scale / scale;
      return { scale, x: gx - (gx - v.x) * k, y: gy - (gy - v.y) * k };
    });
  };

  const fit = () => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const c of sch.components) {
      xs.push(c.x - 3, c.x + 3);
      ys.push(c.y - 3, c.y + 3);
    }
    for (const w of sch.wires)
      for (const p of w.points) {
        xs.push(p[0]);
        ys.push(p[1]);
      }
    for (const l of sch.labels) {
      xs.push(l.x - 2, l.x + 2);
      ys.push(l.y - 1, l.y + 1);
    }
    const svg = svgRef.current;
    if (!xs.length || !svg) return;
    const r = svg.getBoundingClientRect();
    const w = Math.max(...xs) - Math.min(...xs) + 4;
    const h = Math.max(...ys) - Math.min(...ys) + 4;
    const scale = Math.min(
      2,
      Math.max(0.25, Math.min(r.width / (w * GRID), r.height / (h * GRID))),
    );
    setView({
      scale,
      x: (Math.min(...xs) + Math.max(...xs)) / 2 - r.width / (2 * GRID * scale),
      y: (Math.min(...ys) + Math.max(...ys)) / 2 - r.height / (2 * GRID * scale),
    });
  };

  // auto-fit when a new document is loaded (component ids change completely)
  const docKey = sch.components.map((c) => c.id).join("|");
  const lastDoc = useRef("");
  useEffect(() => {
    const prev = lastDoc.current.split("|");
    const now = docKey.split("|");
    if (now.length > 1 && !now.some((id) => prev.includes(id))) fit();
    lastDoc.current = docKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docKey]);

  // ------------------------------------------------------------------ render
  const pinNode = (p: Point) => <circle key={key(p)} cx={p[0] * GRID} cy={p[1] * GRID} r={2.5} />;
  const preview =
    tool.kind === "wire" && wire
      ? [...wire.slice(0, -1), ...route(wire[wire.length - 1]!, cursor, verticalFirst)]
      : null;
  const ghost =
    tool.kind === "place" && library[tool.symbol]
      ? ({
          id: "ghost",
          kind: tool.symbol,
          ref: "",
          x: cursor[0],
          y: cursor[1],
          rot: 0,
          mirror: false,
          params: {},
          part_id: null,
        } as Component)
      : null;

  const probeMarks = sch.probes.flatMap((pr) => {
    const color = probeColors[pr.id] ?? "#888";
    const marks: React.ReactNode[] = [];
    const at = (p: Point | null | undefined, tag: string) =>
      p &&
      marks.push(
        <g key={`${pr.id}${tag}`} transform={`translate(${p[0] * GRID},${p[1] * GRID})`}>
          <path d="M0 0 L-6 -14 L6 -14 Z" fill={color} stroke="none" />
          <text y={-17} textAnchor="middle" fontSize={10} fill={color}>
            {tag}
          </text>
        </g>,
      );
    if (pr.kind === "v") at(pr.target?.at, "V");
    if (pr.kind === "vdiff") {
      at(pr.target?.at, "+");
      at(pr.reference?.at, "−");
    }
    if (pr.kind === "i" || pr.kind === "p") {
      const c = sch.components.find((x) => x.ref === pr.component);
      if (c) {
        const pp = pinPositions(c, library[c.kind]);
        const pin: Point = (pr.pin ? pp[pr.pin] : undefined) ?? [c.x, c.y];
        marks.push(
          <g key={pr.id} transform={`translate(${pin[0] * GRID},${pin[1] * GRID})`}>
            <circle r={7} fill="none" stroke={color} strokeWidth={2} />
            <text y={-11} textAnchor="middle" fontSize={10} fill={color}>
              {pr.kind === "i" ? "I" : "P"}
            </text>
          </g>,
        );
      }
    }
    return marks;
  });

  const cursorClass = tool.kind === "select" ? "" : tool.kind === "probe" ? " probing" : " drawing";

  return (
    <div className="schematic-editor">
      <svg
        ref={svgRef}
        className={`schematic-canvas${cursorClass}`}
        role="application"
        aria-label="Área de desenho do esquemático"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onWheel={onWheel}
        onContextMenu={(e) => {
          e.preventDefault();
          if (wire && preview) finishWire(preview.slice(0, -1));
          else setTool({ kind: "select" });
        }}
      >
        <defs>
          <pattern
            id="grid"
            width={GRID * view.scale}
            height={GRID * view.scale}
            patternUnits="userSpaceOnUse"
            x={-view.x * GRID * view.scale}
            y={-view.y * GRID * view.scale}
          >
            <circle cx={1} cy={1} r={1} className="grid-dot" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
        <g transform={`scale(${view.scale}) translate(${-view.x * GRID},${-view.y * GRID})`}>
          {sch.wires.map((w) => (
            <polyline
              key={w.id}
              className={selection?.kind === "wire" && selection.id === w.id ? "wire sel" : "wire"}
              points={w.points.map((p) => `${p[0] * GRID},${p[1] * GRID}`).join(" ")}
            />
          ))}
          {preview && (
            <polyline
              className="wire preview"
              points={preview.map((p) => `${p[0] * GRID},${p[1] * GRID}`).join(" ")}
            />
          )}
          {[...sch.components, ...(ghost ? [ghost] : [])].map((c) => {
            const sym = library[c.kind];
            const selected = selection?.kind === "component" && selection.id === c.id;
            const pinXs = Object.values(pinPositions(c, sym)).map((q) => q[0]);
            const vertical = pinXs.length > 1 && pinXs.every((x) => x === pinXs[0]);
            const isGround = c.kind === "ground";
            return (
              <g
                key={c.id}
                className={`comp${selected ? " sel" : ""}${c.id === "ghost" ? " ghost" : ""}`}
              >
                <g
                  transform={`translate(${c.x * GRID},${c.y * GRID}) rotate(${c.rot}) scale(${c.mirror ? -1 : 1},1)`}
                >
                  <SymbolBody c={c} sym={sym} />
                </g>
                {!isGround && c.id !== "ghost" && (
                  <text
                    className="ref-text"
                    x={(c.x + (vertical ? 1.4 : 0)) * GRID}
                    y={(c.y + (vertical ? -0.3 : -1.5)) * GRID}
                    textAnchor={vertical ? "start" : "middle"}
                  >
                    <tspan className="ref">{c.ref}</tspan>
                    <tspan x={(c.x + (vertical ? 1.4 : 0)) * GRID} dy={13} className="val">
                      {valueText(c, sym)}
                    </tspan>
                  </text>
                )}
              </g>
            );
          })}
          <g className="pins">{openPins.map((p) => pinNode(p.at))}</g>
          <g className="junctions">
            {dots.map((p) => (
              <circle key={key(p)} cx={p[0] * GRID} cy={p[1] * GRID} r={4} />
            ))}
          </g>
          {sch.labels.map((l) => (
            <g
              key={l.id}
              className={
                selection?.kind === "label" && selection.id === l.id ? "netlabel sel" : "netlabel"
              }
              transform={`translate(${l.x * GRID},${l.y * GRID})`}
            >
              <line x1={0} y1={0} x2={0} y2={-8} />
              <path
                d={`M0 -8 L4 -22 L${12 + l.name.length * 7} -22 L${12 + l.name.length * 7} -8 Z`}
              />
              <text x={8} y={-11} fontSize={11}>
                {l.name}
              </text>
            </g>
          ))}
          {probeMarks}
          {diffStart && (
            <circle
              cx={diffStart[0] * GRID}
              cy={diffStart[1] * GRID}
              r={6}
              className="diff-start"
            />
          )}
          {tool.kind !== "select" && (
            <circle cx={cursor[0] * GRID} cy={cursor[1] * GRID} r={3} className="cursor-dot" />
          )}
        </g>
      </svg>
      <div className="canvas-status small muted">
        <span>
          ({cursor[0]}, {cursor[1]}) · zoom {Math.round(view.scale * 100)} %
        </span>
        <span>
          {tool.kind === "wire"
            ? "Fio: clique nos vértices; termina num pino, fio ou duplo clique · espaço alterna o canto · Esc cancela"
            : tool.kind === "place"
              ? "Clique para posicionar (Shift mantém a ferramenta) · Esc cancela"
              : tool.kind === "probe"
                ? tool.probe === "vdiff"
                  ? diffStart
                    ? "Clique no nó de referência (−)"
                    : "Clique no nó positivo (+)"
                  : tool.probe === "v"
                    ? "Clique num fio ou pino"
                    : "Clique no componente (corrente entra pelo pino mais próximo)"
                : "Arraste para mover · R gira · M espelha · Del apaga · W fio · roda do mouse: zoom · arraste o fundo: mover a vista"}
        </span>
        <button type="button" className="secondary small-btn" onClick={fit}>
          Enquadrar
        </button>
      </div>
    </div>
  );
}
