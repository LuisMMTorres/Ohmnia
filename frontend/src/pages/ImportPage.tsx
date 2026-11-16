import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Candidate,
  Capabilities,
  catalog,
  ImportJob,
  ImportMeta,
  imports,
  ImportSummary,
} from "../api";
import { PdfPage } from "../components/PdfPage";
import { unitSymbol } from "../format";
import { CATEGORY_LABEL } from "./CatalogPage";
import { ComponentReview } from "./ComponentReview";
import { QueuePanel } from "./import/QueuePanel";

const METHOD_LABEL: Record<Candidate["method"], string> = {
  regras: "regras",
  llm: "modelo de linguagem",
  manual: "manual",
};
const STATUS_LABEL: Record<ImportJob["status"], string> = {
  extraido: "Em edição",
  importado: "Importado",
  descartado: "Descartado",
};

function num(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

function show(v: number | null): string {
  return v == null ? "" : String(v).replace(".", ",");
}

function readName(): string {
  try {
    return window.localStorage.getItem("reviewer") ?? "";
  } catch {
    return "";
  }
}

function ValueInput({
  value,
  onChange,
  label,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  label: string;
}) {
  const [text, setText] = useState(show(value));
  useEffect(() => setText(show(value)), [value]);
  return (
    <input
      className="num"
      aria-label={label}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => onChange(num(text))}
    />
  );
}

export function ImportPage() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [list, setList] = useState<ImportSummary[]>([]);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [meta, setMeta] = useState<ImportMeta | null>(null);
  const [cands, setCands] = useState<Candidate[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [useLlm, setUseLlm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [author, setAuthor] = useState(readName);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [onlyAccepted, setOnlyAccepted] = useState(false);

  const refresh = useCallback(() => {
    imports
      .list()
      .then(setList)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    imports
      .capabilities()
      .then(setCaps)
      .catch(() => undefined);
    refresh();
  }, [refresh]);

  const open = (j: ImportJob) => {
    setJob(j);
    setMeta(j.meta);
    setCands(j.candidates);
    setActive(null);
    setPage(1);
    setError(null);
  };

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const upload = (file: File) =>
    run("Lendo o PDF…", async () => {
      const up = await imports.upload(file);
      const j = await imports.start({
        sha256: up.sha256,
        filename: up.filename,
        meta: {},
        use_llm: useLlm,
      });
      open(j);
      refresh();
    });

  const save = () =>
    run("Salvando…", async () => {
      if (!job || !meta) return;
      open(await imports.save(job.id, meta, cands));
      refresh();
    });

  const remap = () =>
    run("Mapeando de novo…", async () => {
      if (!job || !meta) return;
      open(await imports.remap(job.id, meta, useLlm));
      refresh();
    });

  const commit = (replace = false) =>
    run("Criando o componente…", async () => {
      if (!job || !meta) return;
      try {
        window.localStorage.setItem("reviewer", author);
      } catch {
        /* storage unavailable */
      }
      await imports.save(job.id, meta, cands);
      try {
        const detail = await imports.commit(job.id, author, replace);
        refresh();
        setReviewId(detail.record.id);
      } catch (e) {
        const msg = (e as Error).message;
        if (msg.includes("já existe") && window.confirm(`${msg}. Substituir?`)) {
          const detail = await imports.commit(job.id, author, true);
          refresh();
          setReviewId(detail.record.id);
          return;
        }
        throw e;
      }
    });

  const update = (i: number, patch: Partial<Candidate>) =>
    setCands((cs) => cs.map((c, k) => (k === i ? { ...c, ...patch } : c)));

  const select = (i: number) => {
    setActive(i);
    setPage(cands[i]!.page);
  };

  const addManual = () => {
    if (!meta) return;
    const key = window.prompt("Símbolo do parâmetro (como no esquema da categoria, ex.: VRRM)");
    if (!key) return;
    setCands((cs) => [
      ...cs,
      {
        key,
        symbol: key,
        min: null,
        typ: null,
        max: null,
        unit: "",
        conditions: {},
        conditions_text: null,
        page,
        bbox: null,
        excerpt: "valor digitado pelo usuário a partir do PDF",
        method: "manual",
        confidence: 1,
        notes: ["valor digitado na importação"],
        accepted: true,
      },
    ]);
  };

  const rows = useMemo(
    () => cands.map((c, i) => ({ c, i })).filter(({ c }) => !onlyAccepted || c.accepted),
    [cands, onlyAccepted],
  );
  const accepted = cands.filter((c) => c.accepted).length;

  if (reviewId) {
    return <ComponentReview id={reviewId} onBack={() => setReviewId(null)} />;
  }

  if (!job || !meta) {
    return (
      <main className="single">
        <section className="panel">
          <h2>Importar datasheet</h2>
          <p className="small muted">
            Envie o PDF do fabricante. O sistema lê o texto (com OCR em páginas digitalizadas),
            sugere a categoria e propõe valores com a página e o trecho de origem. Nenhum valor
            entra no catálogo sem que você aceite aqui e confira na revisão.
          </p>
          <div className="row">
            <label className="file">
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
              />
              Escolher PDF…
            </label>
            <label title={caps?.llm.reason ?? "Envia o PDF para a API da Anthropic"}>
              <input
                type="checkbox"
                checked={useLlm}
                disabled={!caps?.llm.available}
                onChange={(e) => setUseLlm(e.target.checked)}
              />{" "}
              Usar modelo de linguagem ({caps?.llm.available ? caps.llm.model : "indisponível"})
            </label>
            <span className="small muted">
              OCR {caps?.ocr ? "disponível" : "indisponível (instale o Tesseract)"}
            </span>
          </div>
          {busy && <p className="muted">{busy}</p>}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <QueuePanel
            useLlm={useLlm}
            onJob={(j) => {
              open(j);
              refresh();
            }}
          />
          <h3>Importações anteriores</h3>
          {list.length === 0 ? (
            <p className="small muted">Nenhuma ainda.</p>
          ) : (
            <table className="params clickable">
              <thead>
                <tr>
                  <th>Arquivo</th>
                  <th>Part number</th>
                  <th>Categoria</th>
                  <th>Aceitos</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => run("Abrindo…", async () => open(await imports.get(s.id)))}
                  >
                    <td>{s.filename}</td>
                    <td>{s.part_number || "—"}</td>
                    <td>{CATEGORY_LABEL[s.category] ?? s.category}</td>
                    <td>
                      {s.accepted}/{s.candidates}
                    </td>
                    <td>{STATUS_LABEL[s.status]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    );
  }

  const current = active != null ? cands[active] : null;
  const highlights = cands
    .filter((c) => c.page === page && c.bbox)
    .map((c) => ({
      bbox: c.bbox!,
      label: c === current ? c.key : undefined,
      tone: (c === current ? "active" : "muted") as "active" | "muted",
    }));
  const editable = job.status === "extraido";

  return (
    <main className="review">
      <section className="panel">
        <button className="secondary" onClick={() => setJob(null)}>
          ← Importações
        </button>
        <h2>
          {job.filename} <span className="badge em_revisao">{STATUS_LABEL[job.status]}</span>
        </h2>
        <p className="small muted">
          {job.pages} página(s)
          {job.ocr_pages.length > 0 && ` · OCR nas páginas ${job.ocr_pages.join(", ")}`}
          {job.llm_model && ` · com ${job.llm_model}`}
        </p>
        {job.warnings.map((w) => (
          <div key={w} className="note small">
            {w}
          </div>
        ))}
        <fieldset className="meta" disabled={!editable}>
          <label>
            Fabricante
            <input
              value={meta.manufacturer}
              onChange={(e) => setMeta({ ...meta, manufacturer: e.target.value })}
            />
          </label>
          <label>
            Part number
            <input
              value={meta.part_number}
              onChange={(e) => setMeta({ ...meta, part_number: e.target.value })}
            />
          </label>
          <label>
            Categoria
            <select
              value={meta.category}
              onChange={(e) => setMeta({ ...meta, category: e.target.value })}
            >
              {[
                ...new Set([
                  meta.category,
                  ...job.ranking.map((r) => r.category),
                  ...Object.keys(CATEGORY_LABEL),
                ]),
              ]
                .filter(Boolean)
                .map((c) => {
                  const r = job.ranking.find((x) => x.category === c);
                  return (
                    <option key={c} value={c}>
                      {CATEGORY_LABEL[c] ?? c}
                      {r ? ` (pontuação ${r.score.toString().replace(".", ",")})` : ""}
                    </option>
                  );
                })}
            </select>
          </label>
          <label>
            Encapsulamento
            <input
              value={meta.package ?? ""}
              onChange={(e) => setMeta({ ...meta, package: e.target.value || null })}
            />
          </label>
          <label>
            Documento
            <input
              value={meta.document_number ?? ""}
              onChange={(e) => setMeta({ ...meta, document_number: e.target.value || null })}
            />
          </label>
          <label>
            Revisão
            <input
              value={meta.revision ?? ""}
              onChange={(e) => setMeta({ ...meta, revision: e.target.value || null })}
            />
          </label>
          <label className="wide">
            URL do datasheet
            <input
              value={meta.url ?? ""}
              onChange={(e) => setMeta({ ...meta, url: e.target.value || null })}
            />
          </label>
        </fieldset>
        {editable && (
          <div className="row">
            <button className="secondary" onClick={remap} disabled={!!busy}>
              Mapear de novo (categoria/part number)
            </button>
            <label>
              <input
                type="checkbox"
                checked={useLlm}
                disabled={!caps?.llm.available}
                onChange={(e) => setUseLlm(e.target.checked)}
              />{" "}
              com modelo de linguagem
            </label>
            <button className="secondary" onClick={save} disabled={!!busy}>
              Salvar edição
            </button>
          </div>
        )}
        {busy && <p className="muted">{busy}</p>}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <div className="row">
          <strong>
            {accepted} de {cands.length} valores aceitos
          </strong>
          <label className="small">
            <input
              type="checkbox"
              checked={onlyAccepted}
              onChange={(e) => setOnlyAccepted(e.target.checked)}
            />{" "}
            só os aceitos
          </label>
          {editable && (
            <button className="secondary" onClick={addManual}>
              + valor manual
            </button>
          )}
        </div>
        <table className="params clickable candidates">
          <thead>
            <tr>
              <th>Aceito</th>
              <th>Parâmetro</th>
              <th>Mín.</th>
              <th>Típ.</th>
              <th>Máx.</th>
              <th>Unidade</th>
              <th>Pág.</th>
              <th>Origem</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ c, i }) => (
              <tr key={i} className={i === active ? "active" : undefined} onClick={() => select(i)}>
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`Aceitar ${c.key}`}
                    checked={c.accepted}
                    disabled={!editable}
                    onChange={(e) => update(i, { accepted: e.target.checked })}
                  />
                </td>
                <td>
                  <strong>{c.key}</strong>
                  {c.conditions_text && <div className="small muted">{c.conditions_text}</div>}
                  {c.notes.length > 0 && <div className="small note">{c.notes.join("; ")}</div>}
                </td>
                {(["min", "typ", "max"] as const).map((pos) => (
                  <td key={pos} onClick={(e) => e.stopPropagation()}>
                    {editable ? (
                      <ValueInput
                        label={`${c.key} ${pos}`}
                        value={c[pos]}
                        onChange={(v) => update(i, { [pos]: v })}
                      />
                    ) : (
                      show(c[pos])
                    )}
                  </td>
                ))}
                <td onClick={(e) => e.stopPropagation()}>
                  {editable ? (
                    <input
                      className="unit"
                      aria-label={`${c.key} unidade`}
                      value={c.unit}
                      onChange={(e) => update(i, { unit: e.target.value })}
                    />
                  ) : (
                    unitSymbol(c.unit)
                  )}
                </td>
                <td>{c.page}</td>
                <td className="small">
                  {METHOD_LABEL[c.method]}
                  <div className="muted">confiança {Math.round(c.confidence * 100)} %</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {job.rejected.length > 0 && (
          <details>
            <summary>
              {job.rejected.length} proposta(s) do modelo de linguagem descartada(s)
            </summary>
            <ul className="small">
              {job.rejected.map((r, k) => (
                <li key={k}>
                  <strong>{r.proposal.key}</strong> (pág. {r.proposal.page}): {r.reason}. Trecho
                  citado: “{r.proposal.excerpt}”
                </li>
              ))}
            </ul>
          </details>
        )}
        {editable && (
          <div className="release">
            <p className="small">
              Ao importar, os valores aceitos entram como <strong>extraídos</strong>, com página e
              trecho. O componente fica em revisão e só vai para a seleção automática depois que
              você conferir cada valor obrigatório.
            </p>
            <div className="row">
              <input
                aria-label="Seu nome"
                placeholder="Seu nome"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
              />
              <button
                onClick={() => commit()}
                disabled={!!busy || !author.trim() || accepted === 0}
              >
                Importar e abrir a revisão
              </button>
              <button
                className="secondary"
                onClick={() =>
                  run("Descartando…", async () => {
                    open(await imports.discard(job.id));
                    refresh();
                  })
                }
              >
                Descartar
              </button>
            </div>
          </div>
        )}
        {job.status === "importado" && job.component_id && (
          <button onClick={() => setReviewId(job.component_id)}>
            Abrir a revisão do componente
          </button>
        )}
      </section>
      <section className="panel sheet">
        <div className="row">
          <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ←
          </button>
          <span>
            Página {page} de {job.pages}
          </span>
          <button
            className="secondary"
            disabled={page >= job.pages}
            onClick={() => setPage(page + 1)}
          >
            →
          </button>
          <a className="small" href={catalog.pdfUrl(job.sha256)} target="_blank" rel="noreferrer">
            PDF
          </a>
        </div>
        {current && (
          <p className="small">
            <strong>{current.key}</strong>: “{current.excerpt}”
          </p>
        )}
        <PdfPage sha={job.sha256} page={page} highlights={highlights} />
      </section>
    </main>
  );
}
