import { useCallback, useEffect, useState } from "react";
import { catalog, ComponentSummary } from "../api";
import { ComponentReview } from "./ComponentReview";
import { CategoryReviewButton } from "./review/CategoryReviewButton";

export const CATEGORY_LABEL: Record<string, string> = {
  "diode.rectifier": "Diodo retificador",
  "diode.fast": "Diodo rápido/ultrarrápido",
  "diode.schottky": "Diodo Schottky",
  "diode.signal": "Diodo de sinal",
  "diode.zener": "Diodo Zener",
  "bridge.single_phase": "Ponte retificadora monofásica",
  "bjt.npn": "Transistor bipolar NPN",
  "bjt.pnp": "Transistor bipolar PNP",
  "mosfet.n": "MOSFET canal N",
  "thyristor.scr": "SCR",
  "thyristor.triac": "TRIAC",
  "thyristor.diac": "DIAC",
  "heatsink.extrusion": "Dissipador (perfil)",
  "magnetic.core": "Núcleo magnético",
  "magnetic.bobbin": "Carretel",
  "magnetic.material": "Material magnético",
  "jfet.n": "JFET canal N",
  "igbt.n": "IGBT canal N",
  opamp: "Amplificador operacional",
  comparator: "Comparador",
  "regulator.positive": "Regulador linear positivo",
  "regulator.negative": "Regulador linear negativo",
  timer: "Temporizador",
  gate_driver: "Driver de gate",
  "resistor.fixed": "Resistor fixo",
  "resistor.variable": "Potenciômetro / trimpot",
  "capacitor.fixed": "Capacitor",
  "inductor.fixed": "Indutor",
  "magnetic.transformer": "Transformador",
  "thermistor.ntc": "Termistor NTC",
  "thermistor.ptc": "Termistor PTC / fusível rearmável",
  varistor: "Varistor",
  fuse: "Fusível / proteção",
  "relay.electromechanical": "Relé eletromecânico",
  "relay.solid_state": "Relé de estado sólido",
  "switch.mechanical": "Chave / botão",
  "optoelectronic.led": "LED / display",
  optocoupler: "Optoacoplador / isolador",
  "ic.digital": "CI digital",
  "ic.interface": "Driver / interface",
  "board.mcu": "Placa de microcontrolador",
  "ic.adc": "Conversor A/D",
  "ic.dac": "Conversor D/A",
  "ic.energy_meter": "Medidor de energia (CI)",
  "sensor.temperature": "Sensor de temperatura",
  "sensor.humidity": "Sensor de umidade",
  "sensor.optical": "Sensor de luz",
  "sensor.inertial": "Sensor inercial",
  "sensor.proximity": "Sensor de proximidade",
  "sensor.magnetic": "Sensor magnético (Hall)",
  "sensor.photoelectric": "Sensor fotoelétrico",
  "sensor.force": "Célula de carga / força",
  "sensor.position": "Sensor de posição",
  "sensor.encoder": "Encoder",
  "sensor.level": "Nível",
  "sensor.pressure": "Pressão",
  "sensor.flow": "Vazão",
  "sensor.current": "Sensor de corrente",
  "sensor.voltage": "Sensor de tensão",
  "instrument.transmitter": "Transmissor / condicionador",
  "instrument.controller": "Controlador de processo",
  "actuator.valve": "Válvula / atuador de válvula",
  "actuator.electric": "Atuador elétrico / bomba",
  plc: "CLP",
  hmi: "IHM",
  "drive.vfd": "Inversor de frequência",
  "drive.soft_starter": "Soft-starter",
  "motor.stepper": "Motor de passo",
  "drive.stepper": "Driver de passo / servo",
  "motor.ac": "Motor CA",
  "amplifier.audio": "Amplificador de áudio",
  "ic.mcu": "Microcontrolador (CI)",
  "ic.oscillator": "Oscilador (CI)",
  "ic.pwm_controller": "Controlador PWM",
  "jfet.p": "JFET canal P",
  "mosfet.p": "MOSFET canal P",
  "regulator.switching": "Regulador chaveado",
  ujt: "Transistor de unijunção (UJT)",
};

export const REVIEW_LABEL: Record<string, string> = {
  rascunho: "Rascunho",
  em_revisao: "Em revisão",
  liberado: "Liberado",
  rejeitado: "Rejeitado",
};

export function CatalogPage() {
  const [stats, setStats] = useState<Record<string, number>>({});
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [filterText, setFilterText] = useState("");
  const [items, setItems] = useState<ComponentSummary[]>([]);
  // Columns: union of the highlighted parameters of the listed components, in server order.
  const columns = [...new Set(items.flatMap((c) => Object.keys(c.highlights)))];
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    const filters = filterText
      .split(/[;\n]/)
      .map((f) => f.trim())
      .filter(Boolean);
    catalog
      .list({ category, q, status, filters })
      .then((r) => {
        setItems(r);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [category, q, status, filterText]);

  useEffect(() => {
    catalog
      .stats()
      .then(setStats)
      .catch(() => undefined);
  }, [selected]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load, selected]);

  if (selected) {
    return <ComponentReview id={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <main className="single">
      <section className="panel">
        <div className="filters">
          <label>
            Categoria
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Todas</option>
              {Object.entries(stats).map(([c, n]) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c] ?? c} ({n})
                </option>
              ))}
            </select>
          </label>
          <label>
            Busca
            <input
              value={q}
              placeholder="part number, fabricante, família"
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <label>
            Revisão
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Todas</option>
              {Object.entries(REVIEW_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="grow">
            Filtros por parâmetro (separe por ;)
            <input
              value={filterText}
              placeholder="VRRM>=600 V; IF(AV)>=1 A; trr<=100 ns"
              onChange={(e) => setFilterText(e.target.value)}
            />
          </label>
          <div className="filter-action">
            {category ? (
              <CategoryReviewButton
                category={category}
                label={CATEGORY_LABEL[category] ?? category}
                onDone={load}
              />
            ) : (
              <button className="secondary" disabled title="Escolha uma categoria primeiro">
                Revisar categoria
              </button>
            )}
          </div>
        </div>
        <p className="muted small">
          Os filtros comparam o valor garantido do datasheet: o mínimo, ou o próprio limite no caso
          de valores máximos absolutos, para "≥"; o máximo para "≤".
        </p>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <table className="clickable">
          <thead>
            <tr>
              <th>Componente</th>
              <th>Fabricante</th>
              <th>Categoria</th>
              {columns.map((k) => (
                <th key={k}>{k}</th>
              ))}
              <th>Revisão</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr
                key={c.id}
                tabIndex={0}
                onClick={() => setSelected(c.id)}
                onKeyDown={(e) => e.key === "Enter" && setSelected(c.id)}
              >
                <td>
                  <strong>{c.part_number}</strong>
                  <div className="muted small">{c.package}</div>
                </td>
                <td>{c.manufacturer}</td>
                <td>{CATEGORY_LABEL[c.category] ?? c.category}</td>
                {columns.map((k) => (
                  <td key={k}>{c.highlights[k] ?? "—"}</td>
                ))}
                <td>
                  <span className={`badge ${c.review_status}`}>
                    {REVIEW_LABEL[c.review_status] ?? c.review_status}
                  </span>
                  <div className="muted small">
                    {c.parameters_reviewed}/{c.parameters_total} conferidos
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && !error && <p className="muted">Nenhum componente encontrado.</p>}
      </section>
    </main>
  );
}
