# Validação: Zener, pontes retificadoras e bancada BD-ZENER (Fase 2, 2ª entrega)

Data: 2026-11-14. Status: aguardando revisão do usuário.

## O que foi entregue

- Categorias novas: `diode.zener` e `bridge.single_phase` (herda os parâmetros do retificador
  e acrescenta VISO e Rth com mais de um diodo conduzindo).
- 107 componentes, 1 560 valores, todos transcritos das tabelas dos datasheets oficiais.
- Bancada BD-ZENER: curva reversa I×V em várias temperaturas, VZ e resistência dinâmica no
  ponto de operação, e **ajuste ao datasheet** (calibra VZ0 e Rz pelo ponto de teste VZ, ZZT em
  IZT), com memória de cálculo.
- Catálogo mostra colunas conforme a categoria (Zener: VZ, IZT, ZZT, IR, Ptot).

## Componentes

| Arquivo | Categoria | Partes | Datasheet | Valores |
|---|---|---|---|---|
| `zener/vishay-1n4728a-1n4761a.yaml` | Zener 1,3 W | 1N4728A a 1N4761A (34) | Vishay 85816, Rev. 2.7 | 476 |
| `zener/onsemi-1n5221b-1n5252b.yaml` | Zener 500 mW | 1N5221B a 1N5252B (31; o datasheet não traz o 1N5224B) | onsemi 1N5221B/D, Rev. 5 | 468 |
| `bridge/onsemi-df005s-df10s.yaml` | Ponte 1,5 A, SMD | DF005S a DF10S (7) | onsemi DF10S/D, Rev. 3 | 119 |
| `bridge/vishay-gbu4a-gbu4m.yaml` | Ponte 4 A, em linha | GBU4A a GBU4M (7) | Vishay 88614, 13-Jul-2020 | 105 |
| `bridge/vishay-gbpc12-gbpc35.yaml` | Ponte 12 a 35 A | GBPC12/15/25/35, 005 a 10 (28) | Vishay 88612, 30-Nov-2021 | 392 |

## Como foi verificado

1. As tabelas dos Zener foram lidas diretamente do texto do PDF por um script, linha a linha
   (sem redigitação), e os cabeçalhos conferidos na imagem da página.
2. O teste DS (`pytest -m datasheet`) encontrou cada um dos 1 560 valores na página citada.
   Passou a reconhecer separador de milhar ("1,200" Ω nas tabelas da onsemi).
3. AS-ZENER-01: o modelo da bancada coincide com o ngspice (subcircuito equivalente, varredura
   `.dc` a 27 °C e 100 °C): 0,1 % acima de 1 µA.
4. Suíte completa (`scripts/check.sh`): 2 139 testes Python e 9 de interface passando,
   cobertura 95 %.

## Pontos para sua atenção na revisão

- **1N5221B (onsemi):** a tabela não diz se ZZ, ZZK e IR são típicos ou máximos. Registrei como
  máximos, com nota. TC com "±" virou faixa (mín. −x, máx. +x).
- **1N4728A (Vishay):** a coluna de surto usa o símbolo IR; gravei como IZSM (10 ms) com nota. A
  tolerância de ± 5 % vem da lista de características da página 1.
- **GBPC:** a tabela não dá a temperatura de IF(AV); usei TC = 50 °C lido na fig. 1 (corrente
  nominal constante até 50 °C). A duração do surto IFSM não aparece na tabela, e a fig. 4 diz
  "0.5 ms Single Sine-Wave", o que parece erro do datasheet: esses 28 valores ficaram
  **a verificar** e bloqueiam a liberação até você decidir.
- **GBU4:** IFSM sem duração na tabela; 8,3 ms inferido da fig. 2 (1 ciclo de 60 Hz), com nota.
- **DF005S:** marcado como NRND (o datasheet o lista como DISCONTINUED).

Sugestão de amostra para revisar e liberar: 1N4742A (12 V), 1N5231B (5,1 V), DF04S, GBU4J e
GBPC3510.

## Bancada BD-ZENER: modelo

Fonte VZ0(T) = VZ0·[1 + TC·(T − 27 °C)] em série com um diodo (joelho exponencial, Is,r e nr) e
Rz; em paralelo, o diodo direto da bancada BD-DIODO. É o equivalente linear por partes do
Boylestad (VZ em série com rz), com o joelho arredondado. O ajuste ao datasheet escolhe Rz para
que rz(IZT) = ZZT e VZ0 para que VZ(IZT) = VZ nominal na temperatura do ensaio (TL = 30 °C nos
dois fabricantes). Quando o datasheet traz TC típico (onsemi), ele é usado; quando não traz
(Vishay), o TC do modelo é mantido e a tela avisa.

## Limitações

- Os Zener de 1,3 W da Vishay não informam TC; a deriva térmica desses modelos é a que você
  digitar.
- Pontes trifásicas ficam para a etapa de retificadores trifásicos (Fase 3).
