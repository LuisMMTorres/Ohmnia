import { CataloguePinout } from "../breadboard/CataloguePinout";
import { useEffect, useMemo, useState } from "react";
import { catalog, ComponentDetail, Parameter, ParamStatus } from "../api";
import { formatRaw, formatEng, unitSymbol } from "../format";
import { PdfPage } from "../components/PdfPage";
import { REVIEW_LABEL } from "./CatalogPage";
import { CurvesTab } from "./review/CurvesTab";
import { ModelsTab } from "./review/ModelsTab";

type Tab = "params" | "curves" | "models";
const TAB_LABEL: Record<Tab, string> = {
  params: "Parâmetros",
  curves: "Curvas",
  models: "Modelos SPICE",
};

const STATUS_LABEL: Record<ParamStatus, string> = {
  a_verificar: "A verificar",
  extraido: "Extraído",
  revisado: "Conferido",
};

function conditions(p: Parameter): string {
  return Object.entries(p.conditions)
    .map(([k, q]) => {
      const sym = unitSymbol(q.unit);
      const value =
        sym === "°C" || sym === ""
          ? `${q.value}`.replace(".", ",") + ` ${sym}`
          : formatEng(q.value, q.unit, 4);
      return `${k} = ${value}`.trim();
    })
    .join("; ");
}

function readReviewer(): string {
  try {
    return window.localStorage.getItem("reviewer") ?? "";
  } catch {
    return "";
  }
}

export function ComponentReview({ id, onBack }: { id: string; onBack: () => void }) {
  const [detail, setDetail] = useState<ComponentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState<number | null>(null);
  const [reviewer, setReviewer] = useState(readReviewer);
  const [tab, setTab] = useState<Tab>("params");

  useEffect(() => {
    catalog
      .get(id)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  const record = detail?.record;
  const datasheet = useMemo(() => {
    if (!record || !activeKey) return record?.datasheets[0];
    const src = record.parameters[activeKey]?.source;
    return record.datasheets.find((d) => d.id === src?.datasheet_id) ?? record.datasheets[0];
  }, [record, activeKey]);

  useEffect(() => {
    if (!datasheet?.sha256) return;
    catalog
      .datasheet(datasheet.sha256)
      .then((d) => setPages(d.pages))
      .catch((e: Error) => setError(e.message));
  }, [datasheet?.sha256]);

  const keys = useMemo(() => {
    if (!detail) return [];
    const required = new Set(detail.schema_.required);
    return Object.keys(detail.record.parameters).sort((a, b) => {
      const ra = required.has(a) ? 0 : 1;
      const rb = required.has(b) ? 0 : 1;
      return ra - rb || a.localeCompare(b);
    });
  }, [detail]);

  if (error && !detail) return <div className="error">{error}</div>;
  if (!detail || !record) return <p className="muted">Carregando…</p>;

  const select = (key: string) => {
    setActiveKey(key);
    const p = record.parameters[key]?.source?.page;
    if (p) setPage(p);
  };

  const review = async (key: string, status: ParamStatus) => {
    try {
      setDetail(await catalog.review(record.id, key, status));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const release = async () => {
    try {
      window.localStorage.setItem("reviewer", reviewer);
    } catch {
      /* storage unavailable */
    }
    try {
      setDetail(await catalog.release(record.id, reviewer));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const active = activeKey ? record.parameters[activeKey] : null;

  const tabs = (
    <nav className="tabs" aria-label="Partes do componente">
      {(Object.keys(TAB_LABEL) as Tab[]).map((k) => (
        <button
          key={k}
          className={k === tab ? "tab active" : "tab"}
          aria-current={k === tab ? "page" : undefined}
          onClick={() => setTab(k)}
        >
          {TAB_LABEL[k]}
          {k === "curves" && record.curves.length > 0 && ` (${record.curves.length})`}
          {k === "models" && record.spice_models.length > 0 && ` (${record.spice_models.length})`}
        </button>
      ))}
    </nav>
  );

  if (tab !== "params") {
    return (
      <main className="single">
        <section className="panel">
          <button className="secondary" onClick={onBack}>
            ← Catálogo
          </button>
          <h2>
            {record.part_number}{" "}
            <span className={`badge ${record.review.status}`}>
              {REVIEW_LABEL[record.review.status] ?? record.review.status}
            </span>
          </h2>
          {tabs}
          {tab === "curves" ? (
            <CurvesTab
              detail={detail}
              page={page}
              setPage={setPage}
              pages={pages}
              onChange={setDetail}
              author={reviewer}
            />
          ) : (
            <ModelsTab detail={detail} onChange={setDetail} />
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="review">
      <section className="panel">
        <button className="secondary" onClick={onBack}>
          ← Catálogo
        </button>
        <h2>
          {record.part_number}{" "}
          <span className={`badge ${record.review.status}`}>
            {REVIEW_LABEL[record.review.status] ?? record.review.status}
          </span>
        </h2>
        {tabs}
        <p className="muted">
          {record.manufacturer} · {detail.schema_.description} · {record.package}
          {record.family ? ` · família ${record.family}` : ""}
        </p>
        <CataloguePinout record={record} />
        <p className="small">
          {record.datasheets.map((d) => (
            <span key={d.id}>
              Datasheet {d.document_number} ({d.revision}) ·{" "}
              {d.sha256 && (
                <a href={catalog.pdfUrl(d.sha256)} target="_blank" rel="noreferrer">
                  PDF local
                </a>
              )}
              {d.url && (
                <>
                  {" · "}
                  <a href={d.url} target="_blank" rel="noreferrer">
                    site do fabricante
                  </a>
                </>
              )}
            </span>
          ))}
        </p>
        <p className="small muted">
          Clique num parâmetro para abrir a página citada. Marque "Confere" depois de comparar o
          valor e as condições de teste com o datasheet.
        </p>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <table className="params clickable">
          <thead>
            <tr>
              <th>Parâmetro</th>
              <th>Mín.</th>
              <th>Típ.</th>
              <th>Máx.</th>
              <th>Condições</th>
              <th>Pág.</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const p = record.parameters[key]!;
              const spec = detail.schema_.parameters[p.symbol];
              const required = detail.schema_.required.includes(key);
              return (
                <tr
                  key={key}
                  className={key === activeKey ? "active" : undefined}
                  onClick={() => select(key)}
                >
                  <td>
                    <strong>{key}</strong>
                    {required && (
                      <span className="req" title="Obrigatório para liberar">
                        *
                      </span>
                    )}
                    <div className="muted small">{spec?.description}</div>
                    {p.note && <div className="small note">{p.note}</div>}
                  </td>
                  <td>{formatRaw(p.min, p.unit)}</td>
                  <td>{formatRaw(p.typ, p.unit)}</td>
                  <td>{formatRaw(p.max, p.unit)}</td>
                  <td className="small">{conditions(p)}</td>
                  <td>{p.source?.page ?? "—"}</td>
                  <td>
                    <span className={`badge ${p.status}`}>{STATUS_LABEL[p.status]}</span>
                  </td>
                  <td className="actions" onClick={(e) => e.stopPropagation()}>
                    {p.status !== "revisado" ? (
                      <button onClick={() => review(key, "revisado")}>Confere</button>
                    ) : (
                      <button className="secondary" onClick={() => review(key, "a_verificar")}>
                        Desfazer
                      </button>
                    )}
                    {p.status === "extraido" && (
                      <button className="secondary" onClick={() => review(key, "a_verificar")}>
                        Não confere
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {Object.keys(record.attributes ?? {}).length > 0 && (
          <table className="params attributes">
            <thead>
              <tr>
                <th>Especificação</th>
                <th>Valor no documento</th>
                <th>Pág.</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(record.attributes ?? {}).map(([name, a]) => (
                <tr key={name}>
                  <td>
                    <strong>{name.replace(/_/g, " ")}</strong>
                    <div className="muted small">{detail.schema_.attributes?.[name]}</div>
                  </td>
                  <td>{a.value}</td>
                  <td>{a.source?.page ?? "—"}</td>
                  <td>
                    <span className={`badge ${a.status}`}>{STATUS_LABEL[a.status]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="release">
          {detail.release_blockers.length > 0 ? (
            <details>
              <summary>
                {detail.release_blockers.length} pendência(s) para liberar este componente
              </summary>
              <ul className="small">
                {detail.release_blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </details>
          ) : (
            <p className="small">
              Todos os parâmetros obrigatórios foram conferidos.
              {record.review.reviewed_by && ` Liberado por ${record.review.reviewed_by}.`}
            </p>
          )}
          <div className="row">
            <input
              aria-label="Nome de quem revisou"
              placeholder="Seu nome"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
            />
            <button
              onClick={release}
              disabled={detail.release_blockers.length > 0 || !reviewer.trim()}
            >
              Liberar para seleção automática
            </button>
            <a className="small" href={catalog.yamlUrl(record.id)} download>
              Baixar YAML revisado
            </a>
          </div>
        </div>
      </section>
      <section className="panel sheet">
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
        {active?.source?.location && (
          <p className="small">
            <strong>{activeKey}</strong>: {active.source.location}
          </p>
        )}
        {active?.source?.excerpt && <p className="small muted">“{active.source.excerpt}”</p>}
        {datasheet?.sha256 && (
          <PdfPage
            sha={datasheet.sha256}
            page={page}
            highlights={
              active?.source?.bbox && active.source.page === page
                ? [{ bbox: active.source.bbox, label: activeKey ?? undefined }]
                : []
            }
          />
        )}
      </section>
    </main>
  );
}
