import type { Schematic, Probe } from "../schematic/types";
import type { BoardSpec, ResolveOut } from "./types";
import { emptyBreadboard } from "./types";
import { netAtHole } from "./connections";

export const scopeProbeId = (channel: number) => `bench-scope-ch${channel}`;
export const scopeProbeName = (channel: number) => `OSC_CH${channel}`;
export function syncScopeProbes(sch: Schematic, board: BoardSpec, resolved: ResolveOut): Schematic {
  if (!Object.keys(sch.bench_scope_connections ?? {}).length) return sch;
  const probes: Probe[] = sch.probes.filter((p) => !/^bench-scope-ch[1-4]$/.test(p.id));
  for (let channel = 1; channel <= (sch.bench_scope_channels ?? 0); channel++) {
    const connection = sch.bench_scope_connections?.[String(channel)];
    if (!connection?.positive || !connection.negative) continue;
    try {
      const assembly = sch.breadboard ?? emptyBreadboard();
      const positive = netAtHole(board, assembly, resolved, connection.positive);
      const negative = netAtHole(board, assembly, resolved, connection.negative);
      const name = scopeProbeName(channel);
      if (probes.some((p) => p.name?.toLowerCase() === name.toLowerCase()))
        throw new Error(`O nome ${name} já está em uso por outra probe.`);
      probes.push({
        id: scopeProbeId(channel),
        name,
        kind: "vdiff",
        target: { net: positive },
        reference: { net: negative },
      });
    } catch (e) {
      throw new Error(`CH${channel}: ${(e as Error).message}`);
    }
  }
  return JSON.stringify(probes) === JSON.stringify(sch.probes) ? sch : { ...sch, probes };
}

export function connectScope(
  sch: Schematic,
  board: BoardSpec,
  resolved: ResolveOut,
  channel: number,
  terminal: "positive" | "negative",
  hole: string,
): Schematic {
  netAtHole(board, sch.breadboard ?? emptyBreadboard(), resolved, hole);
  return syncScopeProbes(
    {
      ...sch,
      bench_scope_connections: {
        ...sch.bench_scope_connections,
        [channel]: {
          positive: null,
          negative: null,
          ...sch.bench_scope_connections?.[String(channel)],
          [terminal]: hole,
        },
      },
    },
    board,
    resolved,
  );
}

export function disconnectScope(sch: Schematic, channel: number): Schematic {
  return {
    ...sch,
    bench_scope_connections: {
      ...sch.bench_scope_connections,
      [channel]: { positive: null, negative: null },
    },
    probes: sch.probes.filter((p) => p.id !== scopeProbeId(channel)),
  };
}

export function removeScope(sch: Schematic): Schematic {
  return {
    ...sch,
    bench_scope_channels: 0,
    bench_scope_connections: {},
    probes: sch.probes.filter((p) => !/^bench-scope-ch[1-4]$/.test(p.id)),
  };
}
