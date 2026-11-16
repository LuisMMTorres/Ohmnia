# 5. Bancada de dispositivos

A aba **Bancada de dispositivos** traça as curvas de um dispositivo isolado, com os parâmetros do
catálogo ou digitados:

| Dispositivo | O que a bancada mostra |
|---|---|
| Junção PN | região de depleção, efeito de temperatura e dopagem, equação de Shockley |
| Diodo | I-V direta e reversa, efeito da temperatura, recuperação reversa |
| Zener | curva, regulação, coeficiente de temperatura |
| TBJ | curvas de entrada e saída, hFE × IC, reta de carga, SOA |
| JFET / MOSFET | transferência e saída, RDS(on) × Tj |
| IGBT | VCE(sat) × IC, energias de comutação |
| SCR / TRIAC / DIAC | curva característica, disparo e manutenção, quadrantes |
| Ampop | ensaios simulados de offset, polarização, GBW, slew rate, CMRR, PSRR, excursão |

As curvas são calculadas com as mesmas equações que o ngspice usa (a concordância é verificada nos
testes AS do projeto). Curvas digitalizadas do datasheet (aba Curvas da revisão) servem para
comparar o modelo com o fabricante.
