# Validação: fontes reguladas e amplificadores (Fase 4)

Data: 2026-11-14. Status: aguardando aprovação da Fase 4.

Oito módulos novos na aba **Projeto**, todos com o mesmo caminho da Fase 3: especificação →
cálculo com memória → escolha de peças reais → margens e temperatura de junção (com dissipador do
catálogo quando preciso) → conferência com o ngspice → esquemático, lista de materiais, relatório e
roteiro de prática.

| Módulo | Variantes | Grandezas principais |
|---|---|---|
| `DM-ZEN` | Zener simples; Zener + transistor série | Rs, IZ nos dois extremos (Vin mín. e carga máx.; Vin máx. e carga mín.), PZ, regulação de linha e de carga, potência do transistor |
| `DM-LIN` | fixo (78xx/79xx) ou ajustável (LM317/LM337); baixa queda (LDO: NCP1117, LM2931, fixos e ajustáveis); positiva, negativa ou simétrica | escolha do CI, R1/R2, folga no vale da ondulação, PD, Tj, dissipador, capacitores do datasheet |
| `DM-BIAS` | polarização fixa, estabilizada pelo emissor, divisor, realimentação de coletor, MOSFET com divisor, JFET com autopolarização e JFET com divisor | ponto Q (exato, junção exponencial), IC com hFE mín. e máx., reta de carga |
| `DM-SSA` | emissor comum, coletor comum, base comum, fonte comum (MOSFET e JFET) | Av, Avs, Zin, Zout, capacitores pelo fL pedido, fL e fH (Bode), excursão |
| `DM-DIFF` | cauda resistiva ou espelho de corrente | IC, Ad, Acm, CMRR, faixa de modo comum |
| `DM-PA` | classe A (carga em série), B e AB complementares, B e AB com Darlingtons complementares | Po, Pi, η, PQ máx., THD, dissipador |
| `DM-PAD` | classe D em meia ponte (±VCC), dois MOSFETs canal N, PWM de amostragem natural, filtro LC Butterworth | L e C, índice de modulação, Po, Pi, η, corrente no indutor, ondulação residual, perdas de condução e de comutação (estimativa) |
| `DM-CHAVE` | TBJ, Darlington ou MOSFET no lado de baixo; carga resistiva ou indutiva (diodo de roda livre) | RB com β forçado, VCE(sat)/RDS(on), perdas, aviso de acionamento fora do nível lógico |
| `DM-FORMA` | ceifador paralelo, série e duplo; grampeador; multiplicador de Cockcroft-Walton (n estágios) | níveis de saída, VC, PIV, ondulação e queda com carga |

## Como os cálculos são feitos

A regra 4 (cálculo e simulação concordam) é cumprida usando **as mesmas equações de dispositivo**
no cálculo e no simulador:

- **TBJ:** modelo de Ebers-Moll. BF vem do hFE do datasheet (típico; senão a média geométrica de
  mín. e máx.) no ponto de ensaio mais próximo da IC de projeto; IS vem da premissa VBE = 0,7 V na
  corrente de ensaio do hFE (o catálogo não traz IS). O mesmo `.model` vai para o ngspice. Cπ e Cμ
  saem de fT e Cobo quando o datasheet traz (Sedra & Smith, 7ª ed., cap. 10).
- **MOSFET:** quadrático (LEVEL 1), VT no meio da faixa de VGS(th), KP de RDS(on) no VGS de ensaio.
  É didático: avisa que um MOSFET de potência perto do limiar foge bastante disso.
- **Zener:** linear por partes, VZ0 + rz·IZ, com VZ, IZT e rz (ZZT) do datasheet.
- **Diodo (DM-FORMA):** queda constante VF do datasheet, igual ao DM-RET1.
- **Reguladores:** fonte dependente (B) `min(VO, VI − queda)` com VO/Vref, IAdj e IQ do datasheet.
- **Ponto Q:** solução exata da malha com a junção exponencial (brentq), não a aproximação de
  0,7 V; a memória mostra a fórmula de livro e o valor exato.
- **Pequenos sinais:** solução nodal exata do circuito π-híbrido com todos os capacitores (a mesma
  conta do `.ac` do SPICE); fL e fH saem da curva (−3 dB), não da soma de polos.
- **JFET:** equação de Shockley (NJF do SPICE, `BETA = IDSS/VP²`, `VTO = −VP`). IDSS típico (senão
  média geométrica de mín. e máx.); VP = 2·IDSS/|yfs| (yfs do datasheet), com aviso quando cai fora
  da faixa de VGS(off). CGS e CGD constantes de Ciss e Crss.
- **Darlington:** dois transistores de Ebers-Moll iguais dentro de um `.subckt`; β de cada um de
  hFE = β² + 2β e IS tal que cada junção fica em 0,7 V na corrente de ensaio do hFE.
- **LDO:** mesmo regulador comportamental, com a queda (dropout) ou a menor diferença VI − VO do
  datasheet do LDO escolhido. Peças LDO marcadas no catálogo (`tags: [ldo]`, classificação do
  fabricante); a opção "Baixa queda (LDO)" escolhe só entre elas. Capacitores de entrada e saída
  vêm da aplicação típica do datasheet da peça (o LM2931 exige 100 µF na saída, por estabilidade).
  Sem corrente mínima de carga no datasheet (LM2931AC), R1 conduz 100·IAdj (critério de projeto,
  com aviso).
- **Classe D:** chaves com RDS(on) máximo do datasheet ligadas e 1 GΩ desligadas (o mesmo elemento
  `SW` com RON/ROFF no ngspice), comandadas pelo mesmo comparador (senoide × triangular). Entre
  as comutações o circuito é linear: instantes de comutação por brentq, estado [iL, vC] pela
  exponencial de matriz e regime periódico exato x0 = (I − Φ(T))⁻¹·g. Filtro Butterworth de 2ª
  ordem carregado por RL: L = √2·RL/ωc e C = 1/(√2·RL·ωc) (dedução a partir de H(s)). Perda de
  comutação estimada com tr e tf do datasheet (Mohan, Undeland & Robbins, 3ª ed., cap. 2), não
  simulada.
- **Classes B e AB:** solução quase estática do seguidor complementar com a junção exponencial em
  4 096 pontos por período: Po, Pi, PQ e THD (distorção de cruzamento incluída).
- **Multiplicador:** fórmulas de Cockcroft-Walton com descarga linear
  (ΔV = Io/(fC)·(2n³/3 + n²/2 − n/6), δV = Io/(fC)·n(n+1)/2; Kuffel, Zaengl & Kuffel, 2ª ed., cap. 2).
  São aproximações; a simulação é a referência exata e a tolerância diz isso.

## Conferência com o ngspice (AS-*)

`tests/analytic_vs_sim/test_as_fase4.py`, 44 casos, critério didático, catálogo real liberado.
Medido em 2026-11-14. Maior erro nas grandezas exatas: 0,60 % (THD da classe AB, tolerância 5 %).
O multiplicador, que usa fórmulas aproximadas, chega a 6,1 % na ondulação (tolerância 25 %,
justificada no próprio teste). Na classe D o erro restante (até 0,16 %) vem do passo do
simulador, que desloca os instantes de comutação (passo de Ts/400).

| Caso | Módulo | Peças | Grandeza | Cálculo | ngspice | Erro | Tol. |
|---|---|---|---|---|---|---|---|
| zen_simples | DM-ZEN | 1N4739A | Saída, entrada mínima e carga máxima | 8,986 V | 8,986 V | 0,000 % | 0.5 % |
|  |  |  | Saída, entrada máxima e carga mínima | 9,239 V | 9,239 V | 0,000 % | 0.5 % |
|  |  |  | IZ, entrada mínima e carga máxima | 5,104 mA | 5,104 mA | 0,000 % | 1 % |
|  |  |  | IZ, entrada máxima e carga mínima | 55,85 mA | 55,85 mA | 0,000 % | 1 % |
| zen_transistor | DM-ZEN | 1N5240B, P2N2222A | Saída, entrada mínima e carga máxima | 9,016 V | 9,016 V | 0,004 % | 0.5 % |
|  |  |  | Saída, entrada máxima e carga mínima | 9,705 V | 9,705 V | 0,001 % | 0.5 % |
|  |  |  | IZ, entrada mínima e carga máxima | 2,488 mA | 2,488 mA | 0,010 % | 1 % |
|  |  |  | IZ, entrada máxima e carga mínima | 16,81 mA | 16,81 mA | 0,000 % | 1 % |
| lin_fixo_pos | DM-LIN | MC7805CT | Tensão de saída (média) | 5 V | 5 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,5065 A | 0,5065 A | 0,000 % | 0.5 % |
| lin_fixo_neg | DM-LIN | MC7912CT | Tensão de saída (média) | 12 V | 12 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,508 A | 0,508 A | 0,000 % | 0.5 % |
| lin_fixo_sim | DM-LIN | MC7815CT, MC7915CT | Tensão de saída (média) | 15 V | 15 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,5065 A | 0,5065 A | 0,000 % | 0.5 % |
| lin_ajust | DM-LIN | LM317T | Tensão de saída (média) | 9,041 V | 9,041 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,5106 A | 0,5106 A | 0,000 % | 0.5 % |
| lin_ajust_sim | DM-LIN | LM317T, LM337T | Tensão de saída (média) | 9,041 V | 9,041 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,5106 A | 0,5106 A | 0,000 % | 0.5 % |
| lin_ldo_fixo | DM-LIN | NCP1117DT50G | Tensão de saída (média) | 5 V | 5 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,51 A | 0,51 A | 0,000 % | 0.5 % |
| lin_ldo_100ma | DM-LIN | LM2931T-5.0G | Tensão de saída (média) | 5 V | 5 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,11 A | 0,11 A | 0,000 % | 0.5 % |
| lin_ldo_ajust | DM-LIN | LM2931ACD2TR4G | Tensão de saída (média) | 3,303 V | 3,303 V | 0,000 % | 0.5 % |
|  |  |  | Corrente média de entrada | 0,05002 A | 0,05002 A | 0,000 % | 0.5 % |
| bias_fixa | DM-BIAS | BC548B | Corrente de coletor | 2,048 mA | 2,048 mA | 0,003 % | 0.5 % |
|  |  |  | VCE | 5,856 V | 5,856 V | 0,003 % | 0.5 % |
|  |  |  | Tensão de base | 0,7006 V | 0,701 V | 0,050 % | 0.5 % |
| bias_emissor | DM-BIAS | BC548B | Corrente de coletor | 1,95 mA | 1,95 mA | 0,003 % | 0.5 % |
|  |  |  | VCE | 6,106 V | 6,106 V | 0,003 % | 0.5 % |
|  |  |  | Tensão de base | 1,913 V | 1,913 V | 0,016 % | 0.5 % |
| bias_divisor | DM-BIAS | BC548B | Corrente de coletor | 1,899 mA | 1,898 mA | 0,027 % | 0.5 % |
|  |  |  | VCE | 6,261 V | 6,262 V | 0,025 % | 0.5 % |
|  |  |  | Tensão de base | 1,88 V | 1,88 V | 0,001 % | 0.5 % |
| bias_coletor | DM-BIAS | BC548B | Corrente de coletor | 2,012 mA | 2,012 mA | 0,003 % | 0.5 % |
|  |  |  | VCE | 5,903 V | 5,903 V | 0,003 % | 0.5 % |
|  |  |  | Tensão de base | 1,952 V | 1,952 V | 0,016 % | 0.5 % |
| bias_mos | DM-BIAS | IRF540 | Corrente de dreno | 10,83 mA | 10,83 mA | 0,000 % | 0.5 % |
|  |  |  | VDS | 5,608 V | 5,608 V | 0,000 % | 0.5 % |
|  |  |  | Tensão de porta | 4,408 V | 4,408 V | 0,000 % | 0.5 % |
| bias_jfet_auto | DM-BIAS | 2N5457 | Corrente de dreno | 1,018 mA | 1,018 mA | 0,001 % | 0.5 % |
|  |  |  | VDS | 5,973 V | 5,973 V | 0,001 % | 0.5 % |
|  |  |  | Tensão de fonte | 0,8349 V | 0,8349 V | 0,001 % | 0.5 % |
| bias_jfet_divisor | DM-BIAS | 2N5457 | Corrente de dreno | 0,9971 mA | 0,9971 mA | 0,000 % | 0.5 % |
|  |  |  | VDS | 6,117 V | 6,117 V | 0,000 % | 0.5 % |
|  |  |  | Tensão de fonte | 1,196 V | 1,196 V | 0,000 % | 0.5 % |
| ssa_ec | DM-SSA | BC548B | Corrente de polarização | 1,003 mA | 1,003 mA | 0,028 % | 1 % |
|  |  |  | Ganho na frequência do sinal | 9,672  | 9,671  | 0,005 % | 1 % |
|  |  |  | Frequência de corte inferior | 86,31 Hz | 86,3 Hz | 0,004 % | 2 % |
|  |  |  | Frequência de corte superior | 8969 kHz | 8969 kHz | 0,003 % | 2 % |
| ssa_ec_bypass | DM-SSA | BC548B | Corrente de polarização | 1,035 mA | 1,035 mA | 0,030 % | 1 % |
|  |  |  | Ganho na frequência do sinal | 128,5  | 128,4  | 0,069 % | 1 % |
|  |  |  | Frequência de corte inferior | 95,41 Hz | 95,35 Hz | 0,067 % | 2 % |
|  |  |  | Frequência de corte superior | 1068 kHz | 1069 kHz | 0,067 % | 2 % |
| ssa_cc | DM-SSA | BC548B | Corrente de polarização | 1,009 mA | 1,009 mA | 0,007 % | 1 % |
|  |  |  | Ganho na frequência do sinal | 0,9782  | 0,9782  | 0,002 % | 1 % |
|  |  |  | Frequência de corte inferior | 72,51 Hz | 72,51 Hz | 0,000 % | 2 % |
|  |  |  | Frequência de corte superior | 1,452e+05 kHz | 1,452e+05 kHz | 0,001 % | 2 % |
| ssa_bc | DM-SSA | BC548B | Corrente de polarização | 1,035 mA | 1,034 mA | 0,025 % | 1 % |
|  |  |  | Ganho na frequência do sinal | 5,595  | 5,595  | 0,004 % | 1 % |
|  |  |  | Frequência de corte inferior | 79,41 Hz | 79,41 Hz | 0,003 % | 2 % |
|  |  |  | Frequência de corte superior | 2,59e+04 kHz | 2,59e+04 kHz | 0,000 % | 2 % |
| ssa_fc | DM-SSA | IRF540 | Corrente de polarização | 10,83 mA | 10,83 mA | 0,001 % | 1 % |
|  |  |  | Ganho na frequência do sinal | 4,221  | 4,221  | 0,001 % | 1 % |
|  |  |  | Frequência de corte inferior | 70,38 Hz | 70,38 Hz | 0,000 % | 2 % |
| ssa_fcj | DM-SSA | 2N5457 | Corrente de polarização | 0,9971 mA | 0,9971 mA | 0,001 % | 1 % |
|  |  |  | Ganho na frequência do sinal | 6,062  | 6,062  | 0,000 % | 1 % |
|  |  |  | Frequência de corte inferior | 78,64 Hz | 78,64 Hz | 0,000 % | 2 % |
|  |  |  | Frequência de corte superior | 1,248e+04 kHz | 1,248e+04 kHz | 0,000 % | 2 % |
| diff_resistor | DM-DIFF | BC547A | Corrente de coletor de Q1 | 1,005 mA | 1,005 mA | 0,002 % | 0.5 % |
|  |  |  | Ganho diferencial (c2) | 120,5  | 120,4  | 0,052 % | 0.5 % |
|  |  |  | Ganho de modo comum (c2) | 0,5493  | 0,5493  | 0,000 % | 0.5 % |
| diff_espelho | DM-DIFF | BC547A | Corrente de coletor de Q1 | 0,9549 mA | 0,9549 mA | 0,001 % | 0.5 % |
|  |  |  | Ganho diferencial (c2) | 114,5  | 114,4  | 0,051 % | 0.5 % |
| pa_a | DM-PA | TIP31G | Corrente média de coletor | 0,9375 A | 0,9375 A | 0,000 % | 0.5 % |
|  |  |  | Tensão eficaz na carga (CA) | 2 V | 2 V | 0,000 % | 1 % |
| pa_b | DM-PA | BD135, TIP32G | Tensão eficaz na carga | 6,208 V | 6,208 V | 0,005 % | 0.5 % |
|  |  |  | Corrente média de Q1 | 0,3286 A | 0,3285 A | 0,006 % | 1 % |
|  |  |  | THD da tensão na carga | 4,193 % | 4,195 % | 0,050 % | 5 % |
| pa_ab | DM-PA | BD135, TIP32G | Tensão eficaz na carga | 6,313 V | 6,312 V | 0,005 % | 0.5 % |
|  |  |  | Corrente média de Q1 | 0,3423 A | 0,3422 A | 0,014 % | 1 % |
|  |  |  | THD da tensão na carga | 0,334 % | 0,336 % | 0,597 % | 5 % |
| pa_b_darlington | DM-PA | TIP120, TIP125 | Tensão eficaz na carga | 6,087 V | 6,086 V | 0,010 % | 0.5 % |
|  |  |  | Corrente média de Q1 | 0,3288 A | 0,3288 A | 0,012 % | 1 % |
|  |  |  | THD da tensão na carga | 8,024 % | 8,028 % | 0,051 % | 5 % |
| pa_ab_darlington | DM-PA | TIP120, TIP125 | Tensão eficaz na carga | 6,299 V | 6,298 V | 0,010 % | 0.5 % |
|  |  |  | Corrente média de Q1 | 0,3543 A | 0,3542 A | 0,019 % | 1 % |
|  |  |  | THD da tensão na carga | 0,6729 % | 0,6769 % | 0,596 % | 5 % |
| pad_padrao | DM-PAD | IRF540 | Tensão eficaz na carga | 8,953 V | 8,949 V | 0,038 % | 0.5 % |
|  |  |  | Corrente de pico no indutor | 1,9 A | 1,898 A | 0,147 % | 1 % |
|  |  |  | Corrente média da fonte positiva | 0,2107 A | 0,2103 A | 0,157 % | 2 % |
| pad_4ohm | DM-PAD | IRFZ44 | Tensão eficaz na carga | 8,945 V | 8,946 V | 0,013 % | 0.5 % |
|  |  |  | Corrente de pico no indutor | 3,243 A | 3,246 A | 0,118 % | 1 % |
|  |  |  | Corrente média da fonte positiva | 0,6714 A | 0,6719 A | 0,073 % | 2 % |
| chave_tbj_ind | DM-CHAVE | 1N4148, 2N3904 | Corrente de coletor | 99,29 mA | 99,29 mA | 0,000 % | 0.5 % |
|  |  |  | VCE de saturação | 0,08487 V | 0,08492 V | 0,054 % | 1 % |
| chave_tbj_res | DM-CHAVE | 2N3904 | Corrente de coletor | 99,29 mA | 99,29 mA | 0,000 % | 0.5 % |
|  |  |  | VCE de saturação | 0,08487 V | 0,08492 V | 0,054 % | 1 % |
| chave_darlington_ind | DM-CHAVE | 1N4148, TIP120 | Corrente de coletor | 93,99 mA | 93,98 mA | 0,003 % | 0.5 % |
|  |  |  | VCE de saturação | 0,7215 V | 0,7219 V | 0,052 % | 1 % |
| chave_darlington_res | DM-CHAVE | TIP120 | Corrente de coletor | 934 mA | 934 mA | 0,004 % | 0.5 % |
|  |  |  | VCE de saturação | 0,792 V | 0,7924 V | 0,051 % | 1 % |
| chave_mos | DM-CHAVE | 1N5400, IRF540 | Corrente de dreno | 993,5 mA | 993,5 mA | 0,000 % | 0.5 % |
|  |  |  | VDS em condução | 0,07804 V | 0,07804 V | 0,000 % | 1 % |
| forma_paralelo | DM-FORMA | 1N4148 | Média da saída | -1,412 V | -1,412 V | 0,000 % | 1 % |
|  |  |  | Máximo da saída | 4 V | 4 V | 0,000 % | 1 % |
| forma_serie | DM-FORMA | 1N4148 | Média da saída | 1,441 V | 1,441 V | 0,033 % | 1 % |
|  |  |  | Máximo da saída | 6 V | 6 V | 0,000 % | 1 % |
| forma_duplo | DM-FORMA | 1N4148 | Mínimo da saída | -4 V | -4 V | 0,000 % | 1 % |
|  |  |  | Máximo da saída | 4 V | 4 V | 0,000 % | 1 % |
| forma_grampeador | DM-FORMA | 1N4148 | Média da saída | 11,99 V | 11,99 V | 0,000 % | 1 % |
|  |  |  | Máximo da saída | 21,99 V | 21,99 V | 0,000 % | 1 % |
| forma_grampeador_neg | DM-FORMA | 1N4148 | Média da saída | 6,686 V | 6,686 V | 0,000 % | 1 % |
|  |  |  | Máximo da saída | 16,66 V | 16,66 V | 0,000 % | 1 % |
| forma_dobrador | DM-FORMA | 1N4148 | Média da saída | 17,74 V | 17,62 V | 0,672 % | 3 % |
|  |  |  | Ondulação de pico a pico | 0,2609 V | 0,2459 V | 5,743 % | 25 % |
| forma_cw3 | DM-FORMA | 1N4004 | Média da saída | 563 V | 561,8 V | 0,224 % | 3 % |
|  |  |  | Ondulação de pico a pico | 8,28 V | 7,773 V | 6,125 % | 25 % |

## Casos de referência propostos (GT-P8..P15)

`tests/golden/test_gt_fase4.py`. Mesmo tratamento dos P1–P7 (D6): exercícios no estilo do
Boylestad resolvidos pela fórmula fechada, **aguardando a sua conferência**. Tabela em
[casos-referencia-propostos.md](casos-referencia-propostos.md).

## Limitações conhecidas

- Amplificadores de vários estágios e reguladores com limitação foldback não foram implementados.
- Darlington: os resistores internos entre base e emissor (só no desenho do datasheet, sem
  tolerância) não entram no modelo; eles pesam em corrente baixa.
- JFET: VP sai de IDSS e yfs (Shockley); com a dispersão de IDSS do datasheet (fator de 2 a 5) o
  ponto Q real varia bastante, e o projeto avisa.
- Classe D: sem tempo morto, sem diodo de corpo, sem capacitâncias nem driver de porta; perda de
  comutação só estimada; RDS(on) a 25 °C (cresce com Tj). O modulador e o driver (com tempo morto
  e bootstrap) não são projetados, só listados na lista de materiais.
- IS dos transistores vem da premissa VBE = 0,7 V (o catálogo não traz IS); o ponto Q real de uma
  peça pode diferir alguns por cento.
- O espelho de corrente do DM-DIFF não tem efeito Early (o catálogo não traz VA): a saída do
  espelho é ideal e o CMRR calculado é otimista.
- MOSFET pelo modelo quadrático: bom para o raciocínio, impreciso para peças de potência.
- O multiplicador usa descarga linear para ΔV e δV (a simulação mostra o valor exato).
- Dados dos reguladores e dos demais componentes ainda dependem da sua revisão
  ([catalogo-reguladores.md](catalogo-reguladores.md)).
