/** Example netlists. Component values are generic (no real part data). */
export const EXAMPLES: Record<string, string> = {
  "Filtro RC passa-baixas": `* Filtro RC passa-baixas, fc = 1/(2*pi*R*C) ≈ 159 Hz
V1 in 0 PULSE(0 1 0 1u 1u 5m 10m) AC 1
R1 in out 1k
C1 out 0 1u
.tran 2u 20m
.ac dec 50 1 100k
`,
  "Retificador em ponte (diodo genérico)": `* Ponte de Graetz com filtro capacitivo, modelo de diodo genérico (não é peça real)
.model DGEN D(IS=1n N=1.8 RS=0.05)
V1 a b SIN(0 17 60)
D1 a out DGEN
D2 b out DGEN
D3 0 a DGEN
D4 0 b DGEN
C1 out 0 2200u
RL out 0 100
* Referência CC para a fonte flutuante (sem ela, os nós a e b ficam
* indefinidos quando os quatro diodos cortam e a simulação não converge)
RB b 0 1meg
.tran 20u 100m 0 20u
`,
  "Divisor resistivo (.OP)": `* Divisor resistivo
V1 a 0 12
R1 a b 10k
R2 b 0 4.7k
.op
`,
};
