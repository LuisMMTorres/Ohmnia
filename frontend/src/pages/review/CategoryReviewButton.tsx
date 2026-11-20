import { useState } from "react";
import { catalog, CategoryReview } from "../../api";
import { REVIEW_LABEL } from "../CatalogPage";

function readReviewer(): string {
  try {
    return window.localStorage.getItem("reviewer") ?? "";
  } catch {
    return "";
  }
}

type Review = Omit<CategoryReview, "category" | "already_released"> & {
  already_released?: number;
};

/**
 * Button + dialog: review every pending component of one category at once, or (with `ids`)
 * only the given parts, e.g. the ones of the circuit under design.
 */
export function CategoryReviewButton({
  category = "",
  ids,
  label,
  buttonText = "Revisar categoria",
  onDone,
}: {
  category?: string;
  ids?: string[];
  label: string;
  buttonText?: string;
  onDone: () => void;
}) {
  const run = (who: string, dryRun: boolean): Promise<Review> =>
    ids ? catalog.reviewParts(ids, who, dryRun) : catalog.reviewCategory(category, who, dryRun);
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Review | null>(null);
  const [result, setResult] = useState<Review | null>(null);
  const [reviewer, setReviewer] = useState(readReviewer);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setOpen(true);
    setPreview(null);
    setResult(null);
    setChecked(false);
    setError(null);
    try {
      setPreview(await run("", true));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      window.localStorage.setItem("reviewer", reviewer);
    } catch {
      /* storage unavailable */
    }
    try {
      setResult(await run(reviewer.trim(), false));
      setError(null);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const shown = result ?? preview;
  const marked = shown?.items.reduce((n, i) => n + i.marked, 0) ?? 0;
  const unsourced = shown?.items.reduce((n, i) => n + i.unsourced.length, 0) ?? 0;

  return (
    <>
      <button className="secondary" onClick={start} title={`Revisar todos: ${label}`}>
        {buttonText}
      </button>
      {open && (
        <div className="modal-backdrop" onClick={() => !busy && setOpen(false)}>
          <div
            className="modal category-review"
            role="dialog"
            aria-modal="true"
            aria-label={`Revisar a categoria ${label}`}
            onClick={(e) => e.stopPropagation()}
          >
            <h3>Revisar todos: {label}</h3>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            {!shown && !error && <p className="muted">Carregando…</p>}
            {shown && (
              <>
                {result ? (
                  <p>
                    <strong>{result.released}</strong> componente(s) liberado(s) para seleção
                    automática; <strong>{result.pending}</strong> continua(m) com pendência.
                  </p>
                ) : shown.items.length === 0 ? (
                  <p>
                    Nada a revisar:{" "}
                    {ids ? "os componentes deste circuito" : "os componentes desta categoria"} já
                    estão liberados.
                  </p>
                ) : (
                  <>
                    <p>
                      {shown.items.length} componente(s) pendente(s)
                      {(shown.already_released ?? 0) > 0 &&
                        ` (${shown.already_released} já liberados)`}
                      . Serão marcados como conferidos <strong>{marked}</strong> parâmetros e
                      atributos que citam a página do datasheet; <strong>{shown.released}</strong>{" "}
                      componente(s) ficam liberados e <strong>{shown.pending}</strong> continuam com
                      pendência.
                    </p>
                    {unsourced > 0 && (
                      <p className="small muted">
                        {unsourced} valor(es) sem página ficam como estão: um valor conferido
                        precisa apontar a página do documento.
                      </p>
                    )}
                  </>
                )}
                {shown.items.length > 0 && (
                  <div className="category-review-list">
                    <table>
                      <thead>
                        <tr>
                          <th>Componente</th>
                          <th>Fabricante</th>
                          <th>Conferidos</th>
                          <th>Resultado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.items.map((i) => (
                          <tr key={i.id}>
                            <td>
                              <strong>{i.part_number}</strong>
                            </td>
                            <td>{i.manufacturer}</td>
                            <td>
                              {i.marked}
                              {i.unsourced.length > 0 && (
                                <div className="muted small">
                                  sem página: {i.unsourced.join(", ")}
                                </div>
                              )}
                            </td>
                            <td>
                              <span className={`badge ${i.after}`}>
                                {REVIEW_LABEL[i.after] ?? i.after}
                              </span>
                              {i.blockers.length > 0 && (
                                <details className="small">
                                  <summary>{i.blockers.length} pendência(s)</summary>
                                  <ul>
                                    {i.blockers.map((b) => (
                                      <li key={b}>{b}</li>
                                    ))}
                                  </ul>
                                </details>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {!result && shown.items.length > 0 && (
                  <>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => setChecked(e.target.checked)}
                      />
                      Conferi os valores destes componentes com os datasheets.
                    </label>
                    <div className="row">
                      <input
                        aria-label="Nome de quem revisou"
                        placeholder="Seu nome"
                        value={reviewer}
                        onChange={(e) => setReviewer(e.target.value)}
                      />
                      <button onClick={confirm} disabled={busy || !checked || !reviewer.trim()}>
                        Confirmar revisão de {shown.items.length} componente(s)
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
            <div className="row end">
              <button className="secondary" onClick={() => setOpen(false)} disabled={busy}>
                {result ? "Fechar" : "Cancelar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
