import { useEffect, useMemo, useState } from "react";
import { ImportJob, imports, QueueItem } from "../../api";
import { CATEGORY_LABEL } from "../CatalogPage";

type LinkStatus = NonNullable<QueueItem["link"]>["situacao"];
const LINK_LABEL: Record<LinkStatus, string> = {
  ok: "link ok",
  bloqueado: "baixar pelo navegador",
  quebrado: "link quebrado",
  indisponivel: "sem resposta",
};
const LINK_CLASS: Record<LinkStatus, string> = {
  ok: "liberado",
  bloqueado: "em_revisao",
  quebrado: "rejeitado",
  indisponivel: "rejeitado",
};

function groupName(g: string): string {
  return g.replace(/^\d+_/, "").replace(/_/g, " ");
}

interface Props {
  useLlm: boolean;
  onJob: (job: ImportJob) => void;
}

/** Datasheets listed for import: local PDF and link status, catalogue overlap, one-click import. */
export function QueuePanel({ useLlm, onJob }: Props) {
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [filter, setFilter] = useState<"todos" | "prontos" | "pendentes">("todos");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    imports
      .queue()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  const groups = useMemo(() => {
    const out = new Map<string, QueueItem[]>();
    const needle = text.trim().toUpperCase();
    for (const it of items ?? []) {
      if (filter === "prontos" && !it.importable) continue;
      if (filter === "pendentes" && it.importable) continue;
      if (needle && !`${it.part_number} ${it.fabricante}`.toUpperCase().includes(needle)) continue;
      out.set(it.grupo, [...(out.get(it.grupo) ?? []), it]);
    }
    return [...out.entries()];
  }, [items, filter, text]);

  if (error && !items) return <div className="error">{error}</div>;
  if (!items) return <p className="muted">Carregando a fila…</p>;
  if (items.length === 0) return null;

  const linkCount = (s: LinkStatus) => items.filter((i) => i.link?.situacao === s).length;
  const locals = items.filter((i) => i.local);
  const localOk = locals.filter((i) => i.local!.situacao === "ok").length;
  const ready = items.filter((i) => i.importable).length;

  const run = async (it: QueueItem) => {
    setBusy(it.index);
    setError(null);
    try {
      onJob(await imports.importQueued(it.index, useLlm));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="queue">
      <h3>Fila de datasheets ({items.length})</h3>
      <p className="small muted">
        <strong>{ready} prontos para importar.</strong> PDFs no computador: {localOk} válidos de{" "}
        {locals.length} (os inválidos são páginas HTML salvas no lugar do PDF). Links:{" "}
        {linkCount("ok")} abrem o PDF, {linkCount("bloqueado")} só pelo navegador,{" "}
        {linkCount("quebrado") + linkCount("indisponivel")} quebrados. Para os que faltam, baixe
        pelo navegador e envie com "Escolher PDF…". Importar usa o PDF do computador (ou baixa só
        aquele link) e abre a revisão dos valores.
      </p>
      <div className="row small">
        {(["todos", "prontos", "pendentes"] as const).map((f) => (
          <label key={f}>
            <input
              type="radio"
              name="queue-filter"
              checked={filter === f}
              onChange={() => setFilter(f)}
            />{" "}
            {f === "todos"
              ? "todos"
              : f === "prontos"
                ? "prontos para importar"
                : "precisam de atenção"}
          </label>
        ))}
        <input
          aria-label="Buscar na fila"
          placeholder="buscar part number ou fabricante"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {groups.map(([group, list]) => (
        <details key={group} open={filter !== "todos" || text.trim() !== ""}>
          <summary>
            {groupName(group)} ({list.length})
          </summary>
          <table className="params">
            <tbody>
              {list.map((it) => (
                <tr key={it.index}>
                  <td>
                    <strong>{it.part_number}</strong>
                    {it.tipo === "série" && <span className="muted small"> (série)</span>}
                    <div className="small muted">{it.fabricante}</div>
                  </td>
                  <td className="small">
                    {it.categoria ? (
                      (CATEGORY_LABEL[it.categoria] ?? it.categoria)
                    ) : (
                      <span className="muted">{it.sem_categoria}</span>
                    )}
                    {it.no_catalogo.length > 0 && (
                      <div className="note">já no catálogo: {it.no_catalogo.join("; ")}</div>
                    )}
                  </td>
                  <td className="small">
                    {it.local && (
                      <div>
                        <span
                          className={`badge ${it.local.situacao === "ok" ? "liberado" : "rejeitado"}`}
                          title={it.local.caminho}
                        >
                          {it.local.situacao === "ok" ? "PDF no computador" : "arquivo inválido"}
                        </span>
                        {it.local.nota !== "PDF local" && (
                          <div className="muted">{it.local.nota}</div>
                        )}
                      </div>
                    )}
                    {it.link && (
                      <div>
                        <span
                          className={`badge ${LINK_CLASS[it.link.situacao]}`}
                          title={it.link.nota}
                        >
                          {LINK_LABEL[it.link.situacao]}
                        </span>
                        {it.link.situacao !== "ok" && <div className="muted">{it.link.nota}</div>}
                      </div>
                    )}
                  </td>
                  <td className="actions">
                    {it.url && (
                      <a className="small" href={it.url} target="_blank" rel="noreferrer">
                        abrir link
                      </a>
                    )}
                    {it.importable && (
                      <button disabled={busy !== null} onClick={() => void run(it)}>
                        {busy === it.index ? "abrindo…" : "Importar"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </section>
  );
}
