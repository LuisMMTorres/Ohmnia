# Firmware real para testes

`FirmwareProbe.ino` é código de teste do Ohmnia. Os arquivos `uno.hex`, `nano.hex` e `mega.hex`
foram compilados com Arduino CLI e o pacote oficial `arduino:avr@1.8.8` (AVR GCC
7.3.0-atmel3.6.1-arduino7), em 16 MHz. Não são tradução nem extração do interpretador do Ohmnia.

Para reproduzir, coloque o sketch numa pasta chamada `FirmwareProbe` e execute:

```text
arduino-cli core install arduino:avr@1.8.8
arduino-cli compile --fqbn arduino:avr:uno --output-dir build/uno FirmwareProbe
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 --output-dir build/nano FirmwareProbe
arduino-cli compile --fqbn arduino:avr:mega:cpu=atmega2560 --output-dir build/mega FirmwareProbe
```

Renomeie cada `FirmwareProbe.ino.hex` conforme a placa. O núcleo Arduino AVR incorporado nos
binários é LGPL-2.1-or-later: fontes, licença e instruções de reconstrução estão em
[ArduinoCore-avr](https://github.com/arduino/ArduinoCore-avr). O sketch e os comandos acima
permitem recompilar e religar os firmwares com uma versão modificada do núcleo.


## Pico e ESP32 (21/11/2026)

`PicoProbe.ino`: Arduino-Pico 6.4.0, ferramenta pqt-gcc/pqt-gcc-riscv 5.0.0-9576866.
UF2 gerado pela própria ferramenta, sem alterar instruções. Ponha o sketch na pasta PicoProbe:

```text
arduino-cli core install rp2040:rp2040@6.4.0 --additional-urls https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json
arduino-cli compile --fqbn rp2040:rp2040:rpipico:freq=125 --build-path build/pico --output-dir out/pico PicoProbe
arduino-cli compile --fqbn rp2040:rp2040:rpipico2:freq=150 --build-path build/pico2 --output-dir out/pico2 PicoProbe
arduino-cli compile --fqbn rp2040:rp2040:rpipico2:arch=riscv,freq=150 --build-path build/riscv --output-dir out/riscv PicoProbe
```

Renomeie `PicoProbe.ino.uf2` para `pico.uf2`, `pico2.uf2` e `pico2-riscv.uf2`.
Fontes e licenças para reconstrução/religação com núcleo modificado:
[Arduino-Pico 6.4.0](https://github.com/earlephilhower/arduino-pico/tree/6.4.0) (LGPL-2.1),
[Pico SDK](https://github.com/raspberrypi/pico-sdk) (BSD-3-Clause).

`EspProbe.ino`: núcleo Arduino-ESP32 2.0.17, GCC esp-2021r2-patch5-8.4.0, esptool 4.5.1:

```text
arduino-cli core install esp32:esp32@2.0.17 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli compile --fqbn esp32:esp32:esp32:FlashMode=dio,FlashSize=4M --build-path build/esp32 --output-dir out/esp32 EspProbe
esptool --chip esp32 merge_bin -o esp32.bin --flash_mode dio --flash_size 4MB 0x1000 out/esp32/EspProbe.ino.bootloader.bin 0x8000 out/esp32/EspProbe.ino.partitions.bin 0xe000 boot_app0.bin 0x10000 out/esp32/EspProbe.ino.bin
```

O arquivo `boot_app0.bin` é o distribuído em `tools/partitions` do núcleo instalado.
Fontes e licença (LGPL-2.1 e dependências ESP-IDF com suas respectivas licenças):
[Arduino-ESP32 2.0.17](https://github.com/espressif/arduino-esp32/tree/2.0.17).
Os sketches e comandos permitem reconstruir os binários com versões modificadas dos núcleos.
Os testes não precisam baixar ferramentas nem se conectar a placas USB.
