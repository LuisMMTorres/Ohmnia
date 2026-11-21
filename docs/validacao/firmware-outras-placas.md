# Firmware compilado — ESP32, Pico e Pico 2

Entrega de 21/11/2026, em continuação à [fase AVR](firmware-compilado.md).
As placas executam instruções dos arquivos compilados; o código-fonte interpretado continua
disponível como outro modo. O firmware e a placa de destino são salvos no projeto.

## Instalação pelo código-fonte

Node.js 20+ e as dependências normais do Ohmnia são necessários. Na raiz do repositório:

```powershell
.\scripts\setup-firmware.ps1 -Esp32
```

O comando instala AVR8js 0.21.1 e rp2350js 2.0.1 com lockfile e scripts npm desabilitados.
Com `-Esp32`, baixa etree-esp32 1.1.0 para `var/tools`, verifica o SHA-256 antes da extração
e preserva as licenças. Não é necessário que `var` exista no GitHub: o instalador a cria.
Reinicie o backend depois da instalação. Para apenas AVR/Pico, omita `-Esp32`.

`CIRCUITOS_NODE` pode apontar para Node fora do PATH. `CIRCUITOS_ESP32_ENGINE` permite indicar
outra instalação de `etree-esp32.exe`. O motor ESP32 desta entrega requer Windows e Python
de 64 bits. AVR e Pico não dependem desse executável. A distribuição empacotada do Ohmnia
ainda não foi validada com estes motores; estes passos são para execução pelo código-fonte.

## Compilar e carregar

| Placa na Biblioteca | Formato | Configuração validada |
| --- | --- | --- |
| Arduino Uno R3 / Nano / Mega 2560 | HEX ou ELF | Núcleo AVR, 16 MHz, conforme a primeira fase |
| Raspberry Pi Pico | UF2 ou ELF de flash | Arduino-Pico, RP2040, CPU de 125 MHz |
| Raspberry Pi Pico 2 | UF2 ou ELF de flash | Arduino-Pico, RP2350, CPU de 150 MHz, ARM ou RISC-V |
| ESP32-DevKitC | BIN mesclado | ESP32 clássico/WROOM-32, flash DIO de 4 MiB |

Na Arduino IDE, selecione a placa e o clock indicados, compile e use **Sketch → Exportar
binário compilado**. Para Pico/Pico 2 foi validado o núcleo Arduino-Pico 6.4.0 de Earle
Philhower; para ESP32, o núcleo Espressif 2.0.17. Outras versões e bibliotecas não têm
compatibilidade garantida apenas por produzirem o mesmo formato.

No Ohmnia, selecione a placa no esquemático ou na protoboard e use **Programação da placa
virtual → Carregar firmware da IDE**. O seletor mostra somente os formatos daquele alvo.
Um arquivo recusado mantém o firmware anterior. **Retirar firmware e usar código-fonte**
restaura o programa interpretado que estava salvo na placa.

### Pico e Pico 2

O Pico 2 tem símbolo próprio na Biblioteca, com os mesmos terminais expostos do Pico e
identificação RP2350 na representação da protoboard. Os pinos lógicos são GP0–GP22 e
GP26–GP28; estes três últimos também são ADC. UART0/UART1 aparecem no monitor com prefixos
`UART0:` / `UART1:`. A recepção serial interativa ainda não está conectada.

Use UF2 de flash para a família correta. São aceitos RP2040, RP2350 ARM Secure e RP2350
RISC-V; imagens ARM Non-Secure, imagens em RAM, containers UF2 e extensões não implementadas
são rejeitados. O bloco auxiliar legado de contorno da errata RP2350-E10 gerado pelo
Arduino-Pico é reconhecido sem escrevê-lo fora da flash da placa. A flash é limitada a
2 MiB no Pico e 4 MiB no Pico 2. ELF é limitado a 32 bits little-endian e segmentos em flash.
ELF ARM, sozinho, não identifica de forma inequívoca RP2040 versus RP2350: confira a placa
selecionada na ferramenta de compilação.

Os clocks do motor são fixos em 125 MHz e 150 MHz, respectivamente. Não foi implementada
a mudança dinâmica de clock nem validado overclock. Escolha esses clocks explicitamente
na IDE; algumas versões do núcleo oferecem outro valor como padrão.

### ESP32

O arquivo deve incluir o bootloader em `0x1000`, tabela de partições em `0x8000` e a
aplicação nos endereços daquela tabela. Um BIN apenas da aplicação não basta. O carregador
valida segmentos, checksums e hashes presentes, a identificação de ESP32 clássico e os
limites das partições. Os parâmetros validados são flash de 4 MiB em modo DIO.

Exemplo de composição com a ferramenta esptool do núcleo Arduino (ajuste os caminhos):

```text
esptool --chip esp32 merge_bin -o projeto.merged.bin --flash_mode dio --flash_size 4MB 0x1000 projeto.ino.bootloader.bin 0x8000 projeto.ino.partitions.bin 0xe000 boot_app0.bin 0x10000 projeto.ino.bin
```

`boot_app0.bin` pertence ao núcleo Espressif, em `tools/partitions`. A tabela padrão do
exemplo posiciona a aplicação em `0x10000`; para outra tabela, use seus endereços reais.
No núcleo 2.0.17, a ferramenta distribuída para Windows se chama `esptool.exe`.

A inicialização real do firmware de teste terminou em aproximadamente 329 ms de tempo
simulado. Use ao menos **350 ms** nesse exemplo, com passo máximo de **10 µs**. Outros
firmwares podem precisar de mais tempo. O tempo de processamento no computador pode ser
consideravelmente maior. As mensagens do boot e da UART aparecem no monitor Serial.

O motor usa uma cópia temporária da imagem, preenchida até 4 MiB; o arquivo original não
é alterado. A sincronização usa memória compartilhada e eventos locais, com nomes únicos
por instância e encerramento do processo ao terminar ou interromper a simulação.
Não são fornecidas opções de rede do motor: Wi-Fi/Bluetooth não fazem parte desta entrega.

## Validação funcional

Os sketches e binários reproduzíveis estão em `backend/tests/fixtures/firmware`.

- Pico RP2040 e Pico 2 ARM/RISC-V: GP2 controla GP3, GP26 lê aproximadamente 2048 para
  1,65 V e 1024 para 0,825 V; GP4 gera PWM com duty de aproximadamente 50 %.
- ESP32: IO4 controla IO2, IO34 lê aproximadamente 2048/1024 nas mesmas tensões;
  IO18 gera PWM com duty de aproximadamente 50 %, com transmissão pela UART.
- Com ngspice, Pico e Pico 2 foram verificados com entrada variável, ADC a 1,65 V e
  saída carregada por 1 kΩ. A tensão calculada é `3,3 × 1000 / 1025 V`, conforme o
  modelo didático de saída já existente (25 Ω), com tolerância de 0,2 %.
- ESP32 com ngspice: após o boot, a entrada muda aos 340 ms e a saída carregada acompanha.
  Para o modelo existente de 16,5 Ω e carga de 1 kΩ, a tensão é
  `3,3 × 1000 / 1016,5 V`, com tolerância de 0,2 %; o ADC registra 2048 para 1,65 V.
- Arquivos UF2 truncados, família errada, sequência incompleta/duplicada, endereços fora
  da flash, BIN da aplicação sem bootloader e corrupção de checksum são rejeitados.

- Suíte completa do backend: **1.166 aprovados, um ignorado**, 11.033 testes de datasheet
  externos fora da execução; duração de 18 min 16 s. Inclui a regressão AVR.
- Frontend: **67 testes aprovados**, ESLint e build concluídos.
- Chrome: carregamento, rejeição de arquivo inválido mantendo o anterior, simulação,
  persistência e remoção passaram para Pico, Pico 2 e ESP32.
- Ruff, mypy dos módulos alterados e verificação de sintaxe dos workers concluídos.
- Instalador completo `setup-firmware.ps1 -Esp32` executado e verificado no Windows.

Os exemplos sem firmware para reproduzir o fluxo de interface estão em
`frontend/e2e/fixtures/firmware`; abra o JSON da placa e carregue o binário correspondente
de `backend/tests/fixtures/firmware`. Os exemplos incluem ponteiras de saída, PWM e ADC.

## Limitações conhecidas

- A camada elétrica usa os modelos didáticos das placas do Ohmnia, inclusive limiares,
  resistência de saída e pull-up/pull-down. O ADC conectado ao circuito é linear de
  0 a 3,3 V em 12 bits. Não reproduz a curva de calibração/atenuação física do ESP32.
- O acoplamento é amostrado nos passos transitórios. Pulsos mais curtos exigem passo menor;
  isto não certifica temporização por ciclo nem todas as funções do silício.
- No RP2040, o motor recebe diretamente o vetor de reset da aplicação em flash, pois mapeia
  XIP diretamente. A configuração QSPI do boot2/ROM não é reproduzida. No Pico 2, o boot
  passa pela ROM do motor. Recursos de segurança/TrustZone não foram qualificados.
- A integração corrige o decodificador CP0 GPIOC da versão rp2350js 2.0.1, conforme as
  instruções do SDK, para permitir `pinMode`, `digitalRead` e `digitalWrite` do núcleo atual.
  O firmware carregado não é reescrito. Avisos de registradores não modelados são
  apresentados nos resultados.
- I2C/SPI dos firmwares não estão ligados aos dispositivos do circuito e produzem erro
  ao transferir dados. Sensores com protocolo no fio, EEPROM, watchdog, depuração GDB,
  rede e recepção serial interativa ficam para próximas fases. USB CDC do Pico tem
  suporte do motor, mas ainda não foi qualificado como os testes UART desta entrega.
- São aceitos até 8 MiB por arquivo de entrada, mantendo limites menores de flash por alvo.
  A saída Serial tem limites para evitar crescimento indefinido de memória.

Próxima fase: ampliar protocolos e sensores a partir dos casos de uso aprovados, validar
mais programas das IDEs e melhorar a configuração/diagnóstico de clock.

## Fontes

[rp2350js, motores e licença MIT](https://github.com/c1570/rp2350js),
[formato UF2 no Pico SDK](https://github.com/raspberrypi/pico-sdk/blob/master/src/common/boot_uf2_headers/include/boot/uf2.h),
[Pico 2 datasheet](https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf),
[Arduino-Pico](https://github.com/earlephilhower/arduino-pico),
[etree-esp32 e protocolo local](https://github.com/electronicstree/etree-esp32),
[formato de imagem esptool](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/firmware-image-format.html),
[Arduino-ESP32 2.0.17](https://github.com/espressif/arduino-esp32/tree/2.0.17).

O executável etree-esp32 é externo, GPL-2.0-or-later. O protocolo `esp32link.h` é MIT;
o cliente Python utiliza esse formato. O instalador mantém licenças e informações de
origem junto do pacote baixado. Nenhum executável desse motor é versionado no repositório.
