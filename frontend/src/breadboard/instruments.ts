import type { Schematic } from "../schematic/types";
import { nextRef } from "../schematic/geometry";
import { emptyBreadboard } from "./types";

/** Clean remnants left by older schematic deletion paths, recognizing generated labels only. */
export function pruneOrphanSupplyLabels(sch: Schematic): Schematic {
  const orphanLabels = sch.labels.filter((label) => {
    const match = /^(.*)-([pn])([123])$/.exec(label.id);
    if (!match) return false;
    const [, group, terminal, channel] = match;
    const expected = terminal === "p" ? `${group}_ch${channel}` : "0";
    return (
      label.name.toLowerCase() === expected.toLowerCase() &&
      !sch.components.some((c) => c.params.bench_id === group && c.params.bench_channel === channel)
    );
  });
  if (!orphanLabels.length) return sch;
  const labels = sch.labels.filter((l) => !orphanLabels.includes(l));
  const nodes = new Set(
    orphanLabels
      .map((l) => l.name.toLowerCase())
      .filter((n) => n !== "0" && !labels.some((l) => l.name.toLowerCase() === n)),
  );
  return {
    ...sch,
    labels,
    probes: sch.probes.filter(
      (p) =>
        !nodes.has(p.target?.net?.toLowerCase() ?? "") &&
        !nodes.has(p.reference?.net?.toLowerCase() ?? ""),
    ),
  };
}

export function addSupplyChannel(sch: Schematic, group: string, channel: number): Schematic {
  if (
    sch.components.some(
      (c) => c.params.bench_id === group && c.params.bench_channel === String(channel),
    )
  )
    return sch;
  const ref = nextRef(sch, "V");
  const peer = sch.components.find((c) => c.params.bench_id === group);
  const x = (channel - 1) * 12,
    y = peer?.y ?? Math.max(0, ...sch.components.map((c) => c.y)) + 10;
  const assembly = sch.breadboard ?? emptyBreadboard();
  return {
    ...sch,
    components: [
      ...sch.components,
      {
        id: `${group}-${channel}`,
        kind: "vdc",
        ref,
        x,
        y,
        rot: 0,
        mirror: false,
        part_id: null,
        params: {
          dc: channel === 3 ? "5" : "0",
          ac: "0",
          bench_id: group,
          bench_channel: String(channel),
        },
      },
    ],
    labels: [
      ...sch.labels,
      { id: `${group}-p${channel}`, name: `${group}_ch${channel}`, x, y: y - 2 },
      { id: `${group}-n${channel}`, name: "0", x, y: y + 2 },
    ],
    probes: [
      ...sch.probes,
      { id: `${group}-i${channel}`, kind: "i", component: ref, pin: "p" },
      { id: `${group}-v${channel}`, kind: "v", target: { net: `${group}_ch${channel}` } },
    ],
    breadboard: { ...assembly, parts: [...assembly.parts, { ref, package: "fonte-cc", legs: {} }] },
  };
}

/** Remove an instrument and its generated connections, preserving the rest of the circuit. */
export function removeSources(sch: Schematic, ids: string[]): Schematic {
  const removed = sch.components.filter((c) => ids.includes(c.id));
  const refs = new Set(removed.map((c) => c.ref.toLowerCase()));
  const groups = new Set(removed.map((c) => c.params.bench_id).filter(Boolean));
  const labels = sch.labels.filter(
    (l) =>
      ![...groups].some((g) => {
        if (!sch.components.some((c) => c.params.bench_id === g && !ids.includes(c.id)))
          return l.id.startsWith(`${g}-`);
        return removed.some(
          (c) =>
            c.params.bench_id === g &&
            [`${g}-p${c.params.bench_channel}`, `${g}-n${c.params.bench_channel}`].includes(l.id),
        );
      }),
  );
  const removedNodes = new Set(
    sch.labels
      .filter((l) => !labels.includes(l))
      .map((l) => l.name.toLowerCase())
      .filter((n) => n !== "0" && !labels.some((l) => l.name.toLowerCase() === n)),
  );
  const usesRemovedPin = (pin?: string | null) =>
    !!pin && refs.has(pin.split(".")[0]!.toLowerCase());
  return {
    ...sch,
    components: sch.components.filter((c) => !ids.includes(c.id)),
    labels,
    probes: sch.probes.filter(
      (p) =>
        !refs.has(p.component?.toLowerCase() ?? "") &&
        !removedNodes.has(p.target?.net?.toLowerCase() ?? "") &&
        !removedNodes.has(p.reference?.net?.toLowerCase() ?? "") &&
        !usesRemovedPin(p.target?.pin) &&
        !usesRemovedPin(p.reference?.pin),
    ),
    breadboard: sch.breadboard
      ? {
          ...sch.breadboard,
          parts: sch.breadboard.parts.filter((p) => !refs.has(p.ref.toLowerCase())),
        }
      : sch.breadboard,
  };
}

/**
 * Text of the bench supply's ammeter. ``branch`` is the simulated current of the voltage
 * source as ngspice gives it (positive from + to − inside the source), so the current the
 * supply delivers to the circuit is −branch. No simulation yet: dashes.
 */
export function supplyAmpsText(branch: number | undefined): string {
  if (branch === undefined || !Number.isFinite(branch)) return "-.---";
  const i = -branch;
  const a = Math.abs(i);
  const text = a < 10 ? a.toFixed(3) : a.toFixed(2);
  // a supply that absorbs current (another source pushes into it) shows the minus sign
  return `${i < 0 && Number(text) !== 0 ? "-" : ""}${text}`.replace(".", ",");
}
