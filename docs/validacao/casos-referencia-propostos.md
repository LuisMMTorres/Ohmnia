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
