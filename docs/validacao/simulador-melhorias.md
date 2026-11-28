# Melhorias do simulador, do esquemático 2D e da protoboard (2026-11-20)

Lote de 15 pedidos do usuário. Tudo em uma branch; revisão pelo PR.

## O que mudou

| # | Pedido | Onde | Como conferir |
|---|--------|------|---------------|
| 1 | Telas maiores | Simulador (esquemático e protoboard) | Área de desenho ocupa a largura da janela; botão **Tela cheia** na barra do circuito. |
| 2 | Homologar as peças do circuito | Análise de Projetos | Quando aparece "componente não revisado" ou "sem candidato", surge **Homologar componentes deste circuito**. Abre uma prévia (nada muda), pede "Conferi" e o nome de quem revisou. Só as peças citadas nos avisos são revisadas. |
| 3 | Terra junto das fontes | Biblioteca do esquemático | O terra agora está no grupo **Fontes**. |
| 4 | Girar antes de inserir | Esquemático | Com a peça "na mão", **R** gira e **M** espelha. A prévia já mostra a peça girada. |
| 5 | Copiar componentes | Esquemático | **Ctrl+C**, **Ctrl+V** (cola onde está o ponteiro) e **Ctrl+D** (duplica). As cópias ganham nomes livres (R1 → R3...). Fios e rótulos dentro da seleção vêm junto. |
| 6 | Tirar "subcircuito" de "Outros" | Biblioteca | O subcircuito some da paleta. Continua sendo usado pela importação de netlists. |
| 7 | LEDs que acendem | Grupo **LEDs e lâmpadas** | 8 LEDs do catálogo (vermelho, laranja, amarelo, verde, azul e branco, 3 mm e 5 mm). O brilho segue a corrente média simulada. Acima de IF máx o LED aparece como QUEIMOU. |
| 8 | Lâmpadas 12, 24, 127 e 220 V | Mesmo grupo | 12 V e 24 V: OSRAM 5 W, 10 W, 21 W e 55 W. 230 V: LEDVANCE 15 W, 25 W e 40 W. 127 V e 220 V: **lâmpadas de placa** de 40, 60 e 100 W (ver Limitações). Brilho = P/Pn. Acima de 110 % aparece como ACIMA DE Pn. |
| 9 | Ligar fios automaticamente | Botão **Ligar pinos alinhados** | Liga com fio reto os pinos livres que estão na mesma linha ou coluna, do mais perto para o mais longe. Também liga um pino a um fio que passe alinhado. Nunca atravessa corpo de componente, outro pino, rótulo ou fio. |
| 10 | Selecionar vários com o mouse | Esquemático | **Shift+arrastar** no fundo desenha um retângulo. O grupo selecionado pode ser movido, copiado ou apagado (Delete). **Ctrl+A** seleciona tudo. Para mover a vista: arrastar o fundo com o botão esquerdo (ou botão do meio, ou Alt+arrastar). |
| 11 | Chaves tácteis | Grupo **Chaves** | Botão NA de 2 terminais, botão NF e chave táctil de 4 terminais (6×6 / 12×12 mm, com pares internos 1-2 e 3-4). O instante de aperto é programável e a resistência de contato pode vir do catálogo (`switch.mechanical`, ex.: Omron B3F). Na protoboard a chave de 4 terminais passa sobre a canaleta. |
| 12 | Transformadores configuráveis | Grupo **Transformadores** | **Monofásico**: Vp, Vs, relação de espiras opcional, S, f, % de magnetização e % de perdas no cobre. **Trifásico**: tensões de linha, ligação do primário e do secundário (Y ou Δ), relação por fase opcional e S total. Os cálculos (a, Lm, R) aparecem nos passos de cálculo. |
| 13 | Protoboard automática com menos fios | **Montar automaticamente** | Testa várias ordens de colocação (ordem de leitura, peças que compartilham nós juntas e 40 embaralhamentos fixos). Fica com a montagem que usa menos fios e passa na conferência. |
| 14 | Retirar peças da protoboard | Lista de peças | **Retirar** em cada peça montada, **Retirar todas as peças** (os fios ficam) e **Limpar tudo**. |
| 15 | Mais motores CC | Motor CC + catálogo `motor.dc` | 10 motores FAULHABER (6, 12 e 24 V; de 0,56 a 120 g·cm²). Com o motor escolhido, R, L, kE, kM e J vêm da tabela do fabricante. |

## Ajustes da revisão

| Pedido | O que mudou | Como conferir |
|--------|-------------|---------------|
| Peças sem sobreposição | A montagem automática guarda o retângulo que cada peça ocupa no desenho (corpo do LED, do botão, do CI) e só coloca uma peça onde não encosta em outra nem cobre a perna de outra. | **Montar automaticamente**: nenhuma peça fica por cima de outra. |
| Fios sem cruzar | Cada fio só é colocado se não cruzar outro fio, não passar sobre um corpo nem sobre uma perna. Quando não há caminho limpo, a montagem com menos fios "embolados" é a escolhida. Os fios dos instrumentos sobem em pistas ordenadas para não se cruzarem, e os terminais dos painéis genéricos ficam na borda de cima (o fio não passa sobre o painel). | Capturas `protoboard-revisada.png` e `protoboard-fonte-3-canais-motor.png`. |
| Alimentação pelos barramentos | O circuito é montado na placa de baixo, a mais perto das fontes. Cada faixa ligada à alimentação recebe um fio curto até o barramento (+ / −) da mesma placa. Os barramentos de cima e de baixo do mesmo nó só são unidos pelo barramento vertical quando os dois são usados. | Os fios das fontes chegam nos barramentos, não no meio das faixas. |
| Motor com desenho próprio | O motor CC já é desenhado como motor (vem do PR #6). | Inserir um motor CC e abrir a protoboard. |
| Fonte de vários canais | Fontes com o mesmo número de bancada aparecem num só painel, "Fonte de bancada · N canais", com os bornes CH1, CH2, CH3. | Captura `protoboard-fonte-3-canais-motor.png`. |
| Limpar circuito | Botão **Limpar circuito** no esquemático 2D. Pede confirmação e apaga peças, fios, rótulos, ponteiras e a montagem. | Clicar e confirmar. |
| "Ponteira" | As ferramentas de medição do esquemático se chamam **Ponteira V**, **Ponteira V diferencial** e **Ponteira I**. | Barra de ferramentas do esquemático. |

Teste novo: `test_bb_parts_never_overlap_and_jumpers_stay_clear` (nenhum par de peças se sobrepõe,
nenhum fio passa sobre corpo, perna ou outro fio, a fonte fica nos barramentos e tudo na placa de
baixo). Os 120 circuitos aleatórios de `test_breadboard_properties.py` continuam passando na conferência.

## Modelos e equações

- **LED**: queda constante (VF típico, ou máximo quando o datasheet não dá o típico) na corrente
  de ensaio IF. Uma fonte de 0 V em série mede a corrente. Brilho = corrente média na segunda
  metade da simulação ÷ IF de ensaio.
- **Lâmpada**: resistência a quente constante, R = Vn²/Pn (passo de cálculo `<ref>_r_hot`). A
  corrente de partida a frio não é modelada, porque as fichas técnicas não dão a resistência a frio.
- **Transformador**: circuito equivalente simplificado. Por enrolamento:
  - a = Vp/Vs (ou o valor dado).
  - Lm = Vp/(2πf·Im), com Im = i_m·S/Vp.
  - Rp = (Pcu/2)/Ip² e Rs = (Pcu/2)/Is², com Pcu = p_cu·S.
  - Acoplamento k = 0,9999. Não há perdas no núcleo nem saturação.
  - No trifásico cada coluna é um par de enrolamentos. Em Δ, a tensão do enrolamento é a de
    linha; em Y é a de linha ÷ √3.
  - O deslocamento angular sai das próprias ligações: Dy dá Dyn11 (+30°), Yd dá Yd1 (−30°), Yy e Dd dão 0°.
- **Motor CC com peça do catálogo**: o atrito viscoso vem das perdas a vazio, b = kM·I0/ω0.
- **Chave de 4 terminais**: os pares internos são ligados por 1 mΩ. O contato é uma chave do ngspice
  (ron do catálogo, roff = 1 GΩ).

## Testes

| Teste | O que garante |
|-------|---------------|
| `tests/unit/schematic/test_transformers.py` | Dimensionamento pelos dados de placa. Monofásico 220/12 V com 1 kΩ: 12 V ± 1 %. Trifásico 380/220 V, 3 kVA, 100 Ω por fase: tensão de linha 220 V ± 3 % e ângulo de +30° (Dy), −30° (Yd) e 0° (Yy), ± 2°. |
| `tests/unit/cosim/test_devices_ngspice.py` (`push`, `tact`) | Botão NA conduz depois do aperto, botão NF abre, chave de 4 terminais mantém os pares e une 1-2 a 3-4 quando apertada. |
| `tests/unit/cosim/test_catalogue_parts.py::test_dc_motor_no_load_speed_matches_its_equation` | FAULHABER 2224U012SR em 12 V a vazio. A velocidade simulada é igual à de regime ω = V/(kE + R·b/kM) (± 0,5 %) e fica a 2 % de n0 = 7810 min⁻¹. |
| `tests/property/test_breadboard_properties.py` | A montagem automática sempre passa na conferência e nunca usa mais fios que a ordem de leitura. Em 150 circuitos aleatórios caiu de 988 para 879 fios (−11 %). |
| `tests/datasheet/test_ds_catalogue_values.py` | Os valores dos LEDs Vishay aparecem na página do PDF citado. Para fontes que são páginas web (sem PDF), o número tem de constar no trecho citado (`test_web_values_in_excerpt`). |
| `frontend/src/schematic/editing.test.ts`, `indicators.test.ts` | Seleção por retângulo, mover com fios elásticos, copiar e colar, ligação automática e cálculo do brilho. |

## Fontes dos dados novos

| Peça | Fabricante | Documento | URL | SHA-256 |
|------|------------|-----------|-----|---------|
| TLHR5400, TLHY5400, TLHG5400 | Vishay | 83012 Rev. 2.6, 09-Sep-2022 | https://www.vishay.com/docs/83012/tlhg540.pdf | 25e4aa41… |
| TLHR4400, TLHO4400, TLHY4400, TLHG4400 | Vishay | 83006 Rev. 3.8, 21-Mar-2023 | https://www.vishay.com/docs/83006/tlhg440.pdf | d190590f… |
| VLHW5100 | Vishay | 81159 Rev. 1.3, 20-May-2019 | https://www.vishay.com/docs/81159/vlhw5100.pdf | a65548f4… |
| 5007, 7506, 64210, 5627, 5637, 7511 | OSRAM | eCat on-line (consultado em 2026-11-20) | links em cada YAML | — (página web) |
| SPC.T CL 15/25/40 W 230 V E14 | LEDVANCE | página do produto (productId 106393, 33315, 278862) | links em cada YAML | — (página web) |
| 1524T012SR, 2224U012SR, 2232U012SR, 2342S006CR, 2342S012CR, 2342S024CR, 2642W024CR, 3242G024CR, 3257G024CR, 3863H024CR | FAULHABER | eShop, tabela "Values" (consultada em 2026-11-20) | https://eshop.faulhaber.com/en/&lt;peça&gt;/&lt;peça&gt; | — (página web) |

Todos os registros novos entram como **rascunho**. Não entram na seleção automática até você revisá-los.

## Limitações conhecidas

- **127 V e 220 V**: não consegui acessar a ficha de um fabricante de lâmpada incandescente de
  127 V. As lâmpadas de 127 V e 220 V da paleta são **lâmpadas de placa**: só tensão e potência
  nominais (40, 60 e 100 W), sem peça de catálogo. A LEDVANCE de 230 V é real e serve para 220 V
  (potência ≈ 91 % da nominal).
- **Pinagem dos LEDs do catálogo**: o texto dos datasheets não identifica anodo e catodo. Na
  protoboard eles aparecem "sem pinagem" (regra 1). O LED genérico usa a perna longa como anodo.
- **FAULHABER 2342 (6, 12 e 24 V)**: o kE publicado não bate com kn nem com kM (diferença de ~9 %).
  Foi transcrito como publicado, com nota no YAML para a revisão. O simulador usa kE.
- **Chaves tácteis**: além da Omron B3F já existente, não consegui baixar outros datasheets (Omron
  B3F-4000 e C&K PTS645 bloquearam o acesso). Os modelos são genéricos, com a resistência de contato
  editável ou vinda do catálogo.
- **Transformador**: sem saturação, sem perdas no núcleo e sem corrente de inrush. Os percentuais de
  magnetização (5 %) e de perdas no cobre (2 %) são valores didáticos: ajuste com os ensaios a vazio
  e de curto-circuito.
- **Ligação automática de fios**: só faz fios retos. Pinos desalinhados continuam sendo ligados à mão.

## Revisão no Windows (2026-11-20)

- Corrigida a rolagem horizontal em 390 px: o seletor de instrumentos pode quebrar de linha e
  a regra de largura do esquemático respeita o empilhamento dos painéis em telas menores.
- 112 testes do backend selecionados para esquemático, protoboard e dispositivos passaram.
- 63 testes da interface, ESLint e compilação TypeScript/Vite passaram.
- O teste `frontend/e2e/simulador.e2e.cjs` passou no Chrome: tela estreita, RC, Bode, ponte,
  FFT, Monte Carlo, pior caso, varredura, emissor comum, importação e desenho de circuito.
