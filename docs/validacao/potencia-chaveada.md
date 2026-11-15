# Validação: eletrônica de potência chaveada (Fase 6)

Data: 2026-11-15. Status: aguardando a sua aprovação; dados do catálogo e casos P33–P49 aguardam a sua conferência.

Cinco módulos novos na aba **Projeto**, um serviço de magnéticos (ver [magneticos.md](magneticos.md))
e uma bancada nova na aba **Bancada**, no mesmo caminho das fases anteriores: especificação →
cálculo com memória → escolha de peças reais → margens e térmico → conferência com o ngspice →
esquemático (folha de valores), lista de materiais, relatório e roteiro de prática.

| Módulo | Variantes | Grandezas principais |
|---|---|---|
| `DM-CC` | buck, boost, buck-boost, Ćuk, SEPIC, Zeta; MCC e MCD (MCD em buck, boost e buck-boost); chave MOSFET ou IGBT; compensador tipo III, tipo II ou sem malha | D (com R_on e V_F), L e C, ondulações, L crítico, esforços, perdas de condução e comutação, rendimento, Gvd(s), f0 e zero no semiplano direito, compensador pelo fator K, fc, margens de fase e de ganho |
| `DM-CCI` | flyback, forward (enrolamento de desmagnetização), push-pull, meia ponte, ponte completa | relação de espiras, D, Lm (flyback), L de saída, esforços, transformador e indutor projetados em núcleos do catálogo |
| `DM-INV` | monofásico e trifásico; onda quadrada, quase quadrada (α), SPWM bipolar e unipolar, SPWM e SVPWM trifásicos; filtro LC amortecido opcional; tempo morto | V1, V_rms, I_rms, THD da tensão e da corrente (total e até a 50ª), queda de V1 pelo tempo morto, Lf, Cf, Rd, Cd, perdas por evento de comutação, rendimento |
| `DM-CACA` | controle de fase com carga R ou RL, controle por ciclos inteiros (R ou RL), disparo por ângulo imposto ou rede RC + DIAC | α, β, θ da carga, V_o,rms, I_o,rms, potência, FP, THD da corrente, esforços e perda no TRIAC |
| `DM-CMD` | meia ponte com driver bootstrap; snubber RCD de desligamento opcional; proteção de entrada | R_g, corrente de pico e potência de comando, capacitor de bootstrap (AN-978), tempo máximo da chave alta, C_s e R_s do snubber, energia de desligamento com e sem snubber, I²t da ponte × fusível, MCOV do varistor, R a frio e energia do NTC |
| `BD-IGBT` | bancada do IGBT: modelo manual ou peça do catálogo | curvas I_C × V_CE, ajuste de V_T e r_on ao datasheet, perdas de condução e comutação de um chopper |

## Como os cálculos são feitos

A regra 4 (cálculo e simulação concordam) é cumprida com **o mesmo modelo de dispositivo** no
cálculo e no simulador: chave com R_on (MOSFET) ou V_CE(sat) constante (IGBT), diodo com V_F
constante, TRIAC como dois SCR com V_TM constante, transformador com acoplamento K = 1.

- **CC-CC (Erickson & Maksimović, cap. 2, 3, 5, 7 e 8; Hart, cap. 6):** modelo médio por espaço de
  estados com R_on e V_D. A razão cíclica sai do modelo médio em regime (busca no ramo crescente
  e bissecção). L e C vêm das ondulações pedidas, arredondados para cima (E12 nos capacitores). No
  MCD, L = fração do L crítico e D da relação M(D, K). As perdas de comutação usam E_on/E_off do
  datasheet escaladas (IGBT) ou tr, tf e Coss (MOSFET).
- **Malha de controle (Venable, fator K):** Gvd(s) = C(sI − A)⁻¹[(A1 − A2)X + (B1 − B2)U]; avanço de
  fase pedido com a fase da planta desembrulhada desde CC; K = tan(boost/2 + 45°) no tipo II e
  tan²(boost/4 + 45°) no tipo III; resistores E24 e capacitores E12; margens lidas no último
  cruzamento de |T| = 1. Se a margem cair mais de 15° abaixo do pedido ou houver mais de um
  cruzamento, fc desce em passos de 10 %.
- **CC-CC isolados (Hart, cap. 7; Mohan, cap. 10):** relação de espiras escolhida em D nominal e D
  refeito com as quedas; o flyback é um indutor acoplado (Lm e entreferro), os demais transformadores
  e o indutor de saída são projetados pelo SV-MAG.
- **Inversores (Hart, cap. 8; Mohan, cap. 8; Rashid, cap. 6):** a forma de onda é sintetizada em
  2¹⁷ amostras por período (amostragem natural, SVPWM por injeção min-max), com janela de tempo morto
  centrada em cada borda, quedas V_CE(sat) + R_on·|i| no transistor e V_F no diodo (MOSFET
  síncrono: o canal conduz a corrente reversa). A corrente da carga RL sai harmônico por harmônico
  e a polaridade da corrente realimenta as quedas (iteração com sub-relaxação). O filtro LC tem Lf
  pela ondulação de corrente na portadora, Cf pela frequência de corte e um ramo Rd–Cd de
  amortecimento (Cd = 4Cf, Rd ótimo de Erickson, cap. 10). As perdas somam cada evento de
  comutação com a corrente instantânea.
- **Gradadores (Hart, cap. 5):** carga R pela fórmula fechada; carga RL com β da equação de
  extinção, incluindo a queda V_TM; ciclos inteiros com a corrente RL exata desde o zero (fecha em
  θ = 0, abre no primeiro zero após n ciclos). Rede RC + DIAC: v_C = V_m k sen(ωt − φ) e
  α = φ + asen(V_BO/(V_m k)), com V_BO informado (não há DIAC no catálogo).
- **Comando e proteção:** R_g ≥ V_CC/I_O+ (E24 acima); P_gate = Q_g V_CC f_s; bootstrap pela fórmula
  da AN-978 com Q_g da chave, I_QBS e V_BSUV− do driver, V_F do diodo de bootstrap e V_LS = V_CE(sat)
  (capacitor adotado ≈ 10× o mínimo); snubber RCD de desligamento (Hart, cap. 10):
  C_s = I_o t_f/(2V_s), R_s ≤ D_min T_s/(5C_s), E = I_o² t_f²/(24C_s) + V_F I_o t_f/2; fusível com I²t
  menor que o da ponte (datasheet, ou I_FSM²/(4f) para meio ciclo); varistor com MCOV ≥ V_ca(1 + tol);
  NTC com R a frio pelo pico de partida na crista e energia ≈ ½CV².

## Conferência com o ngspice (AS-*)

`tests/analytic_vs_sim/test_as_fase6.py`: 33 casos, 114 grandezas, nenhuma acima da tolerância.

| Módulo | Casos | Grandezas | Maior erro | Onde | Tolerância |
|---|---|---|---|---|---|
| DM-CC | 9 | 39 | 1,86 % | ondulação de corrente do boost em MCD | 1–5 % (15 % na ondulação de Vo) |
| DM-CCI | 5 | 19 | 0,97 % | ondulação de Vo da meia ponte | 1,5–5 % (15 % na ondulação de Vo) |
| DM-INV | 11 | 36 | 3,68 % | THD da corrente até a 50ª, monofásico filtrado com mf = 201 | 2 % (10 % na THD) |
| DM-CACA | 6 | 16 | 0,03 % | fator de potência, carga RL | 1 % (2 % no FP) |
| DM-CMD | 2 | 4 | 0,04 % | energia de desligamento com snubber | 1 % (2 % na energia) |

As tolerâncias estão em cada `SimCheck` do módulo, com a justificativa. As ondulações de Vo têm
15 % porque a ESR do capacitor não entra em nenhum dos dois lados e o ngspice lê a ondulação num
período depois de 1–2 ms de partida. Na THD do inversor a diferença vem do tempo morto perto do
cruzamento da corrente por zero, onde a polaridade da corrente decide a tensão da perna.

Duas notas de simulação:

- **Inversor:** cada perna tem 100 pF de capacitância de saída no netlist. Sem ela o ngspice
  travava no tempo morto (passo mínimo) com o filtro LC em mf alto; a carga desses 100 pF leva
  poucos nanossegundos e nada muda na fundamental.
- **Gradador:** as portas dos SCR do modelo são referidas à terra (o subcircuito compara v(g) com a
  terra). Com a porta referida ao catodo o segundo SCR não disparava.

## Casos de referência (GT-*), aguardando a sua conferência

`tests/golden/test_gt_fase6.py`, casos P33–P49 (tabela em
[casos-referencia-propostos.md](casos-referencia-propostos.md)). Os conversores rodam a análise
com dispositivos ideais e conferem a fórmula fechada; os casos de proteção usam o catálogo revisado,
e os valores do datasheet entram na fórmula.

## Propriedades (PT-*)

`tests/property/test_phase6_properties.py` (Hypothesis):

- `PT-ENERGIA`: em regime, P_in = P_out + D·R_on·i_ch² + (1 − D)·V_D·i_d nos seis modelos médios.
- `PT-CC-D`: 0 < D < 1 e Vo médio igual ao pedido em especificações aleatórias.
- `PT-INV-MA`: na região linear a fundamental vale ma·Vdc (bipolar e unipolar).
- `PT-FFT-PARSEVAL`: valor quadrático médio da tensão de fase igual à soma das energias dos
  harmônicos (onda quadrada, SPWM e SVPWM trifásicos).

## Correção no catálogo

A liberação de componentes exigia o parâmetro `IGT`, mas os TRIACs têm `IGT@Q1` … `IGT@Q4`; por isso
nenhum TRIAC podia ser liberado. Agora um parâmetro obrigatório dado por condição é aceito quando
todas as entradas com valor estão revisadas.

## Limitações conhecidas

- **Magnéticos de 60 Hz:** o catálogo só tem ferrite. O indutor do filtro do inversor (dezenas de mH a
  60 Hz) não cabe em nenhum núcleo; o projeto avisa e segue com o valor de Lf.
- **Filtro do inversor com mf baixo:** com mf = 21 a portadora fica perto da fundamental e o Lf da
  ondulação derruba V1 (o resumo mostra a queda). Use mf alto com filtro.
- **Snubber:** foi feito o RCD de desligamento, que tem fórmula fechada e é conferido no ngspice. O
  `GT-CMD-SNUB-01` do escopo cita um RC; se quiser o RC dissipativo também, me diga.
- **`GT-CMD-02` (disparo por UJT):** não feito; não há UJT no catálogo. O disparo por DIAC
  (`GT-CMD-01`) está em `DM-CACA`.
- **DIAC, fusível, varistor e NTC:** não há essas categorias no catálogo; V_BO, I²t do fusível e
  energia do NTC são dados que você informa, e a lista de materiais deixa a escolha indicada. Na
  simulação do DIAC entra o α calculado (pulso de porta), não a rede RC.
- **Comando:** Q_ls da AN-978 é entrada (5 nC por padrão, confirme para o CI); o tempo de carga do
  gate é estimativa de primeira ordem; a dissipação do driver é o pior caso (toda a energia de gate
  no driver).
- **Ciclos inteiros:** a THD da corrente é calculada na janela de N ciclos, por isso inclui os
  sub-harmônicos (fica perto de 100 %).
- **BD-IGBT:** modelo linear por partes; o joelho V0 e o ganho K não vêm do datasheet, só V_T e r_on
  são ajustados. As energias de comutação são escaladas linearmente do ponto de ensaio.
- **Perdas de comutação** não são comparadas com o ngspice (o modelo de chave do simulador é ideal);
  a conferência cobre tensões, correntes, ondulações e THD.

## Como executar

```bash
cd backend
pytest tests/golden/test_gt_fase6.py tests/property/test_phase6_properties.py
pytest tests/analytic_vs_sim/test_as_fase6.py      # AS da Fase 6 (ngspice, ~1 min)
bash ../scripts/check.sh                          # suíte completa, lint e tipos
```
