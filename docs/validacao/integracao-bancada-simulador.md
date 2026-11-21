# Validação da bancada e do simulador (2026-11-20 a 2026-11-21)

Os PRs #7 (simulador) e #9 (bancada de dispositivos) partiram da mesma versão da `main`.
A combinação tinha conflitos na netlist e no roadmap. A resolução preserva os sensores
digitais, os indicadores de LED/lâmpada e os limites de esforço dos componentes, com suas
respectivas seções de documentação.

O teste `tests/unit/schematic/test_device_integration.py` monta um DHT22, um LED e um
resistor com potência nominal no mesmo circuito e verifica que a netlist mantém os três
tipos de metadados. Esse teste passou no Windows.

O PR #8, de análise de projetos, foi validado separadamente: 267 testes de backend, 55 testes
de interface, ESLint e compilação passaram. Não houve conflito textual entre ele e cada
uma das outras branches.

A interface com os três PRs combinados passou nos 67 testes, no ESLint e na compilação
TypeScript/Vite. Na combinação de #7 e #9, Ruff passou em `src` e `tests`, e mypy passou
nos dois módulos envolvidos na resolução e na correção numérica. O Chrome completou o E2E
do simulador e os ensaios de LM35, DHT22 e driver de passo pela interface.

## Resultado da suíte completa

A execução padrão do backend (`pytest -m "not datasheet" tests`) terminou com 1.085 testes
aprovados, um ignorado e uma falha de infraestrutura do Hypothesis: geração de dados lenta
em `test_calibration_round_trip`, sem falha de asserção numérica. O teste passou isoladamente
em 1,20 s com a mesma semente (`338884497815064701479565931160493107583`), sem alterar suas
configurações ou tolerâncias. A execução completa durou 18 min 15 s. Os 11.033 casos marcados
como `datasheet`, que exigem acesso às fontes externas, ficaram fora desta execução.

Os 13 testes da API de medições e de edição/medição de netlists passaram também com os três
PRs combinados. O teste de regressão de sensores/indicadores/limites e os quatro ensaios da
bancada de passo passaram. A verificação de lentidão do Hypothesis é sensível à carga do
computador; não foi desabilitada para obter a aprovação.

## Execução

As verificações usaram cópias isoladas, ngspice 47 e Chrome. O checkout principal e os dados
do usuário não foram usados como ambiente de teste. Durante a revisão, os PRs #7, #8 e #9
foram integrados pelo responsável. A correção Gear e o teste de regressão foram reaplicados
separadamente sobre a `main` atual, sem reenviar as antigas resoluções de merge.
