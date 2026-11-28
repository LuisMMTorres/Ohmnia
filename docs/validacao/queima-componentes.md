# Queima de componentes na simulação (2026-11-20)

Depois de cada simulação, o programa compara a tensão, a corrente, a potência e a temperatura
de junção de cada peça com os limites dela. Uma peça acima de algum limite aparece como
**QUEIMOU** no esquemático e **QUEIMADO** na protoboard. Uma caixa de alerta mostra o motivo, o
que fazer para evitar e de onde vem o limite.

## De onde vêm os limites

Nenhum limite é inventado (regra 1):

- **Peça do catálogo**: valores máximos absolutos do datasheet, com documento, revisão e página.
  Se o valor ainda está como rascunho no catálogo, o alerta avisa "valor do catálogo ainda não
  revisado".
- **Peça genérica**: só é verificada quando você informa o limite. O resistor tem o campo
  **Potência nominal** (ex.: 0.25 para 1/4 W). O capacitor tem o campo **Tensão nominal**. O
  indutor tem o campo **Corrente nominal** (corrente eficaz máxima, como o I_rms dos indutores do
  catálogo). Em branco, não há verificação.
- **LED e lâmpada**: continuam usando IF máx. e Pn. O LED do catálogo também verifica a tensão
  reversa (VR).

| Peça | Limites verificados (quando o datasheet traz) |
|------|-----------------------------------------------|
| Diodo | VRRM (pico reverso), IF(AV) (média), IFSM (pico), Ptot e Tj |
| Zener | Ptot e Tj, IZM |
| LED | VR, IF máx. |
| BJT NPN/PNP | VCEO, VEBO (pico), IC (média), ICM (pico), Ptot e Tj |
| MOSFET N | VDS, VGS (pico), ID (média), IDM (pico), Ptot e Tj |
| JFET N | VDG, Ptot e Tj |
| IGBT | VCES, VGES, IC, ICM, Ptot e Tj |
| SCR | VDRM, VRRM, IT(RMS) (eficaz), ITSM (pico) |
| TRIAC | VDRM, IT(RMS), ITSM |
| Amp. op. | VID máx. (diferença entre as entradas) |
| Potenciômetro | V máx. e P nominal |
| Chaves e relé | corrente nominal do contato (eficaz) |
| Resistor genérico | potência nominal informada |
| Capacitor genérico | tensão nominal informada |
| Indutor genérico | corrente nominal informada (eficaz) |

## Como cada grandeza é medida

- **Tensão**: pico da tensão de bloqueio no sentido em que o datasheet a define (ex.: VRRM =
  v(K) − v(A)). Nos limites simétricos (VGS, VID) usa-se o módulo.
- **Corrente contínua** (IF(AV), IC, ID): valor médio da **segunda metade** da simulação, para a
  partida não contar. IT(RMS), corrente de contato e corrente nominal do indutor: valor eficaz da segunda metade. Picos
  repetitivos ou de surto (IFSM, ICM, IDM, ITSM): pico em toda a simulação.
- **Corrente**: medida por uma fonte de 0 V em série com um pino (anodo, coletor, dreno...),
  que não altera o circuito.
- **Potência**: média de |v·i| na segunda metade. No resistor, P = v²/R.
- **Temperatura de junção**: Tj = Ta + P·Rθja, com Ta = temperatura da simulação, **sem
  dissipador** e em regime. Se a peça for usada com dissipador, esse valor é pessimista. Se a
  simulação for curta perto da constante térmica, a conta considera o regime mesmo assim.

## Testes

| Teste | O que garante |
|-------|---------------|
| `tests/unit/schematic/test_stress.py::test_catalogue_diode_gets_its_ratings_with_their_page` | 1N4148 (Vishay 81857 rev. 1.6, p. 1) traz VRRM 100 V, IF(AV) 150 mA, IFSM 2 A, Ptot 440 mW e Tj, com a página. A corrente é medida no anodo. |
| `...::test_generic_parts_are_checked_only_with_a_rating_typed_by_the_user` | Resistor e capacitor genéricos só são verificados com o limite informado. |
| `...::test_generic_inductor_with_rated_current_gets_a_sensed_rms_limit` | Indutor genérico com corrente nominal ganha a fonte de 0 V no pino 1 e o limite eficaz; sem ela, nada é acrescentado. |
| `...::test_evaluate_uses_peak_for_voltage_and_second_half_mean_for_current` | Pico para tensão, média da segunda metade para corrente (a partida não conta). |
| `...::test_junction_temperature_is_ambient_plus_power_times_rth` | Tj = Ta + P·Rθja. |
| `...::test_as_diode_without_enough_resistance_burns` (AS-, ngspice) | 5 V num 1N4148 com 10 Ω: corrente média = (5 − VK)/10 ± 2 %, acima de IF(AV). Com 1 kΩ nada é acusado. |
| `...::test_as_resistor_power_matches_v_squared_over_r` (AS-, ngspice) | 12 V em 100 Ω de 1/4 W: P = 1,44 W ± 0,5 %, acima do nominal. |
| `...::test_as_generic_inductor_rms_current_matches_v_over_r` (AS-, ngspice) | 12 V, 10 Ω e 1 mH por 2 ms: corrente eficaz da segunda metade = V/R = 1,2 A ± 0,5 %, acima da corrente nominal de 0,5 A. |
| `frontend/src/schematic/damage.test.ts` | Agrupamento por peça na caixa de alerta, inclusive LEDs que queimam. |

Capturas: `/mnt/project-files/capturas/queima-componentes/`.

## Limitações conhecidas

- A temperatura não considera dissipador nem a capacidade térmica: é o regime ao ar livre.
- Ptot é comparado como publicado, que costuma ser a 25 °C (ambiente ou cápsula). A redução com
  a temperatura (derating) não é aplicada; o teste de Tj cobre o aquecimento ao ar livre.
- Peças genéricas sem limite informado (indutor sem corrente nominal, transistores genéricos)
  não são verificadas.
- Fontes, motores, transformadores e placas (Arduino, ESP32, CLP) ainda não são verificados.
- O modelo do LED é de queda constante: ligado direto numa fonte ideal, a corrente fica
  limitada só pela fonte (o alerta mostra "mais de 1 kA").
- A corrente nominal do indutor genérico só verifica aquecimento (valor eficaz). A saturação do
  núcleo não é modelada: a indutância continua constante acima de qualquer corrente.
