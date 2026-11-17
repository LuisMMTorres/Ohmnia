// Design assistant: the designed circuit assembled on a breadboard, checked, with its guide.
import { useEffect, useState } from "react";
import { request, type DesignIn, type DesignOut } from "../../api";
import { BreadboardView } from "../../breadboard/BreadboardView";
import { useBreadboardSpec, useResolved } from "../../breadboard/hooks";
import type { AutoOut } from "../../breadboard/types";
import { emptySchematic, type Schematic } from "../../schematic/types";

interface DesignBreadboardOut {
  available: boolean;
  reason: string | null;
  schematic: Schematic | null;
  assembly: AutoOut | null;
  notes: string[];
}

const SIMULATOR_STORAGE = "circuitos.schematic";

export function BreadboardTab({
  moduleId,
  body,
  version,
}: {
  moduleId: string;
  body: DesignIn;
  version: DesignOut;
}) {
  const [data, setData] = useState<DesignBreadboardOut | null>(null);
  const [sch, setSch] = useState<Schematic>(emptySchematic);
  const [error, setError] = useState<string | null>(null);
  const spec = useBreadboardSpec();
  const { resolved } = useResolved(sch);

  useEffect(() => {
    setData(null);
    request<DesignBreadboardOut>(`/design/${moduleId}/breadboard`, {
      method: "POST",
      body: JSON.stringify(body),
    })
      .then((d) => {
        setData(d);
        if (d.schematic) setSch(d.schematic);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
    // the design result changes whenever the body does
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleId, version]);

  const openInSimulator = () => {
    try {
      localStorage.setItem(SIMULATOR_STORAGE, JSON.stringify(sch));
    } catch {
      setError("Não foi possível guardar o circuito para o simulador.");
      return;
    }
    sessionStorage.setItem("circuitos.simulator.view", "protoboard");
    window.location.hash = "simulator";
  };

  if (error) return <div className="error">{error}</div>;
  if (!data || !spec) return <p className="muted">Montando o circuito na protoboard…</p>;
  if (!data.available)
    return (
      <div className="panel">
        <p>{data.reason}</p>
      </div>
    );
  return (
    <div className="bb-design">
      <div className="row">
        <p className="small muted grow">
          Circuito do projeto com as peças escolhidas (pinagem do datasheet quando transcrita),
          montado automaticamente e conferido com o esquemático. Você pode arrastar as peças para
          arrumar a montagem; a conferência acompanha.
        </p>
        <button className="secondary" onClick={openInSimulator}>
          Abrir no simulador
        </button>
      </div>
      {data.notes.map((n) => (
        <p key={n} className="note small">
          {n}
        </p>
      ))}
      <BreadboardView
        schematic={sch}
        onChange={setSch}
        spec={spec}
        resolved={resolved}
        initialGuide={data.assembly?.guide}
      />
    </div>
  );
}
