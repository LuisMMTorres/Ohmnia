import { useEffect, useState } from "react";
import { catalog, type ComponentDetail } from "../api";
import { formatRaw } from "../format";
import type { Component, SymbolDef } from "../schematic/types";

/** Circuit parameters that only wire the bench or label the part, not characteristics. */
const INTERNAL = new Set(["bench_id", "bench_channel", "part_label", "color", "state"]);

const STATUS_LABEL: Record<string, string> = {
  a_verificar: "a verificar",
  extraido: "extraído",
  revisado: "conferido",
};

const detailCache = new Map<string, Promise<ComponentDetail>>();

function loadDetail(id: string): Promise<ComponentDetail> {
  let p = detailCache.get(id);
  if (!p) {
    p = catalog.get(id);
    p.catch(() => detailCache.delete(id));
    detailCache.set(id, p);
  }
  return p;
}

/** The circuit values of a part as "label: value unit" rows, in the symbol's order. */
export function circuitRows(
  comp: Component,
  def: SymbolDef | undefined,
): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  const seen = new Set<string>();
  for (const d of def?.params ?? []) {
    seen.add(d.name);
    if (INTERNAL.has(d.name) || d.type === "code") continue;
    const v = (comp.params[d.name] ?? "").trim() || d.default;
    if (!v) continue;
    rows.push({ label: d.label || d.name, value: d.unit ? `${v} ${d.unit}` : v });
  }
  for (const [k, v] of Object.entries(comp.params)) {
    if (seen.has(k) || INTERNAL.has(k) || !v.trim()) continue;
    rows.push({ label: k, value: v });
  }
  return rows;
}

/** Characteristics of the part picked on the board: circuit values and, for a catalogue
 * part, its datasheet parameters (with their review status, never filled in here). */
export function PartCharacteristics({
  comp,
  def,
}: {
  comp: Component | undefined;
  def: SymbolDef | undefined;
}) {
  const partId = comp?.part_id ?? null;
  const [detail, setDetail] = useState<ComponentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    if (!partId) return;
    let alive = true;
    loadDetail(partId).then(
      (d) => alive && setDetail(d),
      (e: Error) => alive && setError(e.message),
    );
    return () => {
      alive = false;
    };
  }, [partId]);

  if (!comp) return null;
  const rows = circuitRows(comp, def);
  const rec = detail?.record;
  const specs = detail?.schema_.parameters ?? {};
  const params = rec ? Object.entries(rec.parameters) : [];
  const sheet = rec?.datasheets.find((d) => d.url);

  return (
    <div className="bb-characteristics">
      <h4>Características</h4>
      {def && <p className="small muted">{def.label}</p>}
      {rows.length > 0 ? (
        <table className="bb-char-table">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                <td>{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        !partId && <p className="small muted">Sem parâmetros de circuito (valores padrão).</p>
      )}
      {!partId && <p className="small muted">Modelo genérico (didático), sem peça do catálogo.</p>}
      {partId && !rec && !error && <p className="small muted">Lendo o datasheet…</p>}
      {error && <p className="small status-atencao">Não foi possível ler a peça: {error}</p>}
      {rec && (
        <>
          <p className="small">
            <strong>{rec.part_number}</strong> · {rec.manufacturer}
            {rec.package ? ` · ${rec.package}` : ""}
            <br />
            <span className={rec.review.status === "liberado" ? "muted" : "status-atencao"}>
              Revisão: {rec.review.status.replace(/_/g, " ")}
            </span>
          </p>
          {params.length > 0 && (
            <table className="bb-char-table">
              <thead>
                <tr>
                  <th>Parâmetro</th>
                  <th>mín.</th>
                  <th>típ.</th>
                  <th>máx.</th>
                </tr>
              </thead>
              <tbody>
                {params.map(([key, p]) => (
                  <tr key={key} title={specs[key]?.description ?? key}>
                    <th scope="row">
                      {p.symbol || key}
                      {p.status !== "revisado" && (
                        <span className="small muted"> ({STATUS_LABEL[p.status] ?? p.status})</span>
                      )}
                    </th>
                    <td>{p.min == null ? "—" : formatRaw(p.min, p.unit)}</td>
                    <td>{p.typ == null ? "—" : formatRaw(p.typ, p.unit)}</td>
                    <td>{p.max == null ? "—" : formatRaw(p.max, p.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {sheet?.url && (
            <p className="small">
              <a href={sheet.url} target="_blank" rel="noreferrer">
                Datasheet{sheet.revision ? ` (rev. ${sheet.revision})` : ""}
              </a>
            </p>
          )}
        </>
      )}
    </div>
  );
}
