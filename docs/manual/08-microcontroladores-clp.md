# Microcontroladores e CLP no circuito

Arduino, ESP32 e CLP entram no esquemático como qualquer outro componente. O programa de cada um
roda junto com a simulação do circuito no ngspice (co-simulação): o conversor A/D lê a tensão do nó
ligado ao pino, as saídas acionam o circuito, e o tempo de `delay()` ou do ciclo de varredura é o
tempo simulado do circuito.

## Onde ficam

Na paleta do simulador, três grupos novos:

- **Controladores:** Arduino Uno R3, ESP32-DevKitC (ESP32-WROOM-32) e CLP genérico.
- **Sensores:** LM35, Pt100, transmissor 4 a 20 mA, ACS712, potenciômetro.
- **Atuadores:** relé, motor CC, aquecedor com planta térmica, botão (chave temporizada) e a planta
  de bombeamento (inversor de frequência e bomba centrífuga).

Os cinco exemplos prontos estão no menu **Exemplos…**, no grupo **Microcontroladores e CLP**.

## Escrever o programa

Selecione o controlador e clique em **Editar** no campo do programa. O editor mostra a ajuda da
linguagem, numera as linhas e aceita Tab. **Aplicar** guarda o programa no circuito.

### Arduino e ESP32 (estilo Arduino)

O programa tem `setup()` e `loop()`, como na IDE do Arduino. O que está disponível:

| Grupo | Funções |
|---|---|
| Pinos | `pinMode` (`INPUT`, `OUTPUT`, `INPUT_PULLUP`), `digitalWrite`, `digitalRead` |
| Analógico | `analogRead` (Uno: 0 a 1023 em 0 a 5 V; ESP32: 0 a 4095), `analogReadMilliVolts` (ESP32), `analogWrite` (PWM 0 a 255), `dacWrite` (ESP32, pinos 25 e 26), `ledcAttach`, `ledcWrite` |
| Tempo | `delay`, `delayMicroseconds`, `millis`, `micros` |
| Serial | `Serial.begin`, `print`, `println`, `printf` |
| Matemática | `map`, `constrain`, `min`, `max`, `abs`, `sqrt`, `pow`, `sin`, `cos`, `random` |
| Linguagem | variáveis globais e locais, vetores, funções, `#define`, `const`, `if`, `while`, `do`, `for`, `switch`, operadores de C, conversões `(int)`, `(float)` |

Parâmetros do controlador:

- **Tempo por instrução** (10 µs): quanto cada comando consome do tempo simulado. As placas reais
  são mais rápidas; o valor só precisa ter a ordem de grandeza certa. `delay()` é exato.
- **PWM no circuito**: **média** (padrão) põe no pino a tensão média do PWM, e a simulação fica
  rápida. Isso vale para cargas que filtram (filtro RC, motor), **não** para o gate de um MOSFET
  usado como chave: com a tensão média, ele trabalharia na região linear e dissiparia potência que
  um PWM real não dissipa. **chaveado** gera a onda quadrada na frequência da placa (490/980 Hz no
  Uno), com passo de simulação de 1/40 do período; a simulação fica bem mais longa. Para
  aquecedores, prefira o PWM lento por software do exemplo 1.

Os pinos de saída têm a resistência de saída da placa; as entradas leem o nó com histerese (os
limiares estão na validação). Um pino sem fio é um pino livre e não gera aviso.

### CLP (ladder ou texto estruturado)

Escolha a linguagem no parâmetro **Linguagem**. Variáveis de E/S:

| Variável | O que é | No circuito |
|---|---|---|
| `I0` a `I5` | entradas digitais 24 V | liga com 15 V ou mais, desliga com 5 V ou menos; 4,7 kΩ para M |
| `AI0`, `AI1` | entradas analógicas, em mA ou V | 4 a 20 mA em 250 Ω, ou 0 a 10 V em 100 kΩ (parâmetros AI0 e AI1) |
| `Q0` a `Q3` | saídas a relé | contato seco entre os terminais Q*n*a e Q*n*b |
| `AQ0` | saída analógica 0 a 10 V | fonte com 10 Ω de saída |
| `M0`... | memórias internas (ladder) | |

O CLP precisa de 24 V entre L+ e M; abaixo de 19,2 V ele para e abre as saídas. O **ciclo de
varredura** (10 ms) é o intervalo entre duas leituras de entradas, execução e escrita de saídas.

**Texto estruturado** (IEC 61131-3): `VAR ... END_VAR`, `:=`, `IF/ELSIF/ELSE`, `CASE`, `FOR`,
`WHILE`, `REPEAT`, funções `LIMIT`, `MIN`, `MAX`, `ABS`, `SQRT`, conversões `INT_TO_REAL` e afins,
e os blocos `TON`, `TOF`, `TP`, `CTU`, `CTD`, `R_TRIG`, `F_TRIG`, `SR`, `RS` e `PID`. Tempos em
literais `T#5s`, `T#1m30s`, `T#250ms`.

O bloco **PID** tem `SP`, `PV`, `KP`, `TI` (s), `TD` (s), `OUT_MIN`, `OUT_MAX` e `ENABLE`; a
derivada é tomada sobre a medição e o integrador para na saturação (anti-windup).

**Ladder**: o programa é uma lista de degraus em JSON, que o editor desenha ao lado enquanto você
digita. Cada degrau é um OU de ramos; cada ramo, um E de elementos da esquerda para a direita:

```json
{"rungs": [
  {"comment": "Liga (I0) e desliga (I1), com selo",
   "branches": [[{"type": "NO", "var": "I0"}, {"type": "NC", "var": "I1"}],
                [{"type": "NO", "var": "M0"}, {"type": "NC", "var": "I1"}]],
   "coils": [{"type": "coil", "var": "M0"}]}
]}
```

Elementos: `NO` (contato aberto), `NC` (fechado), `P`/`N` (borda de subida/descida), `CMP`
(`"expr": "AI0 > 12.0"`), `TON`/`TOF`/`TP` (`"name"`, `"pt": "T#5s"`), `CTU`/`CTD` (`"name"`,
`"pv"`, `"reset"`). Bobinas: `coil`, `ncoil`, `set`, `reset` e `move` (`"dst"`, `"src"`).
**Organizar JSON** reformata o texto.

## Simular e ver o resultado

Use uma análise **transitória** (as outras não têm tempo para o programa rodar; varredura e Monte
Carlo também não são aceitos com controladores). O passo de co-simulação é escolhido sozinho:
tempo final/20 000, entre 10 µs e 2 ms, no máximo meio ciclo de varredura do CLP.

No resultado:

- **Osciloscópio**: além das tensões e correntes do circuito, aparecem as variáveis do programa
  (`u1.temperatura`, `u1.pwm`), os pinos (`u1.d9`) e as variáveis do CLP (`clp1.q0`, `clp1.ai0`,
  `clp1.pid1.out`). As ponteiras de prova do exemplo já vêm marcadas.
- **Co-simulação**: o passo usado e o **monitor serial** de cada placa, com o instante de cada
  linha impressa.

Um erro no programa (sintaxe, variável não declarada, laço infinito) para a simulação com a
mensagem e o instante em que aconteceu.

## Os exemplos

| Exemplo | O que mostra |
|---|---|
| Arduino: controle PI de temperatura | LM35 em A0, PI a cada janela de 1 s, PWM lento no MOSFET, aquecedor de 10 Ω em 12 V. Chega a 60 °C e fica entre 60 e 61 °C. |
| ESP32: medidor de energia | Rede de 127 V e 60 Hz, carga RL, ACS712 e divisor com polarização de 1,25 V. Imprime Vrms, Irms, P e fator de potência a cada 200 ms. |
| CLP: laço 4-20 mA (ladder) | Transmissor de 0 a 150 °C em AI0, histerese de 58 a 62 °C, botões de liga e desliga com selo. |
| ESP32 + CLP: condicionamento 0-10 V | O ESP32 lê o LM35 e entrega 0 a 3,3 V no DAC; um amp-op leva a 0 a 10 V para a AI1 do CLP, que liga o ventilador acima de 70 °C. |
| Bombeamento com pressão constante | PID do CLP comanda o inversor (AQ0 0 a 10 V = 0 a 60 Hz), transmissor de pressão em 4 a 20 mA, degrau de demanda em 30 s; o ESP32 supervisiona a referência. |
| Partida de motor: direta × soft-starter (CLP) | O botão em I0 liga, pelo ladder com selo, um motor por contator (partida direta, cerca de 48 A de pico) e outro por soft-starter com limite de 15 A; I1 desliga os dois em 9 s, o segundo com rampa de 2 s. |
| Arduino: posicionamento com motor de passo | O Arduino gera STEP/DIR com rampa para o driver em 1/4 de passo e leva o 17HS19-2004S1 a 180°, 90° e de volta à origem; o monitor serial mostra a posição contada e v(m1_deg) a posição real do rotor. |

Todos montam na protoboard (**Montar automaticamente**): as placas e os módulos ficam fora da
placa, ligados por fios aos furos.

## Acionamentos e termopar

Em **Atuadores**, **Controladores** e **Sensores** do simulador:

| Componente | Como ligar | O que aparece |
|---|---|---|
| Motor de indução trifásico | A, B e C na fonte trifásica, no contator, no soft-starter ou no inversor. Parâmetros do circuito equivalente por fase (R1, R2, X1, X2, Xm), polos, inércia, atrito e carga constante ou quadrática. | v(m1_rpm), v(m1_te) (torque), v(m1_i) (corrente de linha eficaz) |
| Inversor de frequência (V/f) | AI-GND recebe 0 a 10 V (0 a fnom); RUN-COM com 11 V ou mais liga; U, V e W vão ao motor. Saída senoidal (rápida) ou SPWM a 5 kHz. | v(inv1_f) (Hz), v(inv1_v) (tensão comandada) |
| Soft-starter | L1 a L3 na rede, T1 a T3 no motor, RUN-COM como no inversor. Rampa de tensão ou limitação de corrente, kick start e parada suave. | v(ss1_kv) (fração da tensão), v(ss1_i) |
| Contator tripolar | Bobina A1-A2 (CC ou CA); contatos L-T. | v(k1_ctl) (nível da bobina, fecha em 0,75) |
| Motor de passo híbrido | A+, A−, B+ e B− no driver. Com a peça do catálogo (por exemplo, 17HS19-2004S1), R, L, inércia e passo vêm do datasheet e a constante de torque vem do torque de retenção. | v(m1_deg), v(m1_w), v(m1_te) |
| Driver de motor de passo | STEP, DIR e EN vêm do Arduino ou do ESP32 (EN solto habilita); VM é a alimentação do motor. Micropasso de 1 a 1/16 e corrente por fase. | drv1.steps (contagem), drv1.ia_ref, drv1.ib_ref |
| Termopar | Tipos J, K, T, E e N; temperatura da junta quente e da junta fria (terminais). | tensão entre + e −, v(tc1_t) |

Os nós internos (como `m1_rpm`) podem ser usados como ponteira de tensão e no osciloscópio. Com motor
de indução, inversor ou soft-starter no circuito, o passo máximo fica em 1/80 de um ciclo de 60 Hz;
com SPWM, em 1/40 da portadora.

## Limites

- O programa é interpretado, não compilado: é o comportamento do código, não o do firmware real
  (sem interrupções, temporizadores de hardware, Wi-Fi ou bibliotecas de terceiros).
- Os valores elétricos das placas com fonte estão na validação; os que não têm fonte são
  didáticos e vêm marcados assim no próprio componente.
- Aquecedor, motor CC e planta de bombeamento são modelos didáticos, não peças do catálogo.
- O motor de indução padrão é didático (não há catálogo de motor de indução com circuito
  equivalente); troque os parâmetros pelos do seu motor.
- O soft-starter simula a fundamental da tensão dos tiristores; as harmônicas do disparo não
  aparecem (o controle de fase com tiristores, em detalhe, está no projeto de controlador CA).
- O driver de motor de passo conta as bordas de STEP nos pontos da simulação: cada pulso precisa
  durar pelo menos 20 µs (o passo máximo com driver no circuito).

## Carregar firmware compilado (Arduino AVR)

Uno R3, Nano clássico ATmega328P e Mega 2560 aceitam `.hex` e `.elf` exportados pela Arduino IDE.
Instale o motor com `scripts/setup-firmware.ps1` (Node.js 20+) ou
`npm ci --ignore-scripts --prefix backend/src/circuitos/cosim/firmware_worker`.
Na IDE, escolha a placa correta e use **Sketch → Exportar binário compilado**.
Selecione a placa virtual no Ohmnia e use **Programação da placa virtual → Carregar firmware**.
Simule em análise transitória; o firmware fica salvo no projeto. Para voltar ao programa
anterior, use **Retirar firmware e usar código-fonte**. O modo firmware usa clock real de
16 MHz, não o tempo didático por instrução do interpretador.

Esta primeira entrega cobre GPIO, ADC, temporizadores/PWM e transmissão Serial0.
ESP32-DevKitC aceita BIN mesclado; Pico e Pico 2 aceitam UF2/ELF de flash.
Para instalar também o motor ESP32 no Windows de 64 bits, use
`scripts/setup-firmware.ps1 -Esp32`. Pico: clock de 125 MHz; Pico 2: 150 MHz.
ESP32: flash DIO de 4 MiB e tempo de simulação suficiente para o boot (350 ms no exemplo).
Instruções de compilação, formatos e limites estão em
[firmware-outras-placas](../validacao/firmware-outras-placas.md).
