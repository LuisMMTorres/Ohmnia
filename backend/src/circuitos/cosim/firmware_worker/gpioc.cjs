// See LICENSE-rp2350js.txt for the upstream engine authors and MIT notice.
// RP2350 GPIO coprocessor (CP0), pico-sdk hardware/gpio_coproc.h encodings.
// Compatibility correction for rp2350js 2.0.1's CP0 register/opcode decoding.
// https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2350/hardware_structs/include/hardware/structs/sio.h
// https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_gpio/include/hardware/gpio_coproc.h
module.exports = function install(chip) {
  const path = require("node:path");
  const modulePath = path.join(path.dirname(require.resolve("rp2350js")), "cortex-m33/coprocessor.js");
  const module = require(modulePath);
  const original = module.coprocessorExecute;
  module.coprocessorExecute = function(core, hw0, hw1) {
    if (((hw1 >>> 8) & 15) !== 0) return original(core, hw0, hw1);
    if (!(core.ppb().cpacr & 3)) return original(core, hw0, hw1);
    const r = core.regs.r, crm = hw1 & 15, rt = hw1 >>> 12 & 15;
    const base = {0: 0x10, 4: 0x30, 8: 4}[crm & 14];
    const read = !!(hw0 & 16), pair = (hw0 >>> 8 & 0xef) === 0xec;
    const write = (hi, op, value) => {
      if (base !== 0x10 && base !== 0x30) return;
      const alias = [0, 0x18, 8, 0x10][op];
      chip.sio.writeUint32(base + (hi ? 4 : 0) + alias, value >>> 0, core.coreIndex);
    };
    const bit = (pin, op) => write(pin >= 32, op, 1 << (pin & 31));
    const get = hi => base === undefined ? 0 : chip.sio.readUint32(base + (hi ? 4 : 0), core.coreIndex) >>> 0;
    if (pair) {
      const op = hw1 >>> 4 & 15, rt2 = hw0 & 15;
      if (read) { r[rt] = get(false); r[rt2] = get(true); }
      else if (op <= 3) { write(false, op, r[rt]); write(true, op, r[rt2]); }
      else if (op === 4) bit(r[rt] & 63, r[rt2] & 1 ? 2 : 3);
      else if (op <= 7) { if (r[rt2] & 1) bit(r[rt] & 63, op - 4); }
      else if (op <= 11) write(!!(r[rt2] & 1), op - 8, r[rt]);
      else throw Error("Operação GPIOC ainda não suportada");
    } else if (hw1 & 16) {
      const op = hw0 >>> 5 & 7;
      if (read) {
        const value = get(!!(crm & 1));
        if (rt === 15) core.regs.xpsr = (core.regs.xpsr & 0x0fffffff) | (value & 0xf0000000);
        else r[rt] = value;
      } else if (op <= 3) write(!!(crm & 1), op, r[rt]);
      else if (op >= 5) bit(r[rt] & 63, op - 4);
      else throw Error("Operação GPIOC ainda não suportada");
    } else throw Error("Instrução GPIOC ainda não suportada");
    return 1;
  };
};
