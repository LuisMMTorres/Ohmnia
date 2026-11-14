# Validação: catálogo de diodos e bancada BD-DIODO (Fase 2, 1ª entrega)

Data: 2026-11-14. Status: aguardando revisão do usuário.

## O que foi entregue

- Banco de componentes em SQLite com importação dos YAML de `data/components`, busca por
  texto, categoria, status de revisão e filtros por parâmetro (ex.: `VRRM>=600 V; trr<=100 ns`).
- Fluxo de revisão: cada valor entra como **extraído**; o revisor marca **confere** ou
  **não confere** vendo a página citada do datasheet ao lado; o componente só é **liberado**
  (e só então entra em seleção automática) quando todos os parâmetros obrigatórios da categoria
  estão conferidos e o revisor se identifica.
- Datasheets guardados por SHA-256 na pasta de dados local, baixados do site do fabricante
  na primeira consulta, com verificação do hash. Nenhum PDF fica no repositório.
- Bancada BD-DIODO: curva I×V em várias temperaturas, escala log, memória de cálculo e
  comparação com os pontos de VF máximo do datasheet.

## Componentes transcritos (28 partes, 421 valores)

| Arquivo | Categoria | Partes | Datasheet | Valores |
|---|---|---|---|---|
| `vishay-1n4001-1n4007.yaml` | Retificador | 1N4001 a 1N4007 | Vishay 88503, 29-Apr-2020 | 126 |
| `vishay-1n5400-1n5408.yaml` | Retificador | 1N5400 a 1N5408 | Vishay 88516, 19-Dec-2025 | 117 |
| `vishay-uf4001-uf4007.yaml` | Rápido | UF4001 a UF4007 | Vishay 88755, 06-Apr-2020 | 98 |
| `onsemi-mur460.yaml` | Rápido | MUR460 | onsemi MUR420/D, Rev. 17 | 16 |
| `vishay-1n5817-1n5819.yaml` | Schottky | 1N5817, 1N5818, 1N5819 | Vishay 88525, 01-Jul-2020 | 45 |
| `vishay-1n4148.yaml` | Sinal | 1N4148 | Vishay 81857, Rev. 1.6 | 19 |

## Como foi verificado

1. **Transcrição:** tabelas lidas do texto do PDF; tabelas com células mescladas (valores que
   valem para várias colunas, como VF e trr da UF400x) conferidas na imagem renderizada da página.
2. **Teste automático DS (`pytest -m datasheet`):** baixa cada PDF, confere o hash e procura
   cada valor na página citada. Resultado: todos os 421 valores encontrados.
3. **Rastreabilidade:** teste unitário garante que todo valor do catálogo tem documento,
   revisão e página.
4. **AS-DIODO-01:** a curva do modelo da bancada coincide com o ngspice (`.dc` em 27 °C e
   100 °C) dentro de 0,1 %.

Resultado da suíte completa (`scripts/check.sh`): 563 testes Python e 9 de interface
passando, cobertura 95 %, lint, tipos e contratos de importação sem erros.

## O que o teste automático não garante

Que o número esteja na **coluna certa** e com a **condição certa**. É isso que a revisão humana
confere. Pontos para atenção:

- MUR460: o datasheet não diz a duração do pulso de IFSM; registrei 8,3 ms (meia senoide em
  60 Hz) como inferência, com nota no parâmetro. Confirmar ou marcar "não confere".
- UF4001–UF4004 têm VF 1,0 V e trr 50 ns; UF4005–UF4007 têm 1,7 V e 75 ns (células mescladas).
- 1N5817–1N5819: Tj máx. 125 °C.

## Pedido de revisão (decisão D7)

Na tela **Componentes**, revisar por amostragem um componente de cada arquivo (sugestão:
1N4007, 1N5408, UF4007, MUR460, 1N5819, 1N4148): conferir cada linha com a página mostrada
e liberar. Os demais ficam como estão até sua revisão.

## Limitações conhecidas

- A bancada usa um modelo didático ajustável, não ajustado ao componente; o ajuste ao datasheet
  vem com a digitalização de curvas (Fase 8).
- Revisões ficam no banco local; para guardá-las no repositório, use "Baixar YAML revisado".
- Alguns sites de fabricante bloquearam o download automático (Nexperia, ST); esses catálogos
  ficam para quando houver outra via de acesso aos PDFs.

## Como executar

```bash
cd frontend && npm ci && npm run build && cd ..
cd backend && uv sync && uv run python -m circuitos
```

Abrir as abas **Componentes** e **Bancada de dispositivos**.
