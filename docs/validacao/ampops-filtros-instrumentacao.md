# Validação: ampops, filtros e instrumentação (Fase 5)

Data: 2026-11-14. Status: Fase 5 aprovada em 2026-11-15; dados do catálogo e casos P20–P32 aguardam a sua conferência.

Cinco módulos novos na aba **Projeto** e uma bancada nova na aba **Bancada**, no mesmo caminho das
fases anteriores: especificação → cálculo com memória → escolha de peças reais → margens →
conferência com o ngspice → esquemático (folha de valores), lista de materiais, relatório e roteiro
de prática.

| Módulo | Variantes | Grandezas principais |
|---|---|---|
| `DM-OPA` | inversor, não inversor, seguidor, somador, subtrator, integrador (com Rf), diferenciador (com R série), transimpedância, transcondutância, amplificador de instrumentação (3 ampops) | Av ideal e com A0 finito, erro de ganho, Vo com entrada nula (VOS, IB, IOS), Rp de compensação, fH, SR exigido e frequência de potência máxima |
| `DM-FIL` | Butterworth, Chebyshev, Bessel, elíptico; passa-baixas, passa-altas, passa-faixa, rejeita-faixa; Sallen-Key, MFB, variáveis de estado (KHN) e escada LC passiva | ordem mínima, polos e Q por seção, R e C comerciais, ganho na borda e na rejeição, corte −3 dB real × ideal |
| `DM-OPNL` | comparador (ampop ou LM311 com pull-up), Schmitt inversor e não inversor, retificador de precisão de meia onda e de onda completa, amplificador logarítmico, limitador com Zener | limiares e histerese, níveis de saída, atraso por SR, valor médio e pico, Vo = −VT ln(Iin/IS), nível de limitação |
| `DM-OSC` | ponte de Wien, deslocamento de fase, astável com ampop, 555 astável e monoestável, multivibrador com TBJ | f0 (ideal e com o ampop do catálogo), ganho de malha, amplitude (diodos limitadores), tH, tL, ciclo de trabalho, largura do pulso |
| `DM-INST` | voltímetro, amperímetro com shunt, medidor de potência, transmissor e receptor 4–20 mA, ponte de Wheatstone com amplificador de instrumentação, condicionamento de sensor (offset e ganho para o ADC) | resistores, ganho, saída no fundo de escala e no zero, erro de VOS, potência no shunt |
| `BD-AMPOP` | bancada do ampop: modelo manual ou peça do catálogo | VOS, IB, IOS, A0, CMRR, PSRR, GBW, SR, excursão (`BV-AMPOP-*`) |

## Como os cálculos são feitos

A regra 4 (cálculo e simulação concordam) é cumprida com **o mesmo circuito** no cálculo e no
simulador.

- **Ampop:** macromodelo de um polo: fonte de corrente gm·vd no nó interno com R e C (1 nF), A0 e
  GBW do datasheet (ou BW = 0,35/tr), VOS em série na entrada +, IB e IOS como fontes de corrente,
  Rin, CMRR e PSRR como fontes controladas na entrada. No transitório entram o limite de SR
  (corrente no capacitor limitada a SR·C) e o grampo da excursão de saída.
- **Circuitos lineares (DM-OPA, DM-FIL, DM-INST):** análise nodal modificada exata (a mesma conta do
  `.op` e do `.ac` do SPICE) sobre o circuito com o macromodelo. Os polos saem dos autovalores
  generalizados do sistema (G, C).
- **Filtros:** protótipos normalizados (Williams & Taylor, cap. 2), transformação de frequência,
  agrupamento em seções de 2ª ordem com ganho unitário em CC (por isso Chebyshev e elíptico de
  ordem par têm pico de 1/(ondulação) na banda), dimensionamento por seção (Mancini, *Op Amps for
  Everyone*, cap. 16) e escada LC pelos elementos g (Matthaei, Young & Jones, cap. 4). O resumo
  traz a resposta exata com os valores arredondados e a resposta ideal, lado a lado.
- **Osciladores:** a frequência é a do par de polos dominante em malha fechada levado ao eixo jω
  (o elemento limitado é escalado até isso acontecer), com o ampop real; a amplitude sai da função
  descritiva do limitador por diodos, N(u) = (2/π)(asen u + u√(1 − u²)) (Slotine & Li, cap. 5).
  Os tempos dos astáveis vêm de cargas RC exponenciais entre os limiares; no 555, os limiares do
  datasheet escalados para a VCC.
- **Multivibrador com TBJ:** a fórmula de livro (VBE de projeto) vai no resumo e no golden. A
  conferência com o ngspice usa um segundo valor, com o limiar de regeneração do modelo de
  Ebers-Moll (gm·RC = 1, VON = VT ln(VT/(RC·IS)) ≈ 0,54 V), porque a transição começa bem antes de
  VBE = 0,65 V. As duas contas estão na memória de cálculo.
- **Não lineares (DM-OPNL):** Schmitt com saída em saturação e ensaio por triângulo lento (atraso por
  SR desprezível frente ao período), retificadores com o ampop fechando a malha pelos diodos (a
  queda VF some da saída), logaritmico com o mesmo modelo de Ebers-Moll do TBJ no ngspice, limitador
  com Zener linear por partes.
- **Integração no tempo:** Gear nos circuitos com ampop (o trapézio travava na saturação);
  trapézio no multivibrador com TBJ (o Gear não passava da borda regenerativa).

## Conferência com o ngspice (AS-*)

`tests/analytic_vs_sim/test_as_fase5.py`: 70 casos, 175 grandezas, nenhuma acima da tolerância.

| Módulo | Casos | Grandezas | Maior erro | Onde | Tolerância |
|---|---|---|---|---|---|
| DM-OPA | 10 | 30 | 0,000 % | todas as configurações | 1 % (0,5 % no ganho) |
| DM-FIL | 38 | 102 | 0,205 % | corte −3 dB, elíptico passa-altas (o .ac lê o corte numa grade) | 0,5 % |
| DM-OPNL | 9 | 19 | 0,162 % | limiar do Schmitt inversor (atraso por SR) | 1 % |
| DM-OSC | 6 | 10 | 2,19 % | amplitude do deslocamento de fase (harmônicos na rede RC) | 5 % |
| DM-INST | 7 | 14 | 0,002 % | amperímetro, fundo de escala | 0,5 % |

Osciladores, um a um: Wien 0,54 % na frequência (tol. 2 %) e 0,06 % na amplitude (tol. 5 %);
deslocamento de fase 0,46 % e 2,19 %; astável com ampop 0,07 % e 0,03 % no ciclo de trabalho; 555
astável 0,14 % e 0,04 %; 555 monoestável 0,02 %; multivibrador com TBJ 1,24 % (tol. 3 %).

Bancada `BV-AMPOP-*` (`tests/unit/devices/test_opamp_bench.py`): os ensaios recuperam os valores do
macromodelo (bipolar e JFET genéricos e as três peças do catálogo) com erro ≤ 0,1 %. O offset é
corrigido pelo A0 medido e o IOS pelo termo 2·VOS/Rin.

## Casos de referência propostos (GT-P20..P32)

`tests/golden/test_gt_fase5.py`, tabela em
[casos-referencia-propostos.md](casos-referencia-propostos.md). Como P8–P19, são exercícios no estilo
dos livros resolvidos em forma fechada, não copiados de exemplos numerados: aguardam a sua conferência
(D6). Cobrem GT-OPA-01..03, GT-FIL-01..03, GT-OSC-01..03, GT-OSC-MV-01 e GT-OPNL-01..03 do escopo.

## Demais testes

- **Unitários** (`tests/unit/design/test_phase5_core.py`): nodal (CC, CA, polos de RC e RLC,
  fontes controladas), macromodelo (polo, ganho finito, VOS, CMRR, banda em malha fechada),
  conversão de dB, protótipos de filtro, ordem mínima, seções e elementos g.
- **Propriedades** (`tests/property/test_phase5_properties.py`): PT-OPA-GBW (fH = fb(1 + A0β)
  exato em 60 combinações) e PT-FIL-E24 (com resistores E24 e capacitores E12 o corte fica a menos
  de 5 % do projeto sem arredondamento).
- **Saídas** (`tests/unit/design/test_phase5_outputs.py`): esquemático, lista de materiais e netlist
  de 34 variantes, mais a escada LC sem semicondutores.
- **API**: lista dos módulos, projeto, esquemático, BOM e relatório dos cinco módulos; simulação de
  filtro com Bode; bancada do ampop com modelo padrão, com peça do catálogo e recusa de categoria
  errada.
- **Interface**: campos por configuração em `specForm.ts` (vitest).

## Como executar

```bash
cd backend
pytest tests/analytic_vs_sim/test_as_fase5.py   # AS da Fase 5 (ngspice, ~10 min)
pytest tests/golden/test_gt_fase5.py tests/unit/design/test_phase5_core.py
bash ../scripts/check.sh                          # suíte completa, lint e tipos
```

Na interface: aba **Projeto**, módulos "Ampop: circuitos lineares", "Filtros ativos e passivos",
"Ampops não lineares", "Osciladores, multivibradores e 555" e "Instrumentação e condicionamento"; aba **Bancada**, guia "Ampop".

## Limitações conhecidas

- Elíptico passa-faixa e rejeita-faixa não implementados (o elíptico cobre passa-baixas e
  passa-altas).
- Escada LC só Butterworth e Chebyshev, passa-baixas e passa-altas; Chebyshev é levado a ordem
  ímpar (terminações iguais).
- Transmissor 4–20 mA a dois fios não modelado (só o de três fios, com carga flutuante).
- Esquemáticos de DM-FIL, DM-OPNL, DM-OSC e DM-INST são folhas de valores (peças e valores), não
  desenhos completos.
- PSRR por trilho, com variação simétrica; CMRR e PSRR constantes com a frequência.
- Macromodelo de um polo: sem segundo polo, margem de fase, ruído nem corrente de curto-circuito.
- Multivibrador com TBJ: a fórmula de livro difere da simulação em cerca de 5 % (o limiar de
  regeneração explica a diferença; a conferência usa esse segundo valor).
- O deslocamento de fase usa diodos sobre parte de Rf para limitar a amplitude (sem eles a saída
  satura e a frequência erra em 6,5 %).

## Próximo passo

Fase 6: eletrônica de potência chaveada (`DM-CC`, `DM-CCI`, `SV-MAG`, malha de controle, `DM-INV`,
`DM-CACA`, `DM-CMD`, `BD-IGBT`).
