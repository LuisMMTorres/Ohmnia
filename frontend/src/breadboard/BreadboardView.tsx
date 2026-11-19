// Breadboard view: the circuit of the schematic assembled on an 830-point breadboard.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { breadboardApi } from "../api";
import type { Schematic } from "../schematic/types";
import {
  allHoles,
  BOARD_GAP,
  boardSize,
  COLS,
  holeXY,
  MX,
  MY,
  nearestHole,
  P,
  parseHole,
  placeLegs,
  shift,
  strip,
  WIRE_COLORS,
} from "./geometry";
import type { Orientation } from "./geometry";
import { ScopeMiniature } from "./ScopeMiniature";
import { connectScope } from "./scopeConnections";
import { netAtHole } from "./connections";
import { InstrumentFace } from "./InstrumentFace";
import { deviceFace } from "./DeviceFaces";
import type { Motion } from "./DeviceFaces";
import { PackageArt, PackagePreview } from "./PackageArt";
import type {
  Breadboard,
  CheckReport,
  PackageSpec,
  PartView,
  PlacedPart,
  ResolveOut,
  Spec,
  Step,
  WireColor,
} from "./types";
import { emptyBreadboard } from "./types";

type Pt = [number, number];

type Tool =
  | { kind: "select" }
  | { kind: "scope"; channel: number; terminal: "positive" | "negative" }
  | { kind: "connect"; ref: string; terminal: string }
  | { kind: "place"; ref: string; orient: Orientation }
  | { kind: "lead"; ref: string; legs: Record<string, string> }
  | { kind: "wire"; from: string | null; color: WireColor };

type Sel = { kind: "part"; ref: string } | { kind: "wire"; id: string } | null;

interface Drag {
  ref: string;
  start: string;
  leg: string | null; // dragging one leg (axial parts) instead of the whole part
}

const ORIGIN_LABEL: Record<PartView["origin"], string> = {
  datasheet: "pinagem do datasheet",
  generico: "genérico",
  sem_pinagem: "sem pinagem",
  sem_montagem: "fora da protoboard",
  implicito: "alimentação",
};
const ORIGIN_CLASS: Record<PartView["origin"], string> = {
  datasheet: "liberado",
  generico: "em_revisao",
  sem_pinagem: "rejeitado",
  sem_montagem: "",
  implicito: "",
};
const ISSUE_LABEL: Record<string, string> = {
  faltando: "Falta ligação",
  sobrando: "Ligação a mais",
  trocada: "Pernas trocadas",
  nao_montado: "Não montado",
  furo: "Furo em conflito",
  fora_do_esquematico: "Fora do esquemático",
  sem_pinagem: "Sem pinagem",
  aviso: "Aviso",
};

interface Props {
  schematic: Schematic;
  onChange: (next: Schematic) => void;
  spec: Spec;
  resolved: ResolveOut | null;
  readOnly?: boolean;
  initialGuide?: Step[];
  /** Shaft speed of each motor after the last simulation (direction of rotation). */
  motion?: Record<string, Motion>;
}

export function BreadboardView({
  schematic,
  onChange,
  spec,
  resolved,
  readOnly,
  initialGuide,
  motion,
}: Props) {
  const bb: Breadboard = schematic.breadboard ?? emptyBreadboard();
  const board = spec.board;
  const pkgs = useMemo(
    () => Object.fromEntries(spec.packages.map((p) => [p.id, p])) as Record<string, PackageSpec>,
    [spec.packages],
  );
  const views = useMemo(
    () =>
      Object.fromEntries((resolved?.parts ?? []).map((p) => [p.ref, p])) as Record<
        string,
        PartView
      >,
    [resolved],
  );
  const [tool, setTool] = useState<Tool>({ kind: "select" });
  const [sel, setSel] = useState<Sel>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [report, setReport] = useState<CheckReport | null>(null);
  const [guide, setGuide] = useState<Step[] | null>(initialGuide ?? null);
  const [mark, setMark] = useState<string[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wireColor, setWireColor] = useState<WireColor>("verde");
  const [probePositive, setProbePositive] = useState("a1");
  const [probeNegative, setProbeNegative] = useState("0");
  const [probeName, setProbeName] = useState("CH1");
  const [zoom, setZoom] = useState(1);
  const svgRef = useRef<SVGSVGElement>(null);
  const size = boardSize(board);
  const instrumentCount = bb.parts.filter((p) => pkgs[p.package]?.style === "offboard").length;
  size.h =
    size.boardH +
    Math.max(1, Math.ceil((instrumentCount + (schematic.bench_scope_channels ? 1 : 0)) / 3)) * 180 +
    40;

  const update = useCallback(
    (next: Breadboard) => onChange({ ...schematic, breadboard: next }),
    [onChange, schematic],
  );

  // live check while assembling (debounced)
  const bbKey = JSON.stringify(schematic.breadboard ?? null);
  useEffect(() => {
    if (!schematic.breadboard || !schematic.breadboard.parts.length) {
      setReport(null);
      return;
    }
    const t = setTimeout(() => {
      breadboardApi
        .check(schematic)
        .then((r) => {
          setReport(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bbKey, resolved]);

  const used = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of bb.parts) for (const h of Object.values(p.legs)) m.set(h, p.ref);
    for (const w of bb.wires) {
      m.set(w.a, "fio");
      m.set(w.b, "fio");
    }
    return m;
  }, [bb]);
  const badRefs = useMemo(
    () =>
      new Set(
        (report?.issues ?? [])
          .filter((i) => i.kind !== "aviso" && i.kind !== "sem_pinagem")
          .flatMap((i) => i.refs),
      ),
    [report],
  );

  const toSvg = (e: { clientX: number; clientY: number }): Pt => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return [0, 0];
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return [p.x, p.y];
  };

  const free = useCallback(
    (holes: string[], except: string | null = null) =>
      holes.every((h) => !used.has(h) || used.get(h) === except),
    [used],
  );

  // ghost of what the current tool or drag would do
  const ghost: PlacedPart | null = useMemo(() => {
    if (!hover) return null;
    if (tool.kind === "place") {
      const pkg = pkgs[views[tool.ref]?.package ?? ""];
      if (!pkg) return null;
      const legs = placeLegs(board, pkg, hover, tool.orient);
      return legs ? { ref: tool.ref, package: pkg.id, legs } : null;
    }
    if (drag) {
      const part = bb.parts.find((p) => p.ref === drag.ref);
      const a = parseHole(board, drag.start);
      const b = parseHole(board, hover);
      if (!part || !a || !b) return null;
      if (drag.leg) return { ...part, legs: { ...part.legs, [drag.leg]: hover } };
      const pkg = pkgs[part.package];
      const dRow = b.row - a.row;
      const dCol =
        pkg?.style === "dip" || pkg?.style === "board"
          ? 0
          : COLS.indexOf(b.col) - COLS.indexOf(a.col);
      const legs: Record<string, string> = {};
      for (const [pin, h] of Object.entries(part.legs)) {
        const shifted = shift(board, h.replace(/^2:/, ""), dRow, dCol);
        const s = shifted && b.board === 2 ? `2:${shifted}` : shifted;
        if (!s) return null;
        legs[pin] = s;
      }
      return { ...part, legs };
    }
    return null;
  }, [hover, tool, drag, bb.parts, board, pkgs, views]);
  const ghostOk = ghost ? free(Object.values(ghost.legs), drag ? drag.ref : null) : false;

  const onMove = (e: ReactMouseEvent) => {
    const [x, y] = toSvg(e);
    setHover(nearestHole(board, x, y));
  };

  const onClick = (e: ReactMouseEvent<SVGSVGElement>) => {
    const hole =
      (e.target as Element).closest("[data-hole]")?.getAttribute("data-hole") ??
      nearestHole(board, ...toSvg(e));
    if (readOnly || !hole) return;
    if (tool.kind === "scope") {
      try {
        if (!resolved) throw new Error("Aguarde o mapeamento das ligações do circuito.");
        onChange(connectScope(schematic, board, resolved, tool.channel, tool.terminal, hole));
        setTool({ kind: "select" });
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
      return;
    }
    if (tool.kind === "connect") {
      const part = bb.parts.find((p) => p.ref === tool.ref);
      if (!part) return;
      if (
        !free([hole], part.ref) ||
        Object.entries(part.legs).some(([pin, h]) => pin !== tool.terminal && h === hole)
      ) {
        setError(`O furo ${hole} já está ocupado. Escolha outro furo do mesmo barramento.`);
        return;
      }
      update({
        ...bb,
        parts: bb.parts.map((p) =>
          p.ref === part.ref ? { ...p, legs: { ...p.legs, [tool.terminal]: hole! } } : p,
        ),
      });
      setTool({ kind: "select" });
      setError(null);
      return;
    }
    if (tool.kind === "place") {
      if (ghost && ghostOk) {
        update({ ...bb, parts: [...bb.parts.filter((p) => p.ref !== ghost.ref), ghost] });
        setSel({ kind: "part", ref: ghost.ref });
        setTool({ kind: "select" });
      }
      return;
    }
    if (tool.kind === "lead") {
      const pkg = pkgs[views[tool.ref]?.package ?? ""];
      if (!pkg || !free([hole])) return;
      const terms = pkg.pins.filter((t) => t in (views[tool.ref]?.pinmap ?? {}));
      const legs = { ...tool.legs, [terms[Object.keys(tool.legs).length]!]: hole };
      if (Object.keys(legs).length >= terms.length) {
        update({
          ...bb,
          parts: [
            ...bb.parts.filter((p) => p.ref !== tool.ref),
            { ref: tool.ref, package: pkg.id, legs },
          ],
        });
        setTool({ kind: "select" });
      } else setTool({ ...tool, legs });
      return;
    }
    if (tool.kind === "wire") {
      if (!free([hole])) return;
      if (!tool.from) setTool({ ...tool, from: hole });
      else if (tool.from !== hole) {
        const id = `w${Date.now().toString(36)}`;
        update({ ...bb, wires: [...bb.wires, { id, a: tool.from, b: hole, color: tool.color }] });
        setTool({ ...tool, from: null });
      }
      return;
    }
    setSel(null);
  };

  const onUp = () => {
    if (drag && ghost && ghostOk) {
      update({ ...bb, parts: bb.parts.map((p) => (p.ref === ghost.ref ? ghost : p)) });
    }
    setDrag(null);
  };

  const removeSelected = useCallback(() => {
    if (!sel) return;
    if (sel.kind === "part") update({ ...bb, parts: bb.parts.filter((p) => p.ref !== sel.ref) });
    else update({ ...bb, wires: bb.wires.filter((w) => w.id !== sel.id) });
    setSel(null);
  }, [sel, bb, update]);

  const rotateSelected = useCallback(() => {
    if (sel?.kind !== "part") return;
    const part = bb.parts.find((p) => p.ref === sel.ref);
    const pkg = part && pkgs[part.package];
    if (!part || !pkg || ["dip", "board", "offboard"].includes(pkg.style)) return;
    const a = parseHole(board, part.legs[pkg.pins[0]!] ?? "");
    const b = parseHole(board, part.legs[pkg.pins[1]!] ?? "");
    if (!a || !b) return;
    const orient: Orientation = a.row === b.row ? "h" : "v";
    const legs = placeLegs(board, pkg, part.legs[pkg.pins[0]!]!, orient);
    if (legs && free(Object.values(legs), part.ref))
      update({ ...bb, parts: bb.parts.map((p) => (p.ref === part.ref ? { ...p, legs } : p)) });
  }, [sel, bb, pkgs, board, update, free]);

  useEffect(() => {
    if (readOnly) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Escape") {
        setTool({ kind: "select" });
        setDrag(null);
      } else if (e.key === "Delete" || e.key === "Backspace") removeSelected();
      else if (e.key === "r" || e.key === "R") {
        if (tool.kind === "place") setTool({ ...tool, orient: tool.orient === "h" ? "v" : "h" });
        else rotateSelected();
      } else if (e.key === "w" || e.key === "W")
        setTool({ kind: "wire", from: null, color: wireColor });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [readOnly, tool, removeSelected, rotateSelected, wireColor]);

  const auto = async () => {
    if (bb.parts.length && !window.confirm("Substituir a montagem atual pela automática?")) return;
    setBusy(true);
    try {
      const r = await breadboardApi.auto({ ...schematic, breadboard: null });
      update(r.breadboard);
      setReport(r.report);
      setGuide(r.guide);
      setNotes(r.notes);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const showGuide = async () => {
    try {
      setGuide(await breadboardApi.guide(schematic));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const placed = new Set(bb.parts.map((p) => p.ref));
  const hoverStrip = hover ? strip(board, hover, bb.rails_split) : null;
  const holes = useMemo(() => allHoles(board), [board]);
  const xy = (h: string): Pt => holeXY(board, h);
  const instruments = bb.parts.filter((p) => pkgs[p.package]?.style === "offboard");
  const instrumentAt = (ref: string): Pt => {
    const i = instruments.findIndex((p) => p.ref === ref);
    return [20 + (i % 3) * 320, size.boardH + 24 + Math.floor(i / 3) * 180];
  };
  const startPlacing = (v: PartView) => {
    const pkg = pkgs[v.package ?? ""];
    if (!pkg) return;
    let legs: Record<string, string> | null = pkg.style === "offboard" ? {} : null;
    if (!legs) {
      for (const h of holes.filter((h) => /^(2:)?[a-j]/.test(h))) {
        const candidate = placeLegs(board, pkg, h, "h");
        if (candidate && free(Object.values(candidate))) {
          legs = candidate;
          break;
        }
      }
    }
    if (!legs) {
      setError("Sem espaço livre para este dispositivo.");
      return;
    }
    update({
      ...bb,
      parts: [...bb.parts.filter((p) => p.ref !== v.ref), { ref: v.ref, package: pkg.id, legs }],
    });
    setSel({ kind: "part", ref: v.ref });
    setTool({ kind: "select" });
  };
  const selPart = sel?.kind === "part" ? bb.parts.find((p) => p.ref === sel.ref) : undefined;
  const selView = sel?.kind === "part" ? views[sel.ref] : undefined;
  const leadTerms =
    tool.kind === "lead"
      ? (pkgs[views[tool.ref]?.package ?? ""]?.pins ?? []).filter(
          (t) => t in (views[tool.ref]?.pinmap ?? {}),
        )
      : [];
  const hint =
    tool.kind === "scope"
      ? `CH${tool.channel}: clique no furo da ponteira ${tool.terminal === "positive" ? "+" : "−"}. Esc cancela.`
      : tool.kind === "connect"
        ? `${tool.ref}: clique no furo para conectar o terminal ${tool.terminal === "p" ? "+" : tool.terminal === "n" ? "−" : (views[tool.ref]?.labels[tool.terminal] ?? tool.terminal)}. Esc cancela.`
        : tool.kind === "place"
          ? `Clique no furo da perna 1 de ${tool.ref}${placeHint(pkgs[views[tool.ref]?.package ?? ""])}. R gira, Esc cancela.`
          : tool.kind === "lead"
            ? `${tool.ref}: clique no furo do terminal ${views[tool.ref]?.labels[leadTerms[Object.keys(tool.legs).length] ?? ""] ?? leadTerms[Object.keys(tool.legs).length]}.`
            : tool.kind === "wire"
              ? tool.from
                ? `Fio a partir de ${tool.from}: clique no outro furo. Esc termina.`
                : "Clique no primeiro furo do fio."
              : "Arraste as peças para mover; arraste a perna de um resistor ou diodo para dobrá-la. Del apaga, R gira.";

  return (
    <div className="bb-layout">
      {!readOnly && (
        <aside className="panel bb-side" aria-label="Peças do circuito">
          <div className="tools">
            <button
              className={tool.kind === "select" ? "tool active" : "tool"}
              onClick={() => setTool({ kind: "select" })}
            >
              Selecionar
            </button>
            <button
              className={tool.kind === "wire" ? "tool active" : "tool"}
              onClick={() => setTool({ kind: "wire", from: null, color: wireColor })}
            >
              Fio (W)
            </button>
            <label className="small">
              Cor do fio{" "}
              <select
                value={wireColor}
                onChange={(e) => {
                  const c = e.target.value as WireColor;
                  setWireColor(c);
                  if (tool.kind === "wire") setTool({ ...tool, color: c });
                }}
              >
                {Object.keys(WIRE_COLORS).map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          </div>
          <button onClick={() => void auto()} disabled={busy || !resolved}>
            {busy ? "Montando…" : "Montar automaticamente"}
          </button>
          <button
            className="secondary"
            onClick={() => void showGuide()}
            disabled={!bb.parts.length}
          >
            Roteiro de montagem
          </button>
          <button
            className="secondary"
            onClick={() =>
              bb.parts.length && window.confirm("Apagar a montagem?") && update(emptyBreadboard())
            }
            disabled={!bb.parts.length}
          >
            Limpar
          </button>
          <label className="small">
            <input
              type="checkbox"
              checked={bb.rails_split}
              onChange={(e) => update({ ...bb, rails_split: e.target.checked })}
            />{" "}
            barramentos cortados ao meio
          </label>
          <h3>Peças</h3>
          {!resolved && <p className="muted small">Lendo as pinagens…</p>}
          <ul className="bb-list">
            {(resolved?.parts ?? [])
              .filter((v) => v.origin !== "sem_montagem")
              .map((v) => (
                <li key={v.ref} className={badRefs.has(v.ref) ? "bad" : ""}>
                  <button className="link" onClick={() => setSel({ kind: "part", ref: v.ref })}>
                    <strong>{v.ref}</strong> <span className="muted">{v.title}</span>
                  </button>
                  <span className={`badge ${ORIGIN_CLASS[v.origin]}`}>
                    {pkgs[v.package ?? ""]?.style === "offboard" && v.origin === "generico"
                      ? "instrumento"
                      : ORIGIN_LABEL[v.origin]}
                  </span>
                  {placed.has(v.ref) ? (
                    <span className="small muted"> montado</span>
                  ) : v.package ? (
                    <>
                      <button className="small" onClick={() => startPlacing(v)}>
                        Colocar
                      </button>
                      {pkgs[v.package]?.style !== "offboard" && (
                        <button
                          className="small secondary"
                          title="Siga o ponteiro do mouse e clique no furo do pino 1"
                          onClick={() => {
                            setSel({ kind: "part", ref: v.ref });
                            setTool({ kind: "place", ref: v.ref, orient: "h" });
                          }}
                        >
                          Pelo pino 1
                        </button>
                      )}
                    </>
                  ) : null}
                </li>
              ))}
          </ul>
          {(resolved?.parts ?? []).some((v) => v.origin === "sem_montagem") && (
            <p className="small muted">
              Fora da protoboard (elementos ideais da simulação):{" "}
              {(resolved?.parts ?? [])
                .filter((v) => v.origin === "sem_montagem")
                .map((v) => v.ref)
                .join(", ")}
            </p>
          )}
        </aside>
      )}

      <div className="panel bb-canvas">
        <p className="small muted bb-hint">
          {hint}
          {hover && (
            <span className="bb-hover">
              {" "}
              · furo {hover}
              {used.get(hover) ? ` (${used.get(hover)})` : ""}
            </span>
          )}
        </p>
        <label className="small bb-zoom">
          Zoom{" "}
          <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
            {[0.5, 0.75, 1, 1.3, 1.6, 2, 2.5].map((z) => (
              <option key={z} value={z}>
                {Math.round(z * 100)} %
              </option>
            ))}
          </select>
        </label>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${size.w} ${size.h}`}
          className={`bb-svg${tool.kind !== "select" ? " placing" : ""}`}
          style={{ width: size.w * zoom }}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          onClick={onClick}
          onMouseUp={onUp}
          role="img"
          aria-label="Protoboard"
        >
          {[0, BOARD_GAP].map((dy, i) => (
            <g key={dy} transform={`translate(0,${dy})`} className="bb-board-panel">
              <text x={MX} y={18} className="bb-ruler">
                Protoboard {i + 1}
              </text>
              <rect
                x={MX - 28}
                y={6}
                width={size.w - MX + 16}
                height={BOARD_GAP - 26}
                rx={10}
                className="bb-board"
              />
              <rect
                x={MX - 24}
                y={MY + 8.5 * P - 4}
                width={size.w - MX + 8}
                height={8}
                className="bb-channel"
              />
              {(["tp", "tn", "bn", "bp"] as const).map((r) => {
                const y = MY + (board.y[r] ?? 0) * P;
                const off = r === "tp" || r === "bn" ? -P * 0.55 : P * 0.55;
                return (
                  <line
                    key={r}
                    x1={MX - 8}
                    x2={size.w - MX + 8}
                    y1={y + (r === "tp" ? -P * 0.55 : r === "bp" ? P * 0.55 : off * 0)}
                    y2={y + (r === "tp" ? -P * 0.55 : r === "bp" ? P * 0.55 : off * 0)}
                    className={board.rail_polarity[r] === "+" ? "bb-rail-plus" : "bb-rail-minus"}
                  />
                );
              })}
              {[1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 63].map((r) => (
                <text
                  key={r}
                  x={MX + (r - 1) * P}
                  y={MY + 2.15 * P}
                  textAnchor="middle"
                  className="bb-ruler"
                >
                  {r}
                </text>
              ))}
              {"abcdefghij".split("").map((c) => (
                <text
                  key={c}
                  x={MX - 18}
                  y={MY + (board.y[c] ?? 0) * P + 3}
                  textAnchor="middle"
                  className="bb-ruler"
                >
                  {c}
                </text>
              ))}
              {(["tp", "tn", "bn", "bp"] as const).map((r) => (
                <text
                  key={r}
                  x={MX - 18}
                  y={MY + (board.y[r] ?? 0) * P + 3}
                  textAnchor="middle"
                  className="bb-ruler"
                >
                  {board.rail_polarity[r]}
                </text>
              ))}
            </g>
          ))}
          <rect x={8} y={8} width={62} height={MY + 40 * P} rx={8} className="bb-board" />
          <line x1={16} x2={16} y1={MY - 8} y2={MY + 39 * P + 8} className="bb-rail-plus" />
          <line x1={62} x2={62} y1={MY - 8} y2={MY + 39 * P + 8} className="bb-rail-minus" />
          <text x={18} y={19} className="bb-ruler">
            +
          </text>
          <text x={48} y={19} className="bb-ruler">
            −
          </text>
          {holes.map((h) => {
            const [x, y] = xy(h);
            const lit = hoverStrip && strip(board, h, bb.rails_split) === hoverStrip;
            return (
              <rect
                key={h}
                data-hole={h}
                x={x - 3}
                y={y - 3}
                width={6}
                height={6}
                rx={1}
                className={`bb-hole${lit ? " lit" : ""}${h === hover ? " hover" : ""}`}
              />
            );
          })}
          {mark.map((h) => {
            const [x, y] = xy(h);
            return <circle key={`m${h}`} cx={x} cy={y} r={7} className="bb-mark" />;
          })}

          {bb.parts.map((p) => {
            const pkg = pkgs[p.package];
            if (!pkg) return null;
            const isGhosted = drag?.ref === p.ref && ghost;
            if (pkg.style === "offboard") {
              const [bx, by] = instrumentAt(p.ref);
              const terms = pkg.pins.filter((t) => t in (views[p.ref]?.pinmap ?? {}));
              const kind = views[p.ref]?.kind ?? "";
              const face = deviceFace(kind);
              return (
                <g
                  key={p.ref}
                  className={`bb-instrument${sel?.kind === "part" && sel.ref === p.ref ? " selected" : ""}${badRefs.has(p.ref) ? " bad" : ""}`}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    setSel({ kind: "part", ref: p.ref });
                  }}
                >
                  <InstrumentFace
                    x={bx}
                    y={by}
                    title={`${p.ref} · ${views[p.ref]?.title ?? pkg.label}`}
                    kind={kind}
                    motion={motion?.[p.ref]}
                  />
                  {terms.map((t, i) => {
                    const spot = face?.terminals[t];
                    const tx = spot
                      ? bx + spot.at[0]
                      : bx + 18 + (i * 244) / Math.max(1, terms.length - 1 || 1);
                    const ty = spot ? by + spot.at[1] : by + 132;
                    const [lx, ly] = spot
                      ? [bx + spot.label[0], by + spot.label[1]]
                      : [tx, by + 156];
                    const [hx, hy] = p.legs[t] ? xy(p.legs[t]!) : [tx, ty + 10];
                    return (
                      <g key={t}>
                        <circle
                          cx={tx}
                          cy={ty}
                          r={spot ? 5.5 : 7}
                          style={{
                            fill: t === "n" ? "#17232f" : "#d32f2f",
                            stroke: "#8496a4",
                            cursor: "pointer",
                          }}
                          role="button"
                          tabIndex={readOnly ? -1 : 0}
                          aria-label={`Conectar terminal ${p.ref}.${t}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (!readOnly) setTool({ kind: "connect", ref: p.ref, terminal: t });
                          }}
                          onKeyDown={(e) => {
                            if (!readOnly && (e.key === "Enter" || e.key === " ")) {
                              e.preventDefault();
                              e.stopPropagation();
                              setTool({ kind: "connect", ref: p.ref, terminal: t });
                            }
                          }}
                        >
                          <title>Clique e depois escolha o furo da protoboard</title>
                        </circle>
                        {p.legs[t] && (
                          <path
                            d={`M ${tx} ${ty} C ${tx} ${by - 30}, ${hx} ${hy + 40}, ${hx} ${hy}`}
                            className="bb-lead-wire"
                            stroke={t === "n" || t === "-" || t === "0" ? "#222" : "#d32f2f"}
                          />
                        )}
                        <circle cx={hx} cy={hy} r={3} className="bb-clip" />
                        <text x={lx} y={ly} textAnchor="middle" className="bb-leg-label">
                          {views[p.ref]?.labels[t] ?? t}
                        </text>
                      </g>
                    );
                  })}
                </g>
              );
            }
            const legs = Object.fromEntries(Object.entries(p.legs).map(([pin, h]) => [pin, xy(h)]));
            return (
              <g
                key={p.ref}
                opacity={isGhosted ? 0.3 : 1}
                onMouseDown={(e) => {
                  if (readOnly) return;
                  e.stopPropagation();
                  setSel({ kind: "part", ref: p.ref });
                  if (tool.kind !== "select" || !hover) return;
                  const leg =
                    pkg.style === "axial"
                      ? Object.entries(p.legs).find(([, h]) => h === hover)?.[0]
                      : undefined;
                  setDrag({ ref: p.ref, start: hover, leg: leg ?? null });
                }}
              >
                <PackageArt
                  pkg={pkg}
                  legs={legs}
                  view={views[p.ref]}
                  refName={p.ref}
                  selected={sel?.kind === "part" && sel.ref === p.ref}
                  bad={badRefs.has(p.ref)}
                  showLabels={(sel?.kind === "part" && sel.ref === p.ref) || pkg.style === "inline"}
                />
              </g>
            );
          })}

          {!!schematic.bench_scope_channels && (
            <ScopeMiniature
              x={20 + (instruments.length % 3) * 320}
              y={size.boardH + 24 + Math.floor(instruments.length / 3) * 180}
              schematic={schematic}
              board={board}
              readOnly={readOnly}
              onConnect={(channel, terminal) => {
                setSel(null);
                setTool({ kind: "scope", channel, terminal });
              }}
            />
          )}
          {bb.wires.map((w) => {
            const [ax, ay] = xy(w.a);
            const [bx, by] = xy(w.b);
            const lift = Math.min(28, Math.hypot(bx - ax, by - ay) / 3 + 6);
            return (
              <path
                key={w.id}
                d={`M ${ax} ${ay} Q ${(ax + bx) / 2} ${(ay + by) / 2 - lift} ${bx} ${by}`}
                className={`bb-wire${sel?.kind === "wire" && sel.id === w.id ? " selected" : ""}`}
                stroke={WIRE_COLORS[w.color] ?? "#2e8b3c"}
                onMouseDown={(e) => {
                  if (readOnly) return;
                  e.stopPropagation();
                  setSel({ kind: "wire", id: w.id });
                }}
              />
            );
          })}
          {tool.kind === "wire" && tool.from && hover && (
            <line
              x1={xy(tool.from)[0]}
              y1={xy(tool.from)[1]}
              x2={xy(hover)[0]}
              y2={xy(hover)[1]}
              stroke={WIRE_COLORS[tool.color]}
              className="bb-wire ghost"
            />
          )}
          {ghost && pkgs[ghost.package] && (
            <g className={ghostOk ? "bb-ghost" : "bb-ghost invalid"}>
              <PackageArt
                pkg={pkgs[ghost.package]!}
                legs={Object.fromEntries(
                  Object.entries(ghost.legs).map(([pin, h]) => [pin, xy(h)]),
                )}
                view={views[ghost.ref]}
                refName={ghost.ref}
                showLabels
              />
            </g>
          )}
        </svg>
      </div>

      <aside className="panel bb-info" aria-label="Conferência e roteiro">
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {notes.map((n) => (
          <p key={n} className="note small">
            {n}
          </p>
        ))}
        {selPart && selView && (
          <div className="bb-selected">
            <h3>
              {selPart.ref} <span className="muted small">{selView.title}</span>
            </h3>
            {pkgs[selPart.package] && (
              <PackagePreview pkg={pkgs[selPart.package]!} view={selView} />
            )}
            <PinoutSource view={selView} />
            {!readOnly && (
              <fieldset className="terminal-connections">
                <legend>Terminais do dispositivo</legend>
                {(pkgs[selPart.package]?.pins ?? [])
                  .filter((pin) => pin in selView.pinmap)
                  .map((pin) => (
                    <label key={pin}>
                      {selView.labels[pin] ?? pin}
                      <select
                        aria-label={`Terminal ${selPart.ref}.${pin}`}
                        value={selPart.legs[pin] ?? ""}
                        onChange={(e) => {
                          const legs = { ...selPart.legs };
                          if (e.target.value) legs[pin] = e.target.value;
                          else delete legs[pin];
                          update({
                            ...bb,
                            parts: bb.parts.map((p) =>
                              p.ref === selPart.ref ? { ...p, legs } : p,
                            ),
                          });
                        }}
                      >
                        <option value="">Desconectado</option>
                        {holes.map((h) => (
                          <option
                            key={h}
                            value={h}
                            disabled={used.has(h) && used.get(h) !== selPart.ref}
                          >
                            {h}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
              </fieldset>
            )}

            {!readOnly && (
              <div className="row">
                <button className="secondary small" onClick={rotateSelected}>
                  Girar (R)
                </button>
                <button className="secondary small" onClick={removeSelected}>
                  Retirar
                </button>
              </div>
            )}
          </div>
        )}
        {sel?.kind === "wire" && !readOnly && (
          <div>
            <h3>Fio</h3>
            <button className="secondary small" onClick={removeSelected}>
              Apagar fio
            </button>
          </div>
        )}
        {!readOnly && !schematic.bench_scope_channels && (
          <fieldset className="scope-probe-connections">
            <legend>Ponteiras do osciloscópio</legend>
            <label>
              Nome do canal
              <input value={probeName} onChange={(e) => setProbeName(e.target.value)} />
            </label>
            <label>
              Ponteira +
              <select value={probePositive} onChange={(e) => setProbePositive(e.target.value)}>
                {holes.map((h) => (
                  <option key={h}>{h}</option>
                ))}
              </select>
            </label>
            <label>
              Referência −
              <select value={probeNegative} onChange={(e) => setProbeNegative(e.target.value)}>
                <option value="0">Terra do circuito (0)</option>
                {holes.map((h) => (
                  <option key={h}>{h}</option>
                ))}
              </select>
            </label>
            <button
              disabled={!resolved || !probeName.trim()}
              onClick={() => {
                try {
                  if (!resolved) return;
                  const positive = netAtHole(board, bb, resolved, probePositive);
                  const negative =
                    probeNegative === "0" ? "0" : netAtHole(board, bb, resolved, probeNegative);
                  const name = probeName.trim();
                  if (schematic.probes.some((p) => p.name?.toLowerCase() === name.toLowerCase()))
                    throw new Error("Já existe uma ponta com esse nome.");
                  onChange({
                    ...schematic,
                    probes: [
                      ...schematic.probes,
                      {
                        id: `scope${Date.now()}`,
                        name,
                        kind: "vdiff",
                        target: { net: positive },
                        reference: { net: negative },
                      },
                    ],
                  });
                  setError(null);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Conectar ponteira
            </button>
            <p className="small muted">
              O sinal segue os fios e barramentos da montagem atual. Simule novamente após mudar a
              ligação.
            </p>
          </fieldset>
        )}
        <h3>Conferência com o esquemático</h3>
        {!report ? (
          <p className="small muted">
            Monte as peças (ou use a montagem automática): a conferência roda a cada mudança.
          </p>
        ) : (
          <>
            <p className={report.ok ? "bb-ok" : "bb-fail"}>{report.summary}</p>
            <ul className="bb-issues">
              {report.issues.map((i, k) => (
                <li
                  key={k}
                  className={`issue-${i.kind} clickable`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setMark(i.holes)}
                  title="Mostrar na protoboard"
                >
                  <strong>{ISSUE_LABEL[i.kind]}:</strong> {i.message}
                </li>
              ))}
            </ul>
          </>
        )}
        {guide && (
          <>
            <h3>Roteiro de montagem</h3>
            {guide
              .filter((s) => !/^\d+\./.test(s.text))
              .map((s) => (
                <p key={s.text} className="small muted">
                  {s.text}
                </p>
              ))}
            <ol className="bb-guide">
              {guide
                .filter((s) => /^\d+\./.test(s.text))
                .map((s, k) => (
                  <li
                    key={k}
                    className="clickable"
                    role="button"
                    tabIndex={0}
                    onClick={() => setMark(s.holes)}
                  >
                    {s.text.replace(/^\d+\.\s*/, "")}
                  </li>
                ))}
            </ol>
          </>
        )}
      </aside>
    </div>
  );
}

function placeHint(pkg: PackageSpec | undefined): string {
  if (pkg?.style === "dip") return " (coluna f, abaixo da canaleta)";
  if (pkg?.style === "board")
    return ` (coluna ${pkg.cols?.[0] ?? "h"}; a outra barra de pinos fica na coluna ${pkg.cols?.[1] ?? "c"})`;
  return "";
}

/** Where the pinout came from: datasheet page, generic labels or missing. */
export function PinoutSource({ view }: { view: PartView }) {
  return (
    <div className="small">
      {view.origin === "datasheet" && view.source && (
        <p>
          Pinagem: {view.source.document}
          {view.source.page ? `, p. ${view.source.page}` : ""}
          {view.source.location ? ` (${view.source.location})` : ""}
          {view.source.url && (
            <>
              {" "}
              ·{" "}
              <a href={view.source.url} target="_blank" rel="noreferrer">
                datasheet
              </a>
            </>
          )}
          .{" "}
          <span className={`badge ${view.status === "revisado" ? "liberado" : "em_revisao"}`}>
            {view.status}
          </span>
        </p>
      )}
      {view.notes.map((n) => (
        <p key={n} className="muted">
          {n}
        </p>
      ))}
    </div>
  );
}
