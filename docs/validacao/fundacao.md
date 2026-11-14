# Validação — Fase 1 (Fundação)

Data: 2026-11-14 · ngspice 42 (Ubuntu 24.04) · Python 3.13 · Node 22

## Resumo

| Conjunto | Testes | Resultado |
|---|---|---|
| Back-end (unitários, propriedades, analítico × simulação, API) | 121 | todos passam |
| Front-end (formatação de grandezas) | 9 | todos passam |
| Cobertura do back-end (exceto camada HTTP) | — | 95 % (mínimo exigido: 80 %) |
| ruff, mypy `--strict`, import-linter, tsc `strict`, ESLint, Prettier | — | sem pendências |

## Casos analítico × ngspice

**AS-SMOKE-01** (`backend/tests/analytic_vs_sim/test_as_smoke_rc.py`). Os valores esperados vêm da
teoria de circuitos (divisor de tensão, resposta ao degrau de 1ª ordem, passa-baixas de 1ª
ordem). Não vêm de exemplo de livro. Tolerância: 0,5 %.

| Grandeza | Analítico | Critério |
|---|---|---|
| Divisor 10 V, 1 kΩ / 2 kΩ: V(b) | 6,667 V | ±0,5 % |
| Degrau em RC, τ = 1 ms: v(t) em t = 0,5τ, τ, 2τ, 3τ | 1 − e^(−t/τ) | ±0,5 % em cada ponto |
| Passa-baixas RC: módulo em fc = 159,15 Hz | 1/√2 (−3,01 dB) | ±0,5 % |
| Passa-baixas RC: fase em fc | −45° | ±0,5 % |
| Frequência de −3 dB localizada na curva simulada | 159,15 Hz | ±0,5 % |

## Testes de propriedade

| ID | Propriedade |
|---|---|
| PT-RMS | RMS² = média² + amplitude²/2 para senoide com nível CC; RMS ≥ \|média\| |
| PT-THD | A THD calculada recupera a razão de um único harmônico injetado (k = 2…9) |
| PT-ESERIES | O arredondamento para E12/E24/E96 nunca se afasta mais de meio passo da série (escala log); "para cima" nunca diminui e "para baixo" nunca aumenta o valor |

## Outras verificações

- **Série de Fourier da onda quadrada:** harmônicos ímpares 4/(πk) com erro < 0,1 %, pares nulos, THD = √(π²/8 − 1) com erro < 1 %.
- **E48 conferida** contra a tabela da IEC 60063 transcrita no teste. E96/E192 são geradas por regra, com a exceção conhecida de 9,20 em E192.
- **Os dois modos do ngspice** (biblioteca compartilhada e executável) produzem vetores idênticos (rtol 1e−9) para o mesmo circuito.
- **Regras de rastreabilidade do banco:** parâmetro revisado sem página é recusado; parâmetro extraído sem fonte é recusado; componente com parâmetro obrigatório não revisado não pode ser liberado; componente não liberado não é selecionável.

## Limitações conhecidas

- Testado apenas em Linux. O carregamento da DLL do ngspice no Windows está implementado (variável `CIRCUITOS_NGSPICE_LIB`), mas não foi executado.
- A imagem Docker não foi construída neste ambiente (sem daemon Docker disponível).
- O visualizador é mínimo: sem cursores de medição, sem eixo de fase separado e sem exportação de figura. Esses recursos estão previstos para a Fase 7.
- A memória de cálculo (`CalcStep`) existe, mas ainda não é usada por nenhum módulo de projeto. O primeiro uso será na Fase 3.
- O banco de componentes tem por enquanto só o esquema de diodo retificador, sem nenhum componente cadastrado. A carga inicial com datasheets é a Fase 2.
