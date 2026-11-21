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

## Terceira etapa: peças com os datasheets enviados pelo usuário

Em 2026-11-20 o usuário mandou os links dos datasheets das peças que ainda faltavam. Os PDFs não
puderam ser baixados nesta sessão (a rede bloqueia os sites dos fabricantes), mas o texto de cada
um foi lido pela web, com a página de cada valor. Como o catálogo exige que todo valor aponte para
um PDF guardado por hash, o que veio só dessa leitura ficou **a verificar**, com a página e o link
na nota; o que já estava num PDF do catálogo foi usado direto (por exemplo, o offset do TMP36 sai
da própria cópia do catálogo: 750 mV a 25 °C menos 25 °C × 10 mV/°C).

| Peça | O que entrou no catálogo | Modelo | Ensaio na bancada |
|---|---|---|---|
| TMP36 (Analog Devices) | offset de 0,5 V (750 mV a 25 °C, p. 1; confere com a Tabela 4 da Rev. H) | o LM35 ganhou o parâmetro **offset** (0 V no LM35, 0,5 V no TMP36) | sensibilidade e saída a 25 °C (750 mV) |
| KTY81-110 e KTY81-210 (NXP, Rev. 05) | R25 e a tabela R × T (−55/−40 a 150 °C, valores mín./típ./máx., Tabelas 7 e 10); KTY81-210 é registro novo, com os valores a verificar | **Sensor de silício KTY81**: R(T) interpolada na tabela do datasheet e escalada por R25 | R nos pontos da tabela com 1 mA |
| DHT22/AM2302 (Aosong) | resolução 0,1 % e 0,1 °C, período de 2 s, temporização do barramento único (p. 6 a 9) | **DHT22** lido pela biblioteca `DHT` do Arduino | resposta, leituras a cada 2 s, valores com a resolução, duração do quadro de 40 bits, número negativo |
| DS18B20 (Analog Devices) | 750 ms em 12 bits (p. 1); tempos de 9 a 11 bits e temporização do 1-Wire da Rev 6 nas notas (a verificar) | **DS18B20** lido por `OneWire` + `DallasTemperature` | sensores no fio, temperatura com a resolução, índice sem sensor (−127), tempo de conversão |
| BME280 (Bosch) | faixa e exatidão de pressão; endereço I2C 0x76/0x77 (p. 33, a verificar) | **BME280** lido pela `Adafruit_BME280` no I2C da placa | endereço certo e errado, temperatura, pressão e umidade |
| Raspberry Pi Pico (RP2040) | já estava no catálogo | **placa Raspberry Pi Pico** na co-simulação: 3,3 V, ADC de 12 bits em GP26 a GP28, LED no GP25, I2C em GP4/GP5 | o mesmo programa de ensaio das outras placas |

Como funcionam os sensores digitais: o programa do Arduino usa as mesmas classes e funções das
bibliotecas de verdade (`DHT dht(2, DHT22); dht.begin(); dht.readTemperature();`,
`OneWire ow(2); DallasTemperature s(&ow); s.requestTemperatures(); s.getTempCByIndex(0);`,
`Adafruit_BME280 bme; bme.begin(0x76); bme.readPressure();`). Cada chamada confere o que o
barramento real exige (sensor alimentado na faixa do datasheet, linha com pull-up, endereço certo),
gasta o tempo da transação calculado pela temporização do datasheet e devolve o valor com a
resolução do sensor. Sem resposta, a biblioteca devolve o que a real devolve: `NAN` no DHT, −127 no
DS18B20, `false` no `begin()` do BME280, e o simulador avisa o motivo.

Limites desta etapa:

- O sinal de cada bit no fio não é simulado: a linha de dados fica no nível de repouso no circuito.
  Por isso o osciloscópio não mostra o quadro do DHT22 nem os pulsos do 1-Wire.
- A biblioteca `DHT` liga o pull-up interno da placa no `begin()`, como a real; então o DHT22
  funciona mesmo sem o resistor externo (o DS18B20 e o BME280 não).
- BME280: devolve o valor do estímulo dentro da faixa de medição; a compensação interna, o filtro e
  a sobreamostragem não são simulados. Acima de 3,6 V em VDD o simulador avisa, mas o sensor
  continua respondendo (o chip real pode queimar).
- DS18B20: o modo parasita (alimentação pela linha DQ) não é simulado; a leitura é arredondada ao
  passo da resolução (o datasheet não diz como o chip arredonda).
- KTY81: entre os pontos da tabela a curva é uma reta; o erro de interpolação é pequeno perto do
  erro máximo do próprio sensor (±1,27 K a 25 °C).
- Raspberry Pi Pico: a tabela elétrica de E/S do RP2040 (seção 5.5.3) e a seção do PWM não puderam
  ser lidas; os limiares de entrada, a resistência de saída, o pull-up e o PWM de 1 kHz em qualquer
  GP são didáticos e estão marcados como a verificar. Os pinos I2C GP4/GP5 são os padrão do núcleo
  Arduino do RP2040 (a verificar).
- DHT11: o catálogo não tem a faixa nem a resolução dele, por isso continua fora do seletor.

## Como executar

```bash
cd backend
uv run pytest tests/analytic_vs_sim/test_as_peripherals.py   # AS-PER-01..03
uv run pytest tests/unit/api/test_devices.py -k peripheral
```

No aplicativo: Análise de dispositivos → **Sensores, atuadores e placas** → escolher a peça →
**Rodar os ensaios**. Os motores de indução, inversor, soft-starter e motor de passo levam de 15 a
30 s; os demais, poucos segundos.

## Revisão no Windows (2026-11-20)

O ensaio padrão do driver de passo ficou preso no ngspice 47 com integração trapezoidal.
A bancada de passo passou a usar `.options method=gear`, adequada à combinação dos reguladores
de corrente e estados mecânicos. Os modelos físicos, as condições e as tolerâncias não mudaram.
Os quatro ensaios existentes de driver, motor, micropasso e motor do catálogo passaram:
`pytest tests/analytic_vs_sim/test_as_peripherals.py -k stepper` (46,30 s no ambiente de revisão).

## Resultado dos testes

- `AS-PER-01`: as 21 bancadas com os valores padrão, todas as medidas dentro da tolerância.
- `AS-PER-02`: 10 bancadas fora do padrão (LM35 saturando, termopar J com junta fria a 0 °C, RTD
  com fios desiguais, relé de 12 V, contator CA, soft-starter em limitação de corrente, micropasso
  16, Arduino com outra carga etc.).
- `AS-PER-02` também cobre os modelos novos fora do padrão (NTC sem autoaquecimento, LDR com
  outro γ, Hall a 3,3 V, chave Hall com outra histerese, sensor de 100 kPa, HC-SR04 a 0 °C com uma
  distância fora do alcance, Arduino Mega com outro duty).
- `AS-PER-03`: peças do catálogo (relé SRD-05VDC-SL-C, LM35DZ, ACS712, 17HS19-2004S1, os dois NTC,
  GL5528, SS49E, A3144, MPX5700DP, HC-SR04, TMP36, KTY81-110, KTY81-210, DHT22, DS18B20 e
  BME280).
- Terceira etapa em `AS-PER-02`: TMP36 com offset, KTY81-210, DHT22 com temperatura negativa e com
  alimentação abaixo de 3,3 V, DS18B20 em 9 bits e sem pull-up, BME280 sem pull-ups e no endereço
  0x77 com pressão acima da faixa. Testes de unidade das bibliotecas em
  `tests/unit/cosim/test_libraries.py` (quadro do DHT22, cache de 2 s, resolução do DS18B20,
  endereço do BME280, mensagens de erro).
- Pela API, todas as peças do catálogo oferecidas nas bancadas foram rodadas: todas dentro da
  tolerância, exceto a família Kalatec "Motores de Passo" (ver limitações).
- Suíte completa do backend e do front-end rodada antes do PR (ver descrição do PR).

## Capturas

Em [capturas-bancada-perifericos/](capturas-bancada-perifericos/): LM35, relé, motor CC, Arduino
Uno, ESP32, CLP, ACS712, motor de indução e motor de passo; e, dos modelos novos, NTC, LDR, Hall
linear, chave Hall, pressão, HC-SR04 e Arduino Mega (10 a 16); da terceira etapa, KTY81, DHT22,
DS18B20, BME280 e Raspberry Pi Pico (17 a 21).

## Limitações conhecidas

- Peças do catálogo ainda sem modelo de simulação: ver a lista na segunda etapa acima.
- HC-SR04: o atraso entre o fim do pulso em TRIG e a subida do ECHO (rajada de 40 kHz) não é
  simulado, e o sensor exige passo de 2 µs (a simulação fica mais lenta quando ele está no
  circuito). O runtime do Arduino não tem `pulseIn`, então a bancada mede o eco direto no SPICE.
- O offset parametrizado distingue LM35 e TMP36. O TMP36 é ensaiado com o offset de 500 mV
  registrado no catálogo.
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

`pulseIn` no runtime do Arduino, para que o HC-SR04 possa ser lido por um programa; o quadro de
bits dos sensores digitais como forma de onda no fio, se for útil ver no osciloscópio; desenhos
próprios dos símbolos novos.
