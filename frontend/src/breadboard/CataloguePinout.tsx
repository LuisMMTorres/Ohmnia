// Package and pinout of a catalogue part (from its datasheet), shown on the component page.
import type { ComponentRecord } from "../api";
import { PinoutSource } from "./BreadboardView";
import { useBreadboardSpec } from "./hooks";
import { PackagePreview } from "./PackageArt";
import type { PartView } from "./types";

export interface PinFunction {
  pin: string;
  name: string;
  role: string | null;
  unit: string | null;
}

export interface Pinout {
  package: string;
  pins: PinFunction[];
  source: { datasheet_id: string; page: number | null; location: string | null };
  status: string;
  note: string | null;
}

export function CataloguePinout({ record }: { record: ComponentRecord }) {
  const spec = useBreadboardSpec();
  const po = record.pinout;
  if (!po) {
    return (
      <p className="small muted">
        Encapsulamento real: pinagem ainda não transcrita do datasheet (a peça aparece na protoboard
        sem rótulos e fica fora da conferência).
      </p>
    );
  }
  const pkg = spec?.packages.find((p) => p.id === po.package);
  const ds = record.datasheets.find((d) => d.id === po.source.datasheet_id);
  const view: PartView = {
    ref: record.part_number,
    kind: record.category,
    package: po.package,
    origin: "datasheet",
    checkable: true,
    pinmap: Object.fromEntries(po.pins.filter((p) => p.role).map((p) => [p.pin, p.role!])),
    labels: Object.fromEntries(po.pins.map((p) => [p.pin, p.name])),
    title: record.part_number,
    part_number: record.part_number,
    source: {
      document: ds
        ? [ds.manufacturer, ds.document_number, ds.revision].filter(Boolean).join(" ")
        : po.source.datasheet_id,
      page: po.source.page,
      location: po.source.location,
      url: ds?.url ?? null,
    },
    status: po.status,
    notes: po.note ? [po.note] : [],
    bands: [],
  };
  return (
    <div className="bb-symbol-package">
      <h3>Encapsulamento real e pinagem</h3>
      {pkg && <p className="small muted">{pkg.label}</p>}
      {pkg && <PackagePreview pkg={pkg} view={view} />}
      <table className="params small">
        <tbody>
          {po.pins.map((p) => (
            <tr key={p.pin}>
              <td>pino {p.pin}</td>
              <td>{p.name}</td>
              <td className="muted">{p.unit ? `unidade ${p.unit}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <PinoutSource view={view} />
    </div>
  );
}
