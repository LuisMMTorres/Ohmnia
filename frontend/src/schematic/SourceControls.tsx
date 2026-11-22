import { useEffect, useState } from "react";
import { formatEng } from "../format";
import {
  configureSource,
  peakToPeakFromRms,
  sourceSettings,
  type SourceSettings,
  type Waveform,
} from "./sourceConfig";
import type { Component } from "./types";

export function SourceControls({
  component,
  onChange,
}: {
  component: Component;
  onChange: (c: Component) => void;
}) {
  const [settings, setSettings] = useState(() => sourceSettings(component));
  const [error, setError] = useState("");
  useEffect(() => {
    setSettings(sourceSettings(component));
    setError("");
  }, [component]);
  const fixed = component.params.bench_channel === "3";
  const unit = component.kind.startsWith("i") ? "A" : "V";
  const apply = (next: SourceSettings) => {
    try {
      const configured = configureSource(component, next);
      setSettings(next);
      onChange(configured);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <fieldset className="source-controls">
      <legend>{unit === "V" ? "Fonte de tensão" : "Fonte de corrente"}</legend>
      {!component.params.bench_id && (
        <label>
          Tipo de saída
          <select
            aria-label="Tipo de saída"
            value={component.kind[0]}
            onChange={(e) =>
              onChange({ ...component, kind: `${e.target.value}${component.kind.slice(1)}` })
            }
          >
            <option value="v">Tensão</option>
            <option value="i">Corrente</option>
          </select>
        </label>
      )}
      <label>
        Modo
        <select
          value={settings.waveform === "dc" ? "dc" : "ac"}
          disabled={!!component.params.bench_id}
          onChange={(e) =>
            apply({ ...settings, waveform: e.target.value === "dc" ? "dc" : "sine" })
          }
        >
          <option value="dc">Contínua (CC)</option>
          <option value="ac">Alternada / variável</option>
        </select>
      </label>
      {settings.waveform !== "dc" && (
        <label>
          Forma de onda
          <select
            value={settings.waveform}
            onChange={(e) => apply({ ...settings, waveform: e.target.value as Waveform })}
          >
            <option value="sine">Senoidal</option>
            <option value="square">Quadrada</option>
            <option value="triangle">Triangular</option>
          </select>
        </label>
      )}
      <label>
        {settings.waveform === "dc" ? `Tensão/corrente ajustada (${unit})` : `Offset (${unit})`}
        <input
          type="number"
          step="any"
          disabled={fixed}
          min={component.params.bench_id ? -30 : undefined}
          max={component.params.bench_id ? 30 : undefined}
          value={settings.offset}
          onChange={(e) => {
            const value = e.target.valueAsNumber;
            if (component.params.bench_id && (value < -30 || value > 30)) {
              setError("Os canais ajustáveis permitem −30 a +30 V.");
              return;
            }
            apply({ ...settings, offset: value });
          }}
        />
      </label>
      {settings.waveform !== "dc" && (
        <>
          <label
            title={
              settings.waveform === "sine"
                ? "Valor eficaz da senoide: o pico é Vrms·√2"
                : "Valor eficaz da parte alternada (sem o offset)"
            }
          >
            {unit === "V" ? "Tensão" : "Corrente"} eficaz, RMS ({unit})
            <input
              type="number"
              min={0}
              step="any"
              value={settings.rms}
              onChange={(e) => apply({ ...settings, rms: e.target.valueAsNumber })}
            />
            <span className="small muted">
              {(() => {
                const vpp = peakToPeakFromRms(settings.waveform, settings.rms, settings.duty);
                return Number.isFinite(vpp)
                  ? `pico ${formatEng(vpp / 2, unit, 4)} · pico a pico ${formatEng(vpp, unit, 4)}`
                  : "";
              })()}
            </span>
          </label>
          <label>
            Frequência (Hz)
            <input
              type="number"
              min={0}
              step="any"
              value={settings.frequency}
              onChange={(e) => apply({ ...settings, frequency: e.target.valueAsNumber })}
            />
          </label>
          {settings.waveform !== "sine" && (
            <label>
              Duty cycle / subida (%)
              <input
                type="number"
                min={0.01}
                max={99.99}
                step="any"
                value={settings.duty}
                onChange={(e) => apply({ ...settings, duty: e.target.valueAsNumber })}
              />
            </label>
          )}
        </>
      )}
      {fixed && <p className="small muted">Canal fixo de 5 V.</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
