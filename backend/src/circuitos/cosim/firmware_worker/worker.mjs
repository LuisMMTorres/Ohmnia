// AVR8js (MIT): actual AVR instructions, not a translation of Arduino source.
// Mega register/vector/pin facts are attributed in mega.json.
import avr from "avr8js";
import { readFileSync } from "node:fs";
import { createInterface } from "node:readline";

const mega = JSON.parse(readFileSync(new URL("./mega.json", import.meta.url)));
const FREQ = 16000000;
let cpu,
  adc,
  ports,
  mapping,
  serial = [],
  serialLine = "",
  board;

function initialize(msg) {
  board = msg.board;
  const big = board === "arduino_mega";
  if (!["arduino_uno", "arduino_nano", "arduino_mega"].includes(board))
    throw new Error("Placa sem motor de firmware validado");
  const flash = Buffer.from(msg.flash, "base64");
  const words = new Uint16Array(flash.length / 2);
  for (let i = 0; i < words.length; i++) words[i] = flash.readUInt16LE(i * 2);
  cpu = new avr.CPU(words, big ? 0x2100 : 2048);
  cpu.pc = msg.entry / 2;
  ports = {};
  for (const letter of big ? "ABCDEFGHJKL" : "BCD") {
    const config = { ...avr[`port${letter}Config`] };
    if (big) {
      delete config.pinChange;
      config.externalInterrupts = [];
      if (letter === "D" || letter === "E") {
        const start = letter === "D" ? 0 : 4;
        for (let i = start; i < start + 4; i++) {
          config.externalInterrupts[letter === "D" ? i : i] = {
            EICR: mega.registers[i < 4 ? "EICRA" : "EICRB"],
            EIMSK: mega.registers.EIMSK,
            EIFR: mega.registers.EIFR,
            iscOffset: (i % 4) * 2,
            index: i,
            interrupt: (i + 1) * 2,
          };
        }
      }
    }
    ports[letter] = new avr.AVRIOPort(cpu, config);
  }
  mapping = {};
  if (big) {
    for (let i = 0; i < 70; i++)
      mapping[i < 54 ? `D${i}` : `A${i - 54}`] = mega.pins[i];
    const outputs = [
      ["G5", "B7"],
      ["B5", "B6", "B7"],
      ["B4", "H6"],
      ["E3", "E4", "E5"],
      ["H3", "H4", "H5"],
      ["L3", "L4", "L5"],
    ];
    const r = mega.registers,
      v = mega.vectors;
    for (let n = 0; n < 6; n++) {
      const config = {
        ...avr[
          n === 0 ? "timer0Config" : n === 2 ? "timer2Config" : "timer1Config"
        ],
      };
      for (const key of ["TIFR", "TCNT", "TIMSK", "ICR"])
        config[key] = r[`${key}${n}`] ?? 0;
      for (const suffix of ["A", "B", "C"]) {
        config[`TCCR${suffix}`] = r[`TCCR${n}${suffix}`] ?? 0;
        config[`OCR${suffix}`] = r[`OCR${n}${suffix}`] ?? 0;
        config[`comp${suffix}Interrupt`] = v[`TIMER${n}_COMP${suffix}`] ?? 0;
        const pin = outputs[n][suffix.charCodeAt(0) - 65];
        config[`compPort${suffix}`] = pin ? ports[pin[0]].portConfig.PORT : 0;
        config[`compPin${suffix}`] = pin ? Number(pin[1]) : 0;
      }
      config.captureInterrupt = v[`TIMER${n}_CAPT`] ?? 0;
      config.ovfInterrupt = v[`TIMER${n}_OVF`];
      config.externalClockPort = 0;
      if (config.bits === 16) {
        config.OCFC = 8;
        config.OCIEC = 8;
      }
      new avr.AVRTimer(cpu, config);
    }
  } else {
    for (let i = 0; i < 14; i++)
      mapping[`D${i}`] = [i < 8 ? "D" : "B", i < 8 ? i : i - 8];
    for (let i = 0; i < 6; i++) mapping[`A${i}`] = ["C", i];
    for (const config of [avr.timer0Config, avr.timer1Config, avr.timer2Config])
      new avr.AVRTimer(cpu, config);
  }
  const adcOptions = { ...avr.adcConfig };
  if (big) {
    adcOptions.adcInterrupt = mega.vectors.ADC;
    adcOptions.numChannels = 16;
    adcOptions.muxInputMask = 0x3f;
    adcOptions.muxChannels = {};
    for (let i = 0; i < 16; i++)
      adcOptions.muxChannels[i < 8 ? i : 0x20 + i - 8] = {
        type: avr.ADCMuxInputType.SingleEnded,
        channel: i,
      };
  }
  adc = new avr.AVRADC(cpu, adcOptions);
  const uartOptions = { ...avr.usart0Config };
  if (big) {
    uartOptions.rxCompleteInterrupt = mega.vectors.USART0_RX;
    uartOptions.dataRegisterEmptyInterrupt = mega.vectors.USART0_UDRE;
    uartOptions.txCompleteInterrupt = mega.vectors.USART0_TX;
  }
  const uart = new avr.AVRUSART(cpu, uartOptions, FREQ);
  uart.onByteTransmit = (byte) => {
    if (byte === 10 || serialLine.length >= 1024) {
      if (serial.length < 256)
        serial.push([
          cpu.cycles / FREQ,
          Buffer.from(serialLine, "latin1").toString("utf8").replace(/\r$/, ""),
        ]);
      serialLine = "";
    } else serialLine += String.fromCharCode(byte);
  };
  // Do not silently emulate unsupported device protocols as if the sensor answered.
  const unsupported = [
    [0xbc, 4, "I2C/TWI"],
    [0x4c, 64, "SPI"],
    [0x3f, 3, "EEPROM"],
    [0x60, 8, "watchdog"],
  ];
  if (big) {
    unsupported.push([0x68, 7, "PCINT do Mega"]);
    for (let n = 1; n <= 3; n++)
      unsupported.push([mega.registers[`UCSR${n}B`], 0x18, `Serial${n}`]);
  }
  for (const [address, mask, feature] of unsupported) {
    cpu.writeHooks[address] = (value) => {
      if (value & mask)
        throw new Error(
          `${feature}: periférico ainda não conectado ao circuito no modo firmware`,
        );
      cpu.data[address] = value;
      return true;
    };
  }
  return { ready: true, frequency_hz: FREQ };
}

function advance(msg) {
  if (!cpu) throw new Error("Firmware não inicializado");
  const target = Math.floor(msg.time * FREQ);
  if (
    !Number.isSafeInteger(target) ||
    target < 0 ||
    target - cpu.cycles > FREQ / 2
  )
    throw new Error("Avanço de tempo de firmware inválido ou maior que 500 ms");
  for (const [pin, voltage] of Object.entries(msg.inputs ?? {})) {
    if (!Number.isFinite(voltage))
      throw new Error("Tensão de entrada inválida");
    const port = mapping[pin];
    if (port) ports[port[0]].setPin(port[1], voltage >= 3);
    if (/^A\d+$/.test(pin))
      adc.channelValues[Number(pin.slice(1))] = Math.max(
        0,
        Math.min(5, voltage),
      );
  }
  while (cpu.cycles < target) {
    avr.avrInstruction(cpu);
    cpu.tick();
  }
  const states = {};
  for (const [pin, [port, bit]] of Object.entries(mapping))
    states[pin] = ports[port].pinState(bit);
  const output = { time: cpu.cycles / FREQ, states, serial };
  serial = [];
  return output;
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  try {
    const message = JSON.parse(line);
    const response =
      message.command === "init" ? initialize(message) : advance(message);
    process.stdout.write(JSON.stringify(response) + "\n");
  } catch (error) {
    process.stdout.write(
      JSON.stringify({ error: String(error.message ?? error) }) + "\n",
    );
  }
}
