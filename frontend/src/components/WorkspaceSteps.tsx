/** Switch workspace panels without discarding the user's inputs. */
export type WorkspaceStep = "circuit" | "analysis" | "results";

interface Props {
  active: WorkspaceStep;
  resultsAvailable: boolean;
  onSelect: (step: WorkspaceStep) => void;
}

const STEPS = [
  { id: "circuit", label: "Circuito", description: "Montar e editar" },
  { id: "analysis", label: "Configurar análise", description: "Escolher o que medir" },
  { id: "results", label: "Resultados", description: "Explorar e comparar" },
] as const;

export function WorkspaceSteps({ active, resultsAvailable, onSelect }: Props) {
  return (
    <nav className="workspace-steps" aria-label="Etapas do simulador">
      <ol>
        {STEPS.map((step, index) => (
          <li key={step.id}>
            <button
              type="button"
              className="workspace-step"
              aria-current={active === step.id ? "step" : undefined}
              disabled={step.id === "results" && !resultsAvailable}
              onClick={() => onSelect(step.id)}
            >
              <span className="step-number" aria-hidden="true">
                {index + 1}
              </span>
              <span>
                <strong>{step.label}</strong>
                <small>{step.description}</small>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
