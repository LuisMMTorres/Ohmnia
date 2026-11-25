# Protoboard da Análise de Projetos — todas as peças ligadas

## O problema

Na aba **Análise de Projetos → Protoboard**, algumas peças apareciam sem nenhum fio nas suas
faixas (por exemplo, o 2N3904 do DM-CHAVE). A causa: a peça escolhida no catálogo não tinha a
pinagem transcrita do datasheet. Pela regra 1 (não supor pinagem), o montador a colocava "sem
ligações", e a conferência deixava essa peça de fora e ainda dizia "Montagem confere".

## O que mudou

1. **Pinagens transcritas dos datasheets** (status `extraido`, aguardando sua revisão):

   | Peça | Encapsulamento | Pinos | Fonte |
   |---|---|---|---|
   | 2N3904 | TO-92 | 1 E, 2 B, 3 C | onsemi 2N3904/D Rev. 3, p. 1 (marking diagram) |
   | BD135/137/139 | TO-225 (TO-126) | 1 E, 2 C, 3 B | onsemi BD135/D Rev. 18, p. 1 |
   | BD140 | TO-126 | 1 E, 2 C, 3 B | onsemi BD136/D Rev. 2, p. 1 |
   | TIP31/TIP32 (todas) | TO-220 | 1 B, 2 C, 3 E | onsemi TIP31A/D Rev. 17, p. 1 |
   | IRF540 | TO-220AB | 1 G, 2 D, 3 S | Vishay 91021, p. 1 (desenho) |
   | IRF840 | TO-220AB | 1 G, 2 D, 3 S | Vishay 91070, p. 1 (desenho) |
   | IRF640N | TO-220AB | 1 G, 2 D, 3 S | Infineon Rev. 2.1, p. 1 |
   | IRLZ44N | TO-220AB | 1 G, 2 D, 3 S | Infineon PD-94831, p. 8 (lead assignments) |
   | LM741 | PDIP-8 | 2 IN−, 3 IN+, 4 V−, 6 OUT, 7 V+ | TI SNOSC25D, p. 3 |
   | TL071 | PDIP-8 | 2 IN−, 3 IN+, 4 VCC−, 6 OUT, 7 VCC+ | TI SLOS080W, p. 3, Tabela 4-1 |
   | NE5532 | PDIP-8 | unidade A: 1, 2, 3; 4 VCC−; 8 VCC+ | TI SLOS075K, p. 2 |
   | MBR20100CT | TO-220 | 1 A1, 2 K comum, 3 A2 | onsemi/Fairchild, p. 2 |
   | MUR460 | axial | 1 K (faixa), 2 A | onsemi MUR420/D Rev. 17, p. 9 |
   | MCR265 (todas) | TO-220AB | 1 K, 2 A, 3 G | onsemi MCR265/D Rev. 3, p. 2 |
   | BT151-500R | TO-220AB | 1 K, 2 A, 3 G | WeEn, p. 2, Tabela 2 |
   | 1N5221B–1N5252B | DO-35 | 1 K (faixa), 2 A | **a verificar**: o datasheet não diz qual ponta é o catodo |

   Na sua base de dados, a pinagem é acrescentada sem apagar as revisões que você já fez nos
   valores (antes, só aumentando a revisão do catálogo, o que zerava as revisões).

2. **Duas protoboards:** quando o circuito não cabe na protoboard de baixo (filtro de variáveis
   de estado, com 8 ampops), as peças que sobram vão para a de cima, ligadas à de baixo por fios
   e barramentos.

3. **Fios retos:** cada fio vai ao longo de uma coluna de furos (a mesma letra em duas faixas) ou
   atravessa o canal na mesma linha. Como os 5 furos de cada faixa estão em curto, o montador
   escolhe o furo que deixa o fio reto; quando as linhas não coincidem, usa uma faixa livre como
   ponte (dois ou três fios retos). Ele também evita deitar um fio sobre outro.

4. **Conferência honesta:** se alguma peça não tiver pinagem, o resultado passa a ser "não
   confere", com o aviso "X não tem pinagem transcrita do datasheet: as pernas ficaram sem
   ligação".

5. **Velocidade:** os testes de folga ficaram mais rápidos; a montagem automática dos 112 casos
   testados levou 42 s, contra 166 s antes.

## Como conferir

1. Abra **Análise de Projetos**, escolha um módulo (por exemplo DM-CHAVE) e a aba **Protoboard**.
2. Confira que cada perna está numa faixa com fio ou peça do mesmo nó.
3. Teste automático: `pytest tests/unit/api/test_design_breadboard.py`. Ele monta cada módulo
   com cada opção (configuração, topologia, aproximação...) e verifica, de forma independente da
   conferência, que cada perna conhecida está no condutor do seu nó, que nenhuma peça com
   pinagem comprovada ficou fora e que nenhum fio está na diagonal. Pinagens pendentes devem
   aparecer no relatório e impedir a mensagem de montagem conferida.

## Capturas

- [1-chave-2n3904.png](capturas-protoboard-ligacoes/1-chave-2n3904.png): o caso da foto, agora ligado.
- [2-ampop-inversor-lm741.png](capturas-protoboard-ligacoes/2-ampop-inversor-lm741.png)
- [3-filtro-variaveis-estado-duas-placas.png](capturas-protoboard-ligacoes/3-filtro-variaveis-estado-duas-placas.png)
- [4-inversor-meia-ponte.png](capturas-protoboard-ligacoes/4-inversor-meia-ponte.png)

## Limitações conhecidas

- Peças ainda sem pinagem no catálogo (por exemplo TYN625, 2N3906, BC337, LM393, MOC3021) ficam
  soltas e a conferência avisa. O site da ST não respondeu para baixar o TYN625.
- Nos filtros grandes (elíptico e variáveis de estado) ainda há fios retos deitados um sobre o
  outro em alguns trechos: a metade de cima da protoboard tem só 4 colunas livres para tantos nós.
- O 1N5221B ficou com status "a verificar" (polaridade não indicada no datasheet).
  A revisão bloqueia suas ligações automáticas e a certificação da montagem, mesmo se a
  peça não tiver sido colocada. O roteiro pede confirmação da pinagem sem indicar polaridade
  presumida. As outras peças continuam sendo conferidas.

## Revisão antes do merge

Correções e reprodução: [revisao-pr33.md](revisao-pr33.md).
