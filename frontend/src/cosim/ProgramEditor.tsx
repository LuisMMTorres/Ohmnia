// Program editor for controllers: Arduino-style code, structured text or ladder (JSON + diagram).
import { useState } from "react";
import { LadderDiagram } from "./LadderDiagram";

const HELP: Record<string, string> = {
  program:
    "Estilo Arduino: setup() e loop(); pinMode, digitalWrite/Read, analogRead (Uno: 0-1023 em " +
    "0-5 V; ESP32: 0-4095, analogReadMilliVolts), analogWrite (PWM 0-255), dacWrite (ESP32, " +
    "pinos 25 e 26), delay, millis, map, constrain, Serial.print/println/printf. O tempo de " +
    "delay() é o tempo simulado do circuito.",
  st:
    "Texto estruturado (IEC 61131-3): VAR ... END_VAR, :=, IF/ELSIF/ELSE/END_IF, CASE, FOR, " +
    "WHILE, blocos TON/TOF/TP (PT := T#5s), CTU/CTD, R_TRIG/F_TRIG, SR/RS e PID (SP, PV, KP, " +
    "TI, TD, OUT_MIN, OUT_MAX). Entradas I0..I5, AI0, AI1 (mA ou V); saídas Q0..Q3, AQ0 (0-10 V).",
  ladder:
    'Degraus ("rungs"): cada degrau é um OU de ramos ("branches"), cada ramo um E de ' +
    "elementos da esquerda para a direita: NO (contato aberto), NC (fechado), P/N (borda), " +
    'CMP ("expr": "AI0 > 12.0"), TON/TOF/TP ("name", "pt": "T#5s"), CTU ("name", "pv", ' +
    '"reset"). Bobinas ("coils"): coil, ncoil, set, reset e move ("dst", "src").',
};

interface Props {
  title: string;
  kind: string; // program | st | ladder
  value: string;
  onSave: (v: string) => void;
  onClose: () => void;
}

export function ProgramEditor({ title, kind, value, onSave, onClose }: Props) {
  const [text, setText] = useState(value);
  const lines = text.split("\n").length;
  let pretty: string | null = null;
  if (kind === "ladder") {
    try {
      pretty = JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      pretty = null;
    }
  }
  return (
    <div className="modal-backdrop" role="dialog" aria-label={title}>
      <div className="modal program-editor">
        <div className="row">
          <h3 className="grow">{title}</h3>
          {pretty && pretty !== text && (
            <button className="secondary small" onClick={() => setText(pretty!)}>
              Organizar JSON
            </button>
          )}
          <button className="secondary" onClick={onClose}>
            Cancelar
          </button>
          <button
            onClick={() => {
              onSave(text);
              onClose();
            }}
          >
            Aplicar
          </button>
        </div>
        <p className="small muted">{HELP[kind]}</p>
        <div className={kind === "ladder" ? "program-split" : ""}>
          <div className="code-area">
            <pre className="line-numbers" aria-hidden>
              {Array.from({ length: lines }, (_, i) => i + 1).join("\n")}
            </pre>
            <textarea
              aria-label="Programa"
              spellCheck={false}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Tab") {
                  e.preventDefault();
                  const el = e.currentTarget;
                  const s = el.selectionStart;
                  setText(`${text.slice(0, s)}  ${text.slice(el.selectionEnd)}`);
                  requestAnimationFrame(() => el.setSelectionRange(s + 2, s + 2));
                }
              }}
            />
          </div>
          {kind === "ladder" && (
            <div className="ladder-view">
              <LadderDiagram source={text} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
