# Revisão do PR #33 — protoboard (25/11/2026)

## Escopo

Revisão da branch `claude/project-thread-9b550z`, comparada à `main` em `e52e184`.
O PR melhora a ligação automática das peças, usa a segunda placa quando necessário e
acrescenta pinagens com indicação de fonte. Os dados com status `extraido` continuam sujeitos
à revisão humana; executar os testes não altera esse status no catálogo do usuário.

## Problemas encontrados e corrigidos

- A resolução aceitava pinagens com status `a_verificar`. Agora elas ficam sem associação
  elétrica automática e impedem a confirmação da montagem. O roteiro também deixa de indicar
  uma polaridade ou posições de ligação presumidas para essas peças.
- Retirar da montagem uma peça sem pinagem podia eliminar o aviso. A conferência agora
  considera também as peças do esquemático que não foram colocadas.
- O DM-ZEN usa duas cópias do circuito para avaliar os extremos de operação (`Za`/`Zb` e
  `Qa`/`Qb`). Essas referências perdiam a identidade da peça escolhida no catálogo e viravam
  peças genéricas. Agora mantêm a associação com `DZ1` e `Q1` da lista de materiais.
- Um teste de propriedades ainda comparava o formato antigo da pontuação de roteamento.
  A nova verificação calcula independentemente sobreposições, cruzamentos e quantidade de fios.

A polaridade da família 1N5221B não está indicada no documento
[onsemi 1N5221B/D, revisão 5](https://www.onsemi.com/pdf/datasheet/1n5221b-d.pdf),
consultado nesta revisão. O status pendente foi mantido; nenhuma pinagem foi presumida.

## Reprodução

Com o ambiente do README instalado, execute a partir de `backend`:

```powershell
python -m pytest tests/unit/api/test_design_breadboard.py `
  tests/unit/breadboard/test_unverified_pinout.py `
  tests/unit/components/test_pinout_import.py `
  tests/property/test_breadboard_properties.py
```

Na interface, abra **Análise de Projetos → Protoboard**:

1. DM-CHAVE: confira as três pernas do transistor e as ligações do circuito.
2. DM-OPA: confira a alimentação e as ligações do amplificador operacional.
3. DM-ZEN, com 1N5231B: as duas cópias do Zener devem manter a peça selecionada e apresentar
   aviso de pinagem pendente; a montagem não deve receber confirmação de conferência.
4. No simulador livre, retirar da protoboard uma peça sem pinagem não deve eliminar o aviso
   enquanto ela continuar no esquemático.

O teste de navegador `frontend/e2e/design-breadboard.e2e.cjs` usa um servidor isolado com o
catálogo da fixture de testes, Playwright e as variáveis `BASE`, `SHOTS` e
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Não deve ser executado contra o catálogo pessoal.

## Limitações

- Peças sem pinagem documentada precisam de confirmação da fonte antes da ligação automática.
- Circuitos grandes ainda podem apresentar trechos de fios sobrepostos, conforme documentado
  em [protoboard-ligacoes.md](protoboard-ligacoes.md).
- Os testes `datasheet`, que baixam milhares de documentos externos, são separados da regressão
  local; não foram executados nesta revisão.

## Validação executada

- Regressão geral com ngspice e runtimes de firmware configurados: 1.255 testes selecionados,
  1.251 aprovados inicialmente, três falhas e um teste de OCR pulado por ausência de
  Tesseract/tessdata. Os 11.037 casos marcados `datasheet` foram desmarcados, conforme o padrão
  do projeto.
- As três falhas foram reexecutadas: teste de propriedades da pontuação corrigido (aprovado),
  teste de variantes corrigido para exigir avisos de pinagem pendente (aprovado na execução
  específica abaixo) e calibração com `HealthCheck.too_slow` do Hypothesis (aprovada
  isoladamente e com a mesma semente que falhou, mantendo a cobertura, sem alterar código
  ou suprimir a verificação).
- Cobertura consolidada: **94,03%**, acima do mínimo de 80%. A execução geral levou 48 min 22 s;
  não foi repetida integralmente após as correções, conforme a orientação do `CLAUDE.md`.
- Frontend: 82 testes em 19 arquivos, build, ESLint e Prettier aprovados.
- Backend: Ruff aprovado (336 arquivos formatados), mypy sem erros nos 195 arquivos de fonte
  e dois contratos de importação preservados.
- Revisão específica: 10 testes aprovados, incluindo todas as variantes dos módulos, as duas
  variantes do DM-ZEN e a preservação das revisões do catálogo.
- Protoboard e roteiro: 26 testes aprovados; teste de propriedades de escolha da montagem
  aprovado após adaptar a comparação à nova pontuação.
- Chrome: DM-CHAVE e DM-OPA com montagem conferida; DM-ZEN com aviso visível e roteiro sem
  polaridade presumida. Servidor e banco exclusivos do teste, encerrados ao final.

A execução de todas as variantes emite um aviso já existente em `fil/module.py`: `log10(0)`
no cálculo da atenuação ideal de um filtro. O teste passa; este PR não altera esse cálculo.
