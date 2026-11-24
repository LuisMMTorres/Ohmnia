# Esquemáticos da Análise de Projetos

Entrega de 24/11/2026. Antes, nove módulos mostravam na aba **Esquemático** só uma caixa
"circuito (ligação completa na netlist)" e a lista de valores. Agora todos desenham o circuito
montado, com os mesmos nós e nomes da netlist simulada e os valores do projeto.

## O que mudou

| Módulo | Variantes desenhadas |
|---|---|
| DM-OPNL (ampop não linear) | comparador (ampop e LM311 com resistor de pull-up), Schmitt inversor e não inversor, retificador de precisão de meia onda e de onda completa, amplificador logarítmico (transdiodo), limitador com zener |
| DM-OSC (osciladores) | ponte de Wien, deslocamento de fase, astável com ampop, 555 astável e monoestável (pinagem 1 a 8), multivibrador astável com TBJ |
| DM-INST (instrumentação) | voltímetro, amperímetro com shunt, medidor de potência, transmissor e receptor 4-20 mA, ponte de Wheatstone com amplificador de instrumentação de 3 ampops, condicionamento de sinal |
| DM-FIL (filtros) | Sallen-Key, MFB, variáveis de estado (KHN), seções de 1ª ordem (uma linha por seção, com f0 e Q) e escada LC passiva |
| DM-CC (CC-CC) | buck, boost, buck-boost, Ćuk, SEPIC e Zeta, com o compensador tipo II ou III do amplificador de erro |
| DM-CCI (CC-CC isolado) | flyback, forward com enrolamento de reset, push-pull, meia ponte e ponte completa, com pontos de polaridade e nomes dos enrolamentos |
| DM-INV (inversores) | monofásico em ponte H e trifásico com carga em estrela, com ou sem filtro LC amortecido |
| DM-CACA (CA-CA) | TRIAC com ângulo imposto ou com rede RC + DIAC, carga R ou RL |
| DM-CMD (comando e proteção) | entrada com fusível, varistor, chave de partida, ponte, NTC e capacitor do barramento; driver de meia ponte com bootstrap; ensaio do snubber RCD |

Os desenhos seguem as topologias de Hart (*Power Electronics*, 1ª ed., cap. 6, 7, 8 e 10),
Mohan, Undeland e Robbins (*Power Electronics*, 3ª ed., cap. 7, 8, 10 e 23), Sedra e Smith
(*Microelectronic Circuits*) para os circuitos com ampop e a ligação típica do datasheet do
IR2110 e do NE555.

## Correção encontrada durante o trabalho: forward

Ao conferir o desenho do forward com a netlist, a polaridade do enrolamento de reset N3 estava
invertida (`LR r1 0`, ponto no lado do diodo). O diodo D3 nunca conduzia e a tensão na chave
chegava a **142 kV** na simulação. Corrigido para `LR 0 r1` (ponto no lado da terra, como diz o
comentário do código e os livros): a tensão máxima na chave passou a **97 V**, o esperado
2·Vin + queda do diodo para Vin = 48 V e N3 = N1. Os testes GT/AS do DM-CCI continuam passando.

## Como conferir

1. Abrir a **Análise de Projetos**, escolher um dos módulos acima e a aba **Esquemático**.
2. Mudar a configuração/topologia no formulário: o desenho muda junto.
3. Clicar num componente do desenho (por exemplo R1 ou L1) para colocar uma ponteira nele.

As capturas de todas as variantes estão em
[capturas-esquematicos/](capturas-esquematicos/).

## Testes

- Novo `tests/unit/design/test_schematic_drawings.py` (44 variantes): nenhum desenho pode mostrar
  a caixa antiga, e todo resistor, capacitor e indutor da netlist tem de aparecer com o mesmo
  nome no desenho. Ficam de fora só os auxiliares de simulação (macromodelo do ampop,
  referências de 1 MΩ, capacitores de 100 pF dos nós do inversor, integrador de energia do
  snubber, trava do modelo do 555 e ligações de 1 mΩ).
- `tests/unit/design`, `tests/unit/api`, `tests/unit/schematic`: 444 aprovados.
- `tests/analytic_vs_sim/test_as_fase5.py`: 72 aprovados; testes do DM-CCI em
  `test_as_fase6.py` e `test_gt_fase6.py`: aprovados.
- `ruff`, `mypy --strict` e `lint-imports` sem erros.

## Limitações conhecidas

- Os desenhos são gerados por gabarito para cada topologia; não são editáveis (para editar, abrir
  o circuito no Simulador).
- Na parte de potência, as fontes de gate aparecem como um terminal com o nome do sinal (g, g1,
  gua...), e não como fonte de pulso.
- Primário e secundário dos conversores isolados têm terras separados no desenho; na simulação
  são o mesmo nó 0 (nota no próprio desenho).
- O compensador do DM-CC é desenhado, mas a simulação usa razão cíclica fixa (malha aberta);
  isso também está escrito no desenho.
- No DM-CMD, o driver com bootstrap é desenhado pela ligação típica do datasheet; a simulação
  confere a partida (NTC) e o snubber.
- Nos inversores trifásicos, os valores aparecem só na fase a (as fases b e c são iguais).
