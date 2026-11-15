# Validação: simulador livre (Fase 7)

Data: 2026-11-15. Status: aprovada em 2026-11-15.

A aba **Simulador** agora abre um editor de esquemático. O editor de netlist em texto das fases
anteriores continua disponível na subaba **Netlist (texto)**. O caminho é o mesmo para todos os
casos: esquemático → netlist SPICE → ngspice → pós-processamento (medidas, FFT, estatística, figuras).

## O que foi feito

| Item da especificação (4.2 e 4.3) | Onde | Situação |
|---|---|---|
| Editor de esquemático com biblioteca | `frontend/src/schematic/SchematicEditor.tsx`, `schematic/library.py` (35 símbolos) | ✅ |
| Peças reais do catálogo no esquemático | painel de propriedades → “Peça”; modelo em `schematic/parts.py` | ✅ diodo, Zener, BJT (inclui Darlington), MOSFET, JFET, amp-op, SCR, TRIAC, IGBT |
| Fontes CC, senoidal, pulso, PWL e trifásica | `vdc/vsin/vpulse/vpwl`, `idc/…`, `v3ph` | ✅ |
| Chaves controladas, transformador, cargas | `switch`, `igbt`, `scr`, `triac`, `transformer`, `rl_load` | ✅ |
| Fontes controladas, fonte comportamental, subcircuito | `vcvs/vccs/cccs/ccvs`, `bsource`, `subckt` | ✅ |
| Pontas de tensão, tensão diferencial, corrente e potência | ferramentas “Ponta”; `plan_probes` em `netlist.py` | ✅ |
| .OP, .TRAN, .AC, .DC (dupla), ruído | painel **Análises** | ✅ |
| .STEP paramétrico (componente ou `.param`) e de temperatura | painel **Varredura** | ✅ lista, linear, década, oitava |
| Monte Carlo e pior caso com tolerâncias de datasheet | painel **Varredura**; `schematic/runs.py` | ✅ ver “Faixas usadas” |
| Fourier/FFT, THD e tabela de harmônicos | resultados → **FFT / THD** | ✅ janela coerente nos últimos N períodos |
| Importar e exportar netlist SPICE (`.model`, `.subckt`) | barra de ferramentas; `schematic/importer.py` | ✅ |
| Osciloscópio: vários traços, dois eixos, cursores, zoom | resultados → **Osciloscópio** (`Scope.tsx`) | ✅ |
| Medidas: média, RMS, pico, pico a pico, frequência, razão cíclica, subida, descida, sobressinal | tabela abaixo do osciloscópio (janela = cursores ou zoom) | ✅ |
| Bode | resultados → **Bode** | ✅ |
| Expressões derivadas e gráfico XY | campo “expressão” e aba **XY** | ✅ `v(out)*i(r1)`, `integ(p(q1))`, `movavg(…)` etc. |
| CSV e figuras SVG/PNG/PDF (Matplotlib) | botões **CSV** e **Exportar figura** | ✅ vírgula decimal ou formato internacional |
| Salvar e abrir circuito | `.circ.json`; o último circuito também fica guardado no navegador | ✅ |

## Como executar

```bash
scripts/check.sh                    # lint, tipos, testes do backend e do front-end, build
scripts/e2e.sh                      # E2E no navegador (precisa de ngspice e do Playwright)
SHOTS=capturas/ scripts/e2e.sh      # idem, salvando as capturas de tela
```

No uso normal, suba a aplicação como antes e abra a aba **Simulador**. O menu **Exemplos…** traz seis
circuitos prontos: filtro RC, emissor comum, ponte retificadora com filtro, Monte Carlo do RC, STEP
de R num RLC série e ruído térmico com varredura de temperatura.

Atalhos do editor: **R** gira, **M** espelha, **Del** apaga, **W** fio, **Esc** cancela, **espaço**
troca o canto do fio, **Ctrl+Z / Ctrl+Y** desfazem e refazem. A roda do mouse dá zoom. Arrastar o
fundo move a vista. No osciloscópio, um clique põe o cursor A, Shift+clique põe o cursor B, arrastar
dá zoom e um duplo clique desfaz o zoom.

## Testes analítico × simulação (AS-SIM)

Todos passam pelo mesmo caminho do editor (modelo de esquemático, `SchematicPlan`, ngspice, pontas de
prova). Arquivo: `backend/tests/analytic_vs_sim/test_as_simulador.py`.

| Caso | Circuito | Grandeza | Analítico | Simulado | Tolerância |
|---|---|---|---|---|---|
| AS-SIM-01 | RC 1 kΩ, 100 nF | \|H(fc)\| | −3,0103 dB | −3,0104 dB | 0,01 dB |
| AS-SIM-01 | idem | ∠H(fc) | −45,000° | −45,000° | 0,1° |
| AS-SIM-02 | RLC série 20 Ω, 10 mH, 1 µF (ζ = 0,1), degrau | pico − 1 V | 0,72925 V | 0,72925 V | 0,01 V |
| AS-SIM-02 | idem | sobressinal pela medida do osciloscópio | 72,9 % | 71,7 % | 2 p.p. (ver limitações) |
| AS-SIM-03 | divisor 10 V, 1 kΩ + 4 kΩ | ponta de corrente i(R1) | 2 mA | 2 mA | 1e-6 |
| AS-SIM-03 | idem | ponta de potência p(R2) | 16 mW | 16 mW | 1e-6 |
| AS-SIM-03 | idem | ponta diferencial v(a,out) | 2 V | 2 V | 1e-6 |
| AS-SIM-04 | divisor 10 kΩ ±1 % | pior caso máx. / mín. | 5,0500 / 4,9500 V | idem | 1e-6 |
| AS-SIM-05 | idem, Monte Carlo uniforme, 40 execuções | todas dentro dos extremos | [4,95; 5,05] V | dentro | exato |
| AS-SIM-06 | dois resistores de 10 kΩ, ruído na saída | √(4kTR), R = 5 kΩ | 8,02 / 9,10 / 10,49 nV/√Hz a −40 / 27 / 125 °C | idem | 0,1 % |

Referências: Sedra & Smith, *Microelectronic Circuits*, 7ª ed., apêndice E (análise no domínio s) e
apêndice sobre ruído; Hayt, Kemmerly & Durbin, *Engineering Circuit Analysis*, 8ª ed., cap. 9 (circuito
RLC). Os números de equação não foram citados porque não os conferi no livro.

Conferência manual do pior caso do exemplo “Filtro RC: Monte Carlo” (R ±5 %, C ±10 %), que o E2E
também verifica: com R e C no mínimo, fc = 1/(2π·950 Ω·143,1 nF) = 1171 Hz e \|H(1 kHz)\| = −2,379 dB.
Com R e C no máximo, fc = 866,6 Hz e \|H(1 kHz)\| = −3,676 dB. A tela mostra −2,37946 e −3,67622 dB.

## Testes de propriedade (PT-SIM)

Arquivo: `backend/tests/property/test_simulator_properties.py` (Hypothesis).

- Monte Carlo nunca sai da faixa [mín.; máx.], nas duas distribuições, e repete com a mesma semente.
  A execução 0 é sempre o circuito nominal.
- `format_value` → `parse_value` volta ao mesmo número (rel. 1e-5) de 1e-15 a 1e15.
- Quatro rotações de 90° devolvem o pino ao lugar; espelhar duas vezes também; girar preserva a distância.
- Uma escada RLC aleatória importada e exportada de novo mantém cada elemento entre os mesmos nós.
- rms(k·x) = \|k\|·rms(x) no avaliador de expressões.

Também há testes de unidade para o esquemático: conectividade (junção em T, fios cruzados sem
contato, rótulos), netlist de cada símbolo, peças do catálogo (Zener regula no V_Z do datasheet, SCR
trava, TRIAC conduz nos dois sentidos), importação e ida e volta com resultado idêntico no ngspice,
medidas e API.

## E2E no navegador

`frontend/e2e/simulador.e2e.cjs` (rodado por `scripts/e2e.sh`) abre a aplicação num Chromium e:

1. simula o filtro RC e abre o Bode;
2. simula a ponte retificadora e calcula a FFT da corrente da fonte (confere f₀ = 60 Hz);
3. roda o Monte Carlo do RC (Bode de todas as execuções e histograma de \|H(1 kHz)\|);
4. configura o pior caso pelo painel e confere os extremos analíticos acima;
5. roda o STEP de R no RLC, o ruído com varredura de temperatura e o emissor comum;
6. importa uma netlist SPICE colada no campo de texto e simula;
7. desenha um circuito do zero com o mouse (fonte, dois resistores, fios, terras, ponta de tensão),
   simula o .op e confere 2,5 V no nó do meio;
8. falha se houver erro no console ou requisição com erro.

Capturas de tela em `capturas/fase7/` (13 imagens, uma por etapa).

## Faixas usadas no Monte Carlo e no pior caso

- Resistor, capacitor, indutor e fontes: o campo **Tolerância (%)** do componente.
- Peças do catálogo, faixa do datasheet: V_Z mín./máx. (ou tolerância de V_Z) do Zener, h_FE mín./máx.
  do BJT, V_GS(th) mín./máx. do MOSFET. Os demais parâmetros das peças ficam no valor nominal.
- Distribuição gaussiana com 3σ no limite da faixa (truncada no limite) ou uniforme.
- Pior caso pelo método da sensibilidade: uma execução nominal, uma por parâmetro no limite superior
  e as duas combinações extremas. É exato quando a medida é monotônica em cada parâmetro. Se a
  medida nominal cair fora do intervalo, o resultado traz um aviso para conferir com Monte Carlo.
- Peça não revisada pode ser usada no simulador livre (é uma escolha manual), mas aparece com o aviso
  “não revisada”. Ela continua fora da seleção automática (regra 5).

## Defeitos achados e corrigidos durante a validação

- Netlists do LTspice com `.tran 0 3m` falhavam no ngspice (TSTEP precisa ser maior que zero).
  Agora um passo zero ou vazio vira tstop/1000.
- A ponta diferencial `v(a,b)` quebrava a leitura dos resultados, porque a lista de vetores era
  separada por vírgula. Agora a separação respeita os parênteses.
- O pior caso aceitava o campo “Sinal” vazio e só falhava no fim. Agora a API recusa antes de simular.
- Ao trocar de análise (transitória ↔ AC), a tela podia pedir um gráfico com a combinação antiga e dar
  erro no eixo logarítmico. O modo de visualização agora é derivado da análise atual.
- O espectro de ruído vinha sem unidade. Agora é V/√Hz e o eixo mostra nV/√Hz.

## Limitações conhecidas

- **Sobressinal pela medida do osciloscópio:** os níveis alto e baixo vêm do histograma do sinal,
  como nos osciloscópios. Numa resposta muito oscilatória e janela curta, o nível alto fica acima do
  valor final, e o sobressinal sai menor (71,7 % contra 72,9 % no AS-SIM-02). Para o valor exato,
  use o cursor no valor final ou a medida “máximo”.
- **Importação:** cobre R, C, L, V, I (DC, AC, SIN, PULSE, PWL), D, Q, M, J, E, G, F, H, B, S e X,
  além de `.model`, `.subckt`, `.param`, `.temp`, `.step` (LTspice) e as análises. Linhas K
  (acoplamento), elementos sem símbolo e `.include` ficam nas diretivas como texto e vão para a
  netlist sem mudança. Blocos `.control` são ignorados. O posicionamento automático é em grade,
  ligado por rótulos (sem fios desenhados).
- **Ruído:** o espectro referido à entrada assume fonte de entrada de tensão (unidade V/√Hz).
- **Temperatura:** o ngspice aplica as leis de temperatura dos modelos SPICE. Os modelos das peças do
  catálogo usam valores a 25 °C do datasheet, e nem todos os parâmetros têm variação com a temperatura.
- **Tela:** o layout em três colunas precisa de 1100 px ou mais; abaixo disso as colunas se empilham.
  O editor não foi pensado para celular.
- **E2E:** usa o pacote `playwright` instalado na máquina (não está nas dependências do front-end).

## Próximo passo

Fase 8: importação de datasheets (extração de texto e tabelas, OCR, digitalização de curvas, ajuste de
modelo SPICE e tela de revisão).
