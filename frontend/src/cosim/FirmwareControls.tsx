import { useEffect, useRef, useState } from "react";
import type { Component, FirmwareImage } from "../schematic/types";

const MCU_KINDS = new Set([
  "arduino_uno",
  "arduino_nano",
  "arduino_mega",
  "esp32_devkitc",
  "rpi_pico",
  "rpi_pico2",
]);
interface Capability {
  board: string;
  available: boolean;
  formats: string[];
  message: string;
  max_bytes?: number;
}

export function FirmwareControls({
  component,
  onChange,
}: {
  component: Component;
  onChange: (c: Component) => void;
}) {
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const latest = useRef(component);
  latest.current = component;
  useEffect(() => {
    let active = true;
    fetch("/api/v1/schematic/firmware/capabilities")
      .then((r) => {
        if (!r.ok) throw new Error("Não foi possível consultar os motores de firmware");
        return r.json();
      })
      .then((value: Capability[]) => {
        if (active) setCapabilities(value);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  if (!MCU_KINDS.has(component.kind)) return null;
  const cap = capabilities.find((c) => c.board === component.kind);
  const load = async (file: File) => {
    const id = component.id;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      if (file.size > (cap?.max_bytes ?? 1024 * 1024))
        throw new Error("O firmware excede o limite de tamanho da placa");
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (const byte of bytes) binary += String.fromCharCode(byte);
      const firmware: FirmwareImage = {
        board: component.kind,
        filename: file.name,
        data_base64: btoa(binary),
      };
      const response = await fetch("/api/v1/schematic/firmware/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(firmware),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string" ? result.detail : "Arquivo de firmware inválido",
        );
      if (latest.current.id !== id) return;
      onChange({ ...latest.current, firmware });
      setInfo(
        `${result.size} bytes de flash · SHA-256 ${result.sha256.slice(0, 12)}… ${result.warning}`,
      );
    } catch (e) {
      if (latest.current.id === id) setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <fieldset>
      <legend>Programação da placa virtual</legend>
      <p className="small">{cap?.message ?? "Consultando motor de firmware…"}</p>
      <p className="small">
        Modo:{" "}
        <strong>{component.firmware ? "Firmware compilado" : "Código-fonte interpretado"}</strong>
      </p>
      {component.firmware && (
        <>
          <p className="small">{component.firmware.filename}</p>
          <button
            className="secondary small"
            onClick={() => {
              onChange({ ...component, firmware: null });
              setInfo(null);
            }}
          >
            Retirar firmware e usar código-fonte
          </button>
        </>
      )}
      <label className="small">
        Carregar firmware da IDE ({cap?.formats.map((f) => `.${f}`).join(" ou ") ?? ".hex ou .elf"})
        <input
          type="file"
          accept={cap?.formats.map((f) => `.${f}`).join(",")}
          disabled={busy || !cap?.available}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void load(file);
          }}
        />
      </label>
      {busy && <p role="status">Validando firmware…</p>}
      {info && (
        <p className="small" role="status">
          {info}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {component.kind === "esp32_devkitc" && (
        <p className="small">
          Exporte BIN mesclado com bootloader e partições, flash DIO de 4 MiB. Use pelo menos 350 ms
          de simulação para observar a inicialização do exemplo. Wi-Fi/Bluetooth e barramentos ainda
          não estão conectados.
        </p>
      )}
      {component.kind.startsWith("rpi_pico") && (
        <p className="small">
          Na IDE, use clock de {component.kind === "rpi_pico" ? "125" : "150"} MHz. Carregue UF2 ou
          ELF de flash. Serial por UART0/UART1; sinais em 3,3 V.
        </p>
      )}
      <p className="small muted">
        Na Arduino IDE: escolha a placa correta e use Sketch → Exportar binário compilado. O arquivo
        fica salvo dentro do projeto do circuito. A simulação usa análise transitória.
      </p>
    </fieldset>
  );
}
