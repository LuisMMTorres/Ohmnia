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

## Retificadores controlado e trifásico (pedido "continue", 2026-11-20)

- **DM-RETC1**: entradas Vsec (eficaz), P da carga, L, E e α nominal. Vm = √2·Vsec; R é a
  resistência que absorve P em α nominal no modelo exato por trechos (busca de raiz). Saíram
  "Tensão média desejada" e "Resistência da carga" (R passa a resultado).
- **DM-RET3**: entradas Vsec (linha, eficaz; cada ponte no de 12 pulsos), P da carga e E.
  V_LL,m = √2·Vsec; como Vo = V₀ − kₓ·Io (forma fechada, Io constante), P = Vo·Io dá
  kₓ·Io² − V₀·Io + P = 0 e vale a raiz menor (abaixo da potência máxima V₀²/4kₓ). Saíram
  "Tensão média desejada" e "Corrente na carga".
- A faixa de α para a variação da rede passa a manter a tensão média calculada em α nominal.
- Potência acima do que o secundário entrega (por exemplo, meia onda controlada com carga RL,
  que tem máximo) gera mensagem pedindo para aumentar Vsec ou reduzir P.

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

- Os rótulos do desenho só ficam clicáveis quando o texto é o nome do componente (D1, C1, R…); os demais componentes estão na lista de botões abaixo do desenho. Nós não aparecem no desenho: a tensão diferencial usa a lista de nós.
- Primário dos retificadores: transformador ideal (sem magnetização nem dispersão).
- Projetos salvos com a especificação antiga do DM-RET1 abrem com os valores padrão de Vsec e P.
- O filtro π leva alguns segundos por cálculo (iteração entre C, L e R).

Capturas: `/mnt/project-files/capturas/analise-projetos/`.

## Carga dada por potência ou por corrente (2026-11-24)

Nos retificadores DM-RET1, DM-RETC1 e DM-RET3 o campo **Carga dada por** escolhe entre a potência da carga (W) e a corrente média na carga (A); o formulário mostra só o campo escolhido.

- DM-RET1 e DM-RETC1: R da carga por busca de raiz no mesmo modelo exato, com a condição (1/2π)∫i_o dθ = I_o no lugar de (1/2π)∫v_o·i_o dθ = P (a corrente média também cai quando R cresce). Sem filtro: R = V_o/I_o.
- DM-RET3: a corrente (contínua, L ≫) entra direto no cálculo; a potência sai de V_o·I_o.
- Teste `tests/unit/design/test_load_by_current.py`: projeta pela potência, passa a corrente média obtida e confere que R, I_o e P coincidem (todas as topologias e filtros).
- Conferência no ngspice (DM-RETC1, ponte, 70 V, α = 30°, L = 100 mH, I_o = 8 A pedida): corrente média simulada 7,998 A.

Também nesta mudança: tabelas de grandezas do ngspice com os dados centralizados em cada coluna; terminal de disparo dos tiristores e TRIACs chamado de "gate" (antes "porta").

Capturas: `/mnt/project-files/capturas/corrente-da-carga/`.
