# Validação: retificadores (Fase 3)

Data: 2026-11-14. Status: aguardando aprovação da Fase 3.

A aba **Projeto** faz o caminho completo de uma topologia: especificação → cálculo com memória →
escolha de componentes reais do catálogo → margens de derating e temperatura de junção → conferência
com o ngspice → esquemático, lista de materiais, relatório e roteiro de prática. Os três módulos
desta fase definem o padrão que as próximas topologias vão seguir (plug-in em
`backend/src/circuitos/design/plugins/<id>/`, nada muda no núcleo).

| Módulo | Topologias | Carga | Grandezas principais |
|---|---|---|---|
| `DM-RET1` | meia onda, onda completa com derivação central, ponte; sem filtro, filtro C, LC e π (C-L-C) | resistiva (Vo, Io) | Vm, relação de espiras, C ou L, ondulação, Vo e Vo ef., correntes média, eficaz e de pico nos diodos, PIV, VA do transformador, FP, THD |
| `DM-RETC1` | meia onda controlada (com ou sem roda livre), ponte totalmente controlada, ponte semicontrolada | R-L-E | α nominal e faixa de α para ±ΔVrede, modo contínuo ou descontínuo, β, Vo, Io, ondulação de Io, IT(AV), IT(RMS), VDRM, VRRM, diodos, FP, FD, THD |
| `DM-RET3` | 3 pulsos, ponte de 6 pulsos, 12 pulsos (duas pontes em série, secundários Y e Δ); diodos ou tiristores | corrente constante (R + L ≫ R/ω, E) | μ (comutação por Ls), queda ΔVμ, Vo, faixa de α, correntes nos dispositivos, tensão de bloqueio, corrente de linha, VA, FP, FD, THD |

## Como os cálculos são feitos

Todos os módulos resolvem a forma de onda de regime em um período (grade de 14 400 a 28 800
pontos) e tiram as grandezas dela, em vez de usar só a aproximação de livro. A aproximação aparece
na memória de cálculo como primeiro passo (por exemplo, `C ≥ Io/(p·f·ΔVo)`), e o valor comercial é
conferido pela solução exata. Cada passo traz equação, entradas, premissas e referência.

- **`DM-RET1`, filtro C:** ângulo de corte θoff por `ωRC·Vm·cos θoff + Vm·sin θoff = nVF`, descarga
  exponencial pela carga e início de condução θon pela periodicidade; `Vm` ajustado por busca de raiz
  (brentq) para dar o Vo pedido com o C comercial.
- **Filtro LC:** solução harmônica completa do estágio L + (C ∥ R) em condução contínua; L = k·Lcrit
  (k escolhido pelo usuário, padrão 2).
- **Filtro π:** ponto fixo entre a forma de onda de C1 (pulsos dos diodos) e a corrente do estágio
  LC; C1 dimensionado para 4× a ondulação final, C2 = C1, L pela atenuação de 2ª harmônica.
- **`DM-RETC1`:** solução por trechos com a corrente `i(θ)` de R-L-E; modo contínuo por ponto fixo
  afim, descontínuo com extinção β; pulso de porta de 5° (dispara assim que o tiristor fica
  polarizado se α for menor que o ângulo em que `v > E`).
- **`DM-RET3`:** pontes com corrente de carga constante e comutação por Ls (ângulo μ);
  12 pulsos com o segundo grupo defasado de 30° e a corrente de linha referida ao primário.
- **Transformador:** ideal (sem resistência nem dispersão), relação de espiras pela Vm calculada
  com a queda dos diodos.

## Seleção de componentes e margens

1. Passo ideal → esforços (tensão reversa, corrente média, eficaz e de pico).
2. Cada posição (por exemplo `D1–D4`) recebe, entre os candidatos **liberados** que atendem aos
   fatores de derating do critério escolhido (`didático` ou `industrial`; critérios de projeto,
   não normativos, conforme D4), o menos superdimensionado: menor soma de
   `ln(nominal / (fator × esforço))` sobre os parâmetros conferidos.
3. Passo real: o cálculo é refeito com VF/VT0 e rT do componente escolhido, até convergir. Se o
   componente não suportar os esforços reais, a seleção é refeita sobre a envoltória dos esforços
   ideal e real (até 5 rodadas).
4. Margens: tabela esforço × valor nominal × fator exigido × margem, com situação ok, atenção ou
   violado.
5. Temperatura de junção: `Tj = TA + P·Rθja` sem dissipador; se passar do limite, o aviso indica
   a resistência térmica máxima do dissipador `Rθsa ≤ (Tj,máx − margem − TA)/P − Rθjc − Rθcs`.

O usuário pode **travar** um componente em qualquer posição (lista suspensa em
*Componentes e margens*). Componente não revisado nunca entra na escolha automática; se for
travado à mão, o resultado leva o aviso `nao_revisado`.

## Conferência com o ngspice (testes AS)

O botão **Conferir com o ngspice** gera a netlist do projeto (com o modelo comportamental de cada
dispositivo: diodo como queda VF e resistência, tiristor com disparo, travamento e manutenção),
simula até o regime e compara as grandezas no último período. As curvas do cálculo e da simulação
aparecem sobrepostas.

Tolerâncias:

| Módulo | Grandezas e tolerâncias |
|---|---|
| `DM-RET1` | Vo, Vo ef. e corrente média no diodo: 1 %; ondulação: 1 % sem filtro, 2 % com filtro; FP 2 %; THD 5 % |
| `DM-RETC1` | Vo, Vo ef., Io e corrente eficaz no secundário: 1 %; FP 2 %; THD 5 % |
| `DM-RET3` | Vo e Io: 1 %; corrente de linha eficaz e FP: 2 %; THD 10 % (na simulação a carga tem L finito, então sobra uma pequena ondulação em Io que muda as harmônicas) |

Erros medidos em 2026-11-14, maior erro de cada caso:

| Teste | Caso | Grandezas | Maior erro | Grandeza do maior erro |
|---|---|---|---|---|
| `AS-RET-01` | meia onda / sem filtro | 6 | 0,00 % | THD da corrente de entrada |
| `AS-RET-01` | meia onda / C | 6 | 0,02 % | Fator de potência |
| `AS-RET-01` | derivação central / sem filtro | 6 | 0,00 % | THD da corrente de entrada |
| `AS-RET-01` | derivação central / C | 6 | 0,11 % | Fator de potência |
| `AS-RET-01` | derivação central / LC | 6 | 0,24 % | THD da corrente de entrada |
| `AS-RET-01` | derivação central / π | 6 | 0,01 % | THD da corrente de entrada |
| `AS-RET-01` | ponte / sem filtro | 6 | 0,01 % | THD da corrente de entrada |
| `AS-RET-01` | ponte / C | 6 | 0,08 % | Fator de potência |
| `AS-RET-01` | ponte / LC | 6 | 0,18 % | THD da corrente de entrada |
| `AS-RET-01` | ponte / π | 6 | 0,15 % | Fator de potência |
| `AS-RET-01` | ponte / C (24 V, 2 A, 10 %, 220 V/50 Hz) | 6 | 0,29 % | Fator de potência |
| `AS-RET-01` | derivação central / LC (24 V, 2 A, 10 %, 220 V/50 Hz) | 6 | 0,26 % | THD da corrente de entrada |
| `AS-RET-01` | ponte / π (24 V, 2 A, 10 %, 220 V/50 Hz) | 6 | 0,23 % | Fator de potência |
| `AS-RET-02` | ponte continua | 6 | 0,03 % | Tensão média na carga |
| `AS-RET-02` | ponte descontinua | 6 | 0,02 % | Tensão média na carga |
| `AS-RET-02` | ponte rle | 6 | 0,02 % | Corrente média na carga |
| `AS-RET-02` | semi continua | 6 | 0,08 % | THD da corrente de entrada |
| `AS-RET-02` | semi rle | 6 | 0,02 % | Corrente média na carga |
| `AS-RET-02` | meia onda rl | 6 | 0,01 % | Fator de potência |
| `AS-RET-02` | meia onda roda livre | 6 | 0,01 % | THD da corrente de entrada |
| `AS-RET-03` | 6p controlado | 5 | 0,21 % | Corrente média na carga |
| `AS-RET-03` | 6p diodos | 5 | 0,08 % | Corrente média na carga |
| `AS-RET-03` | 6p sem Ls | 5 | 0,21 % | Corrente média na carga |
| `AS-RET-03` | 3p controlado | 5 | 0,20 % | Corrente média na carga |
| `AS-RET-03` | 12p controlado | 5 | 0,21 % | Corrente média na carga |

Todas as 145 comparações dentro da tolerância; maior erro geral 0,29 %.

## Testes de referência (GT) e propriedades (PT)

Os testes `GT-RET*` comparam o módulo com fórmulas fechadas dos livros (meia onda e onda completa
resistivas, θoff e ondulação do filtro C, filtro LC, controlado R e R-L com extinção, ponte contínua
e descontínua, semicontrolada, 3 e 6 pulsos, comutação, corrente de linha ideal, cancelamento da
5ª e 7ª harmônicas em 12 pulsos). Hoje eles conferem **fórmulas**; ainda não conferem exemplos
resolvidos de livro, porque isso depende da decisão D6.

**Pedido (D6):** indique os exemplos resolvidos que usa em aula (livro, edição, número do exemplo),
ou envie fotos das páginas. Cada exemplo vira um teste GT com a fonte no docstring e tolerância
explícita. Sugestão de cobertura mínima:

1. ponte com filtro C (ondulação e corrente de pico no diodo);
2. retificador controlado de meia onda com carga R-L (ângulo de extinção);
3. ponte totalmente controlada R-L-E em condução contínua;
4. ponte trifásica controlada com indutância de comutação (μ e queda de tensão).

Os testes `PT-RET-FP` conferem propriedades em pontos de operação aleatórios: fator de potência
entre 0 e 1, Vo ≤ Vm − n·VF, balanço de potência (entrada = carga + diodos, 0,5 %) no filtro C, e
FP ≤ 2√2/π (≈ 0,9) no filtro LC.

## Premissas e limitações conhecidas

- Transformador ideal: sem resistência de enrolamento, sem indutância de dispersão nos módulos
  monofásicos (Ls só no `DM-RET3`). Por isso a corrente de surto na energização não é calculada; o
  relatório avisa para conferir IFSM quando o transformador for escolhido.
- `Rθcs = 0,5 K/W` (pasta térmica) é premissa editável no formulário.
- Perda nos dispositivos por VF/VT0 + rT·I²; sem perdas de recuperação reversa (frequência da rede).
- Capacitores, indutores e transformador saem com valor e requisitos (tensão, corrente de
  ondulação, VA), mas **sem peça do catálogo**: o banco ainda não tem capacitores, e dissipadores e
  núcleos dependem de D8.
- `DM-RET3` assume corrente de carga constante; a ondulação de Io não é calculada.
- O esquemático de 12 pulsos é simplificado: o secundário em Δ aparece com o mesmo símbolo de
  fonte, indicado pelo rótulo.
- Na simulação de 12 pulsos a tensão de saída mostra oscilações curtas nas comutações (efeito
  numérico das fontes ideais com Ls); as médias concordam dentro de 0,25 %.

## O que conferir

- [ ] Abrir a aba **Projeto**, trocar topologia e filtro e ver se os valores fazem sentido para
      as aulas (por exemplo, o C de 15 mF para 12 V, 1 A e 5 % de ondulação).
- [ ] Conferir a memória de cálculo de um caso de cada módulo.
- [ ] Gerar o **Relatório** e o roteiro de prática de um retificador que use no laboratório.
- [ ] Indicar os exemplos de livro para os testes GT (D6).
- [ ] Responder D8 (fabricantes de dissipadores e núcleos).

## Como executar

```bash
scripts/check.sh                            # verificação completa
cd backend && uv run pytest tests -m ngspice -k "as_ret"   # só os testes AS dos retificadores
```

Capturas de tela: `capturas/fase3/`.
