import { useState } from "react";
import { AxisCalibration, AxisScale, ComponentDetail, imports, Rect, VectorPath } from "../../api";
import { CurvePlot } from "../../components/CurvePlot";
import { PAGE_ZOOM, PdfPage } from "../../components/PdfPage";
import { unitSymbol } from "../../format";
import { axisValue, parseFamily, pixelColour } from "./digitizer";

type Mode = "x1" | "x2" | "y1" | "y2" | "rect" | "manual" | "colour" | "idle";
type Pt = [number, number];

const STEP_LABEL: Record<Mode, string> = {
  x1: "Clique na 1ª marca do eixo X",
  x2: "Clique na 2ª marca do eixo X",
  y1: "Clique na 1ª marca do eixo Y",
  y2: "Clique na 2ª marca do eixo Y",
  rect: "Clique em dois cantos opostos da área do gráfico",
  manual: "Clique sobre a curva para marcar pontos",
  colour: "Clique sobre a curva para escolher a cor a seguir",
  idle: "",
};

function num(t: string): number {
  return Number(t.trim().replace(",", "."));
}

function rgb(c: [number, number, number] | null): string {
  return c ? `rgb(${c.map((v) => Math.round(v * 255)).join(",")})` : "transparent";
}

interface Props {
  detail: ComponentDetail;
  page: number;
  setPage: (p: number) => void;
  pages: number | null;
  onChange: (d: ComponentDetail) => void;
  author: string;
}

export function CurvesTab({ detail, page, setPage, pages, onChange, author }: Props) {
  const record = detail.record;
  const ds = record.datasheets.find((d) => d.sha256);
  const [mode, setMode] = useState<Mode>("idle");
  const [marks, setMarks] = useState<{ x1?: number; x2?: number; y1?: number; y2?: number }>({});
  const [vals, setVals] = useState({ x1: "", x2: "", y1: "", y2: "" });
  const [scales, setScales] = useState<{ x: AxisScale; y: AxisScale }>({ x: "lin", y: "log" });
  const [corner, setCorner] = useState<Pt | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const [points, setPoints] = useState<Pt[]>([]);
  const [method, setMethod] = useState<"manual" | "vetor" | "cor">("manual");
  const [paths, setPaths] = useState<VectorPath[]>([]);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [form, setForm] = useState({
    name: "",
    xq: "VF",
    xu: "V",
    yq: "IF",
    yu: "A",
    family: "Tj = 25 °C",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!ds?.sha256) return <p className="muted">Componente sem PDF local.</p>;
  const sha = ds.sha256;

  const calibration = (): { x: AxisCalibration; y: AxisCalibration } | null => {
    const { x1, x2, y1, y2 } = marks;
    if ([x1, x2, y1, y2].some((v) => v === undefined)) return null;
    const v = { x1: num(vals.x1), x2: num(vals.x2), y1: num(vals.y1), y2: num(vals.y2) };
    if (Object.values(v).some((n) => !Number.isFinite(n))) return null;
    return {
      x: { p1: x1!, v1: v.x1, p2: x2!, v2: v.x2, scale: scales.x },
      y: { p1: y1!, v1: v.y1, p2: y2!, v2: v.y2, scale: scales.y },
    };
  };
  const cal = calibration();

  const pick = async (x: number, y: number) => {
    setError(null);
    if (mode === "x1" || mode === "x2") {
      setMarks((m) => ({ ...m, [mode]: x }));
      setMode(mode === "x1" ? "x2" : "y1");
    } else if (mode === "y1" || mode === "y2") {
      setMarks((m) => ({ ...m, [mode]: y }));
      setMode(mode === "y1" ? "y2" : "rect");
    } else if (mode === "rect") {
      if (!corner) setCorner([x, y]);
      else {
        setRect({
          x0: Math.min(corner[0], x),
          y0: Math.min(corner[1], y),
          x1: Math.max(corner[0], x),
          y1: Math.max(corner[1], y),
        });
        setCorner(null);
        setMode("idle");
      }
    } else if (mode === "manual") {
      setMethod("manual");
      setPoints((p) => [...p, [x, y]]);
    } else if (mode === "colour" && rect && img) {
      const colour = pixelColour(img, x, y, PAGE_ZOOM);
      if (!colour) return;
      setBusy(true);
      try {
        setPoints(await imports.trace(sha, page, rect, colour));
        setMethod("cor");
        setMode("idle");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    }
  };

  const findPaths = async () => {
    if (!rect) return;
    setBusy(true);
    setError(null);
    try {
      const found = await imports.vectorPaths(sha, page, rect);
      setPaths(found);
      if (found.length === 0) setError("Nenhum traço vetorial na área: use a cor ou os cliques.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!cal) return setError("Calibre os dois eixos antes de salvar.");
    if (points.length < 2) return setError("Marque pelo menos dois pontos.");
    const { family, rest } = parseFamily(form.family);
    if (rest.length)
      return setError(`Condição não entendida: ${rest.join("; ")} (use NOME = valor unidade)`);
    setBusy(true);
    setError(null);
    try {
      const d = await imports.addCurve(record.id, {
        name: form.name || `${form.yq}×${form.xq}`,
        x: { quantity: form.xq, unit: form.xu, scale: scales.x },
        y: { quantity: form.yq, unit: form.yu, scale: scales.y },
        family,
        calibration: cal,
        positions: points,
        datasheet_id: ds.id,
        page,
        bbox: rect ? [rect.x0, rect.y0, rect.x1, rect.y1] : null,
        method,
        digitized_by: author || "usuário",
      });
      onChange(d);
      setPoints([]);
      setPaths([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Remover esta curva?")) return;
    try {
      onChange(await imports.deleteCurve(record.id, id));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const preview = cal
    ? points.map((p) => [axisValue(cal.x, p[0]), axisValue(cal.y, p[1])] as Pt)
    : [];
  const overlay = (
    <>
      {marks.x1 !== undefined && (
        <line className="cal x" x1={marks.x1} x2={marks.x1} y1={0} y2={2000} />
      )}
      {marks.x2 !== undefined && (
        <line className="cal x" x1={marks.x2} x2={marks.x2} y1={0} y2={2000} />
      )}
      {marks.y1 !== undefined && (
        <line className="cal y" y1={marks.y1} y2={marks.y1} x1={0} x2={2000} />
      )}
      {marks.y2 !== undefined && (
        <line className="cal y" y1={marks.y2} y2={marks.y2} x1={0} x2={2000} />
      )}
      {rect && (
        <rect
          className="plot-area"
          x={rect.x0}
          y={rect.y0}
          width={rect.x1 - rect.x0}
          height={rect.y1 - rect.y0}
        />
      )}
      {corner && <circle className="corner" cx={corner[0]} cy={corner[1]} r={2} />}
      {paths.map((p) => (
        <polyline
          key={p.index}
          className="vpath"
          style={{ stroke: rgb(p.colour) }}
          points={p.points.map((q) => q.join(",")).join(" ")}
        />
      ))}
      {points.map((p, i) => (
        <circle key={i} className="dpoint" cx={p[0]} cy={p[1]} r={1.6} />
      ))}
    </>
  );

  return (
    <div className="curves-tab">
      <div className="digitizer">
        <div className="controls">
          <h3>Digitalizar curva</h3>
          <p className="small muted">
            1) Calibre os eixos clicando em duas marcas de cada eixo e digitando seus valores. 2)
            Marque a área do gráfico. 3) Pegue a curva: traço vetorial do PDF (exato), cor da curva
            (páginas digitalizadas) ou cliques.
          </p>
          <div className="row">
            <button className="secondary" onClick={() => setMode("x1")}>
              Calibrar eixos
            </button>
            <label>
              X
              <select
                value={scales.x}
                onChange={(e) => setScales({ ...scales, x: e.target.value as AxisScale })}
              >
                <option value="lin">linear</option>
                <option value="log">log</option>
              </select>
            </label>
            <label>
              Y
              <select
                value={scales.y}
                onChange={(e) => setScales({ ...scales, y: e.target.value as AxisScale })}
              >
                <option value="lin">linear</option>
                <option value="log">log</option>
              </select>
            </label>
          </div>
          <div className="cal-values">
            {(["x1", "x2", "y1", "y2"] as const).map((k) => (
              <label key={k} className={marks[k] === undefined ? "muted" : undefined}>
                {k.toUpperCase()}
                <input
                  aria-label={`valor ${k}`}
                  value={vals[k]}
                  onChange={(e) => setVals({ ...vals, [k]: e.target.value })}
                />
              </label>
            ))}
          </div>
          <div className="row">
            <button className="secondary" onClick={() => setMode("rect")}>
              Área do gráfico
            </button>
            <button className="secondary" disabled={!rect || busy} onClick={findPaths}>
              Traços vetoriais
            </button>
            <button className="secondary" disabled={!rect} onClick={() => setMode("colour")}>
              Seguir cor
            </button>
            <button className="secondary" onClick={() => setMode("manual")}>
              Cliques
            </button>
            <button className="secondary" disabled={!points.length} onClick={() => setPoints([])}>
              Limpar pontos
            </button>
          </div>
          {paths.length > 0 && (
            <div className="row small">
              Escolha o traço:
              {paths.map((p) => (
                <button
                  key={p.index}
                  className="secondary swatch"
                  onClick={() => {
                    setPoints(p.points);
                    setMethod("vetor");
                    setPaths([]);
                  }}
                >
                  <span style={{ background: rgb(p.colour) }} /> {p.points.length} pts
                </button>
              ))}
            </div>
          )}
          {mode !== "idle" && <p className="step">{STEP_LABEL[mode]}</p>}
          <div className="cal-values">
            <label>
              Nome
              <input
                value={form.name}
                placeholder="IF×VF a 25 °C"
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label>
              Grandeza X
              <input value={form.xq} onChange={(e) => setForm({ ...form, xq: e.target.value })} />
            </label>
            <label>
              Unidade X
              <input value={form.xu} onChange={(e) => setForm({ ...form, xu: e.target.value })} />
            </label>
            <label>
              Grandeza Y
              <input value={form.yq} onChange={(e) => setForm({ ...form, yq: e.target.value })} />
            </label>
            <label>
              Unidade Y
              <input value={form.yu} onChange={(e) => setForm({ ...form, yu: e.target.value })} />
            </label>
            <label className="wide">
              Condições da curva
              <input
                value={form.family}
                onChange={(e) => setForm({ ...form, family: e.target.value })}
              />
            </label>
          </div>
          <div className="row">
            <button disabled={!cal || points.length < 2 || busy} onClick={save}>
              Salvar curva ({points.length} pontos)
            </button>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {preview.length > 1 && (
            <CurvePlot
              series={[{ points: preview, label: "pontos" }]}
              xScale={scales.x}
              yScale={scales.y}
              xLabel={`${form.xq} (${unitSymbol(form.xu)})`}
              yLabel={`${form.yq} (${unitSymbol(form.yu)})`}
            />
          )}
        </div>
        <div className="figure">
          <div className="row">
            <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              ←
            </button>
            <span>
              Página {page}
              {pages ? ` de ${pages}` : ""}
            </span>
            <button
              className="secondary"
              disabled={pages != null && page >= pages}
              onClick={() => setPage(page + 1)}
            >
              →
            </button>
          </div>
          <PdfPage
            sha={sha}
            page={page}
            onPick={mode === "idle" ? undefined : pick}
            overlay={overlay}
            onImage={setImg}
          />
        </div>
      </div>
      <h3>Curvas do componente</h3>
      {record.curves.length === 0 && <p className="small muted">Nenhuma curva digitalizada.</p>}
      <div className="curve-list">
        {record.curves.map((c) => (
          <figure key={c.id} className="curve-card">
            <figcaption>
              <strong>{c.name}</strong> · pág. {c.source.page} · {c.method} · {c.points.length} pts
              ·{" "}
              {Object.entries(c.family)
                .map(([k, q]) => `${k} = ${q.value} ${unitSymbol(q.unit)}`)
                .join("; ")}
              <button className="secondary small" onClick={() => remove(c.id)}>
                remover
              </button>
            </figcaption>
            <CurvePlot
              series={[{ points: c.points, label: c.name }]}
              xScale={c.x.scale}
              yScale={c.y.scale}
              xLabel={`${c.x.quantity} (${unitSymbol(c.x.unit)})`}
              yLabel={`${c.y.quantity} (${unitSymbol(c.y.unit)})`}
              width={360}
              height={220}
            />
          </figure>
        ))}
      </div>
    </div>
  );
}
