import { useState } from "react";
import { ComponentDetail, imports, SpiceModel } from "../../api";
import { CurvePlot } from "../../components/CurvePlot";
import { formatSci } from "../../format";

/** Residuals are in SI: [label of the independent variable, label of the fitted quantity]. */
const SI_LABELS: Record<string, [string, string]> = {
  "VF(IF)": ["IF (A)", "VF (V)"],
  "hFE(IC)": ["IC (A)", "hFE"],
  "ID(VGS)": ["VGS (V)", "ID (A)"],
};

function pct(v: number): string {
  return `${v.toFixed(2).replace(".", ",")} %`;
}

function ModelCard({
  model,
  detail,
  onDelete,
}: {
  model: SpiceModel;
  detail: ComponentDetail;
  onDelete: () => void;
}) {
  const fit = model.fit;
  const curve = fit ? detail.record.curves.find((c) => fit.curves.includes(c.id)) : undefined;
  const swap = curve && fit && fit.quantity === "VF(IF)" && curve.x.quantity !== "IF";
  return (
    <article className="model-card">
      <header className="row">
        <strong>{model.name}</strong>
        <span className={`badge ${model.origin === "ajustado" ? "extraido" : "liberado"}`}>
          {model.origin === "ajustado" ? "ajustado ao datasheet" : "do fabricante"}
        </span>
        <span className={`badge ${model.checked ? "revisado" : "a_verificar"}`}>
          {model.checked ? "roda no ngspice" : "não verificado"}
        </span>
        <span className="small muted">
          {model.kind === "subckt" ? `subcircuito (${model.pins.join(", ")})` : model.device}
        </span>
        <button className="secondary small" onClick={onDelete}>
          remover
        </button>
      </header>
      {model.source_note && <p className="small muted">Arquivo: {model.source_note}</p>}
      <pre className="spice">{model.text}</pre>
      {fit && (
        <>
          <p className="small">
            Erro em {fit.quantity} sobre {fit.points} ponto(s): RMS {pct(fit.rms_error_pct)}, máximo{" "}
            {pct(fit.max_error_pct)}{" "}
            {fit.simulated ? "(simulado no ngspice)" : "(equação do modelo)"}
          </p>
          <table className="params small">
            <thead>
              <tr>
                <th>Parâmetro</th>
                <th>Valor</th>
                <th>Origem</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(model.params).map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{formatSci(v, 4)}</td>
                  <td>{fit.params_origin[k] ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {fit.assumptions.length > 0 && (
            <details open>
              <summary className="small">Premissas do ajuste</summary>
              <ul className="small">
                {fit.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </details>
          )}
          {curve && fit.residuals.length > 0 && (
            <CurvePlot
              series={[
                {
                  label: "datasheet",
                  points: fit.residuals.map((r) => (swap ? [r.measured, r.x] : [r.x, r.measured])),
                },
                {
                  label: "modelo",
                  kind: "line",
                  points: fit.residuals.map((r) => (swap ? [r.model, r.x] : [r.x, r.model])),
                },
              ]}
              xScale={curve.x.scale}
              yScale={curve.y.scale}
              xLabel={(SI_LABELS[fit.quantity] ?? [fit.quantity, ""])[swap ? 1 : 0]!}
              yLabel={(SI_LABELS[fit.quantity] ?? ["", fit.quantity])[swap ? 0 : 1]!}
            />
          )}
        </>
      )}
      {!model.checked && model.check_log && (
        <details>
          <summary className="small">Registro do ngspice</summary>
          <pre className="spice small">{model.check_log}</pre>
        </details>
      )}
    </article>
  );
}

export function ModelsTab({
  detail,
  onChange,
}: {
  detail: ComponentDetail;
  onChange: (d: ComponentDetail) => void;
}) {
  const record = detail.record;
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<ComponentDetail>) => {
    setBusy(label);
    setError(null);
    try {
      onChange(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const readFile = async (file: File) => {
    setText(await file.text());
    setNote(file.name);
  };

  const fittable = /^(diode|bjt|mosfet)\./.test(record.category);

  return (
    <div className="models-tab">
      <div className="two-cols">
        <section>
          <h3>Modelo do fabricante</h3>
          <p className="small muted">
            Cole ou abra o arquivo .lib/.mod/.cir. Cada .model e .subckt é carregado no ngspice num
            circuito mínimo antes de ser guardado.
          </p>
          <input
            type="file"
            accept=".lib,.mod,.cir,.sp,.txt"
            onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])}
          />
          <textarea
            aria-label="Texto do modelo SPICE"
            rows={6}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="row">
            <input
              aria-label="Origem do modelo"
              placeholder="arquivo ou URL do fabricante"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button
              disabled={!text.trim() || !!busy}
              onClick={() =>
                run("Verificando no ngspice…", () =>
                  imports.importModels(record.id, text, note || null),
                )
              }
            >
              Importar modelo
            </button>
          </div>
        </section>
        <section>
          <h3>Ajustar modelo ao datasheet</h3>
          {!fittable ? (
            <p className="small muted">Ajuste disponível para diodos, TBJ e MOSFET.</p>
          ) : (
            <>
              <p className="small muted">
                Diodo: curva IF×VF. TBJ: curva hFE×IC (e VBE×IC, se houver). MOSFET: curva de
                transferência ID×VGS, ou VGS(th) e gfs. O erro é medido simulando o modelo final no
                ngspice nos pontos da curva.
              </p>
              {record.curves.map((c) => (
                <label key={c.id} className="block small">
                  <input
                    type="checkbox"
                    checked={selected.includes(c.id)}
                    onChange={(e) =>
                      setSelected((s) =>
                        e.target.checked ? [...s, c.id] : s.filter((x) => x !== c.id),
                      )
                    }
                  />{" "}
                  {c.name} ({c.points.length} pts)
                </label>
              ))}
              {record.curves.length === 0 && (
                <p className="small">Digitalize uma curva na aba Curvas.</p>
              )}
              <div className="row">
                <input
                  aria-label="Nome do modelo"
                  placeholder={`nome (${record.part_number})`}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <button
                  disabled={!!busy}
                  onClick={() =>
                    run("Ajustando e simulando…", () =>
                      imports.fitModel(record.id, selected, name || undefined),
                    )
                  }
                >
                  Ajustar
                </button>
              </div>
            </>
          )}
        </section>
      </div>
      {busy && <p className="muted">{busy}</p>}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <h3>Modelos do componente</h3>
      {record.spice_models.length === 0 && <p className="small muted">Nenhum modelo.</p>}
      {record.spice_models.map((m) => (
        <ModelCard
          key={m.id}
          model={m}
          detail={detail}
          onDelete={() => {
            if (window.confirm(`Remover o modelo ${m.name}?`))
              void run("Removendo…", () => imports.deleteModel(record.id, m.id));
          }}
        />
      ))}
    </div>
  );
}
