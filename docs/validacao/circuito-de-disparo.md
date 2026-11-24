# Circuito de disparo dos retificadores controlados (DM-RETC1)

Pedido de 2026-11-23: incluir, nos retificadores controlados, o circuito que de fato dispara os
tiristores no ângulo escolhido, com opção de mostrar ou não, para gerar o guia de laboratório.

## O que mudou

- Nova opção **"Incluir circuito de disparo (para o guia de laboratório)"** no formulário do
  retificador controlado (desligada por padrão: com ela desligada nada muda nos resultados
  anteriores). Ao ligar, aparecem a alimentação V_CC (padrão 12 V) e a tensão do trafo de
  sincronismo (padrão 12 V eficaz).
- O circuito é **dimensionado**, entra na **memória de cálculo**, no **esquemático** (painel abaixo
  do circuito de potência), na **lista de materiais**, nas **medições do guia** e ganha um
  **procedimento de prática** no relatório.
- A **simulação** troca os pulsos ideais de porta pelo circuito completo; o tiristor passa a
  disparar pela corrente de porta (I_GT), não por uma tensão referida ao terra.

## Circuito escolhido

Rampa sincronizada com a rede + comparador + optoacopladores com saída TRIAC, só com peças do
catálogo (o TCA785, comum em laboratório, não tem datasheet acessível pela rede do ambiente, então
não entrou: regra 1).

1. **Sincronismo:** trafo TS1 (V_sync) → ponte DS1–DS4 (1N4148) → divisor R1/R2.
2. **Detector de zero:** U1A (LM393) compara v_z com V_th (R3/R4). Perto de cada cruzamento por
   zero a saída de coletor aberto descarrega C1 por R_d.
3. **Rampa:** C1 carrega por R5 a partir de V_CC (rampa exponencial).
4. **Ângulo:** U1B compara a rampa com V_c (cursor de RV1). A partir de α a saída solta, Q1
   (BC337/BC548) satura por R7 e acende os LEDs dos MOC3021, em série com R_LED.
5. **Porta:** cada MOC3021 dispara o seu tiristor a partir do próprio anodo: anodo → fototriac →
   DG (1N400x, bloqueia corrente reversa) → R_G → porta, R_GK = 1 kΩ entre porta e catodo. Só o
   tiristor polarizado diretamente recebe corrente, então o mesmo pulso nos dois semiciclos se
   "endereça" sozinho (T1/T2 no positivo, T3/T4 no negativo). Quando o tiristor trava, a tensão no
   anodo cai e o fototriac desliga.

Fórmula do ângulo (mesma no cálculo e na simulação):

α = θ_r + ωR5C1·ln[(V_CC − V_0)/(V_CC − V_c)]

## Dimensionamento e fontes

| Grandeza | Regra | Fonte |
|---|---|---|
| R_LED | (V_CC − n·V_F,max − V_CE,sat)/(1,2·I_FT) | MOC3023M/D rev. 3, fig. 7 |
| R_G | V_m,max / min(I_TSM, I_GM, P_GM/V_GT) | MOC3023M/D fig. 7; datasheet do SCR |
| α mínimo de porta | V_m,min·sen α − E = V_TM + V_F + V_GT + R_G(I_GT + V_GT/R_GK) | I_GT e V_GT máximos do SCR |
| R_d e R7 | corrente drenada pelo LM393 ≤ I_OL do ensaio de V_OL (4 mA) | datasheet do LM393 |
| C1 | maior E6 com 5(R_d + R_on)C1 ≤ janela de reinício | — |
| R5 | rampa chega a ~75 % de V_CC no fim do semiciclo | — |

Escolhas do projeto (aparecem como premissas): R2 = 10 kΩ, R3 = 100 kΩ, limiar 0,2 V,
R_GK = 1 kΩ, RV1 = 10 kΩ, sobreacionamento de base 5×.

## Dados novos no catálogo (precisam da sua revisão)

`data/components/optocoupler/onsemi-moc3021.yaml` ganhou I_FT (15 mA), I_TSM (1 A) e V_TM
(1,8 típ., 3,0 V máx.), do mesmo documento onsemi MOC3023M/D rev. 3 (jun. 2023), p. 3–4. O
esquema `optocoupler` passou a prever esses três parâmetros.

**Atenção:** no texto extraído do PDF a largura do pulso de I_TSM aparece como "PW = 100 ms";
o símbolo µ dessa fonte sai como "m" (o mesmo acontece em I_R, "100 mA"). Cadastrei 100 µs com
nota; confira no PDF.

O PDF baixado hoje tem SHA-256 diferente do registrado (a onsemi muda os bytes sem mudar a
revisão, como já aconteceu); não troquei o hash.

## Verificação (regra 4)

AS-RET-03 (`tests/analytic_vs_sim/test_as_retc1_firing.py`): ponte contínua e descontínua,
semicontrolada, meia onda RL e com roda livre. Em todos, o ângulo produzido pelo circuito
simulado bate com o calculado (erro ≤ 0,06 %); pico da rampa e corrente nos LEDs ≤ 0,02 %; e as
grandezas da carga e da entrada (que agora dependem do disparo real) ficam dentro das tolerâncias
de AS-RET-02 (pior 0,11 %).

Testes unitários: `tests/unit/design/test_retc1_firing.py`.

## Limitações conhecidas

- Sem o MOC3021, o LM393 ou o transistor liberados no catálogo, o circuito não é dimensionado
  (aviso) e a simulação continua com os pulsos ideais.
- Pulso longo (de α até o fim do semiciclo): com carga RLE descontínua e α pequeno, se o tiristor
  ainda não estiver polarizado em α ele dispara quando ficar; o cálculo da potência continua
  supondo pulso curto. Com E grande e (V_o − E) pequeno, I_o fica muito sensível a pequenas
  diferenças de V_o.
- Atrasos do fototriac e do comparador e a corrente de polarização do LM393 foram desprezados
  (não há valores no catálogo).
- O trafo de sincronismo é suposto em fase com o secundário de potência: confira a polaridade na
  montagem.
- Faixa de α limitada pela janela do detector de zero (cerca de 9° a 171° com 12 V de
  sincronismo); aviso quando α ou a faixa da rede saem dela.
