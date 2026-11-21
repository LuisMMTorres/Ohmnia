import type { PartDamage } from "./damage";

/** Box listing the parts that would burn in the last simulation, why, and how to avoid it. */
export function DamageAlert({
  parts,
  onClose,
  onSelect,
}: {
  parts: PartDamage[];
  onClose: () => void;
  onSelect?: (ref: string) => void;
}) {
  if (!parts.length) return null;
  return (
    <section className="damage-alert" role="alert" aria-label="Componentes danificados">
      <header>
        <strong>
          {parts.length === 1
            ? `1 componente queimaria nesta montagem`
            : `${parts.length} componentes queimariam nesta montagem`}
        </strong>
        <button type="button" className="secondary" onClick={onClose} aria-label="Fechar alerta">
          Fechar
        </button>
      </header>
      <ul>
        {parts.map((p) => (
          <li key={p.ref}>
            <button type="button" className="link" onClick={() => onSelect?.(p.ref)}>
              {p.ref}
            </button>
            <div>
              <p>
                <b>Motivo:</b> {p.causes.join(" ")}
              </p>
              {p.advice.length > 0 && (
                <p>
                  <b>O que fazer:</b> {p.advice.join(" ")}
                </p>
              )}
              {p.sources.length > 0 && (
                <p className="small muted">
                  Limite: {p.sources.join("; ")}
                  {p.unreviewed ? " · valor do catálogo ainda não revisado" : ""}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
