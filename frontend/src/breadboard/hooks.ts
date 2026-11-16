import { useEffect, useMemo, useState } from "react";
import { breadboardApi } from "../api";
import type { Schematic } from "../schematic/types";
import type { ResolveOut, Spec } from "./types";

let specCache: Promise<Spec> | null = null;

export function useBreadboardSpec(): Spec | null {
  const [spec, setSpec] = useState<Spec | null>(null);
  useEffect(() => {
    specCache ??= breadboardApi.spec();
    specCache.then(setSpec).catch(() => {
      specCache = null;
    });
  }, []);
  return spec;
}

/** Packages and pinouts of the schematic's parts; refetched when parts change (debounced). */
export function useResolved(sch: Schematic): { resolved: ResolveOut | null; error: string | null } {
  const [resolved, setResolved] = useState<ResolveOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  // only what changes pinouts and nets: parts, their values and the wiring
  const key = useMemo(
    () =>
      JSON.stringify([
        sch.components.map((c) => [c.ref, c.kind, c.part_id, c.params, c.x, c.y, c.rot, c.mirror]),
        sch.wires,
        sch.labels,
      ]),
    [sch.components, sch.wires, sch.labels],
  );
  useEffect(() => {
    const t = setTimeout(() => {
      breadboardApi
        .resolve({ ...sch, breadboard: null })
        .then((r) => {
          setResolved(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { resolved, error };
}
