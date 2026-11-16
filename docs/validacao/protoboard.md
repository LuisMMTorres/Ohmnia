# Validação: vista de protoboard (Fase 10, decisão D11)

Data: 2026-11-16. Status: aprovada em 2026-11-16.

O circuito passa a ter duas vistas, o esquemático 2D e a montagem numa protoboard de 830 pontos
com as peças reais, e as duas são conferidas uma contra a outra. Manual: `docs/manual/07-protoboard.md`.

## O que foi feito

| Pedido (D11) | Onde | Situação |
|---|---|---|
| Simbologia real de cada componente, ao lado do símbolo 2D | `breadboard/packages.py`, `frontend/src/breadboard/PackageArt.tsx`; painel do componente no simulador e página do catálogo | ✅ 25 encapsulamentos |
| Pinagem com fonte no datasheet | campo `pinout` do registro (pino, nome no datasheet, função no símbolo, unidade, página, status) | ✅ 13 registros, 74 peças (tabela abaixo) |
| Protoboard no simulador (montagem manual) | vista "Protoboard" do simulador; montagem guardada no arquivo do circuito | ✅ colocar, arrastar, dobrar perna, fio, girar, retirar |
| Mesmo circuito, conferido | `breadboard/check.py`; roda a cada mudança | ✅ faltando, sobrando, trocada, não montado, furo em conflito, fora do esquemático |
| Montagem gerada no projeto e roteiro de prática | `breadboard/physical.py`, `autoplace.py`, `guide.py`; aba "Protoboard" do projeto | ✅ 19 de 22 módulos |
| Peças sem pinagem conferida não entram na conferência | origem `sem_pinagem` | ✅ aparecem sem rótulo e com aviso |

### Decisões técnicas para a sua revisão

- **Peça genérica** (sem peça do catálogo): o sistema desenha um encapsulamento didático com as
  pernas rotuladas pela função (TO-92 E-B-C, TO-220 G-D-S, DIP-8 de amp-op simples). Não é a
  pinagem de uma peça real, e o aviso diz isso; a conferência usa esses rótulos. A alternativa era
  deixar genéricos fora da conferência, o que tiraria a conferência dos exemplos do simulador.
- **Alimentação de integrados**: o símbolo do amp-op não tem V+ e V− (a tensão está nos parâmetros
  `vcc`/`vee`). Na protoboard esses pinos vão a uma fonte simétrica implícita (ALIM), que a
  conferência cobra. Com `vee = 0`, V− vai ao terra.
- **Amp-op duplo** (LM358): cada componente do esquemático usa a unidade A de um integrado; a
  unidade B fica livre, com a recomendação de boa prática no aviso. Juntar dois amp-ops do
  esquemático num só LM358 fica para depois.
- **Capacitor ≥ 1 µF genérico** é desenhado como eletrolítico com a perna + no pino 1 do símbolo;
  o aviso pede para conferir se o pino 1 está no nó de maior tensão (a conferência é de ligação,
  não de polaridade elétrica).
- **Projeto guiado**: a netlist de cada módulo é um modelo de verificação. O sistema recupera o
  circuito físico: amperímetros (fontes de 0 V) viram fio; o macromodelo do amp-op (`EU1o` na
  saída, fontes de polarização `IU1bp`/`IU1bn` nas entradas) vira um integrado com a alimentação
  ±VCC do projeto; subcircuitos são reconhecidos pelos nomes dos pinos. Os três módulos que usam
  elementos sem peça física (DM-LIN com regulador comportamental, DM-PAD e DM-CMD com chaves
  ideais e fontes comportamentais) avisam isso em vez de inventar a montagem.
- **Pinagem de catálogo**: transcrita só dos datasheets cujo PDF na sua pasta tem o mesmo SHA-256 do
  datasheet já citado no registro, para que a fonte seja o mesmo documento. Todas com status
  `extraido`.

## Pinagens transcritas (para revisar)

| Registro | Encapsulamento | Pinagem | Fonte |
|---|---|---|---|
| Vishay 1N4001–1N4007 | DO-41 | 1 catodo (faixa), 2 anodo | doc. 88503, p. 1, Mechanical data, Polarity |
| Vishay 1N5400–1N5408 | DO-201AD | idem | doc. 88516, p. 1, Polarity |
| Vishay 1N5817–1N5819 | DO-41 | idem | doc. 88525, p. 1, Polarity |
| Vishay UF4001–UF4007 | DO-41 | idem | doc. 88755, p. 1, Polarity |
| Vishay 1N4148 | DO-35 | idem (faixa preta) | doc. 81857, p. 1 (e desenho na p. 3) |
| Vishay 1N4728A–1N4761A | DO-41 | idem | doc. 85816, p. 3, Cathode identification |
| onsemi BC546B–BC548C | TO-92 | 1 coletor, 2 base, 3 emissor | BC546/D, p. 7, case 29-11 STYLE 17 (p. 1: STYLE 17) |
| onsemi P2N2222A | TO-92 | 1 coletor, 2 base, 3 emissor | P2N2222A/D, p. 7, STYLE 17 |
| onsemi 2N5457/2N5458 | TO-92 | 1 dreno, 2 fonte, 3 porta | 2N5457/D, p. 7, STYLE 5 (p. 2: STYLE 5) |
| onsemi MPF102 | TO-92 | 1 dreno, 2 fonte, 3 porta | MPF102/D, p. 7, STYLE 5 |
| TI LM358P | DIP-8 | 1 OUT1, 2 IN1−, 3 IN1+, 4 V−, 5 IN2+, 6 IN2−, 7 OUT2, 8 V+ | Rev. AB, p. 3, Table 4-1 (coluna PDIP) |
| TI LM311 | DIP-8 | 1 EMIT OUT, 2 IN+, 3 IN−, 4 VCC−, 5 BALANCE, 6 BAL/STRB, 7 COL OUT, 8 VCC+ | SLCS007K, p. 3, Pin Functions |
| TI NE555 | DIP-8 | 1 GND, 2 TRIG, 3 OUT, 4 RESET, 5 CONT, 6 THRES, 7 DISCH, 8 VCC | SLFS022K, p. 3, Table 4-1 |

Ponto a conferir no TO-92: o sentido da numeração (com a face plana para a frente e os terminais
para baixo, pino 1 à esquerda) foi registrado como nota a partir do desenho do encapsulamento; o
texto do datasheet não traz essa frase.

Ficaram **sem pinagem** (o PDF da pasta não é o mesmo do registro ou não está na pasta): os demais
transistores, MOSFETs, IGBT, tiristores, reguladores, LM741, TL071, IR2110, pontes e o MBR20100CT
(o estilo de pinos do TO-220 não está em texto no PDF).

## Resultados dos testes

| Teste | O que verifica | Resultado |
|---|---|---|
| `tests/unit/breadboard` | regras da placa, código de cores, pinagem genérica/datasheet/sem pinagem, amp-op duplo, montagem automática de 3 circuitos, detecção de troca, fio faltando, curto, peça não montada, furo duplo, peça fora do esquemático | ✅ 20 |
| `PT-BB` (`tests/property/test_breadboard_properties.py`) | 120 circuitos aleatórios por execução (repetido com 4 sementes): toda montagem automática passa na conferência | ✅ |
| `test_breadboard_api.py` | encapsulamentos, fonte da pinagem, montar, conferir, roteiro, furo inválido | ✅ 5 |
| `test_design_breadboard.py` | os 22 módulos: 19 montáveis e todos conferem; retificador com o diodo escolhido; amp-op LM358 com ALIM; módulo com chaves ideais recusado | ✅ 4 |
| Interface (vitest) | geometria igual à do backend: tiras, furos inexistentes, DIP na canaleta, peça vertical | ✅ 39 (5 novos) |
| Verificação na tela | ponte retificadora e emissor comum no simulador; DM-RET1 no projeto; LM358P no catálogo | ✅ capturas em `capturas/fase10-protoboard/` |

**Suíte completa do backend** (2026-11-16): cobertura total de 95 % (núcleo `breadboard/` entre
76 % e 100 % por arquivo). Falham só os três casos já conhecidos e anteriores a esta fase:
`test_as_fase5[opnl_limitador]` e `[opnl_limitador_g2]` (Windows) e `test_pt_inv_ma_linear`.

**Achado durante a rodada, para a sua decisão.** Os testes de datasheet (marcador `datasheet`)
baixam os PDFs dos fabricantes. Até a Fase 9 o site da onsemi recusava o download e esses testes
eram pulados; com os cabeçalhos de navegador acrescentados na fila de datasheets, o download passou
a funcionar e a suíte completa baixou os datasheets do catálogo, sem que você tivesse autorizado
(pendência DS-EXT). Resultado: os PDFs atuais da onsemi têm bytes diferentes dos catalogados (a
pendência "PDFs da onsemi com bytes novos"), então 2087 conferências de valor por página falharam
por hash, e o DS-EXT mediu 381 valores divergentes em 1211 comparados (31 %, contra o limite de
10 %), com 89 datasheets indisponíveis. Para não repetir, esses testes agora só rodam quando
pedidos (`pytest -m datasheet`; em `pyproject.toml`, `addopts` exclui o marcador). Os números do
DS-EXT dependem de você decidir o que fazer com os PDFs novos da onsemi.

## Limitações conhecidas

- A montagem automática prioriza a ligação correta; a arrumação visual pode ficar apertada em
  circuitos maiores (ajuste arrastando as peças). Instrumentos ficam abaixo da placa e os cabos
  podem cruzar a placa.
- Um componente do esquemático por integrado (sem juntar dois amp-ops num LM358).
- A conferência é de ligações, não de polaridade elétrica (eletrolítico invertido com as ligações
  certas não é detectado, só avisado).
- DM-ZEN simula dois casos de carga lado a lado; a montagem gerada mostra os dois circuitos.
- Não há vista de protoboard no relatório PDF (fica no aplicativo e no roteiro).
