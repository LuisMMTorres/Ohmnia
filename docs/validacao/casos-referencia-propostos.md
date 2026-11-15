# Casos de referência propostos (D6)

Data: 2026-11-14. Status: **aguardando conferência do usuário.**

São sete exercícios no formato dos livros-texto (rede de 120 V / 60 Hz no monofásico, 480 V /
60 Hz no trifásico). Os valores esperados vêm da solução fechada da teoria (Hart, *Power
Electronics*, 1ª ed., cap. 3 e 4; Mohan, Undeland e Robbins, *Power Electronics*, 3ª ed., cap. 5
e 6), calculada à parte do código dos módulos. **Não foram copiados de exemplos numerados**: não
tenho os livros aqui e não quero atribuir um número de exemplo sem conferir.

Já estão no teste `backend/tests/golden/test_gt_ret_propostos.py` (tolerância de 0,1 %). Todos
passam hoje. O módulo concorda com a fórmula fechada em menos de 0,02 % em todos os casos.

**O que peço:** confira os números de cada linha, ou indique o exemplo equivalente do livro que
usa em aula (livro, edição, número, página). Com a sua indicação, troco o enunciado pelo do livro
e registro a fonte no teste.

| Caso | Enunciado | Grandeza | Esperado |
|---|---|---|---|
| P1 | Meia onda, carga resistiva: 120 V, 60 Hz, R = 10 Ω | Vo | 54,0 V |
| | | Io | 5,40 A |
| | | I eficaz | 8,49 A |
| | | P na carga | 720 W |
| | | FP | 0,707 |
| P2 | Ponte com filtro capacitivo: 120 V, 60 Hz, R = 500 Ω, C = 100 µF, diodos ideais | θoff | 93,0° |
| | | θon | 60,6° |
| | | ΔVo exata | 21,9 V |
| | | ΔVo pela aproximação Vm/(2fRC) | 28,3 V (superestima em ~30 %) |
| P3 | Meia onda controlada, carga R-L: 120 V, R = 20 Ω, L = 40 mH, α = 45° | β (extinção) | 216,9° |
| | | Vo | 40,7 V |
| P4 | Ponte totalmente controlada, R-L com L ≫: 120 V, R = 10 Ω, α = 30° | Vo | 93,6 V |
| | | Io | 9,36 A |
| P5 | Ponte semicontrolada, R-L: 120 V, α = 60° | Vo | 81,0 V |
| P6 | Ponte trifásica a diodos, Io constante: 480 V de linha, Io = 6,48 A | Vo | 648 V |
| | | I de linha eficaz | 5,29 A |
| | | FP | 0,955 (3/π) |
| P7 | Ponte trifásica controlada com Ls: 480 V, α = 30°, Io = 50 A, Ls = 1 mH | μ | 5,86° |
| | | ΔVμ = 3ωLsIo/π | 18,0 V |
| | | Vo | 543 V |

Sugestão para completar com livros que costumam ter exemplos parecidos (confira o número na sua
edição): Hart, cap. 3, retificadores de meia onda (P1, P3) e filtro capacitivo (P2); Hart, cap. 4,
ponte controlada e trifásica (P4, P6); Mohan, cap. 6, efeito de Ls (P7); Rashid, capítulo de
retificadores controlados, ponte semicontrolada (P5); Barbi, *Eletrônica de Potência*, para os
mesmos casos em português.

## Fase 4: casos P8–P15 (`tests/golden/test_gt_fase4.py`)

VBE = 0,7 V e VF = 0,7 V; o modelo exponencial do transistor recebe IS tal que VBE = 0,7 V na
corrente da fórmula fechada, então o resolvedor tem de reproduzir o número de livro.

| Caso | Circuito | Grandeza | Valor |
|---|---|---|---|
| P8 | Polarização fixa: VCC = 12 V, RB = 240 kΩ, RC = 2,2 kΩ, β = 50 | IB / IC / VCE | 47,08 µA / 2,354 mA / 6,82 V |
| P9 | Divisor (exata): VCC = 22 V, R1 = 39 kΩ, R2 = 3,9 kΩ, RC = 10 kΩ, RE = 1,5 kΩ, β = 100 | IC / VCE | 0,838 mA / 12,35 V |
| P10 | Realimentação de coletor: VCC = 10 V, RF = 250 kΩ, RC = 4,7 kΩ, RE = 1,2 kΩ, β = 90 | IC / VCE | 1,064 mA / 3,66 V |
| P11 | E-MOSFET com divisor: VG = 4 V, RS = 1 kΩ, RD = 2 kΩ, VDD = 16 V, VT = 2 V, k = 0,3 mA/V² | ID | 0,594 mA |
| P12 | EC com RE desviado: gm = 40 mS, rπ = 2,5 kΩ, RB = 10 kΩ, RC = 4,7 kΩ, RL = 10 kΩ, Rs = 600 Ω, Cin = 1 µF | Avs / fL | −gm(RC∥RL)·Ri/(Rs+Ri) / 61,2 Hz |
| P13 | Ceifadores: Vm = 10 V, VB = 3 V, R = 1 kΩ, RL = 100 kΩ | paralelo / série / duplo | 3,7 V e −9,90 V / 6,3 V / ±3,7 V |
| P14 | Grampeador positivo: Vm = 10 V, VB = 3 V, C = 10 µF, RL = 100 kΩ, 1 kHz | VC / mín. / máx. | 12,3 V / 2,3 V / ≈ 22,29 V |
| P15 | Cockcroft-Walton, 3 estágios: Vm = 100 V, 60 Hz, RL = 1 MΩ | Vo sem carga / ΔV | 595,8 V / 22·Io/(fC) |

Exemplos parecidos no Boylestad & Nashelsky, 11ª ed. (confira o número na sua edição): cap. 4 para
P8–P10, cap. 7 para P11, cap. 5 e 9 para P12, cap. 2 para P13–P14 e multiplicadores.

## Fase 4, acréscimo: casos P16–P19 (`tests/golden/test_gt_fase4b.py`)

| Caso | Circuito | Grandeza | Valor |
|---|---|---|---|
| P16 | JFET, autopolarização: IDSS = 8 mA, VP = 4 V, RS = 1 kΩ, RD = 3,3 kΩ, VDD = 20 V | ID / VGS / VDS | 2 mA / −2 V / 11,4 V |
| P17 | JFET com divisor: VDD = 16 V, R1 = 2,1 MΩ, R2 = 270 kΩ, RD = 2,4 kΩ, RS = 1,5 kΩ, IDSS = 8 mA, VP = 4 V | VG / VGS / ID | 1,823 V / ≈ −1,80 V / ≈ 2,42 mA |
| P18 | Darlington com β1 = β2 = 30 | βD = β1β2 + β1 + β2 | 960 |
| P19 | Classe D, ±24 V, RL = 8 Ω, fc = 25 kHz (Butterworth) | L / C / fundamental na carga | 72,03 µH / 0,5627 µF / m·V·\|H(jω)\| |

Exemplos parecidos no Boylestad & Nashelsky, 11ª ed.: cap. 7 (polarização de FET) para P16–P17 e
cap. 12 (amplificadores de potência) para P18–P19. Confira o número na sua edição.


## Fase 5: casos P20–P32 (`tests/golden/test_gt_fase5.py`)

Os casos de módulo rodam o projeto (sem simulação) com o catálogo revisado e conferem que o resumo
obedece à fórmula fechada com os valores comerciais escolhidos. Tolerância 1e-9 relativa nas
fórmulas fechadas; 1e-4 nos elementos tabelados da escada LC (quatro casas); 1e-3 nos tempos do 555
(limiares do datasheet).

| Caso | Circuito | Grandeza | Valor |
|---|---|---|---|
| P20 | Inversor, \|Av\| = 10, R1 = 10 kΩ | R2 / Av / Rp | 100 kΩ / −R2/R1 = −10 / R1∥R2 ≈ 9,09 kΩ |
| P21 | Não inversor, Av = 10, R1 = 10 kΩ | R2 (E96) / Av | 90,9 kΩ / 1 + R2/R1 = 10,09 |
| P22 | Inversor com A0 finito | Av | −(R2/R1)/(1 + (1 + R2/R1)/A0) |
| P23 | Butterworth PB, fp = 1 kHz (−3 dB), 30 dB em 3 kHz | n / Q das seções / atenuação em fs | 4 / 0,5412 e 1,3066 / 38,17 dB |
| P24 | Chebyshev 1 dB, ωs/ωp = 3, 30 dB | n / atenuação em ωs | 3 / 10 log(1 + ε²·99²) = 34,05 dB |
| P25 | Escada LC duplamente terminada | g (Butterworth n = 3; Chebyshev 0,5 dB n = 3) | 1, 2, 1; 1,5963, 1,0967, 1,5963 |
| P26 | Ponte de Wien, 1 kHz, C = 10 nF | R (E96) / f0 / ganho mínimo | 15,8 kΩ / 1/(2πRC) = 1 007 Hz / 3 |
| P27 | Deslocamento de fase (3 RC), 1 kHz, C = 10 nF | R (E96) / f0 / ganho mínimo | 6,49 kΩ / 1/(2π√6·RC) = 1 001 Hz / 29 |
| P28 | 555 astável, 1 kHz, D = 60 %, C = 10 nF | tH / tL | ln2·(RA + RB)C / ln2·RB·C |
| P29 | Multivibrador com TBJ, VCC = 5 V, VBE = 0,65 V, VCE(sat) = 0,1 V | T | 2·RB·C·ln(9,25/4,35) = 2·RB·C·0,7544 |
| P30 | Schmitt inversor centrado em 0, histerese de 1 V, Vsat = 13,5 V | β / VT± | R2/(R1 + R2) = 0,0369 / ±0,498 V |
| P31 | Retificador de precisão de onda completa, Vm = 5 V, G = 1 | Vo,méd | 2·Vm·G/π ≈ 3,18 V (com os comerciais: Vm(G+ + G−)/π) |
| P32 | Amplificador logarítmico com transdiodo, Vin = 1 V, R = 10 kΩ | Iin / inclinação | 100 µA / −VT ln 10 = −59,5 mV por década |

Exemplos parecidos (confira o número na sua edição): Boylestad & Nashelsky, 11ª ed., cap. 10
(aplicações de ampops) para P20–P22 e P30–P32 e cap. 14 (osciladores) para P26–P29; Sedra & Smith,
7ª ed., cap. 2 e 18; Williams & Taylor, 4ª ed., cap. 2, para P23–P24; Matthaei, Young & Jones
(1964), cap. 4, para P25.


## Fase 6: casos P33–P49 (`tests/golden/test_gt_fase6.py`)

Os conversores, inversores e gradadores rodam a análise com dispositivos ideais e conferem a fórmula
fechada; os casos de comando e proteção usam o catálogo revisado, e os valores do datasheet entram na
fórmula. Tolerância 1e-9 relativa nas fórmulas fechadas; 1e-6 nas raízes numéricas (β); 1e-3 na
fundamental do PWM sintetizado; 2e-3 na série de Fourier lida pela FFT.

| Caso | Circuito | Grandeza | Valor |
|---|---|---|---|
| P33 | Buck MCC, 24 → 12 V, 2 A, 50 kHz, ΔiL = 30 %, ΔVo = 1 % | D / L / C / ΔVo | 0,5 / 200 µH / 12,5 µF → 15 µF (E12) / 0,1 V |
| P34 | Boost MCC, 12 → 24 V, 1 A | D / IL / L / ΔVo | 0,5 / 2 A / 200 µH / Io·D/(fs C) |
| P35 | Buck-boost MCC, 12 → \|24\| V, 1 A | D / IL / L | 2/3 / 3 A / 177,8 µH |
| P36 | Buck MCD, L = 0,5·L_crit | L_crit / D / i_pk | (1 − M)R/(2fs) = 30 µH / 1/√8 = 0,3536 / (Vin − Vo)D/(L fs) |
| P37 | Flyback 48 → 12 V, D = 0,4 | Ns/Np / I_m,pk | 0,375 / I_m(1 + ΔI/2), I_m = Io n/(1 − D) |
| P38 | Forward 48 → 12 V, D = 0,4 | Ns/Np / L_o | 0,625 / 240 µH |
| P39 | Onda quadrada monofásica, Vdc = 400 V | V1 / V_rms / THD | 360,1 V / 400 V / 48,34 % |
| P40 | SPWM bipolar, ma = 0,8, mf = 21 | V1 | ma·Vdc/√2 = 226,3 V |
| P41 | SPWM unipolar, ma = 0,8, mf = 21 | V1 / harmônico em mf | 226,3 V / cancelado (primeiros em 2mf ± 1) |
| P42 | Onda quase quadrada, α = 30° (GT-HARM-01) | V_n | 4Vdc/(nπ)·cos(nα); V3 = 0 |
| P43 | Filtro LC de saída (GT-INV-FLT-01) | fc / Cf | 1/(2π√(Lf Cf)) / E12 mais próximo de 1/((2π·0,2·fs)² Lf) |
| P44 | Gradador, carga R, 220 V, α = 90° | Vo / FP | 220/√2 = 155,6 V / 0,707 |
| P45 | Gradador, R = 50 Ω, L = 100 mH, α = 90° | θ / β / Vo | 37,0° / raiz de sen(β − θ) = sen(α − θ)e^{(α − β)/ωτ} / Vs√{[(β − α) − (sen 2β − sen 2α)/2]/π} |
| P46 | Rede RC + DIAC, 100 kΩ, 100 nF, V_BO = 32 V (GT-CMD-01) | k / α | 0,0663 / 98,8° |
| P47 | Snubber RCD, 311 V, 10 A (GT-CMD-SNUB-01) | C_s / E / P_R | I_o t_f/(2V_s) / I_o² t_f²/(24C_s) + V_F I_o t_f/2 / ½C_s V² f_s |
| P48 | Fusível × ponte (GT-CMD-I2T-01) | aviso | sem aviso com 20 A²s; aviso com 10⁴ A²s |
| P49 | Bootstrap do IR2110 (GT-CMD-BOOT-01) | C_min | 2[2Q_g + I_QBS/f + Q_ls]/(V_CC − V_F − V_LS − V_Min) |

Exemplos parecidos (confira o número na sua edição): Hart, 1ª ed., cap. 6 (buck, boost, buck-boost,
MCD) para P33–P36, cap. 7 para P37–P38, cap. 8 para P39–P43, cap. 5 para P44–P46 e cap. 10 para P47;
Erickson & Maksimović, 2ª ed., cap. 5, para P36; Infineon/IR AN-978 para P49.
