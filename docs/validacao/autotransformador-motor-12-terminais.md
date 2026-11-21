# Autotransformador e motor de indução de 12 terminais (2026-11-21)

Dois símbolos novos na biblioteca do esquemático, com modelo no ngspice e desenho na aba
Protoboard.

## Autotransformador (grupo Transformadores)

- Terminais: **H** (enrolamento completo), **X** (derivação) e **N** (comum à entrada e à saída).
  Abaixa alimentando em H e tirando em X; eleva alimentando em X e tirando em H.
- Dados de placa: VH (220 V), VX (127 V), potência passante (1 kVA), frequência, corrente de
  magnetização (3 % de In) e perdas no cobre (1 % de Sn). Os dois percentuais são didáticos;
  ajuste com os ensaios a vazio e de curto-circuito.
- Modelo: enrolamento série (H a X) e comum (X a N) acoplados (k = 0,9999). Com acoplamento
  forte, as indutâncias seguem o quadrado da fração de espiras:
  L_série = L_HN·((VH − VX)/VH)², L_comum = L_HN·(VX/VH)², com L_HN = VH/(2πf·Im) e
  Im = im·S/VH. O enrolamento série leva IH = S/VH e o comum IX − IH; as perdas no cobre são
  divididas igualmente entre os dois (Chapman, *Electric Machinery Fundamentals*, 5ª ed., cap. 2,
  seção do autotransformador; capítulo a conferir no livro).
- Memória de cálculo: relação VH/VX, indutâncias e resistências aparecem nos passos do relatório.

| Teste | Esperado | Simulado | Tolerância |
|---|---|---|---|
| 220 V → 127 V, carga nominal (16,1 Ω) | 127 V | 125,7 V | 2 % |
| Corrente de entrada na mesma carga | S/VH × V/127 = 4,46 A | 4,50 A | 3 % |
| 127 V em X → H com 10 kΩ | 220 V | 219,9 V | 1 % |

Testes: `tests/unit/schematic/test_transformers.py` (`test_size_autotransformer*`,
`test_autotransformer_*`).

## Motor de indução trifásico de 12 terminais (grupo Atuadores)

- Duas meias-bobinas por fase: 1-4 e 7-10 (fase 1), 2-5 e 8-11 (fase 2), 3-6 e 9-12 (fase 3).
  As ligações são feitas por fora, com fios ou rótulos, como na caixa de ligação do motor real
  (numeração e esquemas como no guia de especificação de motores da WEG):

| Ligação | Tensão de linha | L1 | L2 | L3 | Pontes |
|---|---|---|---|---|---|
| Triângulo paralelo | 220 V | 1-6-7-12 | 2-4-8-10 | 3-5-9-11 | — |
| Estrela paralelo | 380 V | 1-7 | 2-8 | 3-9 | 4-5-6-10-11-12 |
| Triângulo série | 440 V | 1-12 | 2-10 | 3-11 | 4-7, 5-8, 6-9 |
| Estrela série | 760 V | 1 | 2 | 3 | 4-7, 5-8, 6-9, 10-11-12 |

- Modelo: o mesmo motor dinâmico em αβ do motor de 3 terminais (Krause, cap. 4), com os
  parâmetros por fase da ligação estrela paralelo. A tensão de cada fase é a média das duas
  meias-bobinas e a corrente da fase se divide entre elas. Cada meia-bobina trabalha com 220 V
  em qualquer das quatro ligações.
- Se as duas meias-bobinas de uma fase recebem tensões diferentes (uma invertida, por exemplo),
  circula corrente entre elas, limitada só por 4·R1 e 4·X1 (cada meia-bobina tem o dobro da
  resistência e da dispersão do par em paralelo). Essa corrente não produz torque.
- Saídas: `<ref>_rpm`, `<ref>_te`, `<ref>_w` e `<ref>_i`. No motor de 12 terminais, `<ref>_i` é a
  corrente eficaz **em cada meia-bobina**, igual nas quatro ligações. A corrente de linha se lê na
  fonte.

Teste com 20 N·m de carga e os parâmetros padrão (motor didático de 4 polos), comparado ao
circuito equivalente do motor de 380 V em estrela (AS-DRV-07):

| Ligação | Velocidade (1728,3 rpm) | Torque (20,905 N·m) | Meia-bobina (3,818 A) | Linha esperada | Linha simulada |
|---|---|---|---|---|---|
| Δ paralelo 220 V | 1729,6 | 20,906 | 3,812 | 13,19 A | 13,21 A |
| Y paralelo 380 V | 1729,1 | 20,905 | 3,819 | 7,64 A | 7,64 A |
| Δ série 440 V | 1729,6 | 20,906 | 3,812 | 6,60 A | 6,60 A |
| Y série 760 V | 1729,1 | 20,905 | 3,819 | 3,82 A | 3,82 A |

Tolerâncias: velocidade 0,2 %, torque e corrente na meia-bobina 1 %, corrente de linha 1,5 %.
AS-DRV-08: triângulo paralelo em 220 V com a meia-bobina 7-10 invertida. A corrente circulante
é 2·220/(4·|1,5 + j2,5|) = 37,7 A, dentro de 3 %.

Testes: `tests/analytic_vs_sim/test_as_drives.py` (`test_as_drv_07_*`, `test_as_drv_08_*`).

## Protoboard

- Autotransformador: núcleo E-I com uma bobina e régua de bornes H, X e N.
- Motor de 12 terminais: a mesma carcaça do motor trifásico, com caixa de ligação larga de 12
  bornes numerados e placa "220/380/440/760 V".

Capturas: `/mnt/project-files/capturas/protoboard-desenhos/motor-12-terminais-e-autotransformador.png`
e `esquematico-motor-12-e-autotransformador.png`.

## Limitações conhecidas

- Autotransformador sem dispersão significativa, perdas no ferro e saturação. É monofásico e de
  derivação fixa, sem variac de cursor.
- Motor de 12 terminais sem a componente de sequência zero (circulação de 3ª harmônica no
  triângulo) e sem diferença de dispersão entre as meias-bobinas. A corrente circulante usa só a
  dispersão do estator. Parâmetros padrão didáticos, não de um motor real.
- O número da seção do Chapman ainda precisa ser conferido no livro.

## Transformadores com bobinas acessíveis e placa de ligação (2026-11-21)

Pedido: deixar visível na protoboard a placa de ligação das bobinas, para fazer os fechamentos.

- **Transformador monofásico de 4 bobinas** (`transformer_1ph_4`): primário em P1-P2 e P3-P4,
  secundário em S1-S2 e S3-S4, todos no mesmo núcleo (pontos em P1, P3, S1, S3). Padrão
  115 V + 115 V / 12 V + 12 V, 50 VA. Série (P2-P3) dá 230 V; paralelo (P1-P3, P2-P4) dá 115 V;
  no secundário, série dá 24 V ou derivação central.
  Modelo: cada bobina tem a indutância do enrolamento inteiro em Vp e o dobro da sua
  resistência. Assim, as perdas no cobre na carga nominal são as mesmas em série e em paralelo.
- **Transformador trifásico de bobinas acessíveis** (`transformer_3ph_open`): as seis bobinas
  com as duas pontas na placa, com a marcação da IEC 60076 (1U1-1U2, 1V1-1V2, 1W1-1W2 na alta;
  2U1 … 2W2 na baixa). Estrela ou triângulo se fecham por fora.
- Na protoboard, os dois aparecem com a placa de ligação (régua de bornes) em cima e cada bobina
  ligada ao seu par de bornes. O autotransformador mostra a régua H, X e N. O transformador
  trifásico de ligação fixa (Dyn, Yd…) continua disponível.

| Teste | Esperado | Tolerância |
|---|---|---|
| 4 bobinas, série/série, 230 V, carga nominal | 24 V | 3 % |
| 4 bobinas, paralelo/paralelo, 115 V, carga nominal | 12 V | 3 % |
| Trifásico aberto, Δ no primário (380 V), Y no secundário (127 V por bobina) | 220 V de linha | 3 % |

Testes: `test_four_coil_series_and_parallel` e `test_open_three_phase_closed_delta_wye` em
`tests/unit/schematic/test_transformers.py`.

Limitação: as pontes (fechamentos) são feitas com fios no esquemático e, na protoboard, com cabos
até a placa. Ainda não há a "barra de ligação" desenhada sobre a própria régua do transformador.
