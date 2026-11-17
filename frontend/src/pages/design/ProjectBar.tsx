import { useEffect, useState } from "react";
import { Policy, ProjectDocument, projects, ProjectSummary } from "../../api";
import type { Schematic } from "../../schematic/types";

export interface DesignState {
  moduleId: string;
  spec: Record<string, unknown>;
  policy: Policy;
  locks: Record<string, string>;
  costs: Record<string, number>;
  schematic?: Schematic | null;
}

interface Props {
  state: DesignState;
  project: ProjectDocument | null;
  onProject: (doc: ProjectDocument | null) => void;
  /** Load a saved revision into the design inputs. */
  onOpen: (doc: ProjectDocument) => void;
  onError: (message: string) => void;
}

function sameContent(doc: ProjectDocument, s: DesignState): boolean {
  const c = doc.current;
  return (
    doc.module_id === s.moduleId &&
    JSON.stringify(c.spec) === JSON.stringify(s.spec) &&
    c.policy === s.policy &&
    JSON.stringify(c.locks) === JSON.stringify(s.locks) &&
    JSON.stringify(c.costs) === JSON.stringify(s.costs) &&
    JSON.stringify(c.schematic ?? null) === JSON.stringify(s.schematic ?? null)
  );
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Save, open, duplicate and version design projects (open JSON format). */
export function ProjectBar({ state, project, onProject, onOpen, onError }: Props) {
  const [list, setList] = useState<ProjectSummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = project ? !sameContent(project, state) : true;
  const sameModule = !project || project.module_id === state.moduleId;

  useEffect(() => {
    if (list === null) return;
    projects
      .list()
      .then(setList)
      .catch((e: Error) => onError(e.message));
    // reload only when the dialog opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list === null]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const content = (note?: string | null) => ({
    spec: state.spec,
    policy: state.policy,
    locks: state.locks,
    costs: state.costs,
    note: note ?? null,
    schematic: state.schematic ?? null,
  });

  const saveAs = () =>
    run(async () => {
      const name = window.prompt("Nome do projeto", project?.name ?? "");
      if (!name?.trim()) return;
      onProject(await projects.create(name.trim(), state.moduleId, content()));
    });

  const save = () =>
    run(async () => {
      if (!project || !sameModule) return saveAs();
      const note = window.prompt("Nota desta revisão (opcional)", "") ?? null;
      onProject(await projects.save(project.id, content(note)));
    });

  const open = (id: string) =>
    run(async () => {
      const doc = await projects.get(id);
      onProject(doc);
      onOpen(doc);
      setList(null);
    });

  const importFile = (file: File) =>
    run(async () => {
      const doc = await projects.importFile(await file.text());
      onProject(doc);
      onOpen(doc);
    });

  const restore = (n: number) =>
    run(async () => {
      if (!project) return;
      const doc = await projects.restore(project.id, n);
      onProject(doc);
      onOpen(doc);
    });

  const duplicate = () =>
    run(async () => {
      if (!project) return;
      const doc = await projects.duplicate(project.id);
      onProject(doc);
    });

  return (
    <div className="project-bar">
      <span className="project-name">
        {project ? (
          <>
            <strong>{project.name}</strong>{" "}
            <span className="muted small">
              revisão {project.current.number}
              {dirty ? " · alterações não salvas" : " · salvo"}
            </span>
          </>
        ) : (
          <span className="muted">Projeto não salvo</span>
        )}
      </span>
      <button onClick={save} disabled={busy || (!!project && !dirty)}>
        Salvar
      </button>
      <button className="secondary" onClick={saveAs} disabled={busy}>
        Salvar como…
      </button>
      <button className="secondary" onClick={() => setList([])} disabled={busy}>
        Abrir…
      </button>
      {project && (
        <>
          <select
            aria-label="Revisões do projeto"
            value=""
            onChange={(e) => e.target.value && restore(Number(e.target.value))}
          >
            <option value="">Histórico ({project.history.length + 1})</option>
            {[...project.history, project.current]
              .slice()
              .reverse()
              .map((r) => (
                <option
                  key={r.number}
                  value={r.number}
                  disabled={r.number === project.current.number}
                >
                  rev. {r.number} · {when(r.saved_at)}
                  {r.note ? ` · ${r.note}` : ""}
                </option>
              ))}
          </select>
          <button className="secondary" onClick={duplicate} disabled={busy}>
            Duplicar
          </button>
          <a className="small" href={projects.fileUrl(project.id)} download>
            Baixar arquivo
          </a>
        </>
      )}
      <label className="file small">
        <input
          type="file"
          accept=".json,application/json"
          onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])}
        />
        Importar arquivo
      </label>
      {list !== null && (
        <div className="dialog" role="dialog" aria-label="Abrir projeto">
          <div className="dialog-body">
            <h3>Abrir projeto</h3>
            {list.length === 0 ? (
              <p className="muted">Nenhum projeto salvo.</p>
            ) : (
              <table className="params clickable">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Módulo</th>
                    <th>Revisão</th>
                    <th>Atualizado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((p) => (
                    <tr key={p.id} onClick={() => open(p.id)}>
                      <td>{p.name}</td>
                      <td>{p.module_id}</td>
                      <td>{p.revision}</td>
                      <td>{when(p.updated_at)}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <button
                          className="secondary small"
                          onClick={() =>
                            window.confirm(`Excluir o projeto “${p.name}”?`) &&
                            run(async () => {
                              await projects.remove(p.id);
                              setList(await projects.list());
                              if (project?.id === p.id) onProject(null);
                            })
                          }
                        >
                          excluir
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button className="secondary" onClick={() => setList(null)}>
              Fechar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
