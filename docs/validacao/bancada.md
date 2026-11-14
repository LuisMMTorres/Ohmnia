# Validação: bancada de dispositivos (Fase 2)

Data: 2026-11-14. Status: aguardando aprovação da Fase 2.

A bancada (aba **Bancada de dispositivos**) tem seis telas. Cada uma usa um modelo didático
explícito, mostra a memória de cálculo com fórmula, entradas, premissas e referência, e exporta o
modelo SPICE equivalente. O mesmo modelo é conferido no ngspice por um teste AS. As telas com
componente do catálogo trazem o botão **Ajustar ao datasheet**, que transforma valores do
datasheet em parâmetros do modelo e registra o passo na memória de cálculo.

| Tela | Modelo | O que mostra | Ajuste ao datasheet | Teste analítico × ngspice |
|---|---|---|---|---|
| `BD-PN` Junção PN | Junção abrupta de silício | ni(T), V0, largura da depleção (W, xn, xp), campo máximo, Cj(VR), IS e corrente de Shockley | (física; não usa catálogo) | `AS-PN-01`: Cj em 0, 1, 5 e 20 V, AC de pequeno sinal, 0,1 % |
| `BD-DIODO` Diodo de junção | Shockley + Rs + lei de temperatura do SPICE | I × V em várias temperaturas, escala log | pontos de VF máx. do datasheet sobrepostos | `AS-DIODO-01`: 27 °C e 100 °C, 0,1 % |
| `BD-ZENER` Diodo Zener | VZ0(T) + diodo de joelho + Rz | curva reversa, VZ e rz no ponto de operação | VZ0 e Rz a partir de VZ e ZZT em IZT | `AS-ZENER-01`: 27 °C e 100 °C |
| `BD-TBJ` TBJ | Gummel-Poon reduzido (IS, BF, BR, VAF) | IC × VCE com IB constante, β e ro | BF a partir do hFE | `AS-TBJ-01`: IB = 10 e 30 µA, 0,1 % |
| `BD-FET` MOSFET | quadrático (SPICE nível 1) | ID × VDS para vários VGS | VT de VGS(th), KP de RDS(on) | `AS-FET-01`: VGS = 4, 5 e 6 V, 0,1 % |
| `BD-TIR` SCR e TRIAC | chave com disparo por quadrante (IGT), travamento (IL), manutenção (IH) e reta de condução VT0 + rT·i | formas de onda com carga resistiva e pulso em α; tensão média, eficaz e ângulo de condução | IGT (por quadrante), IH, rT a partir de VTM | `AS-TIR-01` e `AS-TIR-02`: 9 casos |

## BD-TIR em detalhe

Circuito: fonte senoidal, carga resistiva, pulsos de porta de amplitude IG e largura tw em α (e
em α + π no TRIAC). Regras do modelo:

- dispara se a corrente de porta alcança o IGT do quadrante com o dispositivo polarizado
  diretamente;
- trava se a corrente na carga chega a IL enquanto há pulso; senão, desliga ao fim do pulso;
- bloqueia quando a corrente cai abaixo de IH (comutação natural).

No ngspice as mesmas regras viram um subcircuito comportamental (fontes B com estados filtrados
por RC de 1 µs). Os testes comparam os instantes de liga e desliga (tolerância 20 µs, 0,43° em
60 Hz) e as tensões média e eficaz na carga (0,5 % do pico) em:

- SCR com α = 30°, 60°, 90° e 135°;
- SCR com IG abaixo de IGT (não dispara);
- SCR com IL inalcançável (conduz só durante o pulso);
- TRIAC com pulsos positivos (Q1 e Q4), negativos (Q2 e Q3) e acompanhando MT2 (Q1 e Q3), com o
  IGT de Q4 acima de IG para mostrar o semiciclo que não dispara.

A memória de cálculo traz a margem de disparo IG/IGT, a maior corrente durante o pulso
(comparada a IL), o ângulo de bloqueio θoff = π − arcsin[(VT0 + IH·(R + rT))/Vm] e as expressões do
tiristor ideal: Vmed = Vm/(2π)·(1 + cos α) e Vef do retificador de meia onda; Vef do controlador
CA para o TRIAC. Com VT0, IH e IL tendendo a zero, o modelo reproduz essas expressões
(teste unitário, 0,2 %).

## BD-PN em detalhe

Material padrão: silício com B = 7,3·10¹⁵ cm⁻³·K⁻³ᐟ², Eg = 1,12 eV e εr = 11,7 (Sedra & Smith),
editáveis na tela. Testes:

- `GT-PN-02`: ni(300 K) = 1,5·10¹⁰ cm⁻³ (valor do livro), tolerância 2 %;
- `PT-PN-MONOT` (propriedade, Hypothesis): W cresce e Cj cai com VR para dopagens de 10¹⁴ a
  10¹⁹ cm⁻³;
- testes unitários com cálculo independente de V0, W, xn, xp, Emax, Cj e IS.

`GT-PN-01` (largura da depleção em exemplo resolvido do livro) espera a escolha do exemplo
(decisão D6).

## Escala dos gráficos

As escalas acompanham as curvas do modelo. Um ponto do datasheet que cairia fora da faixa (muito
acima das curvas ou além da tensão máxima do eixo) é listado abaixo do gráfico com tensão e
corrente, em vez de achatar as curvas.

## Limitações conhecidas

- Os modelos são didáticos: explicam o comportamento e as grandezas do datasheet, mas não
  substituem o modelo SPICE do fabricante.
- BD-TIR: só carga resistiva; carga RL, snubber e circuito de disparo RC-DIAC entram com os
  módulos de comando (`DM-CMD`).
- BD-PN: junção abrupta, depleção total, baixa injeção; B e Eg constantes com a temperatura.
- Referências bibliográficas registradas com livro e capítulo; equação e página ainda não foram
  conferidas no livro impresso (campo `verified = false`).
- Sobreposição de curvas digitalizadas do datasheet: a bancada já sobrepõe os pontos tabelados.
  A digitalização de figuras faz parte do módulo de extração de datasheets (`SV-PDF`, Fase 8).
