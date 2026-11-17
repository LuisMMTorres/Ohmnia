import { strip } from "./geometry";
import type { BoardSpec, Breadboard, ResolveOut } from "./types";

/** Electrical node at a hole, following only explicit jumpers and board conductors. */
export function netAtHole(
  board: BoardSpec,
  assembly: Breadboard,
  resolved: ResolveOut,
  hole: string,
): string {
  const parents = new Map<string, string>();
  const find = (x: string): string => {
    const p = parents.get(x);
    if (!p || p === x) return x;
    const root = find(p);
    parents.set(x, root);
    return root;
  };
  const conductor = (h: string) => strip(board, h, assembly.rails_split);
  for (const w of assembly.wires) parents.set(find(conductor(w.a)), find(conductor(w.b)));
  const target = find(conductor(hole));
  const nets = new Set<string>();
  for (const part of assembly.parts)
    for (const [pin, h] of Object.entries(part.legs)) {
      if (find(conductor(h)) === target) {
        const net = resolved.nets[`${part.ref}:${pin}`];
        if (net) nets.add(net);
      }
    }
  if (nets.size !== 1)
    throw new Error(
      nets.size
        ? "A ponteira está em uma ligação que une nós diferentes. Corrija a montagem."
        : "Este furo não está conectado a um nó do circuito.",
    );
  return [...nets][0]!;
}
