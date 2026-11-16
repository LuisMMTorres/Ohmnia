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
  `clp1.pid1.out`). As pontas de prova do exemplo já vêm marcadas.
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

Todos montam na protoboard (**Montar automaticamente**): as placas e os módulos ficam fora da
placa, ligados por fios aos furos.

## Limites

- O programa é interpretado, não compilado: é o comportamento do código, não o do firmware real
  (sem interrupções, temporizadores de hardware, Wi-Fi ou bibliotecas de terceiros).
- Os valores elétricos das placas com fonte estão na validação; os que não têm fonte são
  didáticos e vêm marcados assim no próprio componente.
- Aquecedor, motor CC e planta de bombeamento são modelos didáticos, não peças do catálogo.
