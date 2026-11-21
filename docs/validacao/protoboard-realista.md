# Validação: desenhos realistas na protoboard, placas encaixáveis e zoom

Data: 2026-11-19. Status: aguardando revisão do usuário.

Pedidos de 2026-11-18 (thread "Melhorar símbolos e zoom da protoboard"). Capturas em
`docs/validacao/capturas-protoboard-realista/`.

## O que foi feito

| Pedido | Onde | Situação |
|---|---|---|
| "Fonte comportamental" passa a "fonte dependente" | `schematic/library.py` (símbolo `bsource`), docs | ✅ |
| Arduino Uno e ESP32 com pinos nos dois lados, encaixe na protoboard pelo pino 1 com o mouse | estilo de encapsulamento `board` (`breadboard/packages.py`), `PackageArt.tsx`, botão **Pelo pino 1** | ✅ |
| Zoom da protoboard menor que 100 % | seletor de zoom: 50, 75, 100, 130, 160, 200 e 250 % | ✅ |
| Zoom do esquemático 2D além da roda do mouse | botões − / + , lista de níveis (25 a 400 %), **Ajustar** e teclas `+` `−` `0` `F` | ✅ |
| Desenho real do Pt100 | sonda de bainha com cabeçote e bornes 1 e 2; no esquemático, resistor com a barra de grandeza variável (θ) | ✅ |
| Transmissor de corrente para RTD com 3 pinos | novo símbolo `tx420_rtd` (modelo SPICE, AS-TX-01/02) e desenho de cabeçote redondo com bornes 1, 2, 3 e + − | ✅ |
| Termopar com simbologia real | desenho: bainha com a junta quente e conector miniatura polarizado (+ estreito, − largo); esquemático: dois condutores unidos na junta, o negativo mais grosso | ✅ |
| Sensor de corrente mais real | módulo ACS712 com borne de parafuso IP+/IP−, CI SOIC-8 e barra VCC/OUT/GND | ✅ |
| Motor CC e motor trifásico mais reais, sentido de giro na simulação | desenhos próprios (carcaça, eixo, caixa de bornes) e disco no eixo que gira no sentido simulado, com a velocidade em rpm | ✅ |
| Soft-starter, motor de passo, inversor, contator etc. | desenhos para soft-starter, inversor V/f, contator tripolar, motor de passo, driver STEP/DIR, relé, aquecedor e botão | ✅ |

## Decisões técnicas para a sua revisão

- **Placas na protoboard.** As duas placas ficam sobre a canaleta como um DIP largo: uma barra de
  pinos na coluna h (com o pino 1) e a outra na coluna c; os furos d–g das mesmas linhas ficam sob a
  placa, e sobram a–b e i–j para os fios. O pino 1 é o primeiro pino à esquerda da barra de baixo
  (Uno: NC da barra de alimentação; ESP32: 3V3), marcado com um triângulo amarelo.
- **Ordem dos pinos** (vista de cima), da documentação pública das placas; confira com o seu
  material:
  - Uno R3, barra de baixo: NC, IOREF, RESET, 3V3, 5V, GND, GND, VIN | A0–A5. Barra de cima: SCL,
    SDA, AREF, GND, D13–D8 | D7–D0.
  - ESP32-DevKitC (38 pinos), USB à direita. Barra de baixo: 3V3, EN, IO36, IO39, IO34, IO35,
    IO32, IO33, IO25, IO26, IO27, IO14, IO12, GND, IO13, IO9, IO10, IO11, 5V. Barra de cima: GND,
    IO23, IO22, IO1 (TX), IO3 (RX), IO21, GND, IO19, IO18, IO5, IO17, IO16, IO4, IO0, IO2, IO15,
    IO8, IO7, IO6.
- **Limites da montagem didática.** O Uno real não encaixa na protoboard (na bancada, use jumpers
  macho-fêmea), e o desenho usa passo de 0,1" com um furo de folga entre os grupos de pinos (no Uno
  real, o espaço entre D7 e D8 não é múltiplo de 0,1"). O espaçamento entre as fileiras do ESP32
  depende da versão da placa: confira antes de montar. As duas observações aparecem no painel da
  peça e no roteiro.
- **Pinos sem modelo.** Os pinos que a simulação não modela (Uno: NC, IOREF, RESET, 3V3, VIN, AREF,
  SDA, SCL, D0, D1; ESP32: EN, IO0, IO1, IO3, IO6 a IO11) aparecem com o nome, mas ficam fora da
  conferência.
- **GND da placa.** Os vários pinos GND de cada placa são o mesmo nó na placa real. A conferência
  agora junta as tiras dos pinos de mesma função de uma placa, então ligar qualquer um deles basta.
- **Transmissor para RTD a 3 fios (`tx420_rtd`).** A corrente de excitação sai pelo borne 1 e volta
  pelo 2; o 3 só mede. R = (V13 − V32)/I desconta a resistência dos fios quando os fios 1 e 2 são
  iguais. A temperatura sai da inversa de R(T) = R0 (1 + A T + B T²) (IEC 60751) e a corrente do
  laço vai de 4 a 20 mA na faixa configurada. A corrente de excitação (0,5 mA) e a tensão mínima
  (10 V) são valores didáticos, ditos assim no parâmetro. O lado do RTD é referido ao borne − por
  1 GΩ (transmissor não isolado), só para não deixar nó solto.
- **Sentido de giro.** Depois de uma análise transitória, o sistema lê o último ponto de
  `v(<ref>_w)` de cada motor (motor CC, de indução e de passo). Convenção adotada: ω > 0 é sentido
  horário olhando a ponta do eixo. Confira se essa convenção é a que você usa em aula (a IEC
  60034-8 associa a sequência U-V-W ao sentido horário visto do lado acionado). A indicação aparece
  na protoboard (disco no eixo girando, seta e rpm) e no esquemático (texto abaixo do símbolo). A
  animação não segue a velocidade real; só o sentido.
- **Desenhos próprios.** Os desenhos seguem o aspecto usual de cada tipo de equipamento, sem copiar
  imagens de fabricante nem de outro programa, e não implicam especificação de nenhuma peça.
- **Cores dos fios do termopar.** Os fios internos do desenho não seguem nenhuma norma de cores (as
  normas IEC e ANSI usam cores diferentes); a polaridade é dada pelos sinais + e − e pela lâmina
  mais larga do negativo.

## Como verificar

```bash
cd backend
uv run pytest tests/unit/breadboard tests/analytic_vs_sim/test_as_tx420_rtd.py \
  tests/unit/cosim/test_examples.py::test_every_example_assembles_on_the_breadboard
cd ../frontend && npm test
```

No aplicativo: Simulador → Exemplos → "Arduino: controle PI de temperatura" → Protoboard → Montar
automaticamente (ou **Pelo pino 1** e um clique na coluna h). Para o sentido de giro: um motor CC
com fonte de −12 V, análise transitória, Simular, e voltar à Protoboard.

## Testes acrescentados

- `test_boards_sit_over_the_channel_with_both_headers`, `test_board_gnd_pins_are_one_node`
  (backend), "places a board by pin 1 in column h" (front-end).
- AS-TX-01 (fios iguais: 12 mA a 50 °C na faixa de 0 a 100 °C) e AS-TX-02 (fios de 6 Ω e 5 Ω: o
  transmissor lê R(50 °C) + 1 Ω, cerca de 2,6 °C a mais).

## Limitações conhecidas

- O CLP, as fontes de bancada e a planta inversor + bomba continuam com o painel genérico.
- O símbolo do motor no esquemático continua sendo a caixa "M" (o pedido era para a protoboard).
- Montagens salvas antes desta mudança com o Arduino ou o ESP32 fora da placa recebem o aviso
  "montado como mod-…, mas a peça usa board-…"; basta retirar a placa e colocá-la de novo.

## Desenhos reais dos dispositivos fora da placa (2026-11-21)

Os dispositivos que ainda apareciam como painel genérico ("DISPOSITIVO") ganharam desenho próprio
na aba Protoboard. São desenhos didáticos feitos a partir do aspecto usual de cada peça; os
terminais seguem os nomes do modelo de simulação. Confira a serigrafia do seu módulo antes de
ligar.

| Grupo | Dispositivos |
|-------|--------------|
| Sensores | NTC (disco), LDR, KTY81, sensor Hall linear e chave Hall (TO-92), sensor de pressão integrado, HC-SR04, DHT22, DS18B20 (TO-92), BME280 (placa I2C) |
| Controladores | Arduino Nano, Arduino Mega 2560, Raspberry Pi Pico, CLP 24 V |
| Atuadores | planta inversor + motor + bomba (com transmissor de pressão) |
| Transformadores | monofásico (núcleo E-I, régua de bornes P/S) e trifásico (três colunas, bornes H e X) |
| Fontes | fonte de bancada CC regulada (displays de tensão e corrente, knobs de tensão e corrente, bornes vermelho e preto; uma seção por canal quando os canais são da mesma fonte) e gerador de funções (display com a forma de onda, teclado, knob e bornes de saída) |
| Lâmpadas e LEDs | lâmpada no soquete com dois bornes; LED com cúpula na cor escolhida e aba chanfrada no catodo |

Pinagens conferidas: DHT22 1 VCC, 2 DATA, 3 NC, 4 GND (guia SparkFun RHT03/DHT22); HC-SR04 VCC,
Trig, Echo, GND (mischianti.org); DS18B20 TO-92, vista de baixo, 1 GND, 2 DQ, 3 VDD (datasheet,
tabela 1). Nas placas (Nano, Mega, Pico) os terminais estão na ordem do modelo, não na posição
física do pino.

Outros ajustes:

- A protoboard abre com zoom de 75 %.
- Montagem automática: os pinos de mesma função de uma placa (os GND do ESP32 e do Arduino) já são
  ligados pela própria placa, então não recebem mais fios entre si.
- IGBT, SCR e TRIAC passaram do grupo Chaves para Semicondutores na paleta do esquemático.

Capturas: `/mnt/project-files/capturas/protoboard-desenhos/`.
