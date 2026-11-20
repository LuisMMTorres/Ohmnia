# Bancada de sensores, atuadores e placas (BD-PER) — para revisão

Pedido de 2026-11-20: na aba **Análise de dispositivos**, incluir os sensores, atuadores e placas
da biblioteca, com ensaios coerentes para cada tipo.

## O que foi feito

- Nova aba **Sensores, atuadores e placas** na Análise de dispositivos, com as 21 peças da
  biblioteca do simulador agrupadas em Sensores, Atuadores e Placas e controladores.
- Cada peça usa **o mesmo modelo SPICE do esquemático** (nada foi duplicado). A bancada monta um
  circuito de ensaio, roda no ngspice (com a co-simulação para Arduino, ESP32 e CLP) e compara cada
  medida com a equação que o modelo implementa (regra 4). A tabela mostra simulado, analítico, erro
  e tolerância; a memória de cálculo traz a equação, as entradas e a referência de cada ensaio.
- Quando o símbolo aceita peça do catálogo (LM35, Pt100, sensores de corrente, potenciômetros,
  relés, motores de passo), o seletor **Usar o datasheet de** lista só as peças que de fato
  fornecem valores ao modelo; os campos ficam travados com os valores da peça. Peça não revisada
  gera aviso.
- As condições de ensaio (alimentação, carga, resistência de fio, faixa de temperatura, taxa de
  passos etc.) são editáveis e não são parâmetros de componente.
- As netlists de cada ensaio ficam em "Netlists dos ensaios".

## Ensaios por peça

| Grupo | Peça | Ensaio | Medidas comparadas |
|---|---|---|---|
| Sensores | LM35 | rampa de temperatura | sensibilidade, saída a 25 °C, saturação em VS − 1,5 V |
| | Pt100 | corrente constante, 0 a 850 °C | R(0), R(100), α, R no fim (IEC 60751) |
| | Termopar J/K/T/E/N | rampa da junta quente | FEM a 100 °C e no fim, Seebeck, tensão com carga (NIST ITS-90) |
| | Transmissor 4-20 mA | laço de 24 V com 250 Ω | 4, 12 e 20 mA; corrente com fonte abaixo da mínima |
| | Transmissor para RTD 3 fios | Pt100 com fios iguais ou desiguais | temperatura lida, 4/12/20 mA |
| | ACS712 | rampa de ±5 A e análise AC | saída em zero, sensibilidade, R do primário, banda −3 dB |
| | Potenciômetro | cursor de 0 a 1 | R total, divisor sem carga, efeito de carga |
| Atuadores | Relé | rampa na bobina até 120 % e volta | operação, desoperação, R da bobina, R do contato |
| | Motor CC | degrau em vazio e com carga | ω₀, I₀, tempo até 63 % e pico de corrente (solução exata), ω com carga |
| | Aquecedor | degrau de tensão | elevação após 6τ, τ = Rth·Cth, potência |
| | Botão/chave manual | fonte com resistor em série | R fechada, instante do fechamento |
| | Planta de bombeamento | AI fixa, RUN em 0,1 s | frequência, τ da rampa, pressão, corrente do transmissor |
| | Motor de indução | partida direta com carga | velocidade, corrente e torque em regime (circuito equivalente) e curva torque × velocidade |
| | Inversor V/f | motor padrão, carga quadrática | rampa, frequência final, lei V/f, velocidade do motor |
| | Soft-starter | motor padrão, carga quadrática | k no meio da rampa (ou limite de corrente), bypass, velocidade |
| | Contator (CC ou CA) | rampa na bobina | fecha a 75 %, abre a 40 %, corrente da bobina, R do contato |
| | Motor de passo | driver STEP/DIR padrão | contagem de passos, posição com ângulo de carga, corrente |
| Placas e controladores | Driver de passo | motor padrão | os mesmos, variando micropasso e corrente |
| | Arduino Uno R3 | programa de ensaio co-simulado | LSB e leitura do ADC, limiares VIH/VIL, saída alta com carga, PWM médio e frequência |
| | ESP32-DevKitC | idem | idem, mais o DAC |
| | CLP 24 V | programa ST (Q0 := I0; AQ0 := AI1) | liga/desliga da entrada (IEC 61131-2 tipo 1), leitura 4-20 mA, saída 0-10 V |

## Modelos novos para peças do catálogo (segunda etapa)

Pedido seguinte do mesmo dia: criar modelos de simulação, com dados de datasheet, para as peças do
catálogo que ficaram de fora e incluí-las na bancada. Os modelos entram também na biblioteca do
**Simulador** (esquemático), no grupo Sensores ou Controladores, e a bancada passa a ter 29 peças.

| Peça | Modelo | Valores padrão (fonte no catálogo) | Ensaio e medidas |
|---|---|---|---|
| Termistor NTC | R(T) = R25·e^(β(1/T − 1/T25)); corpo com δ (W/K) e τ; autoaquecimento P/δ | Vishay NTCLE100E3103JB0: R25 = 10 kΩ, β = 3977 K, δ = 7 mW/K, τ = 15 s | rampa de temperatura (R a −20, 25 e 100 °C, β medido), autoaquecimento num divisor, constante de tempo |
| LDR | R(E) = R10·(E/10 lx)^(−γ), limitado a R escuro | Token GL5528: R10 = 15 kΩ (centro de 10 a 20 kΩ), γ = 0,6, R escuro = 1 MΩ | R com 10 lux, γ entre 10 e 100 lux, escuro, tensão do divisor |
| Sensor Hall linear | V = Vq + S·B, saturando em ±B faixa | Honeywell SS49E: S = 14 mV/mT (1,4 mV/G), Vq = 2,5 V, faixa ±100 mT | saída sem campo, sensibilidade, saturação |
| Chave Hall | saída coletor aberto com histerese Bop/Brel | Allegro A3144: Bop = 21 mT e Brel = 19 mT (centros das faixas), Vsat = 175 mV com 20 mA | pontos de operação e liberação, tensão com pull-up |
| Sensor de pressão | V = Voff + (VFE − Voff)·p/pFE | NXP MPX5700DP: 0 a 700 kPa, 0,2 a 4,7 V | saída em 0 e no fundo de escala, sensibilidade |
| Ultrassônico HC-SR04 | ECHO alto por 2d/c após o pulso em TRIG; c = 331,3·√(1 + T/273,15) m/s; sem eco fora de 2 cm a 4 m | HC-SR04 (Elecfreaks): alcance 2 cm a 4 m | largura do eco para várias distâncias e sem eco fora do alcance |
| Arduino Nano | ATmega328P como o Uno; A0 a A7 | pinagem e PWM iguais ao Uno | mesmo programa de ensaio do Uno |
| Arduino Mega 2560 | ATmega2560; A0 a A15, PWM em 2 a 13 e 44 a 46 (980 Hz em 4 e 13) | — | mesmo programa de ensaio do Uno |

Peças do catálogo testadas pela bancada (todas dentro da tolerância): Vishay NTCLE100E3103JB0, TDK
B57164K0103J000, Token GL5528, Honeywell SS49E, Allegro A3144, NXP MPX5700DP, outros quatro
transmissores de pressão com saída em tensão e o HC-SR04. Quando o datasheet dá só faixa (mínimo e
máximo), o modelo usa o centro da faixa e isso fica escrito na descrição do parâmetro.

Peças que **continuam sem modelo** e por quê:

- DHT11/DHT22, DS18B20, BME280: saída digital por protocolo (barramento de um fio, I²C). Precisam
  de um modelo de protocolo na co-simulação, não de um modelo SPICE; fica como próximo passo.
- TMP36: o offset de 500 mV não está no catálogo e o datasheet não pôde ser baixado nesta sessão
  (regra 1: não preencher de memória).
- KTY81: falta R25 no catálogo.
- Raspberry Pi Pico e LaunchPad (LAUNCHXL): o catálogo não traz os dados do núcleo (ADC, níveis,
  PWM) que a co-simulação precisa; o runtime também é só para programas estilo Arduino.
- Sensores ultrassônicos industriais (Pepperl+Fuchs UB500, Schneider XX630) e sensores indutivos e
  fotoelétricos: saída de chaveamento, não TRIG/ECHO; não aparecem no seletor do HC-SR04.
- No Simulador, os novos símbolos usam a caixa genérica com os pinos nomeados e ficam fora da
  placa na protoboard (os desenhos próprios ficam para depois, para não conflitar com o trabalho da
  protoboard em outro PR).

## Como executar

```bash
cd backend
uv run pytest tests/analytic_vs_sim/test_as_peripherals.py   # AS-PER-01..03
uv run pytest tests/unit/api/test_devices.py -k peripheral
```

No aplicativo: Análise de dispositivos → **Sensores, atuadores e placas** → escolher a peça →
**Rodar os ensaios**. Os motores de indução, inversor, soft-starter e motor de passo levam de 15 a
30 s; os demais, poucos segundos.

## Resultado dos testes

- `AS-PER-01`: as 21 bancadas com os valores padrão, todas as medidas dentro da tolerância.
- `AS-PER-02`: 10 bancadas fora do padrão (LM35 saturando, termopar J com junta fria a 0 °C, RTD
  com fios desiguais, relé de 12 V, contator CA, soft-starter em limitação de corrente, micropasso
  16, Arduino com outra carga etc.).
- `AS-PER-02` também cobre os modelos novos fora do padrão (NTC sem autoaquecimento, LDR com
  outro γ, Hall a 3,3 V, chave Hall com outra histerese, sensor de 100 kPa, HC-SR04 a 0 °C com uma
  distância fora do alcance, Arduino Mega com outro duty).
- `AS-PER-03`: peças do catálogo (relé SRD-05VDC-SL-C, LM35DZ, ACS712, 17HS19-2004S1, os dois NTC,
  GL5528, SS49E, A3144, MPX5700DP e HC-SR04).
- Pela API, todas as peças do catálogo oferecidas nas bancadas foram rodadas: todas dentro da
  tolerância, exceto a família Kalatec "Motores de Passo" (ver limitações).
- Suíte completa do backend e do front-end rodada antes do PR (ver descrição do PR).

## Capturas

Em [capturas-bancada-perifericos/](capturas-bancada-perifericos/): LM35, relé, motor CC, Arduino
Uno, ESP32, CLP, ACS712, motor de indução e motor de passo; e, dos modelos novos, NTC, LDR, Hall
linear, chave Hall, pressão, HC-SR04 e Arduino Mega (10 a 16).

## Limitações conhecidas

- Peças do catálogo ainda sem modelo de simulação: ver a lista na segunda etapa acima.
- HC-SR04: o atraso entre o fim do pulso em TRIG e a subida do ECHO (rajada de 40 kHz) não é
  simulado, e o sensor exige passo de 2 µs (a simulação fica mais lenta quando ele está no
  circuito). O runtime do Arduino não tem `pulseIn`, então a bancada mede o eco direto no SPICE.
- O LM35 do simulador não tem offset; o TMP36 (offset de 500 mV) aparece no seletor porque o
  catálogo dá a sensibilidade dele, mas a saída simulada não inclui o offset (o mesmo acontece no
  esquemático).
- Contator com bobina CA: o modelo filtra o valor médio retificado em 10 ms, e a ondulação de
  120 Hz antecipa o fechamento e atrasa a abertura em cerca de 5 %; a tolerância desse caso é 7 %
  e a bancada avisa.
- CLP: as medidas de liga/desliga têm o atraso de um ciclo de varredura (10 ms na rampa de
  24 V/s); a tolerância considera esse atraso.
- Motor de passo Kalatec "Motores de Passo" com o driver padrão (1,5 A, 50 passos/s): o rotor
  perde passos, e a bancada mostra o ensaio fora e um aviso de perda de sincronismo. É um resultado
  físico do modelo, não um erro: com menos passos por segundo ou mais corrente ele acompanha.
- Limiares das entradas digitais e resistência de saída das placas continuam didáticos (como no
  Simulador).

## Próximo passo sugerido

Modelo de protocolo para os sensores digitais (DHT22, DS18B20, BME280) e `pulseIn` no runtime do
Arduino, para que o HC-SR04 possa ser lido por um programa; desenhos próprios dos símbolos novos.
