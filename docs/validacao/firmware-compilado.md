# Firmware compilado — primeira entrega AVR (21/11/2026)

Uno R3, Nano clássico (ATmega328P) e Mega 2560 executam instruções do firmware `.hex` ou
`.elf` em um processo Node.js com AVR8js 0.21.1 (MIT). Não há conversão para o subconjunto
C/C++ do interpretador. O arquivo é salvo junto à placa no projeto.

## Instalar e usar

Pré-requisito adicional: Node.js 20+ disponível ao backend. Na raiz do projeto:

```powershell
.\scripts\setup-firmware.ps1
```

Em outros sistemas: `npm ci --ignore-scripts --prefix backend/src/circuitos/cosim/firmware_worker`.
Se necessário, `CIRCUITOS_NODE` define o caminho do executável Node.

1. Na Arduino IDE, selecione Uno R3, Nano ATmega328P ou Mega 2560.
2. Use **Sketch → Exportar binário compilado**. O bootloader não é necessário.
3. No Ohmnia, selecione a mesma placa e carregue o `.hex` ou `.elf` em **Programação da placa virtual**.
4. Conecte os pinos e simule em análise transitória. O passo máximo é limitado a 10 µs;
   escolha um passo menor para pulsos mais curtos. As ponteiras medem as tensões do circuito
   e as linhas `Serial` aparecem no resultado da co-simulação.
5. **Retirar firmware e usar código-fonte** restaura o programa anterior.

O instalador não altera a IDE nem grava placas USB. O firmware não é executado como programa
do Windows. Esta entrega usa a instalação pelo código-fonte; o pacote executável do Ohmnia
ainda não foi validado com este motor.

## Validação

- O mesmo sketch foi compilado para as três placas com Arduino CLI, `arduino:avr@1.8.8`,
  AVR GCC 7.3.0-atmel3.6.1-arduino7 e clock de 16 MHz. HEX e ELF reais foram executados.
- ADC de A0: 512 para 2,5 V e 256 para 1,25 V. A mudança de D2 altera D13.
- `analogWrite(3, 128)`: duty medido entre 44 % e 56 % em 20 ms (tolerância da janela).
- Com ngspice, a entrada muda no circuito e a saída acompanha. No modelo didático existente
  de saída (5 V, 25 Ω), carga de 1 kΩ: tensão = `5 × 1000 / 1025 V`, tolerância 0,2 %.
- Chrome: carregamento, rejeição de HEX corrompido sem perder o anterior, simulação,
  persistência após recarregar a página e retorno ao código-fonte passaram.
- O instalador do motor foi executado e validado no Windows.
- Suíte completa do backend: **1.145 aprovados, um ignorado**, sem os 11.033 testes de
  datasheet externos (21 min 05 s). Após os últimos ajustes, os **13 testes específicos de
  firmware** passaram novamente. Os **67 testes da interface**, ESLint e build passaram.
- Ruff, mypy e a verificação de sintaxe do motor JavaScript passaram. Texto Serial em UTF-8
  também foi conferido com um sketch compilado que imprime "Tensão".

Os comandos de reprodução dos binários estão em `backend/tests/fixtures/firmware/README.md`.
A imagem é validada por checksum, limites de memória, segmentos/ponto de entrada e arquitetura
ELF. HEX não identifica o microcontrolador: confirme o alvo selecionado na IDE.

## Limites e próximos passos

- GPIO bidirecional, pull-up, ADC, temporizadores/PWM e saída Serial0, nos pinos expostos
  pelo símbolo. A frequência é 16 MHz. As impedâncias e limiares são os modelos didáticos
  existentes do Ohmnia. O acoplamento é amostrado; não certifica temporização elétrica por ciclo.
- I2C/TWI, SPI, EEPROM e watchdog dão erro explícito quando ativados. DHT22/DS18B20
  ainda não têm protocolo no fio para firmware; os modelos atuais atendem ao interpretador.
- Sem GDB, upload USB, bootloader ou recepção serial interativa. No Mega, PCINT e portas
  Serial1–3 também produzem erro explícito. O monitor serial limita a saída a 10.000 linhas.
- **ESP32-DevKitC, RP2040 e RP2350/Pico 2 continuam pendentes.** A interface informa o estado
  e não habilita um carregamento sem motor implementado. Pico 2 também precisa de símbolo.

As próximas entregas devem integrar e validar esses três motores com firmware das ferramentas
padrão, GPIO/ADC e sincronização com o ngspice; depois, ampliar sensores, protocolos e depuração.

## Referências

[AVR8js e licença MIT](https://github.com/wokwi/avr8js),
[compilação Arduino CLI](https://docs.arduino.cc/arduino-cli/commands-reference/arduino-cli_compile),
[pinagem Mega no Arduino AVR Core](https://github.com/arduino/ArduinoCore-avr/blob/master/variants/mega/pins_arduino.h),
[registradores/vetores AVR](https://github.com/avrdudes/avr-libc/blob/main/include/avr/iomxx0_1.h).
`mega.json` registra fontes e SHA-256 dos cabeçalhos usados; os números não foram estimados.
