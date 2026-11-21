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
