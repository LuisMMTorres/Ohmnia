# Validação: microcontroladores, CLP e co-simulação (Fase 11, decisão D12)

Data: 2026-11-16. Status: aguardando revisão do usuário.

Arduino, ESP32 e CLP entram no esquemático e o programa de cada um roda junto com o ngspice: o
A/D lê o nó ligado ao pino, as saídas acionam o circuito, e `delay()` e o ciclo de varredura
correm no tempo simulado. Manual: `docs/manual/08-microcontroladores-clp.md`. Capturas de tela:
`capturas/fase11-microcontroladores-clp/` (13 imagens).

## O que foi feito

| Pedido (D12) | Onde | Situação |
|---|---|---|
| ESP32 e Arduino com programa estilo Arduino, co-simulado | `cosim/clang.py` (subconjunto de C), `cosim/arduino.py` (placas e funções), `cosim/engine.py`, `simulation/backend.py` (fontes `EXTERNAL` do ngspice) | ✅ ADC, GPIO com histerese, PWM, DAC, `delay`, `millis`, `Serial` |
| CLP em ladder e texto estruturado, em ciclo de varredura | `cosim/plc.py` | ✅ ST completo para o uso didático, ladder em JSON com diagrama; TON, TOF, TP, CTU, CTD, R_TRIG, F_TRIG, SR, RS, PID |
| E/S do CLP ligadas ao circuito | `cosim/controllers.py` | ✅ DI 24 V, AI 4 a 20 mA e 0 a 10 V, saídas a relé, AQ0 0 a 10 V, queda da alimentação |
| Sensores e atuadores | `schematic/cosim_symbols.py` | ✅ LM35, Pt100, transmissor 4 a 20 mA, ACS712, potenciômetro, relé, motor CC, aquecedor, botão, planta de bombeamento |
| Exemplos: medidor de energia ESP32, PWM com Arduino, laço 4 a 20 mA no CLP, ESP32 e CLP | `cosim/examples.py`, menu Exemplos do simulador | ✅ os quatro, mais o bombeamento com pressão constante |
| Editor de programa | `frontend/src/cosim/ProgramEditor.tsx`, `LadderDiagram.tsx` | ✅ editor com numeração e diagrama ladder ao vivo |
| Resultado | osciloscópio e painel "Co-simulação" | ✅ variáveis do programa e do CLP como sinais; monitor serial com instante |
| Protoboard | `breadboard/packages.py`, `pinout.py`, `autoplace.py`, `check.py` | ✅ placas e módulos fora da placa, ligados por fio; os cinco exemplos montam e conferem |

## Como a co-simulação funciona (para a sua revisão)

- Cada saída de controlador é uma fonte `EXTERNAL` do ngspice com a resistência de saída da placa
  em série; o ngspice pede o valor a cada passo (`GetVSRCData`). As entradas são lidas no último
  ponto aceito do vetor do nó. O programa avança até o instante pedido; a saída é amostrada e
  mantida entre dois despertares.
- Passo: tempo final/20 000, entre 10 µs e 2 ms; no máximo meio ciclo de varredura do CLP; com
  PWM chaveado, 1/40 do período do PWM. Um passo menor dado pelo usuário é mantido.
- Quanto tempo cada comando gasta é didático (10 µs por instrução, ajustável); `delay()` é exato.
- PWM "média" põe a tensão média no pino. Achado nesta fase: no exemplo do Arduino isso deixava o
  MOSFET na região linear, o que não é a física de um PWM real. O exemplo passou a usar PWM lento
  por software (janela de 1 s, como em aquecedores com relé de estado sólido), que chaveia o
  MOSFET de fato; a ajuda do parâmetro agora diz quando a média vale.
- Simulações sem controlador seguem o caminho anterior, sem mudança (testes do simulador passam).

## Fontes dos valores

### Placas

| Valor | Uno R3 | ESP32-DevKitC |
|---|---|---|
| Alimentação | 5 V: Arduino UNO R3 User Manual (SKU A000066), p. 5 | 3,3 V: ESP32-WROOM-32 Datasheet v3.8, p. 26, Table 14 |
| Limiares de entrada | 0,6 e 0,3 VDD: **didáticos** (o datasheet do ATmega328P não está na sua pasta) | VIH ≥ 0,75 VDD, VIL ≤ 0,25 VDD: idem, Table 14 |
| Resistência de saída | 25 Ω: **didático** | 16,5 Ω, derivada da Table 14: VOH ≥ 0,8 VDD com IOH = 40 mA → (3,3 − 2,64)/0,04 |
| A/D | 10 bits, referência 5 V (referência da linguagem Arduino) | 12 bits; faixa efetiva 150 a 2450 mV com 11 dB, p. 24; fundo de escala de 3,3 V **didático** |
| PWM | pinos 3, 5, 6, 9, 10, 11 (manual, p. 2); 490/980 Hz (referência da linguagem) | 1 kHz: **didático** |
| D/A | não tem | dois de 8 bits (pinos 25 e 26), referência na alimentação, p. 24 |
| Pull-up interno | 35 kΩ: **didático** | 45 kΩ: **didático** |

### CLP genérico (didático, não é um modelo comercial)

| Valor | Fonte |
|---|---|
| Entradas digitais: liga com 15 V ou mais, desliga com 5 V ou menos | faixas do tipo 1 da IEC 61131-2 |
| Alimentação mínima 19,2 V | 24 V − 20 % |
| Entrada 4 a 20 mA em 250 Ω; 0 a 10 V em 100 kΩ; DI 4,7 kΩ; L+ 480 Ω; AQ0 10 Ω | **didáticos**, típicos de catálogo; troque pelos do seu CLP quando houver um registro |
| Bloco PID | posicional, derivada na medição, integrador limitado (Åström e Hägglund, *Advanced PID Control*, 2006, cap. 3) |

### Sensores e atuadores

| Componente | Valor | Fonte |
|---|---|---|
| LM35 | +10,0 mV/°C | LM35 (Texas Instruments), p. 1 |
| Pt100 | R0 = 100 Ω, A = 3,9083e-3, B = −5,775e-7 | IEC 60751 (Callendar-Van Dusen, 0 a 850 °C) |
| ACS712ELCTR-05B | 185 mV/A (p. 6), 1,2 mΩ e 80 kHz (p. 1), saída VCC/2 sem corrente (p. 5) | Allegro ACS712 |
| Relé SRD-05VDC-SL-C | bobina de 70 Ω ±10 % | Songle, p. 2 |
| Transmissor 4 a 20 mA | tensão mínima do laço | **didático** |
| Motor CC, aquecedor, planta de bombeamento | todos | **didáticos** (modelos de planta, não peças) |

## Resultados dos exemplos (ngspice, comparados com o cálculo à mão)

| Exemplo | Esperado | Simulado |
|---|---|---|
| E1 Arduino PI de temperatura | regime: P = (60 − 25)/5 = 7,0 W; razão cíclica 7,0/14,4 = 0,49 | 60,1 °C; P = 7,2 W; razão cíclica no circuito 50,7 %, no programa 50,4 %; MOSFET sempre cortado ou saturado |
| E2 ESP32 medidor de energia | \|Z\| = √(50² + 37,7²) = 62,6 Ω; I = 2,03 A; P = 206 W; FP = 0,80 | Vrms = 127,4 V; Irms = 2,02 A; P = 206 W; FP = 0,80 |
| E3 CLP laço 4 a 20 mA | 58 °C = 10,19 mA e 62 °C = 10,61 mA (faixa 0 a 150 °C); desliga com I1 em 40 s | temperatura entre 57,9 e 62,0 °C; Q0 aberta depois de 40 s; esfria para 25,4 °C em 60 s |
| E4 ESP32 + CLP | 70 °C na rampa de 20 a 90 °C em 20 s: t = 14,29 s | ventilador liga em 14,37 s (varredura, D/A de 8 bits e `delay(50)`) |
| E5 bombeamento | 3,0 bar com o PID; degrau de demanda em 30 s | 3,00 bar antes do degrau; mínimo de 2,59 bar em 31 s; 2,93 bar em 35 s; 3,00 bar em 60 s |

Os testes `tests/unit/cosim/test_examples.py` conferem cada linha acima; E1 confere também que a
razão cíclica do programa é a que o circuito vê (±3 %).

## Testes

- `tests/unit/cosim/`: interpretador C (15), CLP (11), co-simulação no ngspice, dispositivos
  (estímulos, Pt100 a 100 °C = 138,5 Ω, potenciômetro, relé), os 5 exemplos e a montagem de todos
  na protoboard.
- Suíte completa do backend (testes de datasheet com rede desmarcados, como de costume): 919
  passam, 3 falham. As 3 são pendências anteriores à fase, já registradas para sua decisão:
  `test_as_fase5[opnl_limitador]`, `test_as_fase5[opnl_limitador_g2]` e
  `test_pt_inv_ma_linear`. Nenhuma falha nova.
- Frontend: 39 testes (vitest), TypeScript, ESLint e Prettier sem erro. Backend: ruff, mypy
  estrito e import-linter sem erro.

## Limitações conhecidas

- Programa interpretado, não compilado: sem interrupções, temporizadores de hardware, Wi-Fi ou
  bibliotecas; inteiros intermediários não são truncados como no AVR de 8 bits.
- Co-simulação só em análise transitória; varredura, Monte Carlo e pior caso não aceitam
  controladores; o backend em lote do ngspice também não.
- O ladder é editado como JSON (com o diagrama ao lado); não há editor gráfico de arrastar.
- Ainda não feitos, do plano D12: modelos de motor de indução, inversor V/f completo,
  soft-starter, motor de passo com driver, e os exemplos de partida de motor e de posicionamento
  com motor de passo. A planta de bombeamento é um modelo de primeira ordem.
- SCT-013 e ZMPT101B não têm PDF na pasta; ficaram sem modelo. Termopar (IEC 60584) não foi feito.
- Os sensores da co-simulação ainda não são registros do catálogo (não há esquema de categoria
  para sensor, transmissor, microcontrolador e CLP); os valores vêm dos datasheets citados acima.

## O que pedir a você

1. Revisar a tabela de fontes; os valores marcados **didáticos** podem ser trocados por valores de
   datasheet que você tenha (ATmega328P, um CLP comercial).
2. Rodar os cinco exemplos no simulador e conferir na protoboard.
3. Decidir se o próximo passo é a parte de acionamentos (motor de indução, inversor, soft-starter,
   motor de passo) ou o esquema de categoria para sensores e CLP no catálogo.
