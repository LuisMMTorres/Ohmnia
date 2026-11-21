// Machine-code execution through rp2350js (MIT); no source interpretation.
import { createInterface } from "node:readline";
import { createRequire } from "node:module";
const { RP2040, RP2350, USBCDC } = createRequire(import.meta.url)("rp2350js");
import installGpioc from "./gpioc.cjs";

let chip, usb;
let serial = [], pending = new Map(), warnings = new Set();
const gpios = [...Array(23).keys(), 26, 27, 28];
function receive(channel, byte) {
  let text = pending.get(channel) ?? "";
  if (byte === 10) {
    if (serial.length < 256)
      serial.push([chip.clock.nanos / 1e9, `${channel}: ${Buffer.from(text, "latin1").toString("utf8")}`]);
    text = "";
  } else if (byte !== 13 && text.length < 1024) text += String.fromCharCode(byte);
  pending.set(channel, text);
}
function initialize(message) {
  chip = message.board === "rpi_pico2"
    ? new RP2350({ coreArch: message.architecture }) : new RP2040();
  if (message.board === "rpi_pico2" && message.architecture === "arm") installGpioc(chip);
  chip.logger = {
    debug() {}, info() {},
    warn(component, message) { if (warnings.size < 20) warnings.add(`${component}: ${message}`); },
    error(component, message) { throw Error(`${component}: ${message}`); },
  };
  chip.flash.set(Buffer.from(message.flash, "base64"));
  chip.reset();
  for (const [name, peripherals, dataRegister] of [["I2C", chip.i2c, 0x10], ["SPI", chip.spi, 8]]) {
    for (const peripheral of peripherals) {
      const write = peripheral.writeUint32.bind(peripheral);
      peripheral.writeUint32 = (offset, value) => {
        if (offset === dataRegister) throw Error(`${name} do firmware ainda não conectado ao circuito`);
        return write(offset, value);
      };
    }
  }
  if (message.board === "rpi_pico") {
    // RP2040's QSPI stage2 config is bypassed: this engine maps XIP directly.
    // Execute the application's real reset vector; no program instruction is replaced.
    chip.core[0].VTOR = 0x10000100;
    chip.core[0].SP = chip.readUint32(0x10000100);
    chip.core[0].PC = chip.readUint32(0x10000104) & ~1;
  }
  for (let i = 0; i < chip.uart.length; i++)
    chip.uart[i].onByte = byte => receive(`UART${i}`, byte);
  usb = new USBCDC(chip.usbCtrl);
  usb.onSerialData = (buffer, length) => {
    for (let i = 0; i < length; i++) receive("USB", buffer[i]);
  };
  return { ready: true };
}
function advance({time, inputs}) {
  const target = time * 1e9;
  if (!Number.isFinite(target) || target < chip.clock.nanos - 100 || target - chip.clock.nanos > 5e8)
    throw Error("Intervalo de firmware inválido (máximo 500 ms por avanço)");
  for (const pin of gpios) {
    const voltage = inputs[`GP${pin}`] ?? 0;
    chip.gpio[pin].setInputValue(voltage >= 1.98);
    if (pin >= 26)
      chip.adc.channelValues[pin - 26] = Math.round(Math.max(0, Math.min(1, voltage / 3.3)) * 4095);
  }
  while (chip.clock.nanos < target) chip.step();
  const output = {
    time: chip.clock.nanos / 1e9,
    states: Object.fromEntries(gpios.map(n => [`GP${n}`, chip.gpio[n].value])),
    serial, warnings: [...warnings],
  };
  serial = []; warnings.clear();
  return output;
}
for await (const line of createInterface({input: process.stdin, crlfDelay: Infinity})) {
  try {
    const message = JSON.parse(line);
    const response = message.command === "init" ? initialize(message) : advance(message);
    process.stdout.write(JSON.stringify(response) + "\n");
  } catch (error) {
    process.stdout.write(JSON.stringify({error: String(error.message ?? error)}) + "\n");
  }
}
