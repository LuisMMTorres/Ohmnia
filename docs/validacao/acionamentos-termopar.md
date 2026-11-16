# Validação: acionamentos, motor de passo e termopar (pendências da Fase 11, decisão D12)

Data: 2026-11-16. Status: aguardando sua revisão.

Fecha o que a Fase 11 deixou de fora: motor de indução, inversor de frequência V/f completo,
soft-starter, motor de passo com driver, os exemplos de partida de motor e de posicionamento, e o
termopar. Tudo entra no simulador como os outros sensores e atuadores e funciona junto com o
Arduino, o ESP32 e o CLP. Manual: seção "Acionamentos e termopar" de
`docs/manual/08-microcontroladores-clp.md`.

## O que foi feito

| Item | Onde | Situação |
|---|---|---|
| Motor de indução trifásico (gaiola) | `schematic/drive_symbols.py` (`induction_motor`), referência analítica em `machines/induction.py` | ✅ modelo dinâmico em αβ; carga constante ou quadrática |
| Inversor de frequência V/f | `vfd` | ✅ rampas de aceleração e desaceleração, frequência mínima, boost, saída senoidal ou SPWM com injeção de 3ª harmônica |
| Soft-starter | `soft_starter` | ✅ rampa de tensão, limitação de corrente, kick start, parada suave, bypass |
| Contator tripolar | `contactor` | ✅ bobina CC ou CA, fecha em 75 % e abre em 40 % da nominal |
| Motor de passo híbrido | `stepper_motor`, referência em `machines/stepper.py` | ✅ duas fases, detent opcional, carga constante e atrito seco; peça do catálogo traz R, L, J, passo e K |
| Driver STEP/DIR | `stepper_driver`, contador em `cosim/engine.py` (`StepperDriverAdapter`) | ✅ micropasso 1 a 1/16, EN, regulação de corrente PI limitada a VM |
| Termopar | `thermocouple`, funções em `machines/thermocouple.py` | ✅ tipos J, K, T, E e N, junta fria pela temperatura dos terminais |
| Exemplo de partida de motor | `cosim/examples.py`, `motor_start_comparison` | ✅ CLP, contator, soft-starter e dois motores |
| Exemplo de posicionamento | `stepper_positioning` | ✅ Arduino, driver e 17HS19-2004S1 |
| Nós internos na ponta de prova | `schematic/netlist.py` | ✅ `m1_rpm`, `inv1_f` etc. podem ser pontas de tensão |

## Modelos (para a sua revisão)

### Motor de indução

Fluxos do estator e do rotor no referencial estacionário αβ (Krause, Wasynczuk e Sudhoff,
*Analysis of Electric Machinery and Drive Systems*, 2ª ed., cap. 4), cada um num capacitor de 1 F:

- dψs/dt = vs − R1·is; dψr/dt = −R2·ir ∓ ωr·ψr (rotor em curto);
- correntes pela inversa da matriz [[Ls, Lm], [Lm, Lr]], com Ls = X1/ω + Lm, Lr = X2/ω + Lm e
  Lm = Xm/ω na frequência de referência;
- Te = 3/2 · p · (ψsα·isβ − ψsβ·isα); J dω/dt = Te − TL − B ω.

As tensões vα e vβ vêm das tensões de linha, então o motor não precisa de neutro. Os integradores
partem de zero (`.ic`); sem isso o ponto de operação seria o regime CC de cada integrador, um motor
"girando" em t = 0. Em regime, com alimentação senoidal equilibrada, o modelo é o circuito
equivalente por fase (Chapman, *Electric Machinery Fundamentals*, 5ª ed., cap. 6), que é a
referência analítica dos testes.

Os parâmetros padrão são **didáticos**: 4 polos, 380 V em Y, R1 = 1,5 Ω, R2 = 1,2 Ω,
X1 = X2 = 2,5 Ω, Xm = 60 Ω, J = 0,02 kg·m². Dão cerca de 3,7 kW: 20 N·m a 1732 rpm, 7,35 A,
fator de potência 0,83, corrente de rotor bloqueado de 39,4 A (5,4 × In), torque máximo de
54 N·m (2,7 × Tn). O catálogo não tem motor de indução com circuito equivalente; troque pelos do
seu motor (ensaio a vazio e de rotor bloqueado).

### Inversor V/f

- Frequência: rampa limitada a fnom/aceleração e fnom/desaceleração, seguindo a referência
  AI (0 a 10 V); RUN-COM ≥ 11 V liga. Os nomes seguem o CFW500 (P0100, P0101, P0133, P0136;
  manual WEG, p. 38 e p. 39), mas o modelo é genérico.
- Tensão de linha: vnom · min(1, boost + (1 − boost) f/fnom), com o boost aplicado só acima de
  1 Hz (senão 0 Hz daria tensão CC no motor).
- Saída senoidal: só a fundamental (modelo médio). SPWM: portadora triangular de 5 kHz (CFW500,
  Tabela B.4, p. 153) e referência com 1/6 de 3ª harmônica, que estende a região linear até
  Vlinha = Vcc/√2, o mesmo alcance do SVPWM (Holmes e Lipo, *Pulse Width Modulation for Power
  Converters*, cap. 6). Barramento padrão de 537 V (√2 × 380 V).

### Soft-starter

Modelo da fundamental: a tensão em cada terminal T é vn + k (vL − vn), com vn a média das três
fases da rede, e a corrente na rede é k vezes a do motor (balanço de potência). k:

- rampa de tensão: salta para a tensão inicial e sobe até 1 no tempo da rampa;
- limitação de corrente: sobe enquanto a corrente está abaixo do limite e desce acima dele
  (o SSW-07 mantém a corrente no limite até o motor chegar à velocidade, p. 32);
- kick start: 80 % da tensão durante o tempo escolhido (SSW-07, p. 31);
- sem RUN: rampa de desaceleração (para bombas, p. 33) ou parada livre;
- k = 1 ao fim: bypass.

A corrente de linha é o módulo do vetor αβ dividido por √2, que é o valor eficaz para correntes
senoidais equilibradas, sem filtro. As harmônicas do disparo dos tiristores não são simuladas.

### Motor de passo e driver

- Motor de duas fases (Kenjo, *Stepping Motors and Their Microprocessor Controls*, 2ª ed.,
  cap. 4): e_a = −K ω sen Nθ, e_b = K ω cos Nθ, T = K (−i_a sen Nθ + i_b cos Nθ) − T_det sen 4Nθ,
  N = 90°/passo (50 dentes para 1,8°). A corrente de cada fase é um estado (L di/dt = v − R i − e),
  retirado dos terminais por fonte de corrente: um indutor entre fontes de tensão travava o passo
  de tempo.
- Constante de torque a partir do datasheet: K = T_hold / (√2 · I_nominal). **Premissa:** o
  torque de retenção é medido com as duas fases na corrente nominal (vetor de corrente de
  módulo √2 I). Confirme na tabela do seu motor. Para o 17HS19-2004S1 (0,59 N·m, 2,0 A):
  K = 0,2086 N·m/A.
- Driver: conta as bordas de subida de STEP (DIR alto soma), EN baixo ou solto habilita. Ângulo
  elétrico = 45° + passos × 90°/micropasso, então o passo inteiro tem as duas fases a 70,7 %, e a
  origem do rotor fica em 0,9° (meio passo). Corrente de cada fase por um laço PI (20 V/A, zero em
  1000 rad/s) com saída limitada a ±VM por tanh; o driver retira de VM a potência entregue.
  Valores do driver são **didáticos** (não é um A4988 ou DRV8825 específico).

### Termopar

E(T) das funções de referência NIST ITS-90 (Monograph 175; as mesmas da IEC 60584-1), com a junta
de referência a 0 °C; a saída é E(T) − E(T_ref). Coeficientes transcritos da tabela de dados do
pacote de domínio público `thermocouples_reference` 0.20 (módulo `source_NIST`, "NIST SRD 60"),
porque o site do NIST está fora da rede liberada nesta sessão. Conferência contra as tabelas
Omega da sua pasta `datasheets-baixados/26_Temperatura_RTD_e_Termopar`: **todos os 1177 pontos do
tipo K (Z-204) e os 1397 do tipo E (Z-206)** batem com erro máximo de 0,0005 mV, que é o
arredondamento da terceira casa. J, T e N não têm tabela na pasta: conferidos só pela forma
(zero em 0 °C) e pela fonte.

## Resultados (analítico × ngspice)

Testes em `tests/analytic_vs_sim/test_as_drives.py` (AS-DRV) e `tests/unit/cosim/test_examples.py`.

| Caso | Analítico | ngspice | Tolerância |
|---|---|---|---|
| AS-DRV-01 partida direta, 20 N·m: velocidade | 1728,3 rpm | 1729,1 rpm | 0,2 % |
| AS-DRV-01 corrente de linha | 7,636 A | 7,639 A | 1 % |
| AS-DRV-01 torque (carga + atrito) | 20,905 N·m | 20,905 N·m | 1 % |
| AS-DRV-01 pico de corrente na partida | 5 a 8 × In | 48,6 A (6,4 × In) | faixa |
| AS-DRV-02 inversor a 30 Hz, carga quadrática: velocidade | 884,07 rpm | 884,17 rpm | 0,5 % |
| AS-DRV-02 corrente | 3,895 A | 3,894 A | 1 % |
| AS-DRV-02 rampa: 15 Hz em 1,25 s; tensão a 30 Hz | 15 Hz; 195,7 V | 15 Hz; 195,7 V | 1 % e 0,1 % |
| AS-DRV-03 SPWM: fundamental da tensão de linha | 380 V | dentro de 1,5 % | 1,5 % |
| AS-DRV-03 SPWM: velocidade | regime senoidal | dentro de 0,5 % | 0,5 % |
| AS-DRV-04 rampa de tensão: k em 2,5 s da rampa | 0,675 | 0,674 | 1 % |
| AS-DRV-04 limitação de corrente em 20 A: maior corrente | ≤ 20 A | 19,45 A | +3 % |
| AS-DRV-04 regime depois do bypass | 1733,9 rpm | 1734,7 rpm | 0,2 % |
| AS-DRV-05 passo: 40 passos à frente e 10 para trás | 0,9 + 30 × 1,8 − atraso | dentro de 0,05° | 0,05° |
| AS-DRV-05 atraso com 0,15 N·m | asin(T_L/(K I))/N = 0,573° | idem | idem |
| AS-DRV-05 corrente da fase | 1,5 × cos 45° = 1,061 A | dentro de 1 % | 1 % |
| AS-DRV-06 termopar J, K, T, E, N (T_ref = 25 °C) | NIST | dentro de 1 µV | 1 µV |

| Exemplo | Esperado | Simulado |
|---|---|---|
| E6 partida direta × soft-starter | direta: 5 a 8 × In; soft: limite de 15 A | 48,4 A × 14,9 A; os dois a 1734,7 rpm; I1 em 9 s desliga, o soft-starter com rampa de 2 s |
| E7 posicionamento | 180°, 90° e 0° (mais 0,9° da origem do driver) | 180,9°, 90,9° e 0,9°; monitor serial com "posição: 180.00 graus" etc. |

## Achados durante o trabalho

- Ponto de operação: sem `.ic` nos integradores, o ngspice resolvia o regime CC (fluxo CC no
  motor, 146 A de pico na partida). Com `.ic` em zero, o pico ficou em 48,6 A, coerente com a
  corrente de rotor bloqueado mais o deslocamento CC.
- Limitador por min/max no driver fazia o ponto de operação falhar no gmin stepping, e o
  indutor entre fontes de tensão travava o passo de tempo. Trocados por tanh e pela corrente
  como estado.
- Um motor de passo a 200 passos/s com inércia só do rotor está perto da ressonância
  (√(K I N / J) ≈ 220 Hz com 1,5 A) e perde passo com carga; o teste usa 50 passos/s. É um
  fenômeno real que vale mostrar em aula.

## Testes

- Novos: `tests/unit/machines/test_machines.py` (13: tabelas do termopar, balanço de potência,
  torque máximo, carga quadrática, relações do motor de passo), `tests/unit/cosim/test_drives.py`
  (4: símbolos, peça do catálogo, passo máximo, contator), `tests/analytic_vs_sim/test_as_drives.py`
  (11) e dois exemplos em `test_examples.py`.
- Resultado da suíte completa: ver a mensagem de entrega.

## Limitações conhecidas

- Motor de indução sem saturação magnética, perdas no ferro e efeito pelicular; parâmetros
  padrão didáticos.
- Inversor sem barramento CC dinâmico (sem frenagem nem sobretensão na desaceleração) e sem
  controle vetorial; SPWM ideal (sem tempo morto).
- Soft-starter sem harmônicas do disparo, sem proteções e sem o erro de tempo de partida.
- Driver de motor de passo genérico; não modela decaimento rápido ou lento do chopper.
- SCT-013 e ZMPT101B continuam sem modelo (sem PDF na pasta).
- O termopar não tem amplificador com compensação de junta fria pronto (MAX6675, AD8495): monte
  com amp-op e LM35, ou peça e eu faço o símbolo do MAX6675, cujo datasheet está na pasta.

## O que pedir a você

1. Conferir a premissa do torque de retenção (duas fases energizadas) nos motores de passo do
   catálogo.
2. Se tiver dados de placa ou ensaio de um motor de indução (WEG W22, por exemplo), passar para eu
   cadastrar um motor real e estimar o circuito equivalente.
3. Rodar os dois exemplos novos no simulador.
