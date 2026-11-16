import { useEffect, useState } from "react";
import { BomOut, design, DesignIn } from "../../api";

const STATUS: Record<string, string> = { ok: "ok", atencao: "atenção", violado: "violado" };

function money(v: number | null): string {
  return v == null
    ? ""
    : v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Props {
  moduleId: string;
  body: DesignIn;
  costs: Record<string, number>;
  onCosts: (c: Record<string, number>) => void;
  /** Changes whenever the design is recomputed. */
  version: unknown;
}

/** Bill of materials with the governing stress × rating, Tj, datasheet and editable cost. */
export function BomTab({ moduleId, body, costs, onCosts, version }: Props) {
  const [bom, setBom] = useState<BomOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    design
      .bomLines(moduleId, { ...body, costs })
      .then((b) => alive && (setBom(b), setError(null)))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
    // body/version cover the design inputs; costs are applied locally below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleId, version, costs]);

  if (error) return <div className="error">{error}</div>;
  if (!bom) return <p className="muted">Carregando…</p>;

  const setCost = (part: string, text: string) => {
    // "1.234,50" (pt-BR) or "2.5": a dot is a thousands separator only next to a comma
    const clean = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
    const v = Number(clean);
    const next = { ...costs };
    if (text.trim() === "" || !Number.isFinite(v)) delete next[part];
    else next[part] = v;
    onCosts(next);
  };

  return (
    <div className="bom-tab">
      <p className="small muted">
        Cada linha mostra a verificação com a menor margem daquela posição. O custo unitário é
        opcional e entra na exportação (CSV, XLSX, PDF) e no relatório; ele fica salvo no projeto.
      </p>
      <table className="params bom">
        <thead>
          <tr>
            <th>Designador</th>
            <th>Qtd</th>
            <th>Descrição</th>
            <th>Código</th>
            <th>Valor</th>
            <th>Esforço × nominal</th>
            <th>Margem</th>
            <th>Tj</th>
            <th>Custo unit.</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {bom.lines.map((l, i) => (
            <tr key={i}>
              <td>{l.designator}</td>
              <td>{l.quantity}</td>
              <td>
                {l.description}
                {l.note && <div className="small muted">{l.note}</div>}
              </td>
              <td>
                {l.datasheet ? (
                  <a href={l.datasheet} target="_blank" rel="noreferrer">
                    {l.part_number}
                  </a>
                ) : (
                  l.part_number
                )}
                {l.manufacturer && <div className="small muted">{l.manufacturer}</div>}
              </td>
              <td>{l.value}</td>
              <td className="small">
                {l.parameter && `${l.parameter}: ${l.stress} / ${l.rating}`}
              </td>
              <td className={l.margin_status}>
                {l.margin_pct != null &&
                  `${l.margin_pct.toFixed(0)} % (${STATUS[l.margin_status] ?? ""})`}
              </td>
              <td>{l.tj}</td>
              <td>
                <input
                  className="num"
                  aria-label={`Custo unitário de ${l.designator}`}
                  defaultValue={costs[l.cost_key] != null ? money(costs[l.cost_key]!) : ""}
                  onBlur={(e) => setCost(l.cost_key, e.target.value)}
                />
              </td>
              <td>{money(l.total_cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {bom.total_cost != null && (
        <p>
          Custo total estimado: <strong>{money(bom.total_cost)}</strong>
        </p>
      )}
    </div>
  );
}
