import { CalcStep } from "../api";
import { formatEng } from "../format";
import { Equation } from "./Equation";

/** Input name as LaTeX: a subscript of several characters written without braces ("E_on",
 * "V_pk,max") gets them, so KaTeX does not subscript only the first letter. */
export function texName(name: string): string {
  return name.replace(/_([^{\s][^\s]*)/, (_, sub: string) =>
    sub.length > 1 ? `_{${sub}}` : `_${sub}`,
  );
}

/** Calculation record (memória de cálculo): equation, inputs, result and assumptions. */
export function CalcSteps({ steps }: { steps: CalcStep[] }) {
  return (
    <ol className="calc-steps">
      {steps.map((s) => (
        <li key={s.id}>
          <strong>{s.description}</strong>
          <Equation latex={s.latex} block />
          <div className="small">
            {Object.entries(s.inputs).map(([name, q]) => (
              <span key={name} className="calc-input">
                <Equation latex={texName(name)} /> = {formatEng(q.value, q.unit, 4)}
              </span>
            ))}
          </div>
          <div>
            Resultado: <strong>{formatEng(s.output.value, s.output.unit, 4)}</strong>
          </div>
          {s.assumptions.length > 0 && (
            <div className="muted small">Premissas: {s.assumptions.join("; ")}</div>
          )}
        </li>
      ))}
    </ol>
  );
}
