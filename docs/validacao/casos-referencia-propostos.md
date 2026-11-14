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
