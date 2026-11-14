import { CalcStep } from "../api";
import { formatEng } from "../format";
import { Equation } from "./Equation";

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
                <Equation latex={name} /> = {formatEng(q.value, q.unit, 4)}
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
