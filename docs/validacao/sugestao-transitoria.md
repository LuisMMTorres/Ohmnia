# Sugestão da transitória, fonte em RMS, transformador Np/Ns e gráficos dos resultados

Entrega de 22/11/2026 (branch `claude/project-thread-dnovat`). Pedidos do usuário no simulador
livre (esquemático).

## 1. Sugestão dos parâmetros da transitória (.tran)

Na aba **Configurar análise → Análises**, cada transitória mostra a caixa **Sugestão para este
circuito**, recalculada sempre que o circuito muda:

| Parâmetro | Regra |
|---|---|
| Tempo final | maior entre 5 períodos da excitação mais lenta, 5τ da maior constante de tempo, 5 períodos de ressonância LC, fim dos pontos PWL (×1,2) e rampas de partida (×1,5); arredondado para cima na série 1-2-5 |
| Passo máximo | menor entre T/50 (senoide, trifásica), min(T/100, t_on/20) (pulso/PWM), τ/10, T₀/50 (LC), menor intervalo PWL/5 e o limite dos acionamentos/sensores; nunca acima de t_stop/50; arredondado para baixo na série 1-2-5 |
| Passo de saída | min(t_stop/1000, passo máximo) |
| Início da gravação | 0 |
| UIC | "sim" se algum capacitor ou indutor tem tensão/corrente inicial |

As constantes de tempo são estimativas de 1ª ordem: τ = C·(R₁‖R₂‖…) com os resistores ligados aos
nós do capacitor e τ = L/(R₁ + R₂ + …) para o indutor (Hayt, Kemmerly & Durbin, *Engineering
Circuit Analysis*, 8ª ed., cap. 8); T₀ = 2π√(LC) (cap. 9). Capítulos a conferir no livro
(`verified: false`). "Como foi calculado" mostra a memória de cálculo de cada valor.

**Aplicar sugestão** copia todos os valores para os campos; **usar** copia só um. Os campos
continuam editáveis.

### Falha da simulação com os valores padrão

Com o passo máximo em branco o ngspice limita o passo a min(TSTEP, (TSTOP − TSTART)/50). Em
100 ms isso dá 100 µs, apenas 10 pontos por período de um sinal de 1 kHz ou 40 µs de pulso: a
forma de onda sai serrilhada ou o chaveamento some (é o que aparece na captura enviada do
retificador). Agora, **se o campo Passo máximo estiver vazio** e o padrão do ngspice for maior que
o sugerido, a netlist usa o valor sugerido e mostra um aviso. Valor digitado pelo usuário nunca é
alterado.

Não consegui reproduzir uma falha com mensagem de erro do ngspice nos circuitos de teste (senoide
+ R, RC, retificador com filtro, buck). Se a falha que o usuário viu tinha mensagem, ela continua
a ser explicada pelo diagnóstico existente (passo muito pequeno, matriz singular etc.).

## 2. Fonte CA em tensão eficaz (RMS)

O campo "Amplitude pico a pico" virou **Tensão eficaz, RMS** (corrente eficaz nas fontes de
corrente), com o pico e o pico a pico mostrados abaixo. Conversões:

- senoide: V_p = V_rms·√2;
- quadrada com razão cíclica D: V_rms = V_pp·√(D(1 − D)) (V_pp/2 em 50 %);
- triangular/dente de serra: V_rms = V_pp/(2√3).

O valor eficaz é o da parte alternada (o offset fica à parte). Circuitos salvos com pico a pico
(`bench_vpp`) são lidos e convertidos (360 V pp → 127,279 V).

## 3. Transformador: relação Np/Ns

O campo "Relação Ns/Np" virou **Relação de espiras Np/Ns** (L_s = L_p/(N_p/N_s)²). Circuitos
salvos com o campo antigo são convertidos ao abrir (n = 0,1 → Np/Ns = 10); a netlist também aceita
o campo antigo.

## 4. Gráficos dos resultados

- Cada sinal tem um seletor **Gráfico 1, 2, … / + novo gráfico**; **Separar por grandeza** põe
  tensões, correntes e potências em gráficos distintos e **Tudo em um gráfico** desfaz.
- Eixo do tempo, zoom e cursores são comuns a todos os gráficos.
- Cada sinal tem um campo **legenda**: o nome vale na legenda, na tabela de cursores e nas
  medições; o nome original fica na lista e na dica. Nomes e gráficos ficam guardados no
  navegador.
- Tabelas dos resultados (medições, cursores, FFT/THD, estatística, pior caso, sugestão) com
  cabeçalhos e valores centralizados.

## Testes

- `tests/unit/schematic/test_transient_suggestion.py` (arredondamento 1-2-5, senoide 60 Hz, RC
  com R de Thévenin, buck, sem escala, UIC, aviso de simulação longa, passo máximo automático e
  valor do usuário preservado); `test_netlist.py::test_transformer_turns_ratio_is_np_over_ns`;
  `test_schematic_api.py::test_tran_suggestion`.
- Front-end: `sourceConfig.test.ts` (RMS ↔ pico, circuitos antigos) e `migrate.test.ts` (Np/Ns).
- Executados aqui: `tests/unit/schematic`, `tests/unit/simulation`, `tests/unit/api`,
  `tests/unit/breadboard`, `tests/unit/cosim`, `tests/analytic_vs_sim` (todos passaram) e
  `vitest` (70 testes). A suíte completa fica para o computador do usuário.

## Limitações

- As constantes de tempo ignoram semicondutores, fontes controladas e motores (τ mecânico); em
  circuitos assim a sugestão vem só das fontes.
- "Exportar figura" ainda gera um só gráfico com os nomes originais.
- Ao separar em vários gráficos, cada um tem no máximo dois eixos verticais, como antes.

## Capturas

`capturas-sugestao-transitoria/`: 1 sugestão, 2 resultado após aplicar, 3 fonte em RMS,
4 transformador Np/Ns, 5 gráficos separados com legendas renomeadas, 6 tabela da FFT centralizada.
