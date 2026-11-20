# Análise de Projetos: grandezas da simulação, sondas e edição pelo esquemático

Pedido do usuário em 2026-11-20 (9 itens). Branch `claude/project-thread-kcwdpq`.

## O que mudou

| Item | Como ficou |
|---|---|
| 1 | O seletor "Módulo de projeto" passou a se chamar **Circuito**. |
| 2 | DM-RET1 tem o ajuste **Tensão do secundário (eficaz)**; Vm = √2·Vsec (cada metade, na derivação central). |
| 3 | DM-RET1 tem o ajuste **Potência da carga** (W). A resistência da carga é a que absorve essa potência ativa, resolvida no modelo periódico exato (sem filtro: R = Vo,ef²/P). Com filtro C ou π, C e R são iterados até o capacitor comercial e a potência ficarem estáveis. |
| 4 | Rótulos: "Tensão do primário (eficaz)", "Tensão do secundário (eficaz)"; no DM-RET3, "Tensão de linha do primário (eficaz)". |
| 5 | A "Tensão média desejada" e a "Corrente na carga" saíram do DM-RET1; a tensão média passa a ser resultado. |
| 6 | Aba Resultados: tabelas medidas no **ngspice** (último período em regime): pico, médio, eficaz, mínimo e máximo de cada tensão e corrente; por ponto de potência: V ef, I ef, S (VA), P (W), Q (var), D (VA), FP e cos φ₁. O cálculo analítico continua abaixo. A simulação roda sozinha a cada mudança. |
| 7 | Em cada forma de onda: linha tracejada laranja = médio, pontilhada verde = eficaz, ponto rosa = pico (valores na legenda). Caixa para desligar as marcas e caixas para escolher quais ondas mostrar. |
| 8 | Retificadores (RET1, RETC1, RET3): tensão e corrente no primário (transformador ideal), no secundário, na carga e nos dispositivos (tensão anodo-catodo, corrente, tensão de porta). Em qualquer circuito, clicando no esquemático: tensão no nó, tensão nos terminais, tensão diferencial entre dois nós, corrente (por terminal, em transistores) e potência. |
| 9 | Clicando em um componente: editar o valor (R, C, L) ou a descrição da fonte; trocar o modelo (peça do catálogo) dos dispositivos. Valores editados valem só para a simulação; o aviso diz que o cálculo analítico descreve o projeto original, e a comparação mostra a divergência (regra 4: não é escondida). |

## Definições das potências

Q é a potência reativa da fundamental e D a de distorção (decomposição de Budeanu), com
S² = P² + Q² + D². IEEE Std 1459-2010, seções 3.1 e 3.2 (a norma recomenda N = √(S² − P²) =
√(Q² + D²)). Corrente medida com a convenção do receptor (P > 0 = potência absorvida). No
primário, a componente contínua da corrente do secundário (meia onda) é retirada, como num
transformador real.

## Testes

- `tests/unit/design/test_measure.py`: senoides com defasagem (P, Q, S, FP exatos) e corrente com 3ª harmônica (D).
- `tests/unit/design/test_netlist_edit.py`: elementos, edição de valores, sondas (fonte de 0 V em série).
- `tests/unit/api/test_design_measurements.py` (ngspice): ponte com filtro C, 127 V / 12 V eficazes e 12 W; P no primário = P no secundário; S² = P² + Q² + D²; FP medido = FP analítico (2 %).
- Testes do DM-RET1 e AS-RET1 adaptados à nova especificação (P_out = P pedida; Vm = √2·Vsec).
- Front-end: `circuitMatch.test.ts`, `markers.test.ts`.

## Limitações

- Itens 2, 3 e 5 só no DM-RET1. RETC1 e RET3 ainda partem da tensão média desejada em α nominal (podem receber o mesmo tratamento).
- Os rótulos do desenho só ficam clicáveis quando o texto é o nome do componente (D1, C1, R…); os demais componentes estão na lista de botões abaixo do desenho. Nós não aparecem no desenho: a tensão diferencial usa a lista de nós.
- Primário dos retificadores: transformador ideal (sem magnetização nem dispersão).
- Projetos salvos com a especificação antiga do DM-RET1 abrem com os valores padrão de Vsec e P.
- O filtro π leva alguns segundos por cálculo (iteração entre C, L e R).

Capturas: `/mnt/project-files/capturas/analise-projetos/`.
