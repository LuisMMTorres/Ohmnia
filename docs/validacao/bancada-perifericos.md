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
- `AS-PER-03`: peças do catálogo (relé SRD-05VDC-SL-C, LM35DZ, ACS712, 17HS19-2004S1).
- Pela API, todas as peças do catálogo oferecidas nas bancadas foram rodadas: todas dentro da
  tolerância, exceto a família Kalatec "Motores de Passo" (ver limitações).
- Suíte completa do backend e do front-end rodada antes do PR (ver descrição do PR).

## Capturas

Em [capturas-bancada-perifericos/](capturas-bancada-perifericos/): LM35, relé, motor CC, Arduino
Uno, ESP32, CLP, ACS712, motor de indução e motor de passo.

## Limitações conhecidas

- As peças do catálogo **sem modelo de simulação** (por exemplo DHT22, HC-SR04, BME280, sensores
  indutivos e fotoelétricos industriais, Arduino Mega/Nano, Raspberry Pi Pico, LAUNCHXL, CLPs
  comerciais) não entram nesta bancada: cada uma precisaria de um modelo novo com valores do
  datasheet. A bancada cobre todas as peças que o Simulador sabe simular.
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

Criar modelos de simulação para os sensores mais usados em aula que ainda não têm (DHT22, HC-SR04,
LDR, NTC), com valores do datasheet, para que entrem no Simulador e nesta bancada.
