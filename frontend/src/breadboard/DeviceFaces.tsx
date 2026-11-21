// Real-looking drawings of the devices that stay off the breadboard (sensors, transmitters,
// motors, drives), wired by their terminals. Own drawings, made after the usual look of each
// kind of device; no manufacturer specification is implied by them.
import type { CSSProperties, ReactNode } from "react";

type Pt = [number, number];

/** Where a terminal is drawn (local coordinates) and where its label goes. */
export interface FaceTerminal {
  at: Pt;
  label: Pt;
  /** Label written downwards from the point (dense pin headers). */
  vertical?: boolean;
}

/** Shaft speed of a motor after the simulation (last point of v(<ref>_w)). */
export interface Motion {
  rpm: number;
}

export interface Face {
  terminals: Record<string, FaceTerminal>;
  draw: (motion: Motion | undefined) => ReactNode;
}

const st = (fill: string, stroke = "none", width = 1): CSSProperties => ({
  fill,
  stroke,
  strokeWidth: width,
});
const BOTTOM = 132;

/** Terminals in a row along the bottom (x positions given), labels below. */
function bottomRow(xs: Record<string, number>): Record<string, FaceTerminal> {
  return Object.fromEntries(
    Object.entries(xs).map(([pin, x]) => [pin, { at: [x, BOTTOM], label: [x, BOTTOM + 24] }]),
  );
}

function at(pin: string, x: number, y: number, lx = x, ly = y + 20): [string, FaceTerminal] {
  return [pin, { at: [x, y], label: [lx, ly] }];
}

/** A wire drawn from a point of the device down to its terminal. */
function lead(from: Pt, to: Pt, color: string, key: string) {
  const midY = (from[1] + to[1]) / 2;
  return (
    <path
      key={key}
      d={`M ${from[0]} ${from[1]} C ${from[0]} ${midY}, ${to[0]} ${midY}, ${to[0]} ${to[1]}`}
      style={{ fill: "none", stroke: color, strokeWidth: 2.4, strokeLinecap: "round" }}
    />
  );
}

function screw(x: number, y: number, key: string) {
  return (
    <g key={key}>
      <circle cx={x} cy={y} r={5.5} style={st("#c9ced3", "#59636c", 1)} />
      <line x1={x - 3.5} y1={y} x2={x + 3.5} y2={y} style={st("none", "#59636c", 1.4)} />
    </g>
  );
}

function silk(x: number, y: number, text: string, size = 8, color = "#f3f3f3", anchor = "middle") {
  return (
    <text
      x={x}
      y={y}
      fontSize={size}
      textAnchor={anchor as "middle" | "start" | "end"}
      style={{ fill: color }}
    >
      {text}
    </text>
  );
}

// ------------------------------------------------------------------ rotation of a shaft

/** Direction convention: ω > 0 turns clockwise looking at the shaft end. */
export function rotationText(m: Motion | undefined): string {
  if (!m) return "Simule para ver o sentido de giro";
  if (Math.abs(m.rpm) < 1) return "Parado";
  const dir = m.rpm > 0 ? "horário" : "anti-horário";
  return `${m.rpm > 0 ? "↻" : "↺"} ${dir} · ${Math.abs(m.rpm).toFixed(0)} rpm`;
}

/** Shaft end seen from the front: a coupling disk that spins in the simulated direction. */
function ShaftEnd({ x, y, r, motion }: { x: number; y: number; r: number; motion?: Motion }) {
  const turning = motion && Math.abs(motion.rpm) >= 1;
  const cw = (motion?.rpm ?? 0) > 0;
  const arc = r + 7;
  const arrow = cw
    ? `M ${x - arc} ${y} A ${arc} ${arc} 0 0 1 ${x} ${y - arc}`
    : `M ${x + arc} ${y} A ${arc} ${arc} 0 0 0 ${x} ${y - arc}`;
  const head = cw
    ? `M ${x - 5} ${y - arc - 5} L ${x + 2} ${y - arc} L ${x - 5} ${y - arc + 5}`
    : `M ${x + 5} ${y - arc - 5} L ${x - 2} ${y - arc} L ${x + 5} ${y - arc + 5}`;
  return (
    <g>
      <circle cx={x} cy={y} r={r} style={st("#9aa4ad", "#4a5560", 1.5)} />
      <g
        className={turning ? `bb-spin ${cw ? "cw" : "ccw"}` : undefined}
        style={{ transformOrigin: `${x}px ${y}px`, transformBox: "view-box" }}
      >
        <line x1={x} y1={y - r + 2} x2={x} y2={y + r - 2} style={st("none", "#2b3640", 2)} />
        <circle cx={x} cy={y - r + 5} r={2.5} style={st("#e0442c")} />
      </g>
      <circle cx={x} cy={y} r={r * 0.28} style={st("#5e6973", "#2b3640", 1)} />
      {turning && (
        <>
          <path d={arrow} style={st("none", "#1e7bd6", 2.2)} />
          <path d={head} style={st("none", "#1e7bd6", 2.2)} />
        </>
      )}
    </g>
  );
}

function RotationLabel({ x, y, motion }: { x: number; y: number; motion?: Motion }) {
  return (
    <text x={x} y={y} fontSize={9} textAnchor="middle" style={{ fill: "#1e5fa8" }}>
      {rotationText(motion)}
    </text>
  );
}

// ------------------------------------------------------------------ sensors

const pt100: Face = {
  terminals: Object.fromEntries([
    at("1", 196, BOTTOM, 196, BOTTOM + 24),
    at("2", 236, BOTTOM, 236, BOTTOM + 24),
  ]),
  draw: () => (
    <>
      {/* stainless sheath with the sensing element at the tip */}
      <rect x={14} y={56} width={150} height={14} rx={7} style={st("#c7ccd1", "#7c868f", 1)} />
      <rect x={18} y={59} width={36} height={8} rx={4} style={st("#aeb5bc")} />
      {silk(36, 52, "elemento", 7, "#43515d")}
      {/* zig-zag resistor inside the tip (cutaway) */}
      <path
        d="M 22 63 l 3 -3 l 4 6 l 4 -6 l 4 6 l 4 -6 l 4 6 l 3 -3"
        style={st("none", "#b45a1c", 1.2)}
      />
      {silk(105, 66, "Pt100 · IEC 60751", 7, "#43515d")}
      {/* neck and connection head */}
      <rect x={164} y={58} width={14} height={10} style={st("#9aa3ab", "#6c757d")} />
      <rect x={178} y={30} width={76} height={66} rx={12} style={st("#b9c1c8", "#5e6a74", 1.5)} />
      <rect x={186} y={40} width={60} height={34} rx={4} style={st("#f4f1ea", "#8d8a80")} />
      {screw(202, 57, "s1")}
      {screw(230, 57, "s2")}
      {silk(202, 84, "1", 8, "#24323d")}
      {silk(230, 84, "2", 8, "#24323d")}
      <rect x={210} y={96} width={12} height={14} style={st("#5e6a74")} />
      {lead([202, 62], [196, BOTTOM - 6], "#d03a2b", "l1")}
      {lead([230, 62], [236, BOTTOM - 6], "#f2f2f2", "l2")}
      {silk(216, 24, "cabeçote", 7, "#43515d")}
    </>
  ),
};

/** Round head-mount transmitter ("puck"), the usual 4-20 mA transmitter of a probe head. */
function puck(x: number, y: number, title: string, body: ReactNode) {
  return (
    <g>
      <circle cx={x} cy={y} r={58} style={st("#f1f2f0", "#77818a", 2)} />
      <circle cx={x} cy={y} r={9} style={st("#d5d9dc", "#77818a", 1)} />
      {silk(x, y - 30, title, 9, "#1f3646")}
      {body}
    </g>
  );
}

const tx420: Face = {
  terminals: Object.fromEntries([at("+", 118, 108, 118, 126), at("-", 162, 108, 162, 126)]),
  draw: () =>
    puck(
      140,
      66,
      "4-20 mA",
      <>
        {silk(140, 92, "2 fios · alimentado pelo laço", 6.5, "#40525f")}
        <circle cx={92} cy={58} r={4} style={st("#9aa3ab")} />
        <circle cx={188} cy={58} r={4} style={st("#9aa3ab")} />
      </>,
    ),
};

const tx420Rtd: Face = {
  terminals: Object.fromEntries([
    at("1", 100, 89, 82, 100),
    at("2", 114, 104, 100, 124),
    at("3", 132, 111, 128, 134),
    at("-", 159, 108, 169, 130),
    at("+", 178, 92, 197, 105),
  ]),
  draw: () => (
    <>
      <circle cx={140} cy={66} r={58} style={st("#f1f2f0", "#77818a", 2)} />
      <circle cx={140} cy={66} r={9} style={st("#d5d9dc", "#77818a", 1)} />
      {silk(140, 24, "TT 4-20 mA", 9, "#1f3646")}
      {/* RTD symbol printed on the body: resistor with the slash of a sensing element */}
      <rect x={128} y={32} width={24} height={8} style={st("none", "#1f3646", 1)} />
      <line x1={124} y1={45} x2={156} y2={28} style={st("none", "#1f3646", 1)} />
      {silk(108, 66, "RTD", 8, "#1f3646")}
      {silk(108, 76, "3 fios", 6.5, "#40525f")}
      {silk(174, 66, "LAÇO", 8, "#1f3646")}
      {silk(174, 76, "2 fios", 6.5, "#40525f")}
    </>
  ),
};

const thermocouple: Face = {
  terminals: Object.fromEntries([at("+", 214, 78, 214, 100), at("-", 252, 78, 252, 100)]),
  draw: () => (
    <>
      {/* sheath cut open at the hot junction: two different alloys welded at the tip */}
      <rect x={14} y={56} width={120} height={14} rx={7} style={st("#c7ccd1", "#7c868f", 1)} />
      <path d="M 24 63 L 128 60" style={st("none", "#c0392b", 1.6)} />
      <path d="M 24 63 L 128 66" style={st("none", "#2f6fb5", 1.6)} />
      <circle cx={24} cy={63} r={3.2} style={st("#2b2b2b")} />
      {silk(30, 50, "junta quente", 7, "#43515d", "start")}
      {/* extension cable to the miniature plug */}
      <path d="M 134 63 C 150 63, 156 72, 172 72" style={st("none", "#6d6d6d", 6)} />
      <rect x={172} y={52} width={46} height={40} rx={4} style={st("#f0f0ec", "#7a7a72", 1.5)} />
      {silk(195, 68, "TC", 9, "#24323d")}
      {silk(184, 86, "+", 10, "#24323d")}
      {silk(206, 86, "−", 10, "#24323d")}
      {/* flat pins: the negative one is wider, so the plug only fits one way */}
      <rect x={218} y={62} width={14} height={4} style={st("#d7b650", "#8a7020", 0.8)} />
      <rect x={218} y={74} width={14} height={7} style={st("#d7b650", "#8a7020", 0.8)} />
      {lead([232, 64], [214, 78], "#c0392b", "lp")}
      {lead([232, 77], [252, 78], "#2f6fb5", "ln")}
      {silk(140, 112, "+ e −: polaridade do termopar", 7, "#43515d")}
    </>
  ),
};

const acs712: Face = {
  terminals: Object.fromEntries([
    at("IP+", 44, 58, 22, 62),
    at("IP-", 44, 88, 22, 92),
    at("VCC", 196, 52, 222, 56),
    at("OUT", 196, 72, 222, 76),
    at("GND", 196, 92, 222, 96),
  ]),
  draw: () => (
    <>
      <rect x={30} y={34} width={180} height={78} rx={4} style={st("#1f5fae", "#123c70", 1.5)} />
      {/* screw terminal block for the measured current */}
      <rect x={32} y={44} width={26} height={58} rx={2} style={st("#2c8c3c", "#1d5d27")} />
      {/* Hall-effect IC (SOIC-8) */}
      <rect x={100} y={60} width={34} height={26} rx={2} style={st("#1b1b1b")} />
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <rect x={103 + i * 8} y={55} width={3} height={5} style={st("#c9c9c9")} />
          <rect x={103 + i * 8} y={86} width={3} height={5} style={st("#c9c9c9")} />
        </g>
      ))}
      {silk(117, 76, "ACS712", 6.5)}
      <path d="M 64 56 C 90 56, 92 73, 100 73" style={st("none", "#e9c46a", 2)} />
      <path d="M 64 90 C 90 90, 92 73, 100 73" style={st("none", "#e9c46a", 2)} />
      {silk(80, 106, "IP+ → IP−", 7)}
      {/* 3-pin header */}
      <rect x={188} y={44} width={16} height={56} rx={1} style={st("#1b1b1b")} />
      <circle cx={170} cy={44} r={3} style={st("#e53935")} />
      {silk(150, 47, "PWR", 6)}
      {silk(150, 26, "sensor de corrente (efeito Hall)", 7, "#40525f")}
    </>
  ),
};

const relay: Face = {
  terminals: bottomRow({ A1: 60, A2: 100, COM: 150, NA: 190, NF: 230 }),
  draw: () => (
    <>
      <rect x={60} y={22} width={170} height={84} rx={4} style={st("#2a62c9", "#173d82", 1.5)} />
      {silk(145, 42, "RELÉ", 11)}
      {/* contact diagram printed on the cover */}
      <rect x={82} y={56} width={30} height={14} style={st("none", "#f3f3f3", 1.2)} />
      <line x1={82} y1={76} x2={112} y2={50} style={st("none", "#f3f3f3", 1)} />
      {silk(97, 88, "bobina", 7)}
      <line x1={150} y1={80} x2={182} y2={58} style={st("none", "#f3f3f3", 1.4)} />
      <circle cx={150} cy={80} r={2} style={st("#f3f3f3")} />
      {silk(186, 54, "NA", 7, "#f3f3f3", "start")}
      {silk(186, 86, "NF", 7, "#f3f3f3", "start")}
      {silk(150, 96, "COM", 7)}
      {[60, 100, 150, 190, 230].map((x, i) =>
        lead([x === 60 ? 70 : x === 230 ? 220 : x, 106], [x, BOTTOM - 6], "#9aa0a6", `r${i}`),
      )}
    </>
  ),
};

// ------------------------------------------------------------------ motors

const dcMotor: Face = {
  terminals: Object.fromEntries([at("+", 14, 55, 4, 46), at("-", 14, 83, 4, 100)]),
  draw: (m) => (
    <>
      {/* can (side view) with the end bell, the brush tabs and the shaft */}
      <rect x={36} y={34} width={132} height={70} rx={10} style={st("#c3c9cf", "#56616b", 1.5)} />
      <rect x={30} y={42} width={12} height={54} rx={4} style={st("#3a3f44")} />
      <rect x={60} y={34} width={4} height={70} style={st("#a8b0b8")} />
      <rect x={168} y={46} width={14} height={46} rx={3} style={st("#a4acb4", "#56616b")} />
      <rect x={182} y={65} width={46} height={8} rx={2} style={st("#d2d7dc", "#56616b")} />
      {silk(112, 72, "M", 20, "#33414d")}
      {silk(112, 92, "CC", 9, "#33414d")}
      {/* brush tabs: the terminals; the red dot marks + */}
      <rect x={18} y={52} width={14} height={6} style={st("#d7b650")} />
      <rect x={18} y={80} width={14} height={6} style={st("#d7b650")} />
      <circle cx={36} cy={48} r={2.5} style={st("#d03a2b")} />
      <ShaftEnd x={252} y={69} r={20} motion={m} />
      <RotationLabel x={200} y={124} motion={m} />
    </>
  ),
};

const inductionMotor: Face = {
  terminals: Object.fromEntries([
    at("A", 96, 27, 96, 11),
    at("B", 112, 27, 112, 11),
    at("C", 128, 27, 128, 11),
  ]),
  draw: (m) => (
    <>
      {/* fan cover, finned frame, terminal box on top, feet and shaft */}
      <path d="M 18 40 Q 10 69 18 98 L 40 98 L 40 40 Z" style={st("#7d8b97", "#46525c", 1.5)} />
      {[48, 58, 68, 78, 88].map((y) => (
        <line key={y} x1={16} y1={y} x2={38} y2={y} style={st("none", "#46525c", 1)} />
      ))}
      <rect x={40} y={34} width={140} height={70} rx={6} style={st("#5f87a8", "#2f4a61", 1.5)} />
      {[42, 52, 62, 72, 82, 92].map((y) => (
        <line key={y} x1={44} y1={y} x2={176} y2={y} style={st("none", "#3f6482", 1.4)} />
      ))}
      <rect x={84} y={16} width={56} height={20} rx={3} style={st("#5f87a8", "#2f4a61", 1.5)} />
      <rect x={52} y={104} width={26} height={8} style={st("#46525c")} />
      <rect x={142} y={104} width={26} height={8} style={st("#46525c")} />
      <rect x={180} y={50} width={12} height={38} rx={2} style={st("#4f7593", "#2f4a61")} />
      <rect x={192} y={64} width={36} height={10} rx={2} style={st("#d2d7dc", "#56616b")} />
      <rect x={118} y={62} width={44} height={20} rx={2} style={st("#e9edf0", "#8996a1")} />
      {silk(140, 76, "M 3~", 9, "#24323d")}
      <ShaftEnd x={256} y={69} r={20} motion={m} />
      <RotationLabel x={206} y={124} motion={m} />
    </>
  ),
};

const stepperMotor: Face = {
  terminals: bottomRow({ "A+": 34, "A-": 64, "B+": 94, "B-": 124 }),
  draw: (m) => (
    <>
      {/* square flange (front view) with chamfered corners and mounting holes */}
      <path
        d="M 52 14 L 128 14 L 140 26 L 140 102 L 128 114 L 52 114 L 40 102 L 40 26 Z"
        style={st("#2f3338", "#15181b", 1.5)}
      />
      {[
        [50, 24],
        [130, 24],
        [50, 104],
        [130, 104],
      ].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r={3.5} style={st("#9aa3ab")} />
      ))}
      <circle cx={90} cy={64} r={24} style={st("#b9c0c7", "#5b646c", 1.2)} />
      <ShaftEnd x={90} y={64} r={12} motion={m} />
      {lead([66, 112], [34, BOTTOM - 6], "#d03a2b", "a1")}
      {lead([80, 112], [64, BOTTOM - 6], "#1e63c6", "a2")}
      {lead([100, 112], [94, BOTTOM - 6], "#2e8b3c", "b1")}
      {lead([114, 112], [124, BOTTOM - 6], "#222", "b2")}
      {silk(214, 48, "motor de passo", 9, "#24323d")}
      {silk(214, 62, "bipolar, 4 fios", 8, "#40525f")}
      <RotationLabel x={214} y={84} motion={m} />
    </>
  ),
};

// ------------------------------------------------------------------ drives and switchgear

const stepperDriver: Face = {
  terminals: bottomRow({
    STEP: 22,
    DIR: 50,
    EN: 78,
    GND: 106,
    VM: 150,
    "A+": 178,
    "A-": 206,
    "B+": 234,
    "B-": 262,
  }),
  draw: () => (
    <>
      <rect x={64} y={20} width={150} height={86} rx={3} style={st("#b2232b", "#6e1217", 1.5)} />
      {/* driver IC under a small finned heat sink */}
      <rect x={112} y={38} width={54} height={46} rx={2} style={st("#a9b1b8", "#5f6870")} />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line
          key={i}
          x1={116 + i * 9}
          y1={40}
          x2={116 + i * 9}
          y2={82}
          style={st("none", "#6f7880", 1.6)}
        />
      ))}
      <circle cx={88} cy={44} r={5} style={st("#d9c27a", "#7a6322")} />
      {silk(88, 60, "ajuste I", 6.5)}
      {silk(139, 98, "DRIVER STEP/DIR", 7)}
      {silk(190, 40, "VM", 7)}
      {[22, 50, 78, 106].map((x, i) =>
        lead([70 + i * 8, 106], [x, BOTTOM - 6], "#8a8f96", `c${i}`),
      )}
      {[150, 178, 206, 234, 262].map((x, i) =>
        lead([172 + i * 9, 106], [x, BOTTOM - 6], i === 0 ? "#d03a2b" : "#8a8f96", `p${i}`),
      )}
    </>
  ),
};

/** Keypad of an inverter or soft-starter: display and buttons. */
function keypad(x: number, y: number, text: string) {
  return (
    <g>
      <rect x={x} y={y} width={64} height={46} rx={4} style={st("#2b3036", "#14171a")} />
      <rect x={x + 6} y={y + 6} width={52} height={16} rx={2} style={st("#0e2b1f")} />
      {silk(x + 32, y + 18, text, 10, "#5af08f")}
      {[0, 1, 2].map((i) => (
        <circle key={i} cx={x + 14 + i * 18} cy={y + 34} r={5} style={st("#59626b")} />
      ))}
    </g>
  );
}

const vfd: Face = {
  terminals: bottomRow({ AI: 26, GND: 56, RUN: 86, COM: 116, U: 176, V: 206, W: 236 }),
  draw: () => (
    <>
      <rect x={70} y={8} width={150} height={104} rx={6} style={st("#e9ecee", "#69747e", 1.5)} />
      <rect x={70} y={8} width={150} height={14} rx={6} style={st("#2f5f8a")} />
      {silk(145, 19, "INVERSOR V/f", 8)}
      {keypad(80, 30, "60.0")}
      {silk(112, 88, "Hz", 8, "#24323d")}
      {/* cooling slots */}
      {[0, 1, 2, 3, 4].map((i) => (
        <rect key={i} x={158} y={34 + i * 9} width={52} height={4} rx={2} style={st("#b7bfc6")} />
      ))}
      <rect x={76} y={96} width={70} height={12} rx={1} style={st("#4a8c3c", "#2c5a23")} />
      {silk(111, 105, "comando", 6.5)}
      <rect x={156} y={96} width={58} height={12} rx={1} style={st("#4a8c3c", "#2c5a23")} />
      {silk(185, 105, "U V W", 6.5)}
      {[26, 56, 86, 116].map((x, i) =>
        lead([82 + i * 18, 108], [x, BOTTOM - 6], "#8a8f96", `c${i}`),
      )}
      {[176, 206, 236].map((x, i) =>
        lead([166 + i * 18, 108], [x, BOTTOM - 6], ["#6b4b2a", "#222", "#8a8f96"][i]!, `p${i}`),
      )}
    </>
  ),
};

const softStarter: Face = {
  terminals: Object.fromEntries([
    at("L1", 110, 14, 110, 34),
    at("L2", 140, 14, 140, 34),
    at("L3", 170, 14, 170, 34),
    at("T1", 110, BOTTOM, 110, BOTTOM + 24),
    at("T2", 140, BOTTOM, 140, BOTTOM + 24),
    at("T3", 170, BOTTOM, 170, BOTTOM + 24),
    at("RUN", 236, 72, 262, 76),
    at("COM", 236, 96, 262, 100),
  ]),
  draw: () => (
    <>
      <rect x={92} y={2} width={124} height={142} rx={6} style={st("#e4e7ea", "#69747e", 1.5)} />
      <rect x={92} y={42} width={124} height={12} style={st("#2f5f8a")} />
      {silk(154, 51, "SOFT-STARTER", 7.5)}
      {/* ramp settings and status LEDs */}
      {[0, 1, 2].map((i) => (
        <g key={i}>
          <circle cx={112 + i * 26} cy={74} r={7} style={st("#c9ced3", "#59636c")} />
          <line
            x1={112 + i * 26}
            y1={74}
            x2={112 + i * 26 + 4}
            y2={69}
            style={st("none", "#2b3640", 1.5)}
          />
        </g>
      ))}
      {silk(112, 90, "Vini", 6.5, "#24323d")}
      {silk(138, 90, "tac", 6.5, "#24323d")}
      {silk(164, 90, "Ilim", 6.5, "#24323d")}
      <circle cx={200} cy={70} r={3} style={st("#5af08f")} />
      <circle cx={200} cy={82} r={3} style={st("#f0b35a")} />
      <rect x={214} y={64} width={14} height={40} rx={2} style={st("#4a8c3c", "#2c5a23")} />
      {silk(154, 112, "rede ↑   motor ↓", 7, "#40525f")}
    </>
  ),
};

const contactor: Face = {
  terminals: Object.fromEntries([
    at("A1", 92, 14, 92, 34),
    at("L1", 122, 14, 122, 34),
    at("L2", 150, 14, 150, 34),
    at("L3", 178, 14, 178, 34),
    at("A2", 92, BOTTOM, 92, BOTTOM + 24),
    at("T1", 122, BOTTOM, 122, BOTTOM + 24),
    at("T2", 150, BOTTOM, 150, BOTTOM + 24),
    at("T3", 178, BOTTOM, 178, BOTTOM + 24),
  ]),
  draw: () => (
    <>
      <rect x={76} y={2} width={120} height={142} rx={5} style={st("#d6dade", "#5e6a74", 1.5)} />
      <rect x={84} y={44} width={104} height={56} rx={3} style={st("#c3c9ce", "#7b8790")} />
      {/* contact carrier window and the coil marking */}
      <rect x={118} y={54} width={36} height={18} rx={2} style={st("#3d4650")} />
      <rect x={126} y={58} width={20} height={10} rx={1} style={st("#e0b84a")} />
      {silk(136, 86, "K", 11, "#24323d")}
      {silk(136, 96, "1-3-5 → 2-4-6", 6.5, "#40525f")}
      {silk(92, 112, "bobina", 6.5, "#40525f")}
      {silk(150, 112, "contatos", 6.5, "#40525f")}
    </>
  ),
};

const heater: Face = {
  terminals: bottomRow({ "1": 70, "2": 210 }),
  draw: () => (
    <>
      {/* finned strip heater: resistance element inside a metal sheath */}
      <rect x={60} y={50} width={160} height={30} rx={4} style={st("#b8875a", "#6b4a2b", 1.5)} />
      {Array.from({ length: 15 }, (_, i) => (
        <rect key={i} x={68 + i * 10} y={38} width={4} height={54} rx={1} style={st("#9aa3ab")} />
      ))}
      <rect x={52} y={58} width={10} height={14} style={st("#e8e2d0", "#8d8a80")} />
      <rect x={218} y={58} width={10} height={14} style={st("#e8e2d0", "#8d8a80")} />
      {lead([56, 72], [70, BOTTOM - 6], "#d03a2b", "h1")}
      {lead([224, 72], [210, BOTTOM - 6], "#d03a2b", "h2")}
      {silk(140, 110, "aquecedor resistivo", 8, "#40525f")}
    </>
  ),
};

const pushButton: Face = {
  terminals: bottomRow({ "1": 110, "2": 170 }),
  draw: () => (
    <>
      {/* 22 mm panel push button with its contact block (NA) */}
      <rect x={96} y={78} width={88} height={30} rx={3} style={st("#e3e6e9", "#69747e")} />
      {silk(140, 98, "13 NA 14", 7.5, "#24323d")}
      <circle cx={140} cy={48} r={30} style={st("#c9ced3", "#59636c", 1.5)} />
      <circle cx={140} cy={48} r={21} style={st("#2e9b46", "#1d6a2f", 1.5)} />
      {lead([110, 108], [110, BOTTOM - 6], "#8a8f96", "b1")}
      {lead([170, 108], [170, BOTTOM - 6], "#8a8f96", "b2")}
    </>
  ),
};

// ---------------------------------------------- sensors, modules and controller boards
// Drawn with their pins or connector facing up, so that the leads leave the device straight
// to the board without crossing it. Terminal names follow the simulation model; check the
// silkscreen of your own module before wiring.

const TOP = 16;

/** Terminals along the top edge (x positions given), labels above. */
function topRow(xs: Record<string, number>): Record<string, FaceTerminal> {
  return Object.fromEntries(
    Object.entries(xs).map(([pin, x]) => [pin, { at: [x, TOP], label: [x, TOP - 8] }]),
  );
}

/** A dense pin header: terminals every ``pitch`` from ``x0`` at height ``y``, labels written
 * downwards over the board's silkscreen. */
function header(pins: string[], x0: number, pitch: number, y: number) {
  return Object.fromEntries(
    pins.map((pin, i) => [
      pin,
      { at: [x0 + i * pitch, y], label: [x0 + i * pitch + 2, y + 8], vertical: true },
    ]),
  ) as Record<string, FaceTerminal>;
}

/** A leg (tinned wire) going up from a body (at ``from``, default straight below) to its
 * terminal at ``x``. */
function leg(x: number, y0: number, key: string, color = "#b9bec4", from = x) {
  return (
    <path
      key={key}
      d={`M ${from} ${y0} V ${y0 - 8} L ${x} ${TOP + 6} V ${TOP}`}
      style={st("none", color, 2.2)}
    />
  );
}

/** Row of square header pins drawn on a board (decorative, the terminals are on top). */
function pinStrip(x0: number, y: number, n: number, pitch: number, key: string) {
  return (
    <g key={key}>
      <rect x={x0 - 4} y={y - 4} width={(n - 1) * pitch + 8} height={8} style={st("#1d1d1d")} />
      {Array.from({ length: n }, (_, i) => (
        <rect
          key={i}
          x={x0 + i * pitch - 1.5}
          y={y - 1.5}
          width={3}
          height={3}
          style={st("#d8c27a")}
        />
      ))}
    </g>
  );
}

/** TO-92 body (flat face towards the viewer) with its legs going up. */
function to92(cx: number, top: number, marking: string, legs: number[], color = "#1c1c1c") {
  return (
    <>
      {legs.map((x, i) =>
        leg(x, top + 4, `l${i}`, "#b9bec4", cx + (i - (legs.length - 1) / 2) * 12),
      )}
      <path
        d={`M ${cx - 18} ${top} L ${cx + 18} ${top} L ${cx + 18} ${top + 30} A 18 18 0 0 1 ${cx - 18} ${top + 30} Z`}
        style={st(color, "#000", 1)}
      />
      {silk(cx, top + 20, marking, 6.5)}
    </>
  );
}

const ntc: Face = {
  terminals: topRow({ "1": 128, "2": 152 }),
  draw: () => (
    <>
      {/* epoxy-coated disc thermistor on two tinned legs */}
      {leg(128, 70, "a")}
      {leg(152, 70, "b")}
      <ellipse cx={140} cy={84} rx={20} ry={17} style={st("#2f3b8f", "#1d2560", 1.2)} />
      {silk(140, 87, "NTC", 7)}
      {silk(140, 126, "termistor NTC (disco)", 8, "#40525f")}
    </>
  ),
};

const ldr: Face = {
  terminals: topRow({ "1": 128, "2": 152 }),
  draw: () => (
    <>
      {/* light dependent resistor: ceramic disc with the CdS track under clear lacquer */}
      {leg(128, 66, "a")}
      {leg(152, 66, "b")}
      <circle cx={140} cy={86} r={22} style={st("#f1e7cf", "#b9a67a", 1.5)} />
      <path
        d="M 124 74 H 156 V 79 H 124 V 84 H 156 V 89 H 124 V 94 H 156 V 99 H 124"
        style={st("none", "#c2621e", 2)}
      />
      <rect x={120} y={70} width={6} height={32} style={st("#d6d6d6")} />
      <rect x={154} y={70} width={6} height={32} style={st("#d6d6d6")} />
      {silk(140, 128, "LDR (fotorresistor)", 8, "#40525f")}
    </>
  ),
};

const kty81: Face = {
  terminals: topRow({ "1": 130, "2": 150 }),
  draw: () => (
    <>
      {/* silicon sensor in a two-leg plastic package */}
      {to92(140, 66, "KTY81", [130, 150])}
      {silk(140, 132, "sensor de temperatura de silício", 8, "#40525f")}
    </>
  ),
};

function hallFace(marking: string, text: string): Face {
  return {
    terminals: topRow({ VS: 112, GND: 140, OUT: 168 }),
    draw: () => (
      <>
        {/* Hall-effect sensor in a flat TO-92 (SIP-3) package, branded face to the viewer */}
        {to92(140, 66, marking, [112, 140, 168])}
        {silk(140, 132, text, 8, "#40525f")}
      </>
    ),
  };
}

const pressure: Face = {
  terminals: topRow({ VS: 112, GND: 140, OUT: 168 }),
  draw: () => (
    <>
      {/* integrated pressure sensor: SIP package with a pressure port */}
      {[112, 140, 168].map((x, i) => leg(x, 54, `p${i}`, "#b9bec4", 126 + i * 14))}
      <rect x={96} y={54} width={100} height={46} rx={4} style={st("#e6e6e6", "#8a8f96", 1.4)} />
      <circle cx={146} cy={77} r={13} style={st("#cfd3d6", "#7d848b", 1.2)} />
      <rect x={196} y={70} width={34} height={14} rx={3} style={st("#d6d9dc", "#7d848b")} />
      <circle cx={146} cy={77} r={4} style={st("#5d646a")} />
      {silk(112, 96, "P", 7, "#40525f")}
      {silk(150, 124, "sensor de pressão integrado", 8, "#40525f")}
    </>
  ),
};

const ultrasonic: Face = {
  terminals: topRow({ VCC: 98, TRIG: 126, ECHO: 154, GND: 182 }),
  draw: () => (
    <>
      {/* HC-SR04 module seen from the front, header up: two 16 mm transducers */}
      {[98, 126, 154, 182].map((x, i) => leg(x, 34, `h${x}`, "#b9bec4", 116 + i * 16))}
      <rect x={40} y={30} width={200} height={84} rx={3} style={st("#1d5fa8", "#123d70", 1.5)} />
      {pinStrip(116, 36, 4, 16, "hdr")}
      {[88, 192].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy={76} r={32} style={st("#c9ced3", "#6b737a", 2)} />
          <circle cx={cx} cy={76} r={24} style={st("#2a2a2a")} />
          {Array.from({ length: 5 }, (_, i) => (
            <line
              key={i}
              x1={cx - 22}
              x2={cx + 22}
              y1={64 + i * 6}
              y2={64 + i * 6}
              style={st("none", "#555", 1)}
            />
          ))}
        </g>
      ))}
      <rect x={128} y={92} width={24} height={9} rx={4} style={st("#c9ced3", "#6b737a")} />
      {silk(88, 122, "T", 8, "#40525f")}
      {silk(192, 122, "R", 8, "#40525f")}
      {silk(140, 52, "HC-SR04", 8)}
    </>
  ),
};

const dht22: Face = {
  // pin 1 VCC, 2 DATA, 3 NC, 4 GND (SparkFun RHT03/DHT22 hookup guide)
  terminals: topRow({ VCC: 98, DATA: 124, GND: 176 }),
  draw: () => (
    <>
      {/* white housing with the ventilation grille; pins up */}
      {[98, 124, 150, 176].map((x, i) =>
        leg(x, 40, `p${i}`, i === 2 ? "#8d9399" : "#b9bec4", 113 + i * 18),
      )}
      <rect x={100} y={40} width={80} height={96} rx={4} style={st("#f4f4f2", "#9da3a8", 1.5)} />
      {Array.from({ length: 6 }, (_, r) =>
        Array.from({ length: 4 }, (_, c) => (
          <rect
            key={`${r}-${c}`}
            x={110 + c * 16}
            y={50 + r * 12}
            width={10}
            height={7}
            rx={1}
            style={st("#c3c7ca")}
          />
        )),
      )}
      {silk(150, TOP - 8, "NC", 6.5, "#40525f")}
      {silk(140, 130, "DHT22", 8, "#40525f")}
    </>
  ),
};

const ds18b20: Face = {
  // TO-92, bottom view: 1 GND, 2 DQ, 3 VDD (datasheet table 1); drawn flat face to the viewer
  // with the legs up, so the order reads VDD, DQ, GND from left to right
  terminals: topRow({ VDD: 112, DQ: 140, GND: 168 }),
  draw: () => (
    <>
      {to92(140, 66, "18B20", [112, 140, 168])}
      {silk(140, 132, "termômetro digital 1-Wire (TO-92)", 8, "#40525f")}
    </>
  ),
};

const bme280: Face = {
  terminals: topRow({ VDD: 98, GND: 126, SCL: 154, SDA: 182 }),
  draw: () => (
    <>
      {/* small purple breakout with a 4-pin header and the metal-lid sensor */}
      {[98, 126, 154, 182].map((x, i) => leg(x, 40, `h${x}`, "#b9bec4", 116 + i * 16))}
      <rect x={96} y={36} width={88} height={84} rx={4} style={st("#5b2c8a", "#3a1a5c", 1.5)} />
      {pinStrip(116, 44, 4, 16, "hdr")}
      <rect x={130} y={78} width={20} height={20} rx={2} style={st("#c8ccd0", "#7d848b")} />
      <circle cx={136} cy={84} r={1.6} style={st("#5d646a")} />
      {[106, 174].map((x) => (
        <circle key={x} cx={x} cy={110} r={5} style={st("#2a1640", "#d8c27a", 1.5)} />
      ))}
      {silk(140, 64, "BME280", 7)}
      {silk(140, 136, "I2C", 8, "#40525f")}
    </>
  ),
};

// controller boards: the modelled pins on top, in the order of the model
const NANO = ["D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13",
  "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "5V", "GND"]; // prettier-ignore

const nano: Face = {
  terminals: header(NANO, 20, 12, TOP),
  draw: () => (
    <>
      {/* Nano: narrow blue board, Mini-B USB at one end, ATmega328P in TQFP */}
      <rect
        x={6}
        y={TOP - 6}
        width={276}
        height={124}
        rx={4}
        style={st("#1f5fae", "#123c70", 1.5)}
      />
      {pinStrip(20, TOP, 22, 12, "top")}
      {pinStrip(20, TOP + 110, 22, 12, "bot")}
      <rect x={-2} y={TOP + 42} width={26} height={26} rx={2} style={st("#c9ced3", "#6b737a")} />
      <rect
        x={128}
        y={TOP + 66}
        width={30}
        height={30}
        transform={`rotate(45 143 ${TOP + 81})`}
        style={st("#1b1b1b")}
      />
      <rect x={210} y={TOP + 70} width={16} height={10} rx={2} style={st("#e8e8e8", "#9da3a8")} />
      {silk(218, TOP + 92, "RESET", 6)}
      {silk(80, TOP + 92, "Arduino Nano", 8)}
    </>
  ),
};

const MEGA = ["D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13",
  "D20", "D21", "D22", "D23", "D24", "D25", "D26", "D27", "D28", "D29",
  "D44", "D45", "D46", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10",
  "A11", "A12", "A13", "A14", "A15", "5V", "GND"]; // prettier-ignore

const mega: Face = {
  terminals: {
    ...header(MEGA.slice(0, 22), 14, 12.4, TOP),
    ...header(MEGA.slice(22), 14, 12.4, TOP + 56),
  },
  draw: () => (
    <>
      {/* Mega 2560: long blue-green board, USB-B and barrel jack at the left end */}
      <rect
        x={0}
        y={TOP - 6}
        width={288}
        height={138}
        rx={4}
        style={st("#0e7c86", "#095057", 1.5)}
      />
      {pinStrip(14, TOP, 22, 12.4, "h1")}
      {pinStrip(14, TOP + 56, 21, 12.4, "h2")}
      <rect x={-8} y={TOP + 92} width={34} height={28} rx={2} style={st("#c9ced3", "#6b737a")} />
      <rect x={30} y={TOP + 100} width={30} height={22} rx={2} style={st("#1b1b1b")} />
      <rect
        x={150}
        y={TOP + 92}
        width={34}
        height={34}
        transform={`rotate(45 167 ${TOP + 109})`}
        style={st("#1b1b1b")}
      />
      {silk(236, TOP + 116, "MEGA 2560", 8)}
    </>
  ),
};

const PICO = ["GP0", "GP1", "GP2", "GP3", "GP4", "GP5", "GP6", "GP7", "GP8", "GP9", "GP10",
  "GP11", "GP12", "GP13", "GP14", "GP15", "GP16", "GP17", "GP18", "GP19", "GP20", "GP21",
  "GP22", "GP26", "GP27", "GP28", "3V3", "GND"]; // prettier-ignore

const pico: Face = {
  terminals: {
    ...header(PICO.slice(0, 14), 26, 17, TOP),
    ...header(PICO.slice(14), 26, 17, TOP + 62),
  },
  draw: () => (
    <>
      {/* Pico: green board with castellated edges, micro-USB at one end, RP2040 */}
      <rect
        x={8}
        y={TOP - 8}
        width={262}
        height={134}
        rx={3}
        style={st("#2f7d32", "#1b4d1e", 1.5)}
      />
      {Array.from({ length: 14 }, (_, i) => (
        <g key={i}>
          <circle cx={26 + i * 17} cy={TOP} r={4} style={st("#d8c27a")} />
          <circle cx={26 + i * 17} cy={TOP + 62} r={4} style={st("#d8c27a")} />
        </g>
      ))}
      <rect x={-2} y={TOP + 96} width={22} height={18} rx={2} style={st("#c9ced3", "#6b737a")} />
      <rect x={120} y={TOP + 92} width={26} height={26} style={st("#1b1b1b")} />
      {silk(133, TOP + 108, "RP2040", 6)}
      <rect x={60} y={TOP + 98} width={16} height={12} rx={2} style={st("#f4f4f2", "#9da3a8")} />
      {silk(68, TOP + 122, "BOOTSEL", 5.5)}
      {silk(220, TOP + 112, "Raspberry Pi Pico", 7.5)}
    </>
  ),
};

const PLC_IN = ["L+", "M", "I0", "I1", "I2", "I3", "I4", "I5", "AI0", "AI1"];
const PLC_OUT = ["Q0a", "Q0b", "Q1a", "Q1b", "Q2a", "Q2b", "Q3a", "Q3b", "AQ0"];

const plc: Face = {
  terminals: {
    ...Object.fromEntries(
      PLC_IN.map((p, i) => [p, { at: [22 + i * 26, TOP], label: [22 + i * 26, TOP - 8] }]),
    ),
    ...Object.fromEntries(
      PLC_OUT.map((p, i) => [p, { at: [22 + i * 26, TOP + 26], label: [22 + i * 26, TOP + 44] }]),
    ),
  } as Record<string, FaceTerminal>,
  draw: () => (
    <>
      {/* compact PLC on a DIN rail: grey housing, screw terminals for supply, inputs and
          outputs, status LEDs and a small display */}
      <rect x={-2} y={TOP + 64} width={292} height={12} style={st("#b0b6bb", "#7d848b")} />
      <rect
        x={6}
        y={TOP - 10}
        width={276}
        height={140}
        rx={5}
        style={st("#dfe3e6", "#7d848b", 1.5)}
      />
      <rect x={10} y={TOP - 7} width={268} height={14} style={st("#9aa3ab")} />
      <rect x={10} y={TOP + 19} width={242} height={14} style={st("#9aa3ab")} />
      {PLC_IN.map((p, i) => screw(22 + i * 26, TOP, `i${p}`))}
      {PLC_OUT.map((p, i) => screw(22 + i * 26, TOP + 26, `o${p}`))}
      <rect x={30} y={TOP + 56} width={110} height={44} rx={3} style={st("#1d3b2a", "#0d2016")} />
      {silk(85, TOP + 82, "CLP 24 V CC", 9, "#9be7b0")}
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <circle key={i} cx={164 + i * 16} cy={TOP + 66} r={3.5} style={st("#6fcf73")} />
      ))}
      {silk(204, TOP + 84, "I0 … I5", 6.5, "#40525f")}
      {[0, 1, 2, 3].map((i) => (
        <circle key={i} cx={164 + i * 16} cy={TOP + 98} r={3.5} style={st("#f2a33a")} />
      ))}
      {silk(188, TOP + 116, "Q0 … Q3", 6.5, "#40525f")}
    </>
  ),
};

const pumpPlant: Face = {
  terminals: {
    ...topRow({ AI: 24, GND: 46, RUN: 68, COM: 90 }),
    ...topRow({ "PT+": 226, "PT-": 248 }),
  },
  draw: () => (
    <>
      {/* frequency inverter, induction motor and centrifugal pump with a pressure transmitter */}
      <rect
        x={10}
        y={TOP - 6}
        width={96}
        height={118}
        rx={4}
        style={st("#e8ebee", "#7d848b", 1.5)}
      />
      {[24, 46, 68, 90].map((x) => screw(x, TOP, `s${x}`))}
      <rect x={22} y={TOP + 22} width={70} height={30} rx={2} style={st("#1d3b2a")} />
      {silk(57, TOP + 42, "60,0 Hz", 9, "#9be7b0")}
      {silk(57, TOP + 70, "inversor", 7.5, "#40525f")}
      <path d={`M 106 ${TOP + 80} H 120`} style={st("none", "#59636c", 4)} />
      <rect
        x={120}
        y={TOP + 56}
        width={56}
        height={46}
        rx={6}
        style={st("#3c5a78", "#22374b", 1.5)}
      />
      {Array.from({ length: 5 }, (_, i) => (
        <line
          key={i}
          x1={124}
          x2={172}
          y1={TOP + 62 + i * 9}
          y2={TOP + 62 + i * 9}
          style={st("none", "#2b4560", 1.5)}
        />
      ))}
      <rect x={176} y={TOP + 74} width={10} height={10} style={st("#9aa3ab")} />
      <circle cx={204} cy={TOP + 80} r={20} style={st("#2d6fb0", "#1a4570", 1.5)} />
      <rect x={196} y={TOP + 32} width={16} height={30} style={st("#9aa3ab", "#6b737a")} />
      <rect x={196} y={TOP + 22} width={70} height={12} style={st("#9aa3ab", "#6b737a")} />
      {/* pressure transmitter on the discharge pipe */}
      <rect x={226} y={TOP + 2} width={22} height={20} rx={3} style={st("#c9ced3", "#6b737a")} />
      {leg(226, TOP + 4, "pt1", "#d03a2b")}
      {leg(248, TOP + 4, "pt2", "#222")}
      {silk(237, TOP + 50, "PT", 7, "#40525f")}
      {silk(150, TOP + 118, "motor", 7.5, "#40525f")}
      {silk(204, TOP + 118, "bomba", 7.5, "#40525f")}
    </>
  ),
};

// --------------------------------------------------------------- transformers and lamps

/** Laminated E-I core (front view) with the winding window filled by the bobbin. */
function eiCore(x: number, y: number, w: number, h: number, key: string) {
  return (
    <g key={key}>
      <rect x={x} y={y} width={w} height={h} style={st("#5f666d", "#3a4046", 1.5)} />
      {Array.from({ length: Math.floor(h / 4) }, (_, i) => (
        <line
          key={i}
          x1={x}
          x2={x + w}
          y1={y + 2 + i * 4}
          y2={y + 2 + i * 4}
          style={st("none", "#4b5157", 0.8)}
        />
      ))}
    </g>
  );
}

function coil(x: number, y: number, w: number, h: number, color: string, key: string) {
  return (
    <g key={key}>
      <rect x={x} y={y} width={w} height={h} rx={3} style={st(color, "#5c3a12", 1.2)} />
      {Array.from({ length: Math.floor(h / 5) }, (_, i) => (
        <line
          key={i}
          x1={x + 2}
          x2={x + w - 2}
          y1={y + 3 + i * 5}
          y2={y + 3 + i * 5}
          style={st("none", "#8a5a24", 1)}
        />
      ))}
    </g>
  );
}

const transformer1ph: Face = {
  terminals: topRow({ p1: 64, p2: 92, s1: 188, s2: 216 }),
  draw: () => (
    <>
      {/* single-phase E-I transformer with a terminal strip on top: primary left, secondary
          right */}
      <rect x={46} y={TOP - 8} width={188} height={18} rx={2} style={st("#efe9dc", "#a39a86")} />
      {[64, 92, 188, 216].map((x) => screw(x, TOP, `t${x}`))}
      {silk(78, TOP + 30, "PRIMÁRIO", 7, "#40525f")}
      {silk(202, TOP + 30, "SECUNDÁRIO", 7, "#40525f")}
      {eiCore(70, TOP + 36, 140, 92, "core")}
      {coil(104, TOP + 46, 32, 72, "#c9822f", "cp")}
      {coil(144, TOP + 46, 32, 72, "#d99a45", "cs")}
      <rect x={70} y={TOP + 36} width={140} height={10} style={st("#6b7279", "#3a4046")} />
      <rect x={70} y={TOP + 118} width={140} height={10} style={st("#6b7279", "#3a4046")} />
      {lead([120, TOP + 46], [64, TOP + 8], "#c62828", "lp1")}
      {lead([124, TOP + 46], [92, TOP + 8], "#c62828", "lp2")}
      {lead([156, TOP + 46], [188, TOP + 8], "#1f5fae", "ls1")}
      {lead([160, TOP + 46], [216, TOP + 8], "#1f5fae", "ls2")}
    </>
  ),
};

const transformer3ph: Face = {
  terminals: topRow({
    H1: 18,
    H2: 46,
    H3: 74,
    H0: 102,
    X1: 178,
    X2: 206,
    X3: 234,
    X0: 262,
  }),
  draw: () => (
    <>
      {/* three-limb core, one primary and one secondary coil on each limb; terminal strips on
          top (H: primary, X: secondary) */}
      <rect x={4} y={TOP - 8} width={112} height={18} rx={2} style={st("#efe9dc", "#a39a86")} />
      <rect x={164} y={TOP - 8} width={112} height={18} rx={2} style={st("#efe9dc", "#a39a86")} />
      {[18, 46, 74, 102, 178, 206, 234, 262].map((x) => screw(x, TOP, `t${x}`))}
      {silk(60, TOP + 24, "AT (H)", 7, "#40525f")}
      {silk(220, TOP + 24, "BT (X)", 7, "#40525f")}
      {eiCore(36, TOP + 34, 212, 100, "core")}
      {[60, 128, 196].map((x, i) => (
        <g key={x}>
          {coil(x, TOP + 44, 30, 80, "#c9822f", `p${i}`)}
          <rect
            x={x + 6}
            y={TOP + 44}
            width={18}
            height={80}
            rx={2}
            style={{ ...st("#e0aa5a", "#8a5a24", 1), opacity: 0.85 }}
          />
          {silk(x + 15, TOP + 88, "ABC"[i]!, 9, "#5c3a12")}
        </g>
      ))}
      <rect x={36} y={TOP + 34} width={212} height={10} style={st("#6b7279", "#3a4046")} />
      <rect x={36} y={TOP + 124} width={212} height={10} style={st("#6b7279", "#3a4046")} />
    </>
  ),
};

const lamp: Face = {
  terminals: topRow({ "1": 118, "2": 162 }),
  draw: () => (
    <>
      {/* incandescent bulb in a screw socket (lamp holder) with two screw terminals */}
      <rect
        x={102}
        y={TOP - 8}
        width={76}
        height={34}
        rx={6}
        style={st("#f2efe8", "#9d968a", 1.5)}
      />
      {screw(118, TOP, "s1")}
      {screw(162, TOP, "s2")}
      <rect x={116} y={TOP + 26} width={48} height={22} style={st("#c9ced3", "#6b737a", 1.2)} />
      {[0, 1, 2, 3].map((i) => (
        <line
          key={i}
          x1={116}
          x2={164}
          y1={TOP + 30 + i * 5}
          y2={TOP + 32 + i * 5}
          style={st("none", "#8a9097", 1.2)}
        />
      ))}
      <path
        d={`M 120 ${TOP + 48} C 92 ${TOP + 70}, 96 ${TOP + 132}, 140 ${TOP + 134} C 184 ${TOP + 132}, 188 ${TOP + 70}, 160 ${TOP + 48} Z`}
        style={{ ...st("#fff8dc", "#b9b29c", 1.5), opacity: 0.9 }}
      />
      <path
        d={`M 132 ${TOP + 52} L 132 ${TOP + 96} M 148 ${TOP + 52} L 148 ${TOP + 96}`}
        style={st("none", "#8a8f96", 1.2)}
      />
      <path d={`M 132 ${TOP + 96} q 4 -6 8 0 q 4 6 8 0`} style={st("none", "#c77b1e", 1.6)} />
    </>
  ),
};

const FACES: Record<string, Face> = {
  heater,
  switch_manual: pushButton,
  pt100,
  tx420,
  tx420_rtd: tx420Rtd,
  thermocouple,
  acs712,
  relay,
  dc_motor: dcMotor,
  induction_motor: inductionMotor,
  stepper_motor: stepperMotor,
  stepper_driver: stepperDriver,
  vfd,
  soft_starter: softStarter,
  contactor,
  ntc,
  ldr,
  kty81,
  hall_linear: hallFace("49E", "sensor Hall linear (TO-92)"),
  hall_switch: hallFace("3144", "chave Hall (TO-92)"),
  pressure,
  ultrasonic,
  dht22,
  ds18b20,
  bme280,
  arduino_nano: nano,
  arduino_mega: mega,
  rpi_pico: pico,
  plc,
  pump_plant: pumpPlant,
  transformer: transformer1ph,
  transformer_1ph: transformer1ph,
  transformer_3ph: transformer3ph,
  lamp,
};

export const MOTOR_KINDS = new Set(["dc_motor", "induction_motor", "stepper_motor"]);

export function deviceFace(kind: string): Face | undefined {
  return FACES[kind];
}
